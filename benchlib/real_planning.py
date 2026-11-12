"""A separate admission boundary for frozen real single-isolate inputs."""
from pathlib import Path

from .adapters import load_registry, resolve_assembler, validate_environment
from .io import digest
from .real_data import inspect_manifest
from .references import validate_reference_definition


def build_real_plan(project, preset, groups=None, cases=None, assemblers=None):
    from .planning import load, tokens, unique_rows, admission_sources, plan_digest, STANDARD_RESOURCE_POLICY
    project = Path(project).resolve()
    if preset != 'standard':
        raise ValueError('Real inputs require --preset standard; Quick remains simulated')
    manifest = load(project / 'assets/real-pilot.json')
    if manifest.get('status') != 'pilot_admitted':
        raise ValueError('Real pilot is not admitted')
    study_name = manifest['study_manifest']
    study = load(project / study_name)
    inspect_manifest(study, project)
    rows = unique_rows(manifest['cases'], 'real case')
    selected_groups, selected_cases = tokens(groups, 'group'), tokens(cases, 'case')
    if set(selected_groups) - {'plasmids'} or set(selected_cases) - set(rows):
        raise ValueError('Unknown real-data group or case')
    selected = [c for c in rows.values() if not selected_cases or c['id'] in selected_cases]
    refs = unique_rows(load(project / 'assets/references.json')['references'], 'reference')
    reads, source_names = {}, {'assets/real-pilot.json', study_name, 'assets/references.json',
                               'assets/assemblers.json', 'environments/pixi.toml', 'environments/pixi.lock'}
    source_names.update(r['file'] for r in study['source_receipts'] if 'file' in r)
    for case in selected:
        if (case.get('track') != 'real' or case.get('purpose') != 'real_data_pilot'
                or case.get('headline_eligible') is not False or case.get('preset') != 'standard'
                or case.get('group') != 'plasmids' or case.get('input_policy') != 'full_archive_reads_no_filtering_no_subsampling'):
            raise ValueError('Real pilot scope or input policy differs')
        definition = manifest['read_inputs'][case['id']]
        isolate = next(x for x in study['isolates'] if x['isolate_id'] == definition['isolate_id'])
        if any(m['role_status'] == 'conflict_requires_resolution' for m in isolate['reference']['molecules']):
            raise ValueError('Unresolved archive molecule role conflict')
        if (definition['run_accession'] != isolate['ont']['run_accession']
                or definition['sample_accession'] != isolate['sample_accession']
                or len(isolate['ont']['files']) != 1):
            raise ValueError('Real input/run/BioSample binding differs')
        archived = isolate['ont']['files'][0]
        if any(definition[k] != archived[k] for k in ('url', 'publisher_md5', 'compressed_bytes')):
            raise ValueError('Real read archive source differs')
        receipt_name = definition['admission_receipt']
        path = (project / receipt_name).resolve()
        if not path.is_relative_to(project) or digest(path) != definition['admission_sha256']:
            raise ValueError('Read admission receipt changed')
        receipt = load(path)
        for field in ('download_sha256', 'reads_sha256', 'read_count', 'total_bases', 'decompressed_bytes', 'sample_accession', 'run_accession'):
            if receipt.get(field) != definition.get(field):
                raise ValueError('Read admission binding differs: ' + field)
        if (definition['read_count'] != isolate['ont']['read_count'] or definition['total_bases'] != isolate['ont']['base_count']):
            raise ValueError('Read admission statistics differ from archive metadata')
        ref = refs[case['reference_id']]
        validate_reference_definition(ref)
        if ref.get('biosample') != definition['sample_accession'] or ref.get('accession') != isolate['reference']['assembly_accession']:
            raise ValueError('Real reference/BioSample binding differs')
        inventory = {m['accession']: (m['length_bp'], m['type'], m['topology']) for m in ref['molecules']}
        expected = {m['accession']: (m['length_bp'], m['proposed_biological_role'], m['topology']) for m in isolate['reference']['molecules']}
        if inventory != expected:
            raise ValueError('Real reference molecule inventory differs')
        source_names.update((receipt_name, admission_sources(project, ref)))
        reads[case['id']] = definition
    registry = load_registry(project / 'assets/assemblers.json')
    requested = tokens(assemblers, 'assembler') or ['flye', 'raven']
    definitions = [resolve_assembler(registry, name) for name in requested]
    ids = [d['id'] for d in definitions]
    if len(set(ids)) != len(ids):
        raise ValueError('Assembler selections resolve to the same immutable version')
    for definition in definitions:
        if definition['status'] != 'admitted':
            raise ValueError('Assembler is not admitted')
        validate_environment(definition, project)
        source_names.update((definition['manifest'], Path(definition['manifest']).with_name('pixi.lock').as_posix()))
    if any(not (project / name).resolve().is_relative_to(project) for name in source_names):
        raise ValueError('Real admission source escapes project')
    ref_ids = sorted({c['reference_id'] for c in selected})
    plan = {'schema_version': 1, 'track': 'real', 'preset': 'standard', 'purpose': 'real_data_pilot', 'headline_eligible': False,
            'selection': {'track': 'real', 'groups': selected_groups, 'cases': selected_cases, 'assemblers': ids},
            'cases': selected, 'assemblers': ids, 'assembler_definitions': {d['id']: d for d in definitions},
            'reference_ids': ref_ids, 'references': {r: refs[r] for r in ref_ids}, 'read_inputs': reads,
            'slots': [{'case_id': c['id'], 'assembler': a} for c in selected for a in ids],
            'resource_policy': STANDARD_RESOURCE_POLICY,
            'source_file_sha256': {n: digest(project / n) for n in sorted(source_names)}}
    plan['expected_slots'] = len(plan['slots'])
    plan['plan_sha256'] = plan_digest(plan)
    return plan
