"""Inspect and freeze admitted selections before scheduling any work."""
import hashlib
import json
import math
from pathlib import Path
import re

from .adapters import load_registry, resolve_assembler, validate_environment
from .io import digest

IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*\Z')
RESOURCE_POLICY = {
    'queue_capacity': 1000,
    'assembly': {'cpus': 2, 'time_minutes': 30, 'default_memory_gb': 4,
                 'memory_gb_by_tool': {'flye': 16, 'raven': 4}},
}
STANDARD_RESOURCE_POLICY = {
    'queue_capacity': 1000,
    'assembly': {'cpus': 4, 'time_minutes': 240, 'default_memory_gb': 16,
                 'memory_gb_by_tool': {'flye': 16, 'raven': 16}},
    'simulation': {'cpus': 1, 'time_minutes': 120},
}



def identifier(value, label):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError('Invalid ' + label + ': ' + repr(value))
    return value


def tokens(values, label):
    if values is None or values == '':
        return []
    values = values.split(',') if isinstance(values, str) else list(values)
    result = [identifier(v.strip() if isinstance(v, str) else v, label) for v in values]
    if len(set(result)) != len(result):
        raise ValueError('Duplicate ' + label + ' selection')
    return result


def load(path):
    return json.loads(Path(path).read_text())


def unique_rows(rows, label):
    if not isinstance(rows, list) or not rows:
        raise ValueError(label + ' must be a non-empty list')
    indexed = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(label + ' entries must be objects')
        key = identifier(row.get('id'), label + ' ID')
        if key in indexed:
            raise ValueError('Duplicate ' + label + ' ID: ' + key)
        indexed[key] = row
    return indexed


def validate_standard_reference(reference):
    """Standard uses whole native circular chromosome/plasmid inventories."""
    from .references import validate_reference_definition

    validate_reference_definition(reference)
    if reference.get('status') != 'admitted' or reference.get('preparation') != 'whole_genome':
        raise ValueError('Standard reference is not admitted as a whole genome')
    if 'quick_slice_bases' in reference or reference.get('purpose') == 'workflow_check':
        raise ValueError('Quick fragments cannot be Standard references')
    molecules = reference.get('molecules', [])
    if sum(m.get('type') == 'chromosome' for m in molecules) != 1:
        raise ValueError('Standard requires exactly one chromosome plus native plasmids')
    if any(m.get('topology') != 'circular' or m.get('ambiguous_bases') != 0 for m in molecules):
        raise ValueError('Standard requires unambiguous native circular molecules; use diagnostics for linear cases')
    return reference


def admission_sources(project, reference):
    """Bind the retained admission receipt; it is evidence, not a live lookup."""
    name = reference.get('admission_receipt')
    checksum = reference.get('admission_receipt_sha256')
    if not isinstance(name, str):
        raise ValueError('Standard reference has no admission receipt')
    relative = Path(name)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Admission receipt must be a project-relative path')
    path = Path(project) / relative
    if not path.resolve().is_relative_to(Path(project).resolve()) or not path.is_file():
        raise ValueError('Admission receipt is missing or escapes the project')
    if not isinstance(checksum, str) or digest(path) != checksum:
        raise ValueError('Reference admission receipt checksum mismatch')
    receipt = load(path)
    if receipt.get('reference_id') != reference['id']:
        raise ValueError('Admission receipt belongs to a different reference')
    for field in ('download_sha256', 'canonical_fasta_sha256', 'molecules'):
        if receipt.get(field) != reference.get(field):
            raise ValueError('Reference admission receipt binding mismatch: ' + field)
    return name


