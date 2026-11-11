"""Portable exports with explicit scientific scope and retained-file checksums."""
import csv
from html import escape
import json
from pathlib import Path
import re
import shutil

from .assessment import sha256, write_json

SAFE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*\Z')


def identifier(value):
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise ValueError('Unsafe case or assembler identifier: ' + repr(value))
    return value


def expected_plan(path):
    """Expand a frozen explicit slot list or case/assembler Cartesian product."""
    plan = json.loads(Path(path).read_text())
    if 'slots' in plan:
        pairs = [(identifier(row['case_id']), identifier(row['assembler'])) for row in plan['slots']]
    else:
        cases = [identifier(row['id'] if isinstance(row, dict) else row) for row in plan['cases']]
        assemblers = [identifier(row['id'] if isinstance(row, dict) else row) for row in plan['assemblers']]
        if len(cases) != len(set(cases)) or len(assemblers) != len(set(assemblers)):
            raise ValueError('Duplicate case or assembler in expected slot plan')
        pairs = [(case, assembler) for case in cases for assembler in assemblers]
    if not pairs or len(pairs) != len(set(pairs)):
        raise ValueError('Expected slot plan must contain unique non-empty slots')
    return set(pairs)


def export_results(paths, output, expected_slots, run_id, plan_path=None):
    if expected_slots < 1:
        raise ValueError('Expected slot count must be positive')
    sources = sorted(map(Path, paths))
    expected = expected_plan(plan_path) if plan_path else None
    if expected is not None:
        actual = [(identifier(row['case']['id']), identifier(row['assembler']))
                  for row in (json.loads(p.read_text()) for p in sources)]
        if len(expected) != expected_slots:
            raise ValueError('Expected slot count differs from frozen slot plan')
        if len(actual) != len(set(actual)) or set(actual) != expected:
            missing = sorted(expected - set(actual))
            extra = sorted(set(actual) - expected)
            raise ValueError(f'Result slots differ from frozen plan; missing={missing}, extra={extra}')
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Export directory must be empty; refusing to overwrite retained evidence')
    output.mkdir(parents=True, exist_ok=True)
    records, seen, assemblies, graphs = [], set(), [], []
    for source in sources:
        record = json.loads(source.read_text())
        case_id = identifier(record['case']['id'])
        assembler = identifier(record['assembler'])
        key = case_id, assembler
        if key in seen:
            raise ValueError('Duplicate result slot: ' + '/'.join(key))
        seen.add(key)
        evidence_name = record['evidence_directory']
        if Path(evidence_name).name != evidence_name:
            raise ValueError('Evidence directory must be a sibling of its result')
        evidence_source = source.parent / evidence_name
        if not evidence_source.is_dir():
            raise ValueError('Missing assessment evidence for ' + '/'.join(key))
        target = output / 'evidence' / case_id / assembler
        target.mkdir(parents=True)
        shutil.copyfile(source, target / 'result.json')
        for item in sorted(evidence_source.iterdir()):
            if not item.is_file() or item.is_symlink():
                raise ValueError('Evidence must contain regular files only: ' + str(item))
            destination = target / item.name
            if item.name == 'assembly.fasta' or item.suffix == '.gfa':
                destination = output / 'assemblies' / case_id / assembler / item.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                relative = destination.relative_to(output).as_posix()
                (assemblies if item.name == 'assembly.fasta' else graphs).append(relative)
            shutil.copyfile(item, destination)
        verify_evidence(record, target, output / 'assemblies' / case_id / assembler)
        record['source_result_sha256'] = sha256(source)
        record['evidence_directory'] = target.relative_to(output).as_posix()
        records.append(record)
    write_json(output / 'results.json', {'schema_version': 1, 'run_id': run_id, 'results': records})
    write_table(output / 'results.tsv', records)
    (output / 'index.html').write_text(render_html(records, expected_slots, run_id))
    complete = len(records) == expected_slots and all(
        r['assessment']['status'] == 'completed' or (
            r['assessment']['status'] == 'not_run' and r['execution']['status'] == 'software_error')
        for r in records)
    manifest = {'schema_version': 1, 'run_id': run_id, 'complete': complete,
                'expected_slots': expected_slots, 'result_count': len(records),
                'presets': sorted({r['preset'] for r in records}),
                'retention': {'assemblies': sorted(assemblies), 'graphs': sorted(graphs)},
                'files': {p.relative_to(output).as_posix(): sha256(p)
                          for p in sorted(output.rglob('*')) if p.is_file()}}
    if expected is not None:
        manifest['expected_slot_plan'] = [{'case_id': case, 'assembler': assembler}
                                          for case, assembler in sorted(expected)]
        manifest['plan_sha256'] = sha256(plan_path)
        shutil.copyfile(plan_path, output / 'slot-plan.json')
        manifest['files']['slot-plan.json'] = sha256(output / 'slot-plan.json')
    write_json(output / 'manifest.json', manifest)
    return manifest


