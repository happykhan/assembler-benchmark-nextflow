"""Selectable diagnostic scientific designs; no controller or scheduler side effects."""
import copy
from .common import ROOT, fingerprint, load
from .cases import plan
from .determinism import assembly_tasks, repeat_settings
from .read_order import build_cases

PROFILES = {'S1':'baseline-large', 'S2':'coverage-large', 'S3':'repeatability-large',
            'S4':'small-plasmids', 'S5':'linear-plasmids', 'S6':'noisy-large', 'S7':'read-order'}


def profile_config(profile):
    if isinstance(profile, dict):
        return copy.deepcopy(profile)
    name = PROFILES.get(profile, profile)
    if not isinstance(name, str) or '/' in name or '\\' in name or name.startswith('.'):
        raise ValueError('Unknown diagnostic profile')
    return load(ROOT / 'profiles' / (name + '.json'))


def build_plan(profile, case_ids=None, tools=None):
    """Keep historical case fingerprints; execution options remain outside them."""
    config = profile_config(profile)
    if tools is not None:
        if not tools or len(set(tools)) != len(tools) or set(tools) - set(config['tools']):
            raise ValueError('Tools must be a unique subset of the profile')
        config['tools'] = list(tools)
        if config.get('determinism', {}).get('modes'):
            config['determinism']['modes'] = {t:config['determinism']['modes'][t] for t in tools}
    if config.get('read_order'):
        source = next(c for c in plan(profile_config('baseline-large'))
                      if c['id'] == config['read_order']['source']['case_id'])
        cases = build_cases(source, config)
        tasks = [{'scenario':c['id'], 'tool':t, 'repeat':c['read_order']['repeat'],
                  'order_id':c['read_order']['order_id']} for c in cases for t in config['tools']]
    else:
        cases = plan(config)
        panel = repeat_settings(config)
        if panel:
            if set(panel['scenarios']) - {c['id'] for c in cases}:
                raise ValueError('Repeat panel uses unknown cases')
            cases = [c for c in cases if c['id'] in panel['scenarios']]
        tasks = assembly_tasks(config, cases)
    if case_ids is not None:
        if not case_ids or len(set(case_ids)) != len(case_ids) or set(case_ids) - {c['id'] for c in cases}:
            raise ValueError('Select unique existing case identifiers')
        cases = [c for c in cases if c['id'] in case_ids]
        tasks = [t for t in tasks if t['scenario'] in case_ids]
    by_id = {c['id']:c for c in cases}
    executions = []
    for task in tasks:
        case = by_id[task['scenario']]
        category = 'S3' if config.get('determinism') else case['category']
        executions.append({**task, 'case_id':case['id'], 'input_id':case['id'],
            'category':category, 'threads':task.get('threads',config['threads']),
            'mode':task.get('mode','default'), 'repeat':task.get('repeat',1),
            'run_id':task.get('run_id','default'), 'assessor_id':'exact-dedicated-molecule-v1',
            'supplementary_assessor_id':config.get('assessment_mode'),
            'comparison_id':'reference-independent-contig-multiset-v1' if category == 'S7' else
                            'truth-anchored-repeatability-v1' if category == 'S3' else None,
            'deferred':category == 'S6',
            'options':{'flye_meta':task['tool'] == 'flye-meta',
                       'flye_input_mode':config.get('flye_input_mode','nano-hq'),
                       'plassembler_raw_flag':config.get('plassembler_raw_flag',False),
                       'deterministic':task.get('mode') == 'deterministic',
                       'plassembler_no_chromosome':config.get('plassembler_no_chromosome',False),
                       'plassembler_chromosome_threshold':config.get('plassembler_chromosome_threshold',1000000)},
            'input_recipe':{'model':case['simulation']['model'], 'case_fingerprint':case['fingerprint'],
                'source':config.get('read_order',{}).get('source'),
                'order':next((o for o in config.get('read_order',{}).get('orders',[])
                              if o['id'] == task.get('order_id')),None)}})
    return {'schema_version':1, 'config':config, 'config_fingerprint':fingerprint(config),
            'cases':cases, 'executions':executions, 'execution_count':len(executions),
            'deferred_error_runs':sum(t['deferred'] for t in executions)}


def catalogue():
    """Expose selectable scenarios and historical variants without doing work."""
    profiles=[]
    for path in sorted((ROOT/'profiles').glob('*.json')):
        planned=build_plan(path.stem)
        profiles.append({'id':path.stem,'profile_id':planned['config'].get('profile_id','read-order-v1'),
            'categories':sorted({t['category'] for t in planned['executions']}),
            'case_count':len(planned['cases']),'legacy_execution_count':len(planned['executions']),
            'deferred':bool(planned['deferred_error_runs']),
            'cases':[{'id':c['id'],'category':c['category'],'title':c['title'],
                      'fingerprint':c['fingerprint'],
                      'reference_accessions':[r['refseq_accession'] for r in c['replicons']]}
                     for c in planned['cases']]})
    return {'schema_version':1,'groups':[{'id':group,'default_profile':name,
        'deferred':group=='S6'} for group,name in PROFILES.items()], 'profiles':profiles}