def validate_case(case, groups, references, preset='quick'):
    identifier(case.get('id'), 'case ID')
    if case.get('group') not in groups:
        raise ValueError('Case uses an unknown group: ' + case['id'])
    memberships = case.get('groups', [case['group']])
    if not isinstance(memberships, list) or not memberships or set(memberships)-set(groups) or case['group'] not in memberships:
        raise ValueError('Invalid scenario memberships: ' + case['id'])
    if case.get('reference_id') not in references:
        raise ValueError('Case uses an unknown reference: ' + case['id'])
    purpose = 'workflow_check' if preset == 'quick' else 'baseline_validation'
    if case.get('preset') != preset or case.get('purpose') != purpose or case.get('headline_eligible') is not False:
        raise ValueError(preset.title() + ' case must retain its declared non-headline purpose: ' + case['id'])
    if preset == 'standard':
        validate_standard_reference(references[case['reference_id']])
    for field in ('coverage', 'length_mean', 'length_sd'):
        value = case.get(field)
        if (not isinstance(value, (float, int)) or isinstance(value, bool)
                or not math.isfinite(value) or value < 0
                or (field != 'length_sd' and value == 0)):
            raise ValueError('Invalid case ' + field + ': ' + case['id'])
    seed = case.get('seed')
    if type(seed) is not int or not 0 <= seed < 2**32 - 1:
        raise ValueError('Case seed must be an integer in [0, 2**32 - 2]')
    for field, minimum in (('repeat', 1), ('repeat_index', 0)):
        if field in case and (type(case[field]) is not int or case[field] < minimum):
            raise ValueError('Invalid case ' + field)
    fraction = case.get('short_fraction', 0)
    if (not isinstance(fraction, (float, int)) or isinstance(fraction, bool)
            or not math.isfinite(fraction) or not 0 <= fraction <= 1):
        raise ValueError('Case short_fraction must be a base fraction in [0, 1]')
    for field in ('short_length_mean', 'short_length_sd'):
        if field in case:
            value = case[field]
            if (not isinstance(value, (float, int)) or isinstance(value, bool)
                    or not math.isfinite(value) or value < 0
                    or (field.endswith('_mean') and value == 0)):
                raise ValueError('Invalid case ' + field)
    supported = {'id', 'group', 'reference_id', 'description', 'preset', 'purpose', 'headline_eligible',
                 'coverage', 'seed', 'length_mean', 'length_sd', 'short_fraction',
                 'short_length_mean', 'short_length_sd', 'plasmid_relative_depth', 'simulation_method', 'groups'}
    if 'simulation_method' in case and case['simulation_method'] != 'native-error-free-v1':
        raise ValueError('Unsupported Standard simulation method')
    if 'plasmid_relative_depth' in case:
        depth = case['plasmid_relative_depth']
        if preset != 'standard' or type(depth) not in (int, float) or not math.isfinite(depth) or depth <= 0:
            raise ValueError('Invalid plasmid relative depth')
    if set(case) - supported:
        raise ValueError('Unsupported ' + preset + ' simulation fields: ' + ', '.join(sorted(set(case) - supported)))


def catalogues(project, preset='quick'):
    project = Path(project)
    groups = unique_rows(load(project / 'assets/groups.json')['groups'], 'group')
    references = unique_rows(load(project / 'assets/references.json')['references'], 'reference')
    manifest = project / ('assets/' + preset + '.json')
    if not manifest.is_file():
        raise ValueError(preset.title() + ' manifest is not admitted')
    cases = unique_rows(load(manifest), 'case')
    for case in cases.values():
        validate_case(case, groups, references, preset)
        if preset == 'standard':
            admission_sources(project, references[case['reference_id']])
        admitted_status = 'implemented' if preset == 'quick' else 'baseline_admitted'
        if groups[case['group']].get(preset + '_status') != admitted_status:
            raise ValueError(preset.title() + ' case belongs to an unadmitted group: ' + case['id'])
    registry = load_registry(project / 'assets/assemblers.json')
    return groups, references, cases, registry


def catalogue(project):
    """List choices without creating a run or downloading any data."""
    groups, references, cases, registry = catalogues(project)
    standard_status, standard_cases, admission_error = 'not_admitted', [], None
    try:
        _, _, standard, _ = catalogues(project, 'standard')
        standard_cases = list(standard.values())
        standard_status = 'baseline_admitted'
    except (ValueError, OSError, KeyError) as error:
        admission_error = str(error)
    real_cases = []
    if (Path(project) / 'assets/real-pilot.json').is_file():
        real_cases = build_plan(project, preset='standard', track='real')['cases']
    return {'tracks': {'simulated': 'implemented', 'real': 'pilot_admitted' if real_cases else 'not_admitted', 'general': 'published_50_admitted', 'diagnostic': 'selectable_preserved_methods'},
            'general_collection': {'datasets': 50, 'default_reported_slots': 200, 'preset': 'standard', 'input_policy': 'Published frozen bytes; no resimulation'},
            'diagnostic_groups': {key: {'new_execution': 'deferred' if key == 'S6' else 'implemented', 'original_source_required': key == 'S7'} for key in ('S1','S2','S3','S4','S5','S6','S7')},
            'real_cases': real_cases, 'schema_version': 1, 'scope': 'single_isolate_bacterial_long_read',
            'presets': {'quick': 'workflow_check', 'standard': standard_status},
            'standard_scope': 'Beta simulated panel; five seeds, native genomes, error-free contrasts; no headline rankings',
            'standard_admission_error': admission_error,
            'groups': list(groups.values()), 'cases': list(cases.values()) + standard_cases,
            'references': list(references.values()), 'aliases': registry['aliases'],
            'assemblers': list(registry['assemblers'].values())}