def verify_evidence(record, target, assembly_dir):
    provenance = record['provenance']
    for name, key in (('execution.json', 'execution_sha256'), ('simulation.json', 'simulation_sha256'),
                      ('reference-provenance.json', 'reference_provenance_sha256')):
        if sha256(target / name) != provenance[key]:
            raise ValueError('Evidence hash mismatch: ' + name)
    execution = json.loads((target / 'execution.json').read_text())
    simulation = json.loads((target / 'simulation.json').read_text())
    reference = json.loads((target / 'reference-provenance.json').read_text())
    if execution != record['execution']:
        raise ValueError('Embedded execution differs from retained execution')
    if record['assessment']['status'] != 'error' and (simulation.get('case') != record['case'] or simulation.get('status') != 'completed'
            or simulation.get('reference_sha256') != provenance['reference_sha256']
            or reference.get('reference_sha256') != provenance['reference_sha256']
            or execution.get('reads_sha256') != simulation.get('reads_sha256')):
        raise ValueError('Retained reference/simulation/execution binding mismatch')
    graphs = provenance.get('retained_graphs', [])
    if len(graphs) != len({row['file'] for row in graphs}):
        raise ValueError('Duplicate retained graph')
    actual_graphs = {p.name for p in assembly_dir.glob('*.gfa')}
    if {row['file'] for row in graphs} != actual_graphs:
        raise ValueError('Retained graph inventory differs')
    for graph in graphs:
        if identifier(graph['file']) != graph['file'] or sha256(assembly_dir / graph['file']) != graph['sha256']:
            raise ValueError('Graph hash mismatch')
    if record['assessment']['status'] == 'completed':
        if sha256(target / 'alignment.paf') != record['assessment']['paf_sha256']:
            raise ValueError('Alignment hash mismatch')
        if sha256(assembly_dir / 'assembly.fasta') != provenance['assembly_sha256']:
            raise ValueError('Assembly hash mismatch')


def rows(records):
    for record in records:
        molecules = record['replicons'] or [None]
        for molecule in molecules:
            row = {'case_id': record['case']['id'], 'group': record['case']['group'],
                   'preset': record['preset'], 'assembler': record['assembler'],
                   'execution_status': record['execution']['status'],
                   'assessment_status': record['assessment']['status'],
                   'sequence_outcome': record['sequence_outcome'],
                   'workflow_wall_seconds': record['resources']['workflow_wall_seconds'],
                   'assembler_process_tree_peak_rss_bytes': record['resources']['assembler_process_tree_peak_rss_bytes'],
                   'assessment_mapper_wall_seconds': record['resources'].get('assessment_mapper_wall_seconds'),
                   'assessment_mapper_process_tree_peak_rss_bytes': record['resources'].get('assessment_mapper_process_tree_peak_rss_bytes'),
                   'reference_sha256': record['provenance']['reference_sha256'],
                   'reads_sha256': record['execution'].get('reads_sha256'),
                   'assembly_sha256': record['provenance'].get('assembly_sha256'),
                   'assembler_version': record['execution'].get('version'),
                   'structural_correctness': None}
            for key in ('accession', 'molecule_type', 'length_bp', 'contiguity', 'complete',
                        'identity', 'identity_measured', 'max_indel_bp'):
                row[key] = molecule[key] if molecule else None
            yield row


def write_table(path, records):
    data = list(rows(records))
    if not data:
        raise ValueError('No result records to export')
    with Path(path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data[0]), delimiter='\t')
        writer.writeheader()
        writer.writerows(data)


