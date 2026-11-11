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


def validate_case(case, groups, references):
    identifier(case.get('id'), 'case ID')
    if case.get('group') not in groups:
        raise ValueError('Case uses an unknown group: ' + case['id'])
    if case.get('reference_id') not in references:
        raise ValueError('Case uses an unknown reference: ' + case['id'])
    if case.get('preset') != 'quick' or case.get('purpose') != 'workflow_check' or case.get('headline_eligible') is not False:
        raise ValueError('Quick case must remain an excluded workflow check: ' + case['id'])
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
                 'short_length_mean', 'short_length_sd'}
    if set(case) - supported:
        raise ValueError('Unsupported Quick simulation fields: ' + ', '.join(sorted(set(case) - supported)))


def catalogues(project):
    project = Path(project)
    groups = unique_rows(load(project / 'assets/groups.json')['groups'], 'group')
    references = unique_rows(load(project / 'assets/references.json')['references'], 'reference')
    cases = unique_rows(load(project / 'assets/quick.json'), 'case')
    for case in cases.values():
        validate_case(case, groups, references)
        if groups[case['group']].get('quick_status') != 'implemented':
            raise ValueError('Quick case belongs to an unimplemented group: ' + case['id'])
    registry = load_registry(project / 'assets/assemblers.json')
    return groups, references, cases, registry


def catalogue(project):
    """List choices without creating a run or downloading any data."""
    groups, references, cases, registry = catalogues(project)
    return {'schema_version': 1, 'scope': 'single_isolate_bacterial_long_read',
            'presets': {'quick': 'workflow_check', 'standard': 'not_admitted'},
            'groups': list(groups.values()), 'cases': list(cases.values()),
            'references': list(references.values()), 'aliases': registry['aliases'],
            'assemblers': list(registry['assemblers'].values())}


def plan_digest(plan):
    payload = {key: value for key, value in plan.items() if key != 'plan_sha256'}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def build_plan(project, preset='quick', groups=None, cases=None, assemblers=None):
    project = Path(project).resolve()
    if preset != 'quick':
        if preset == 'standard':
            raise ValueError('Standard is not admitted yet; curate and validate its scientific panel first')
        raise ValueError('Unknown preset: ' + str(preset))
    group_rows, reference_rows, case_rows, registry = catalogues(project)
    selected_groups, selected_cases = tokens(groups, 'group'), tokens(cases, 'case')
    for requested, known, label in ((selected_groups, group_rows, 'group'), (selected_cases, case_rows, 'case')):
        unknown = set(requested) - set(known)
        if unknown:
            raise ValueError('Unknown ' + label + ' selection: ' + ', '.join(sorted(unknown)))
    unavailable = [g for g in selected_groups if group_rows[g].get('quick_status') != 'implemented']
    if unavailable:
        raise ValueError('Groups are not implemented in Quick: ' + ', '.join(unavailable))
    selected = [row for row in case_rows.values()
                if (not selected_groups or row['group'] in selected_groups)
                and (not selected_cases or row['id'] in selected_cases)]
    if selected_cases and set(selected_cases) != {row['id'] for row in selected}:
        raise ValueError('Selected cases are excluded by the selected groups')
    if not selected:
        raise ValueError('No admitted cases match the selection')
    requested_assemblers = tokens(assemblers, 'assembler') or sorted(registry['aliases'] or registry['assemblers'])
    definitions = [resolve_assembler(registry, value) for value in requested_assemblers]
    assembler_ids = [row['id'] for row in definitions]
    if len(set(assembler_ids)) != len(assembler_ids):
        raise ValueError('Assembler selections resolve to the same immutable version ID')
    if any(row.get('status') != 'admitted' for row in definitions):
        raise ValueError('Selected assembler version is not admitted')
    source_names = {'assets/quick.json', 'assets/groups.json', 'assets/references.json', 'assets/assemblers.json',
                    'environments/pixi.toml', 'environments/pixi.lock'}
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
    plan = {'schema_version': 1, 'preset': preset, 'purpose': 'workflow_check', 'headline_eligible': False,
            'selection': {'groups': selected_groups, 'cases': selected_cases, 'assemblers': assembler_ids},
            'cases': selected, 'assemblers': assembler_ids,
            'assembler_definitions': {row['id']: row for row in definitions},
            'reference_ids': reference_ids,
            'references': {key: reference_rows[key] for key in reference_ids},
            'slots': [{'case_id': case['id'], 'assembler': assembler} for case in selected for assembler in assembler_ids],
            'resource_policy': RESOURCE_POLICY,
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
    rebuilt = build_plan(project, plan.get('preset'), selection.get('groups'), selection.get('cases'), selection.get('assemblers'))
    if rebuilt != plan:
        raise ValueError('Frozen plan differs from current admitted sources or selections')
    return plan
