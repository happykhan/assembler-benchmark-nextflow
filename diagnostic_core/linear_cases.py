"""Isolated, pinned linear-plasmid controls with explicit terminal-read admission."""
import copy
import re
from .common import ROOT, load, fingerprint


def plan_linear(config):
    if config['linear_panel'].get('scope') == 'native_genome':
        return plan_native_linear(config)
    panel=load(ROOT/'references/linear-panel.json')
    references={r['refseq_accession']:r for r in panel['replicons']}
    selected=config['references'];settings=config['simulation'];profiles=config['linear_panel']['read_profiles']
    if not selected or len(set(selected))!=len(selected) or set(selected)-set(references):raise ValueError('Unknown or duplicate linear references')
    if config.get('scenario_categories')!=['S5'] or settings.get('model')!='exact-linear-anchored-v1':raise ValueError('Linear controls require the S5 anchored-linear profile')
    if not config.get('plassembler_no_chromosome') or config.get('determinism') or config.get('noisy_panel'):raise ValueError('This isolated panel requires explicit no-chromosome mode without repeat/noise panels')
    if not profiles or len({p['id'] for p in profiles})!=len(profiles):raise ValueError('Linear read profiles must be unique')
    result=[]
    for accession in selected:
        reference=references[accession]
        if reference.get('admission_scope')!='isolated_linear_reference_record' or reference['topology']!='linear' or reference['molecule_type']!='plasmid':raise ValueError('Reference is not admitted for isolated linear controls')
        for profile in profiles:
            if not re.fullmatch('[a-z][a-z0-9-]*',profile['id']):raise ValueError('Invalid linear profile identifier')
            simulation=copy.deepcopy(settings);simulation.update({k:v for k,v in profile.items() if k not in ('id','title')})
            case={'id':f's5-{reference["replicon_name"].lower()}-length-{profile["id"]}',
                  'title':f'{reference["replicon_name"]} · linear plasmid only · {profile["title"]}',
                  'category':'S5','assembly_accession':None,'reference_accession':accession,'reference_url':reference['record_url'],
                  'organism':reference['organism'],'truth_type':'isolated_linear_reference_record',
                  'replicons':[copy.deepcopy(reference)],'simulation':simulation,'profile_id':config['profile_id'],
                  'reference_context':'Isolated plasmid control; no native chromosome complement is claimed.',
                  'linear_repeat_evidence':copy.deepcopy(reference['terminal_repeat_evidence'])}
            case['fingerprint']=fingerprint(case);result.append(case)
    return result


def plan_native_linear(config):
    """Complete deposited linear genomes, retaining their native plasmids."""
    panel = load(ROOT / 'references/streptomyces-linear-panel.json')
    assemblies = {a['assembly_accession']: a for a in panel['assemblies']}
    selected = config['references']
    profiles = config['linear_panel']['read_profiles']
    if not selected or len(set(selected)) != len(selected) or set(selected) - set(assemblies):
        raise ValueError('Unknown or duplicate native linear assemblies')
    if config.get('scenario_categories') != ['S5'] or config['simulation'].get('model') != 'exact-linear-anchored-v1':
        raise ValueError('Native linear controls require the S5 anchored-linear model')
    if config.get('plassembler_no_chromosome') or config.get('determinism') or config.get('noisy_panel'):
        raise ValueError('Native linear controls require chromosome context without repeat/noise panels')
    if not profiles or len({p['id'] for p in profiles}) != len(profiles):
        raise ValueError('Linear read profiles must be unique')
    result = []
    for accession in selected:
        assembly = assemblies[accession]
        molecules = assembly['replicons']
        if (assembly['assembly_status'] != 'Complete Genome'
                or sum(m['molecule_type'] == 'chromosome' for m in molecules) != 1
                or any(m['topology'] != 'linear' or m.get('admission_scope') != 'native_linear_genome_record' for m in molecules)):
            raise ValueError('Native linear reference complement is not admitted')
        for profile in profiles:
            if not re.fullmatch('[a-z][a-z0-9-]*', profile['id']):
                raise ValueError('Invalid linear profile identifier')
            simulation = copy.deepcopy(config['simulation'])
            simulation.update({k: v for k, v in profile.items() if k not in ('id', 'title')})
            case = {'id': f's5-{assembly["label"]}-native-length-{profile["id"]}',
                    'title': f'{assembly["organism"]} {assembly["strain"]} · Complete linear genome · {profile["title"]}',
                    'category': 'S5', 'assembly_accession': accession,
                    'organism': assembly['organism'], 'truth_type': 'native_complement',
                    'replicons': copy.deepcopy(molecules), 'simulation': simulation,
                    'profile_id': config['profile_id'],
                    'reference_context': 'All replicons in the pinned complete deposited assembly.'}
            case['fingerprint'] = fingerprint(case)
            result.append(case)
    return result


def validate_terminal_reference(reference, sequence):
    """Recheck admitted literal terminal evidence; not physical-end validation."""
    from .common import reverse_complement
    evidence=reference['terminal_repeat_evidence'];length=len(sequence)
    if evidence.get('method') == 'literal_terminal_inverted_prefix-v1':
        half = length // 2
        observed = next((i for i, (a, b) in enumerate(zip(sequence[:half], reverse_complement(sequence)[:half])) if a != b), half)
        if reference['topology'] != 'linear' or observed != evidence['exact_terminal_inverted_prefix_bp']:
            raise ValueError('Pinned native linear terminal evidence differs from admission')
        return
    window=evidence['literature_length_bp_approx']
    if reference['topology']!='linear' or type(window) is not int or not 0<window<=length//2:
        raise ValueError('Invalid admitted linear terminal window')
    inverted=reverse_complement(sequence)
    exact=next((i for i,(left,right) in enumerate(zip(sequence,inverted)) if left!=right),length)
    mismatches=sum(left!=right for left,right in zip(sequence[:window],inverted[:window]))
    if (exact!=evidence['exact_terminal_prefix_match_bp'] or mismatches!=evidence['literature_window_mismatched_positions']
            or evidence['left_window_0based_half_open']!=[0,window] or evidence['right_window_0based_half_open']!=[length-window,length]):
        raise ValueError('Pinned linear terminal evidence differs from admission')
