"""Common catalogue and deduplicated scientific selection, without network I/O.

Read technology, scientific source kind and download transport are independent.
Memberships never change input identity; workflow releases never change slots.
"""
import copy
import hashlib
import json
from pathlib import Path
import re

from .workflow_options import workflow_options

SCHEMA_VERSION = 2
IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*\Z')


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def result_identity(case_id, workflow_id, scientific_repeat_id=None):
    identity = json.dumps([case_id, workflow_id, scientific_repeat_id], ensure_ascii=True, separators=(',', ':'))
    return 'result-' + hashlib.sha256(identity.encode()).hexdigest()[:24]


def _identifier(value, label):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError('Invalid ' + label + ': ' + repr(value))
    return value


def _indexed(rows, label):
    if isinstance(rows, dict):
        rows = [dict(row, id=key) for key, row in rows.items()]
    if not isinstance(rows, list):
        raise ValueError(label + ' must be a list or an ID-indexed object')
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(label + ' entries must be objects')
        key = _identifier(row.get('id'), label + ' ID')
        if key in result:
            raise ValueError('Duplicate ' + label + ': ' + key)
        result[key] = copy.deepcopy(row)
    return result


def _selection(values, label):
    if values in (None, ''):
        return []
    values = values.split(',') if isinstance(values, str) else list(values)
    return sorted(set(_identifier(v.strip() if isinstance(v, str) else v, label) for v in values))


def dataset_science_identity(dataset, reference):
    reference_fields = ('id', 'accession', 'download_sha256', 'canonical_fasta_sha256', 'quick_slice_bases', 'compression', 'molecules', 'member')
    files = {role: {'sha256': source['sha256']} if source.get('sha256') else {'source': source.get('source')}
             for role, source in dataset.get('files', {}).items()}
    return {'dataset_id': dataset['id'], 'read_technology': dataset['read_technology'],
            'source_kind': dataset['source_kind'], 'sample_id': dataset.get('sample_id'),
            'run_accession': dataset.get('run_accession'),
            'reference': {name: reference[name] for name in reference_fields if name in reference},
            'files': files, 'published_identity': dataset.get('published_identity')}


def case_science_key(dataset, reference, recipe):
    return canonical_digest({'dataset': dataset_science_identity(dataset, reference), 'recipe': recipe})


def input_identity(dataset, reference, recipe):
    return 'input-' + case_science_key(dataset, reference, recipe)[:24]


def _validate_dependency(row):
    target = Path(row.get('target', ''))
    if not row.get('kind') or str(target) == '.' or target.is_absolute() or '..' in target.parts:
        raise ValueError('Dependency target must be relative to its cache: ' + row['id'])
    if row['kind'] not in ('software', 'container_image'):
        source = row.get('source', {})
        if not isinstance(source, dict) or not (source.get('url') or source.get('path')):
            raise ValueError('Dependency requires explicit URL or local source: ' + row['id'])
    if row.get('sha256') is not None and not re.fullmatch(r'[0-9a-f]{64}', row['sha256']):
        raise ValueError('Invalid dependency SHA256: ' + row['id'])
    if row.get('size_bytes') is not None and (type(row['size_bytes']) is not int or row['size_bytes'] < 0):
        raise ValueError('Invalid dependency size: ' + row['id'])


def _load_json(path):
    return json.loads(Path(path).read_text())


