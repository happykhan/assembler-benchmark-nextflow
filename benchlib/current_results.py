"""Portable current results, with atomic catalogue publication and no run history.

The catalogue is the commit point: it references only fully written packages.
Package generations are implementation details, removed after replacement.
Readers and subset exports take the same lock as publishers for a consistent view.
"""
from contextlib import contextmanager
import copy
import csv
import hashlib
from html import escape
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import tempfile
import time
import uuid

from .catalogue import result_identity

STATUSES = {'measured', 'execution_failure', 'assessment_failure', 'not_applicable', 'not_run'}
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*\Z')
MANIFEST = 'manifest.json'


def _digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n'


def _identifier(value, label):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError('Invalid ' + label)
    return value


def _relative(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('Package paths must be relative POSIX paths')
    path = Path(value)
    if path.is_absolute() or any(part in ('..', '.') for part in path.parts):
        raise ValueError('Package path escapes its package: ' + value)
    return path


def _portable(value):
    if isinstance(value, dict):
        for child in value.values():
            _portable(child)
    elif isinstance(value, list):
        for child in value:
            _portable(child)
    elif isinstance(value, str) and (value.startswith(('/', 'file:')) or re.match(r'^[A-Za-z]:[\\/]', value)):
        raise ValueError('Result metadata must not require an absolute work-directory path')


def validate_record(record):
    if record.get('schema_version') != 2 or record.get('status') not in STATUSES:
        raise ValueError('Unsupported result schema or status')
    case, workflow = record.get('case', {}), record.get('workflow', {})
    for field in ('id', 'dataset_id', 'input_id'):
        _identifier(case.get(field), 'case ' + field)
    _identifier(workflow.get('id'), 'workflow configuration ID')
    if not isinstance(case.get('science_key'), str) or not case['science_key']:
        raise ValueError('Case science_key is required')
    if case.get('read_technology') not in ('short', 'long') or case.get('source_kind') not in ('real', 'simulated'):
        raise ValueError('Read technology and source kind must be explicit')
    for field in ('collections', 'scenarios'):
        if not isinstance(case.get(field), list):
            raise ValueError('Case ' + field + ' must be a list')
        for membership in case[field]:
            _identifier(membership, field + ' membership')
    repeat = case.get('scientific_repeat_id')
    repeat_description = case.get('scientific_repeat')
    if repeat is not None:
        _identifier(repeat, 'scientific repeat ID')
        if not isinstance(repeat_description, dict) or repeat_description.get('id') != repeat:
            raise ValueError('Scientific repeat description must match its repeat ID')
        if not isinstance(repeat_description.get('kind'), str) or not repeat_description['kind'] or type(repeat_description.get('index')) is not int or repeat_description['index'] < 1:
            raise ValueError('Scientific repeat needs a kind and positive index')
    elif repeat_description is not None:
        raise ValueError('Scientific repeat description requires its repeat ID')
    if not isinstance(workflow.get('version'), str) or not workflow['version']:
        raise ValueError('Actual assembler version is required')
    if type(workflow.get('version_order')) is not int or workflow['version_order'] < 0:
        raise ValueError('Workflow version_order must be an explicit non-negative integer')
    expected = result_identity(case['id'], workflow['id'], repeat)
    if record.get('result_id', expected) != expected:
        raise ValueError('Result identity differs from its case, configuration or scientific repeat')
    metrics = record.get('metrics')
    if not isinstance(metrics, list):
        raise ValueError('Measurements must be a list')
    if record['status'] == 'measured' and not any(m.get('value') is not None for m in metrics if isinstance(m, dict)):
        raise ValueError('Measured status requires at least one measured value')
    if record['status'] in ('not_run', 'not_applicable') and any(m.get('value') is not None for m in metrics if isinstance(m, dict)):
        raise ValueError('Unrun or inapplicable result cannot contain measured values')
    for metric in metrics:
        if not isinstance(metric, dict) or any(not isinstance(metric.get(k), str) or not metric[k] for k in ('name', 'unit', 'method')):
            raise ValueError('Every metric needs a name, unit and method')
        value = metric.get('value')
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Non-finite measurements are not portable')
    if record['status'] in ('execution_failure', 'assessment_failure') and record.get('sequence_outcome') is not None:
        raise ValueError('Failed measurement cannot establish a sequence outcome')
    _portable(record)
    json.dumps(record, allow_nan=False)
    return record


@contextmanager
def _locked(root, timeout=120, interval=.05, name='.current-result-lock'):
    """Atomic mkdir works across GPFS clients; never steal an uncertain lock."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / name
    deadline = time.monotonic() + timeout
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError('Result store is locked; inspect its owner before recovery: ' + str(lock))
            time.sleep(interval)
    token = uuid.uuid4().hex
    owner = lock / 'owner.json'
    owner.write_text(_json({'token': token, 'hostname': socket.gethostname(), 'pid': os.getpid()}))
    try:
        yield
    finally:
        if json.loads(owner.read_text()).get('token') != token:
            raise RuntimeError('Result-store lock ownership changed')
        owner.unlink()
        lock.rmdir()


def _write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.partial-' + uuid.uuid4().hex)
    with temporary.open('x') as stream:
        stream.write(_json(value))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _seal(path, kind, identity):
    files = {p.relative_to(path).as_posix(): _digest(p) for p in path.rglob('*') if p.is_file() and p.name != MANIFEST}
    _write_json(path / MANIFEST, {'schema_version': 2, 'kind': kind, 'id': identity, 'files': files})


def validate_package(path, *, verify_artifacts=True):
    path = Path(path).resolve()
    manifest = json.loads((path / MANIFEST).read_text())
    if manifest.get('schema_version') != 2 or manifest.get('kind') not in ('case_result', 'shared_dependency', 'summary'):
        raise ValueError('Unsupported package manifest')
    files = manifest.get('files', {})
    if not files or MANIFEST in files:
        raise ValueError('Invalid package inventory')
    actual = {p.relative_to(path).as_posix() for p in path.rglob('*') if p.is_file()}
    if actual != set(files) | {MANIFEST}:
        raise ValueError('Package contains missing or unmanifested files')
    if any(p.is_symlink() for p in path.rglob('*')):
        raise ValueError('Portable packages cannot contain symlinks')
    for relative, checksum in files.items():
        item = path / _relative(relative)
        metadata = relative in ('result.json', 'dependency.json', 'summary.json', 'index.html', 'measurements.tsv')
        if item.is_symlink() or not item.resolve().is_relative_to(path) or ((verify_artifacts or metadata) and _digest(item) != checksum):
            raise ValueError('Package artifact checksum/path mismatch: ' + relative)
    if manifest['kind'] == 'case_result':
        record = json.loads((path / 'result.json').read_text())
        validate_record(record)
        if record['result_id'] != manifest['id']:
            raise ValueError('Package identity mismatch')
        for item in record.get('artifacts', {}).values():
            if item['path'] not in files or files[item['path']] != item['sha256']:
                raise ValueError('Result artifact differs from its package inventory')
    return manifest


def _copy_artifacts(destination, artifacts, prefix='artifacts'):
    copied = {}
    for name, supplied in sorted((artifacts or {}).items()):
        relative = _relative(name)
        if not prefix and name in ('dependency.json', MANIFEST):
            raise ValueError('Shared dependency file uses a reserved package name')
        metadata = supplied if isinstance(supplied, dict) else {'source': supplied}
        source = Path(metadata['source'])
        if not source.is_file():
            raise ValueError('Artifact source is not a file: ' + str(source))
        target = destination / prefix / relative if prefix else destination / relative
        if target.exists():
            raise ValueError('Artifact target collision')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied[name] = {'path': target.relative_to(destination).as_posix(), 'sha256': _digest(target),
                        'size_bytes': target.stat().st_size,
                        **{k: v for k, v in metadata.items() if k not in ('source', 'path', 'sha256', 'size_bytes')}}
    return copied


def _metric_table(metrics):
    rows = []
    for metric in metrics:
        context = {k: v for k, v in metric.items() if k not in ('name', 'value', 'unit', 'method')}
        values = [metric['name'], 'Unmeasured' if metric.get('value') is None else metric['value'],
                  metric['unit'], metric['method'], json.dumps(context, sort_keys=True) if context else '']
        rows.append('<tr>' + ''.join('<td>' + escape(str(v)) + '</td>' for v in values) + '</tr>')
    return '<div class="scroll"><table><thead><tr><th>Metric</th><th>Value</th><th>Unit</th><th>Method</th><th>Context</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'


def _html(title, body):
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + escape(title) + '</title><style>body{font:16px system-ui,sans-serif;line-height:1.5;margin:2rem;color:#20242a}main{max-width:1100px;margin:auto}.scroll{overflow:auto}table{border-collapse:collapse;width:100%}th,td{padding:.5rem;text-align:left;border-bottom:1px solid #ddd}pre{white-space:pre-wrap;overflow-wrap:anywhere}img{max-width:100%}a{color:#2457a6}@media(max-width:600px){body{margin:1rem}}</style></head><body><main><h1>' + escape(title) + '</h1>' + body + '</main></body></html>'


def _write_result_package(path, record, artifacts):
    path.mkdir(parents=True)
    record['artifacts'] = _copy_artifacts(path, artifacts)
    validate_record(record)
    _write_json(path / 'result.json', record)
    with (path / 'measurements.tsv').open('w', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerow(['name', 'value', 'unit', 'method', 'context'])
        for metric in record['metrics']:
            writer.writerow([metric['name'], metric.get('value'), metric['unit'], metric['method'],
                             json.dumps({k: v for k, v in metric.items() if k not in ('name', 'value', 'unit', 'method')}, sort_keys=True)])
    case, workflow = record['case'], record['workflow']
    body = '<p><strong>' + escape(record['status']) + '</strong> · ' + escape(case['read_technology'] + ' reads · ' + case['source_kind']) + '</p>'
    body += '<p>' + escape(str(case.get('description', case['id']))) + '</p><p>Assembler configuration: ' + escape(workflow['id']) + '; actual version: ' + escape(workflow['version']) + '.</p>'
    body += '<p><a href="result.json">Result JSON</a> · <a href="measurements.tsv">Measurements TSV</a></p>' + _metric_table(record['metrics'])
    for title, value in [('Experiment', record.get('experiment', case)), ('Input', record.get('input', {'dataset_id': case['dataset_id'], 'input_id': case['input_id']})), ('Software configuration', workflow), ('Provenance', record.get('provenance', {}))]:
        body += '<h2>' + title + '</h2><pre>' + escape(_json(value)) + '</pre>'
    body += '<h2>Supporting artifacts</h2><ul>'
    for name, item in record['artifacts'].items():
        body += '<li><a href="' + escape(item['path'], quote=True) + '">' + escape(name) + '</a></li>'
        if Path(item['path']).suffix.lower() in ('.svg', '.png', '.jpg', '.jpeg', '.webp'):
            body += '<li><img src="' + escape(item['path'], quote=True) + '" alt="' + escape(name, quote=True) + '"></li>'
    body += '</ul>'
    if record.get('dependency_packages'):
        body += '<h2>Shared input dependencies</h2><ul>'
        for identity, relative in record['dependency_packages'].items():
            body += '<li><a href="' + escape(relative, quote=True) + '/dependency.json">' + escape(identity) + '</a></li>'
        body += '</ul>'
    (path / 'index.html').write_text(_html(case.get('title', case['id']) + ' · ' + workflow['id'], body))
    _seal(path, 'case_result', record['result_id'])
    validate_package(path)


def _catalogue(root):
    path = root / 'catalogue.json'
    if not path.exists():
        return {'schema_version': 2, 'kind': 'current_results', 'results': [], 'dependencies': {}, 'summaries': []}
    value = json.loads(path.read_text())
    if value.get('schema_version') != 2 or value.get('kind') != 'current_results':
        raise ValueError('Unsupported current-result catalogue')
    return value


def _package(root, entry, *, verify_artifacts=False):
    relative = _relative(entry['package'])
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Current package escapes result store')
    manifest = validate_package(path, verify_artifacts=verify_artifacts)
    if manifest['id'] != entry['result_id']:
        raise ValueError('Catalogue/package identity mismatch')
    return path


def _records(root, catalogue, *, verify_artifacts=False):
    return [json.loads((_package(root, entry, verify_artifacts=verify_artifacts) / 'result.json').read_text()) for entry in catalogue['results']]


def load_current(root, *, with_packages=False, verify_artifacts=True):
    """Return a consistent snapshot of current records, not operational attempts."""
    root = Path(root).resolve()
    if not root.exists():
        return []
    with _locked(root):
        catalogue = _catalogue(root)
        records = _records(root, catalogue, verify_artifacts=verify_artifacts)
        for dependency, relative in catalogue['dependencies'].items():
            _identifier(dependency, 'shared dependency ID')
            path = root / _relative(relative)
            if path != root / 'dependencies' / dependency:
                raise ValueError('Shared dependency path differs from catalogue identity')
            validate_package(path, verify_artifacts=verify_artifacts)
        if with_packages:
            for record, entry in zip(records, catalogue['results']):
                record['package'] = entry['package']
        return records


def _dependencies(root, supplied):
    result = []
    for identity, definition in sorted((supplied or {}).items()):
        _identifier(identity, 'shared dependency ID')
        with _locked(root, name='.dependency-lock-' + identity):
            _store_dependency(root, identity, definition)
        result.append(identity)
    return result


def _store_dependency(root, identity, definition):
    metadata = copy.deepcopy(definition.get('record', {}))
    _portable(metadata)
    path = root / 'dependencies' / identity
    stage = root / 'dependencies' / ('.staging-' + uuid.uuid4().hex)
    stage.mkdir(parents=True)
    try:
        files = _copy_artifacts(stage, definition.get('files', {}), prefix='')
        metadata.update(schema_version=2, id=identity, files=files)
        _write_json(stage / 'dependency.json', metadata)
        _seal(stage, 'shared_dependency', identity)
        validate_package(stage)
        if path.exists():
            existing = validate_package(path)
            incoming = json.loads((stage / MANIFEST).read_text())
            if existing != incoming:
                raise ValueError('Shared dependency ID already identifies different bytes or metadata: ' + identity)
        else:
            stage.rename(path)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _version_guard(old, new):
    if old['case']['science_key'] != new['case']['science_key']:
        raise ValueError('Changed scientific case requires a new case identity')
    for field in ('dataset_id','input_id','read_technology','source_kind','recipe','scientific_repeat'):
        if old['case'].get(field) != new['case'].get(field):
            raise ValueError('Changed scientific case fields require a new case identity or scientific repeat identity')
    before, after = old['workflow'], new['workflow']
    if before.get('tool') != after.get('tool') or before.get('configuration', {}) != after.get('configuration', {}):
        raise ValueError('Changed assembler configuration requires a new configuration ID')
    if after['version_order'] < before['version_order']:
        raise ValueError('An older assembler version cannot replace the current newer version')
    if (after['version_order'] == before['version_order']) != (after['version'] == before['version']):
        raise ValueError('Assembler version and explicit version_order are inconsistent')


def _entry(record, package):
    return {'result_id': record['result_id'], 'case_id': record['case']['id'],
            'workflow_id': record['workflow']['id'], 'scientific_repeat_id': record['case'].get('scientific_repeat_id'),
            'package': package}


def _summary_views(root, catalogue, records):
    """Summaries reference shared case packages and never copy their artifacts."""
    summaries = []
    for kind, field in [('collection', 'collections'), ('scenario', 'scenarios')]:
        identities = sorted({identity for r in records for identity in r['case'][field]})
        for identity in identities:
            directory = root / 'summaries' / kind / identity
            directory.mkdir(parents=True, exist_ok=True)
            selected = [r for r in records if identity in r['case'][field]]
            entries = [e for e in catalogue['results'] if e['result_id'] in {r['result_id'] for r in selected}]
            links = [{**entry, 'package': Path(os.path.relpath(root / entry['package'], directory)).as_posix()} for entry in entries]
            definition = catalogue.get('collections' if kind == 'collection' else 'scenarios', {}).get(identity, {})
            summary = {'schema_version': 2, 'kind': kind, 'id': identity, 'definition': definition, 'results': links}
            _write_json(directory / 'summary.json', summary)
            with (directory / 'measurements.tsv').open('w', newline='') as stream:
                writer = csv.writer(stream, delimiter='\t')
                writer.writerow(['case_id', 'workflow_id', 'version', 'status', 'metric', 'value', 'unit', 'method'])
                for r in selected:
                    for metric in r['metrics'] or [{}]:
                        writer.writerow([r['case']['id'], r['workflow']['id'], r['workflow']['version'], r['status'], metric.get('name'), metric.get('value'), metric.get('unit'), metric.get('method')])
            body = '<p>' + escape(str(definition.get('question', 'Current ' + kind + ' results.'))) + '</p>'
            for label in ('conditions', 'scope'):
                if label in definition:
                    body += '<h2>' + label.title() + '</h2><pre>' + escape(_json(definition[label])) + '</pre>'
            body += '<p>Real/simulated source and short/long read technology are independent properties. No overall winner score.</p><p><a href="summary.json">Summary JSON</a> · <a href="measurements.tsv">Measurements TSV</a></p><ul>'
            for entry, r in zip(entries, selected):
                body += '<li><a href="../../../' + escape(entry['package'], quote=True) + '/index.html">' + escape(r['case']['id'] + ' · ' + r['workflow']['id']) + '</a> — ' + escape(r['status'] + '; ' + r['case']['read_technology'] + '; ' + r['case']['source_kind']) + '</li>'
            (directory / 'index.html').write_text(_html(definition.get('title', identity), body + '</ul>'))
            _seal(directory, 'summary', identity)
            summaries.append({'kind': kind, 'id': identity, 'package': directory.relative_to(root).as_posix()})
    # Remove only obsolete generated summary packages, never shared inputs/results.
    expected = {r['package'] for r in summaries}
    for path in (root / 'summaries').glob('*/*') if (root / 'summaries').exists() else []:
        if path.is_dir() and path.relative_to(root).as_posix() not in expected:
            shutil.rmtree(path)
    return summaries


def _index(root, catalogue):
    body = '<h2>Broad benchmarks</h2><ul>'
    for kind, title in [('collection', 'Broad benchmarks'), ('scenario', 'Targeted scenarios')]:
        if kind == 'scenario':
            body += '</ul><h2>' + title + '</h2><ul>'
        for row in catalogue['summaries']:
            if row['kind'] == kind:
                body += '<li><a href="' + escape(row['package'], quote=True) + '/index.html">' + escape(row['id']) + '</a></li>'
    body += '</ul><p><a href="catalogue.json">Current package catalogue</a></p>'
    (root / 'index.html').write_text(_html('Genome assembly benchmark', body))


def publish_result(root, record, artifacts=None, dependencies=None, *, summaries=False):
    """Atomically replace one current case/configuration, including failures.

    Artifacts map relative names to source files or {source, role, media_type}.
    Shared dependencies map immutable IDs to {record, files}; source paths are
    transport arguments only and are never serialized. Aggregation is optional.
    """
    root = Path(root).resolve()
    record = copy.deepcopy(record)
    record.setdefault('schema_version', 2)
    validate_record(record)
    identity = result_identity(record['case']['id'], record['workflow']['id'], record['case'].get('scientific_repeat_id'))
    record['result_id'] = identity
    generation = root / 'packages' / identity / uuid.uuid4().hex
    try:
        with _locked(root, name='.result-lock-' + identity):
            added = _dependencies(root, dependencies)
            required = record.get('dependencies', [])
            if not isinstance(required, list) or any(not isinstance(d, str) for d in required):
                raise ValueError('Result dependencies must be shared dependency IDs')
            record['dependencies'] = sorted(set(required + added))
            record['dependency_packages'] = {d: '../../../dependencies/' + d for d in record['dependencies']}
            for dependency in record['dependencies']:
                _identifier(dependency, 'shared dependency ID')
                validate_package(root / 'dependencies' / dependency)
            _write_result_package(generation, record, artifacts)
            with _locked(root):
                catalogue = _catalogue(root)
                previous = next((e for e in catalogue['results'] if e['result_id'] == identity), None)
                old = _package(root, previous) if previous else None
                if old:
                    if not old.is_relative_to(root / 'packages' / identity):
                        raise ValueError('Refusing to delete an unowned result package')
                    _version_guard(json.loads((old / 'result.json').read_text()), record)
                entry = _entry(record, generation.relative_to(root).as_posix())
                catalogue['results'] = sorted([e for e in catalogue['results'] if e['result_id'] != identity] + [entry], key=lambda e:e['result_id'])
                catalogue['dependencies'] = {d:'dependencies/' + d for r in _records(root,catalogue) for d in r['dependencies']}
                obsolete = _invalidate_summaries(root, catalogue, record)
                _write_json(root / 'catalogue.json', catalogue)
                if old:
                    shutil.rmtree(old)
                for directory in obsolete:
                    shutil.rmtree(directory)
                if summaries:
                    _refresh_summaries(root, catalogue)
                return entry
    except BaseException:
        current = _catalogue(root) if (root / 'catalogue.json').exists() else {'results':[]}
        if generation.exists() and not any(e['package'] == generation.relative_to(root).as_posix() for e in current['results']):
            shutil.rmtree(generation)
        raise


def _invalidate_summaries(root, catalogue, record):
    obsolete, keep = [], []
    for entry in catalogue.get('summaries', []):
        directory = root / _relative(entry['package'])
        manifest = validate_package(directory, verify_artifacts=False)
        if manifest['kind'] != 'summary' or not directory.is_relative_to(root/'summaries'):
            raise ValueError('Unowned summary package')
        document = json.loads((directory/'summary.json').read_text())
        membership = 'collections' if entry['kind']=='collection' else 'scenarios'
        if any(e['result_id']==record['result_id'] for e in document['results']) or entry['id'] in record['case'][membership]:
            obsolete.append(directory)
        else:
            keep.append(entry)
    catalogue['summaries'] = keep
    return obsolete


def _refresh_summaries(root, catalogue):
    catalogue['summaries'] = _summary_views(root,catalogue,_records(root,catalogue))
    _write_json(root/'catalogue.json',catalogue)
    _index(root,catalogue)
    return catalogue


def refresh_summaries(root):
    """Aggregate only the available current results; never schedule science."""
    root=Path(root).resolve()
    with _locked(root):
        return _refresh_summaries(root,_catalogue(root))


def set_catalogue_metadata(root, metadata):
    """Update collection/scenario descriptions without replacing current results."""
    if set(metadata)-{'collections','scenarios'}:
        raise ValueError('Only collection/scenario definitions belong in catalogue metadata')
    _portable(metadata)
    root=Path(root).resolve()
    with _locked(root):
        catalogue=_catalogue(root)
        for key,value in metadata.items():
            if not isinstance(value,dict):
                raise ValueError('Catalogue definitions must be ID-indexed objects')
            for identity in value:_identifier(identity,'definition ID')
            catalogue[key]={**catalogue.get(key,{}),**copy.deepcopy(value)}
        _write_json(root/'catalogue.json',catalogue)
    return catalogue


render_page = _html
render_metric_table = _metric_table


def export_subset(root, output, result_ids=None, *, case_ids=None):
    """Copy selected current packages plus their shared dependency closure once."""
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists() or root == output or root in output.parents or output in root.parents:
        raise ValueError('Subset output must be a fresh directory outside the result store')
    output.parent.mkdir(parents=True, exist_ok=True)
    with _locked(root), tempfile.TemporaryDirectory(prefix='.subset-', dir=output.parent) as temporary:
        catalogue = _catalogue(root)
        known = {e['result_id'] for e in catalogue['results']}
        requested = set(result_ids) if result_ids is not None else known
        if requested - known:
            raise ValueError('Unknown current result selection')
        if case_ids is not None and set(case_ids) - {e['case_id'] for e in catalogue['results']}:
            raise ValueError('Unknown current case selection')
        selected = [e for e in catalogue['results'] if e['result_id'] in requested and (case_ids is None or e['case_id'] in set(case_ids))]
        if not selected:
            raise ValueError('No current results match subset selection')
        staged = Path(temporary) / 'package'
        staged.mkdir()
        dependencies = set()
        for entry in selected:
            source = _package(root, entry, verify_artifacts=True)
            target = staged / entry['package']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)
            record = json.loads((target / 'result.json').read_text())
            dependencies.update(record['dependencies'])
        for dependency in sorted(dependencies):
            source = root / 'dependencies' / dependency
            validate_package(source)
            target = staged / 'dependencies' / dependency
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)
        subset = {'schema_version': 2, 'kind': 'current_results', 'results': selected,
                  'dependencies': {d: 'dependencies/' + d for d in sorted(dependencies)}, 'summaries': []}
        for field in ('collections', 'scenarios'):
            subset[field] = copy.deepcopy(catalogue.get(field, {}))
        subset['summaries'] = _summary_views(staged, subset, _records(staged, subset))
        _write_json(staged / 'catalogue.json', subset)
        _index(staged, subset)
        staged.rename(output)
    return output