def display(value, multiplier=1, suffix=''):
    return 'Not measured' if value is None else f'{value * multiplier:,.2f}{suffix}'


def render_html(records, expected_slots, run_id):
    body = []
    for record in records:
        case_id, assembler = record['case']['id'], record['assembler']
        sequence = record['sequence_outcome'] or 'No sequence verdict'
        molecules = record['replicons']
        details = '; '.join(f"{m['accession']}: {display(m['contiguity'], 100, '%')} contiguity, "
                            f"{display(m['identity'], 100, '%')} identity, "
                            f"{m['max_indel_bp'] if m['max_indel_bp'] is not None else 'not measured'} bp maximum indel"
                            for m in molecules) or record['assessment'].get('reason', record['assessment'].get('error', 'No sequence measurement'))
        link = ''
        if record['assessment']['status'] == 'completed':
            path = f'assemblies/{case_id}/{assembler}/assembly.fasta'
            link = f'<a href="{escape(path, quote=True)}">Assembly FASTA</a> · '
        evidence = record['evidence_directory'] + '/result.json'
        body.append('<tr>' + ''.join(f'<td>{escape(str(v))}</td>' for v in
                    (case_id, record['case']['group'], assembler,
                     record['execution']['status'], sequence, details,
                     display(record['resources']['workflow_wall_seconds'], suffix=' s'),
                     display(record['resources']['assembler_process_tree_peak_rss_bytes'], 1 / 1024**2, ' MiB'),
                     display(record['resources'].get('assessment_mapper_wall_seconds'), suffix=' s'),
                     display(record['resources'].get('assessment_mapper_process_tree_peak_rss_bytes'), 1 / 1024**2, ' MiB')))
                    + f'<td>{link}<a href="{escape(evidence, quote=True)}">Evidence</a></td></tr>')
    quick = any(r['preset'] == 'quick' for r in records)
    label = 'Quick workflow check — excluded from headline comparisons' if quick else 'Standard benchmark'
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Assembly benchmark: {escape(run_id)}</title>
<style>body{{font:16px system-ui,sans-serif;margin:2rem;line-height:1.5;color:#20242a}}main{{max-width:1400px;margin:auto}}.scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%}}th,td{{padding:.7rem;text-align:left;vertical-align:top;border-bottom:1px solid #ccd1d8}}th{{background:#edf0f4}}.scope{{padding:1rem;background:#fff4d1}}a{{color:#174a95}}@media(max-width:600px){{body{{margin:1rem}}}}</style></head>
<body><main><h1>Assembly benchmark</h1><p>{escape(run_id)} · {len(records)}/{expected_slots} recorded slots</p>
<p class="scope"><strong>{label}</strong>. No overall winner score is calculated.</p>
<p><a href="results.tsv">Download TSV</a> · <a href="results.json">Results JSON</a> · <a href="manifest.json">Checksums and completion gate</a></p>
<div class="scroll"><table><thead><tr><th>Case</th><th>Group</th><th>Assembler</th><th>Execution</th><th>Sequence outcome</th><th>Measured replicon metrics</th><th>Workflow time</th><th>Assembler peak RAM</th><th>Mapper time</th><th>Mapper peak RAM</th><th>Files</th></tr></thead><tbody>{''.join(body)}</tbody></table></div>
<h2>Measurement scope</h2><p>Completeness is the longest single alignment span against a tripled reference divided by the original molecule length. Completion requires at least 99%; contiguity is uncapped. Identity and maximum indel are reported only when that alignment spans more than 100,000 bp or one quarter of the reference. Structural correctness is not measured by this assessment. An execution or assessment failure does not establish sequence absence.</p>
<p>Workflow time includes assembler verification/execution and exact assessment; downloads, environment provisioning, simulation and scheduler waiting are excluded. Assembler and assessment mapper RAM are separate sampled process-tree sums; shared pages may be counted more than once. Separate molecule types are reported only where provided by reference provenance.</p>
<p>Method attribution: <a href="https://github.com/rrwick/Long-read-assembler-comparison">Wick and Holt long-read assembler comparison</a>; alignment with <a href="https://github.com/lh3/minimap2">minimap2</a>. Reference accessions, input hashes, simulator settings and software versions are retained in the evidence files.</p>
</main></body></html>'''