def load_catalogue(project, catalogue_path=None):
    """Read one explicit current catalogue; return records indexed by IDs."""
    project = Path(project).resolve()
    path = Path(catalogue_path) if catalogue_path else project / 'assets/catalogue.json'
    if not path.is_absolute():
        path = project / path
    document = _load_json(path)
    if document.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Catalogue schema_version must be 2')
    catalogue = {'schema_version': SCHEMA_VERSION, 'defaults': copy.deepcopy(document.get('defaults', {})),
                 'scope': document.get('scope', 'single-isolate-bacterial-assembly')}
    for name in ('datasets', 'cases', 'workflows', 'collections', 'scenarios', 'dependencies'):
        catalogue[name] = _indexed(document.get(name, []), name)
    reference_file = document.get('reference_registry', 'assets/references.json')
    references = _indexed(_load_json(project / reference_file)['references'] if reference_file else [], 'references')
    for reference in document.get('references', []):
        references[reference['id']] = copy.deepcopy(reference)
    catalogue['references'] = references
    for row in catalogue['dependencies'].values():
        _validate_dependency(row)
    for dataset in catalogue['datasets'].values():
        if dataset.get('read_technology') not in ('short', 'long') or dataset.get('source_kind') not in ('real', 'simulated'):
            raise ValueError('Dataset requires independent read technology/source kind: ' + dataset['id'])
        if dataset.get('reference_id') not in references:
            raise ValueError('Unknown dataset reference: ' + dataset['id'])
        _check_selected(dataset.get('dependencies', []), catalogue['dependencies'], 'dataset dependencies')
        if dataset['source_kind'] == 'real':
            if not dataset.get('sample_id') or not dataset.get('reference_sample_id') or dataset['sample_id'] != dataset['reference_sample_id']:
                raise ValueError('Real reads require matching read/reference sample identities: ' + dataset['id'])
            reference_sample=references[dataset['reference_id']].get('biosample',references[dataset['reference_id']].get('sample_id'))
            if reference_sample and reference_sample != dataset['reference_sample_id']:
                raise ValueError('Real dataset sample differs from reference record: '+dataset['id'])
            roles = {'r1', 'r2'} if dataset['read_technology'] == 'short' else {'reads'}
            if set(dataset.get('files', {})) != roles:
                raise ValueError('Real input roles differ from read technology: ' + dataset['id'])
            for file in dataset['files'].values():
                if not isinstance(file, dict) or not isinstance(file.get('source'), dict) or not (file['source'].get('path') or file['source'].get('url')):
                    raise ValueError('Real input file requires a local path or URL: ' + dataset['id'])
    for workflow in catalogue['workflows'].values():
        if workflow.get('configuration_id', workflow['id']) != workflow['id']:
            raise ValueError('Workflow ID must be the stable configuration identity')
        workflow['configuration_id'] = workflow['id']
        if not workflow.get('version') or type(workflow.get('version_order')) is not int or workflow['version_order'] < 0:
            raise ValueError('Workflow requires version and explicit version_order: ' + workflow['id'])
        if not workflow.get('read_technologies') or not set(workflow['read_technologies']) <= {'short', 'long'}:
            raise ValueError('Workflow requires supported technologies: ' + workflow['id'])
        if not workflow.get('source_kinds') or not set(workflow['source_kinds']) <= {'real', 'simulated'}:
            raise ValueError('Workflow requires supported source kinds: ' + workflow['id'])
        _check_selected(workflow.get('dependencies', []), catalogue['dependencies'], 'workflow dependencies')
        workflow_options(workflow.get('tool'),workflow.get('configuration',{}))
        runtimes=[catalogue['dependencies'][key] for key in workflow.get('dependencies',[])]
        if not any(row.get('kind')=='software' and row.get('environment')==workflow.get('environment') and row.get('manifest')==workflow.get('manifest') for row in runtimes):
            raise ValueError('Workflow requires its declared manifest/environment dependency: '+workflow['id'])
    for case in catalogue['cases'].values():
        if case.get('dataset_id') not in catalogue['datasets']:
            raise ValueError('Unknown case dataset: ' + case['id'])
        _check_selected(case.get('collections', []), catalogue['collections'], 'case collections')
        _check_selected(case.get('scenarios', []), catalogue['scenarios'], 'case scenarios')
        if not case.get('collections') and not case.get('scenarios'):
            raise ValueError('Case must belong to a collection/scenario: ' + case['id'])
        if not isinstance(case.get('recipe'), dict) or not case['recipe'].get('method'):
            raise ValueError('Case requires an explicit input recipe: ' + case['id'])
        dataset = catalogue['datasets'][case['dataset_id']]
        method = case['recipe']['method']
        if method in ('native-error-free-v2', 'art-illumina-v1', 'published-frozen-reads-v1') and dataset['source_kind'] != 'simulated':
            raise ValueError('Generated or published simulated reads cannot be labelled real')
        if method == 'art-illumina-v1' and dataset['read_technology'] != 'short':
            raise ValueError('ART requires a short-read dataset')
        if method == 'native-error-free-v2' and dataset['read_technology'] != 'long':
            raise ValueError('Native long-read simulation requires a long-read dataset')
        eligible = case.get('eligible_workflows')
        if eligible is not None and not isinstance(eligible, list):
            raise ValueError('Case eligible_workflows must be a list')
        _check_selected(eligible or [], catalogue['workflows'], 'eligible workflows')
        if dataset['read_technology'] == 'short' and 'plasmids' in case.get('scenarios', []) and eligible is None:
            raise ValueError('Short-read plasmid cases require explicit eligibility')
        expected = case_science_key(dataset, references[dataset['reference_id']], case['recipe'])
        if case.get('science_key') != expected:
            raise ValueError('Case scientific identity changed; declare new case ID/science_key: ' + case['id'])
        repeats = case.get('scientific_repeats', [case.get('scientific_repeat')])
        if not isinstance(repeats, list) or not repeats:
            raise ValueError('Scientific repeats must be a non-empty list')
        identities = []
        for repeat in repeats:
            if repeat is None:
                identities.append(None)
            else:
                if not isinstance(repeat, dict):
                    raise ValueError('Scientific repeat must be an object or null')
                identities.append(_identifier(repeat.get('id'), 'scientific repeat ID'))
                if repeat.get('kind') not in ('technical', 'sampling', 'read-order') or type(repeat.get('index')) is not int or repeat['index'] < 1:
                    raise ValueError('Invalid scientific repeat definition: ' + case['id'])
        if len(set(identities)) != len(identities):
            raise ValueError('Duplicate scientific repeat identity: ' + case['id'])
    return catalogue