def plan_digest(plan):
    payload = {key: value for key, value in plan.items() if key != 'plan_sha256'}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def build_plan(project, preset='quick', groups=None, cases=None, assemblers=None, track='simulated'):
    if track == 'real':
        from .real_planning import build_real_plan
        return build_real_plan(project, preset, groups, cases, assemblers)
    if track == 'general':
        from .general_planning import build_general_plan
        return build_general_plan(project, preset, groups, cases, assemblers)
    if track == 'diagnostic':
        from .diagnostic_planning import build_diagnostic_plan
        return build_diagnostic_plan(project, preset, groups, cases, assemblers)
    if track != 'simulated':
        raise ValueError('Unknown input track')
    project = Path(project).resolve()
    if preset not in ('quick', 'standard'):
        raise ValueError('Unknown preset: ' + str(preset))
    group_rows, reference_rows, case_rows, registry = catalogues(project, preset)
    selected_groups, selected_cases = tokens(groups, 'group'), tokens(cases, 'case')
    for requested, known, label in ((selected_groups, group_rows, 'group'), (selected_cases, case_rows, 'case')):
        unknown = set(requested) - set(known)
        if unknown:
            raise ValueError('Unknown ' + label + ' selection: ' + ', '.join(sorted(unknown)))
    admitted_status = 'implemented' if preset == 'quick' else 'baseline_admitted'
    unavailable = [g for g in selected_groups if group_rows[g].get(preset + '_status') != admitted_status]
    if unavailable:
        raise ValueError('Groups are not admitted in ' + preset.title() + ': ' + ', '.join(unavailable))
    selected = [row for row in case_rows.values()
                if (not selected_groups or set(row.get('groups', [row['group']])) & set(selected_groups))
                and (not selected_cases or row['id'] in selected_cases)]
    if selected_cases and set(selected_cases) != {row['id'] for row in selected}:
        raise ValueError('Selected cases are excluded by the selected groups')
    if not selected:
        raise ValueError('No admitted cases match the selection')
    requested_assemblers = tokens(assemblers, 'assembler') or ['flye', 'raven']
    definitions = [resolve_assembler(registry, value) for value in requested_assemblers]
    assembler_ids = [row['id'] for row in definitions]
    if len(set(assembler_ids)) != len(assembler_ids):
        raise ValueError('Assembler selections resolve to the same immutable version ID')
    if any(row.get('status') != 'admitted' for row in definitions):
        raise ValueError('Selected assembler version is not admitted')
    source_names = {'assets/' + preset + '.json', 'assets/groups.json', 'assets/references.json', 'assets/assemblers.json',
                    'environments/pixi.toml', 'environments/pixi.lock'}
    if preset == 'standard':
        source_names.update(admission_sources(project, reference_rows[case['reference_id']]) for case in selected)
    for definition in definitions:
        name = Path(definition['manifest'])
        if name.is_absolute() or '..' in name.parts:
            raise ValueError('Assembler manifest must be a relative project path')
        source_names.update((name.as_posix(), name.with_name('pixi.lock').as_posix()))
    if any(not (project / name).resolve().is_relative_to(project) for name in source_names):
        raise ValueError('Source manifest or lock escapes the project')
    for definition in definitions:
        validate_environment(definition, project)
    reference_ids = sorted({row['reference_id'] for row in selected})
    purpose = 'workflow_check' if preset == 'quick' else 'baseline_validation'
    plan = {'schema_version': 1, 'preset': preset, 'purpose': purpose, 'headline_eligible': False,
            'selection': {'groups': selected_groups, 'cases': selected_cases, 'assemblers': assembler_ids},
            'cases': selected, 'assemblers': assembler_ids,
            'assembler_definitions': {row['id']: row for row in definitions},
            'reference_ids': reference_ids,
            'references': {key: reference_rows[key] for key in reference_ids},
            'slots': [{'case_id': case['id'], 'assembler': assembler} for case in selected for assembler in assembler_ids],
            'resource_policy': RESOURCE_POLICY if preset == 'quick' else STANDARD_RESOURCE_POLICY,
            'source_file_sha256': {name: digest(project / name) for name in sorted(source_names)}}
    plan['expected_slots'] = len(plan['slots'])
    # Isolate callers from shared constants and return a JSON-only snapshot.
    plan = json.loads(json.dumps(plan, allow_nan=False))
    plan['plan_sha256'] = plan_digest(plan)
    return plan


def validate_plan(project, plan):
    """Reject altered plans and changed registries before scheduling."""
    if not isinstance(plan, dict) or plan.get('plan_sha256') != plan_digest(plan):
        raise ValueError('Frozen plan checksum mismatch')
    selection = plan.get('selection', {})
    rebuilt = build_plan(project, plan.get('preset'), selection.get('groups'), selection.get('cases'), selection.get('assemblers'), track=plan.get('track', 'simulated'))
    if rebuilt != plan:
        raise ValueError('Frozen plan differs from current admitted sources or selections')
    return plan
