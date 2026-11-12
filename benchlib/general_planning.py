"""Immutable Wick/Holt published-50 inputs, independent of execution controllers."""
from pathlib import Path
import hashlib
import json

from .adapters import load_registry, resolve_assembler, validate_environment
from .io import digest
from .planning import load, plan_digest, tokens

GENERAL_FILES = ('selection-50.json', 'profile.json', 'inputs.json', 'reference-archive.json')


def load_collection(project):
    root = Path(project) / 'assets/general'
    checks = load(root / 'checksums.json')
    if set(checks) != set(GENERAL_FILES):
        raise ValueError('General catalogue checksum inventory differs')
    for name in GENERAL_FILES:
        if digest(root / name) != checks[name]:
            raise ValueError('Frozen general source changed: ' + name)
    selection = load(root / 'selection-50.json')
    inputs = load(root / 'inputs.json')['inputs']
    datasets = selection['datasets']
    ids = [d['id'] for d in datasets]
    if (len(ids) != 50 or len(set(ids)) != 50 or set(inputs) != set(ids)
            or sum(d['plasmid_count'] > 0 for d in datasets) != 25
            or sum(d['plasmid_count'] for d in datasets) != 50):
        raise ValueError('Published fifty-dataset selection or sampling balance differs')
    reference_receipt = load(root / 'reference-archive.json')
    if reference_receipt['archive'] != selection['archives']['references']:
        raise ValueError('Reference archive identity differs')
    for dataset in datasets:
        admission = inputs[dataset['id']]
        manifest = admission['manifest']
        original = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
        if hashlib.sha256(original).hexdigest() != admission['source_sha256']:
            raise ValueError('Archived input manifest source checksum differs')
        if manifest['status'] != 'valid' or any(manifest['case'].get(k) != v for k, v in dataset.items()):
            raise ValueError('Published input/case binding differs')
        member = manifest['read_archive_member']
        if (member['name'] != dataset['id'] + '.fastq.gz' or member['offset'] < 512
                or member['offset'] % 512 or member['size'] < 1
                or member['offset'] + member['size'] > selection['archives']['reads']['size']
                or manifest['source_read_archive'] != selection['archives']['reads']
                or manifest['source_reference_archive'] != selection['archives']['references']
                or reference_receipt['selected'][dataset['id']]['sha256'] != manifest['truth_sha256']):
            raise ValueError('Published archive/input binding differs')
        if any(manifest['statistics'][k] != dataset['published_read_statistics'][k]
               for k in ('read_count', 'total_read_bases', 'read_n50_bp')):
            raise ValueError('Published statistics binding differs')
    return selection, inputs


def build_general_plan(project, preset='standard', groups=None, cases=None, assemblers=None):
    project = Path(project).resolve()
    if preset != 'standard':
        raise ValueError('General published collection requires --preset standard')
    selection, inputs = load_collection(project)
    selected_groups, selected_cases = tokens(groups, 'group'), tokens(cases, 'case')
    if set(selected_groups) - {'general'} or set(selected_cases) - set(inputs):
        raise ValueError('Unknown published general group or dataset')
    chosen = [d for d in selection['datasets'] if not selected_cases or d['id'] in selected_cases]
    registry = load_registry(project / 'assets/assemblers.json')
    requested = tokens(assemblers, 'assembler') or ['flye', 'raven', 'plassembler', 'miniasm-plus']
    definitions = [resolve_assembler(registry, name) for name in requested]
    ids = [d['id'] for d in definitions]
    if len(set(ids)) != len(ids):
        raise ValueError('Assembler selections resolve to the same immutable version')
    sources = {'assets/general/' + n for n in (*GENERAL_FILES, 'checksums.json')}
    sources.update(('assets/assemblers.json', 'environments/pixi.toml', 'environments/pixi.lock'))
    for definition in definitions:
        if definition['tool'] == 'miniasm':
            raise ValueError('Raw Miniasm is an intermediate, not a reported general workflow')
        if definition['status'] != 'admitted':
            raise ValueError('General assembler is not admitted')
        validate_environment(definition, project)
        sources.update((definition['manifest'], Path(definition['manifest']).with_name('pixi.lock').as_posix()))
    case_rows = [dict(d, group='general', reference_id=d['id'], track='general', preset='standard',
                      purpose='published_general_benchmark', headline_eligible=True,
                      assembly_options={'flye_input_mode': 'nano-raw', 'plassembler_raw_flag': True,
                                        'plassembler_chromosome_threshold': 400000},
                      input_policy='published_frozen_bytes_no_resimulation') for d in chosen]
    references = {d['id']: {'id': d['id'], 'mode': 'whole_genome', 'status': 'admitted',
        'reference_sha256': inputs[d['id']]['manifest']['truth_sha256'],
        'molecules': [dict(r, accession=r['refseq_accession'], type=r['molecule_type']) for r in d['replicons']]}
        for d in chosen}
    plan = {'schema_version': 1, 'track': 'general', 'preset': 'standard',
        'purpose': 'published_general_benchmark', 'headline_eligible': True,
        'selection': {'track': 'general', 'groups': selected_groups, 'cases': selected_cases, 'assemblers': ids},
        'collection_id': selection['panel_id'], 'cases': case_rows, 'reference_ids': list(references),
        'references': references, 'read_inputs': {d['id']: inputs[d['id']] for d in chosen},
        'assemblers': ids, 'assembler_definitions': {d['id']: d for d in definitions},
        'slots': [{'case_id': c['id'], 'assembler': a} for c in case_rows for a in ids],
        'assessment': 'wick-longest-alignment-v1', 'completion_threshold': .99,
        'intermediate_policy': 'Raw miniasm belongs to miniasm-plus; never a fifth reported outcome.',
        'resource_policy': {'queue_capacity': 1000, 'assembly': {'cpus': 4, 'time_minutes': 240,
            'default_memory_gb': 16, 'time_minutes_by_tool': {'plassembler': 120}}},
        'source_file_sha256': {n: digest(project / n) for n in sorted(sources)}}
    plan['expected_slots'] = len(plan['slots'])
    plan['plan_sha256'] = plan_digest(plan)
    return plan


def validate_general_plan(project, plan):
    selection = plan['selection']
    expected = build_general_plan(project, plan['preset'], selection['groups'], selection['cases'], selection['assemblers'])
    if expected != plan:
        raise ValueError('General plan differs from frozen selection, bindings or execution definitions')
    return plan