def _check_selected(selected, known, label):
    unknown = set(selected) - set(known)
    if unknown:
        raise ValueError('Unknown ' + label + ': ' + ', '.join(sorted(unknown)))


def build_plan(project, cases=None, scenarios=None, collections=None, workflows=None,
               all_eligible=False, catalogue_path=None):
    """Union mixed selections; deduplicate inputs, memberships and result slots."""
    if type(all_eligible) is not bool:
        raise ValueError('all_eligible must be an explicit boolean')
    catalogue = load_catalogue(project, catalogue_path)
    selected = {'cases': _selection(cases, 'case'), 'scenarios': _selection(scenarios, 'scenario'),
                'collections': _selection(collections, 'collection'), 'workflows': _selection(workflows, 'workflow'),
                'all': bool(all_eligible)}
    if not selected['all'] and not any(selected[k] for k in ('cases', 'scenarios', 'collections')):
        selected['collections'] = list(catalogue['defaults'].get('collections', ['quick']))
    for key in ('cases', 'scenarios', 'collections', 'workflows'):
        _check_selected(selected[key], catalogue[key], key)
    if not selected['workflows']:
        selected['workflows'] = list(catalogue['workflows'] if selected['all'] else catalogue['defaults'].get('workflows', catalogue['workflows']))
        _check_selected(selected['workflows'], catalogue['workflows'], 'default workflows')
    chosen = [row for key, row in sorted(catalogue['cases'].items()) if selected['all'] or key in selected['cases']
              or set(row.get('collections', [])) & set(selected['collections'])
              or set(row.get('scenarios', [])) & set(selected['scenarios'])]
    if not chosen:
        raise ValueError('No cases match the selection')
    definitions = {key: catalogue['workflows'][key] for key in sorted(selected['workflows'])}
    datasets, inputs, expanded, slots, exclusions = {}, {}, [], [], []
    dependency_ids = set()
    for original in chosen:
        dataset = catalogue['datasets'][original['dataset_id']]
        reference = catalogue['references'][dataset['reference_id']]
        input_id = input_identity(dataset, reference, original['recipe'])
        datasets[dataset['id']] = copy.deepcopy(dataset)
        dependencies = set(dataset.get('dependencies', [])) | set(original.get('dependencies', []))
        _check_selected(dependencies, catalogue['dependencies'], 'case dependencies')
        inputs[input_id] = {'id': input_id, 'dataset_id': dataset['id'], 'dataset': copy.deepcopy(dataset),
            'read_technology': dataset['read_technology'], 'source_kind': dataset['source_kind'],
            'layout': 'long_single' if dataset['read_technology'] == 'long' else 'short_paired',
            'recipe': copy.deepcopy(original['recipe']), 'reference': copy.deepcopy(reference),
            'science_key': original['science_key'], 'dependencies': sorted(dependencies)}
        for repeat in original.get('scientific_repeats', [original.get('scientific_repeat')]):
            case = copy.deepcopy(original)
            case.pop('scientific_repeats', None)
            case.update(input_id=input_id, read_technology=dataset['read_technology'], source_kind=dataset['source_kind'],
                        scientific_repeat=repeat, scientific_repeat_id=repeat['id'] if repeat else None,
                        sampling_seed=case['recipe'].get('seed'), read_order=case['recipe'].get('read_order', case['recipe'].get('order', 'generated_order')))
            expanded.append(case)
            for workflow_id, workflow in definitions.items():
                reason = None
                if case['read_technology'] not in workflow['read_technologies']:
                    reason = 'Workflow does not support ' + case['read_technology'] + ' reads'
                elif case['source_kind'] not in workflow['source_kinds']:
                    reason = 'Workflow does not support ' + case['source_kind'] + ' inputs'
                elif original.get('eligible_workflows') is not None and workflow_id not in original['eligible_workflows']:
                    reason = 'Workflow is not explicitly eligible for this case'
                result_id = result_identity(case['id'], workflow_id, case['scientific_repeat_id'])
                row = {'id': result_id, 'result_id': result_id, 'case_id': case['id'], 'input_id': input_id,
                       'workflow_id': workflow_id, 'case': copy.deepcopy(case), 'workflow': copy.deepcopy(workflow),
                       'scientific_repeat_id': case['scientific_repeat_id'], 'status': 'not_run'}
                if reason:
                    row.update(status='not_applicable', reason=reason)
                    exclusions.append(row)
                else:
                    slots.append(row)
                    dependency_ids.update(dependencies)
                    dependency_ids.update(workflow.get('dependencies', []))
    if len({r['id'] for r in slots}) != len(slots):
        raise ValueError('Duplicate scientific result identities')
    collection_ids = sorted({k for case in expanded for k in case.get('collections', [])})
    scenario_ids = sorted({k for case in expanded for k in case.get('scenarios', [])})
    used_inputs = {row['input_id'] for row in slots}
    plan = {'schema_version': SCHEMA_VERSION, 'scope': catalogue['scope'], 'selection': selected,
            'datasets': datasets, 'cases': expanded, 'workflows': definitions,
            'inputs': [inputs[k] for k in sorted(used_inputs)], 'slots': slots, 'exclusions': exclusions,
            'collections': {k: catalogue['collections'][k] for k in collection_ids},
            'scenarios': {k: catalogue['scenarios'][k] for k in scenario_ids},
            'dependencies': [catalogue['dependencies'][k] for k in sorted(dependency_ids)],
            'expected_slots': len(slots), 'not_applicable_slots': len(exclusions)}
    plan['plan_sha256'] = canonical_digest(plan)
    return plan


def validate_plan(project, plan, catalogue_path=None):
    if plan.get('plan_sha256') != canonical_digest({k: v for k, v in plan.items() if k != 'plan_sha256'}):
        raise ValueError('Plan checksum differs')
    selection = plan['selection']
    rebuilt = build_plan(project, selection['cases'], selection['scenarios'], selection['collections'],
                         selection['workflows'], selection['all'], catalogue_path)
    if rebuilt != plan:
        raise ValueError('Plan differs from current catalogue')
    return plan
