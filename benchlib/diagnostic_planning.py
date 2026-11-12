"""Bridge preserved diagnostic designs into native Nextflow run slots."""
from pathlib import Path
import copy
from .adapters import load_registry, resolve_assembler, validate_environment
from .io import digest
from .planning import plan_digest, tokens, STANDARD_RESOURCE_POLICY
from diagnostic_core.planning import PROFILES, build_plan
from diagnostic_core.common import fingerprint

GROUPS = {'plasmids':'S1', 'coverage':'S2', 'reproducibility':'S3', 'read-length':'S4',
          'linear':'S5', 'errors':'S6', 'read-order':'S7'}


def build_diagnostic_plan(project, preset='standard', groups=None, cases=None, assemblers=None):
    project = Path(project).resolve()
    if preset not in ('quick','standard'):
        raise ValueError('Unknown diagnostic preset')
    selected_groups = tokens(groups,'group')
    selected_cases = tokens(cases,'case')
    names = [GROUPS.get(g,g) for g in selected_groups] or ['S1','S2','S3','S4','S5','S7']
    if len(set(names)) != len(names) or set(names)-set(PROFILES):
        raise ValueError('Select unique diagnostic groups S1-S7')
    if 'S6' in names:
        raise ValueError('New S6 error runs are deferred by protocol review; historical results may be imported')
    registry = load_registry(project/'assets/assemblers.json')
    requested = tokens(assemblers,'assembler')
    definitions = [resolve_assembler(registry,a) for a in requested] if requested else [
        resolve_assembler(registry,a) for a in ('flye','raven','plassembler','miniasm','miniasm-plus')
        if a in registry['aliases']]
    if not definitions or len({d['id'] for d in definitions}) != len(definitions):
        raise ValueError('Select unique admitted assembler versions')
    for definition in definitions:
        if definition.get('status') != 'admitted':
            raise ValueError('Diagnostic assembler is not admitted')
        validate_environment(definition, project)
    assembled, refs, slots = [], {}, []
    known = set()
    for group in names:
        scientific = build_plan(group)
        default_tools = {('flye' if t == 'flye-meta' else t) for t in scientific['config']['tools']}
        if group == 'S5':
            default_tools.update(('miniasm', 'miniasm-plus'))
        group_definitions = definitions if requested else [d for d in definitions if d['tool'] in default_tools]
        by_id = {c['id']:c for c in scientific['cases']}
        known.update(by_id)
        tasks = scientific['executions']
        # New workflow adapters use the same frozen inputs and default-mode
        # repeat/order design; adding a version never changes scientific cases.
        extra_tools = sorted({d['tool'] for d in group_definitions} - set(scientific['config']['tools']))
        templates = [t for t in tasks if t['tool']=='raven']
        if not templates:
            templates = [t for t in tasks if t['tool']==scientific['config']['tools'][0] and t['mode']=='default']
        additions = []
        for tool in extra_tools:
            for template in templates:
                task = copy.deepcopy(template)
                task['tool'] = tool
                task['options']['flye_meta'] = False
                task['options']['deterministic'] = False
                additions.append(task)
        tasks = tasks + additions
        if selected_cases:
            tasks = [t for t in tasks if t['case_id'] in selected_cases]
        if preset == 'quick' and tasks:
            first = tasks[0]['case_id']
            tasks = [t for t in tasks if t['case_id'] == first and t['repeat'] == 1 and t['mode'] == 'default']
        for task in tasks:
            matches = [d for d in group_definitions if d['tool'] == task['tool'] or task['tool'] == 'flye-meta' and d['tool'] == 'flye']
            for definition in matches:
                original = by_id[task['case_id']]
                reference_id = 'diagnostic-' + fingerprint(original['replicons'])[:20]
                refs[reference_id] = {'id':reference_id,'status':'admitted','mode':'diagnostic_replicons',
                    'replicons':copy.deepcopy(original['replicons']),
                    'molecule_types':{r['refseq_accession']:r['molecule_type'] for r in original['replicons']}}
                run_id = group.lower()+'--'+original['id']+'--'+task['tool']+'--'+task['run_id']+'--'+definition['id']
                meta = {'id':run_id,'track':'diagnostic','group':group,'category':group,
                    'reference_id':reference_id,'preset':preset,'purpose':'workflow_check' if preset=='quick' else 'diagnostic_benchmark',
                    'headline_eligible':False,'diagnostic_case':copy.deepcopy(original),
                    'legacy_case_id':original['id'],'profile_id':original['profile_id'],
                    'input_id':original['id'],'repeat':task['repeat'],'threads':task['threads'],
                    'mode':task['mode'],'configuration_id':task['tool']+'--'+task['mode'],'assembler_options':task['options'],
                    'assessor_id':task['assessor_id'],'supplementary_assessor_id':task['supplementary_assessor_id'],
                    'comparison_id':task['comparison_id'],'input_recipe':task['input_recipe'],
                    'source_config_fingerprint':scientific['config_fingerprint']}
                assembled.append(meta)
                slots.append({'case_id':run_id,'assembler':definition['id']})
    if selected_cases and set(selected_cases)-known:
        raise ValueError('Unknown diagnostic cases: '+', '.join(sorted(set(selected_cases)-known)))
    if not assembled:
        raise ValueError('No diagnostic execution slots match this selection')
    sources = set()
    for folder in ('assets/diagnostics','diagnostic_core'):
        sources.update(p.relative_to(project).as_posix() for p in (project/folder).rglob('*')
                       if p.is_file() and '__pycache__' not in p.parts)
    sources.add('assets/assemblers.json')
    for definition in definitions:
        manifest = Path(definition['manifest'])
        sources.update((manifest.as_posix(),manifest.with_name('pixi.lock').as_posix()))
    plan = {'schema_version':1,'track':'diagnostic','preset':preset,'purpose':'diagnostic_benchmark',
        'headline_eligible':False,'selection':{'groups':selected_groups,'cases':selected_cases,'assemblers':[d['id'] for d in definitions]},
        'cases':assembled,'assemblers':[d['id'] for d in definitions],
        'assembler_definitions':{d['id']:d for d in definitions},
        'reference_ids':sorted(refs),'references':refs,'slots':slots,'expected_slots':len(slots),
        'resource_policy':copy.deepcopy(STANDARD_RESOURCE_POLICY),
        'source_file_sha256':{name:digest(project/name) for name in sorted(sources)}}
    plan['plan_sha256'] = plan_digest(plan)
    return plan
