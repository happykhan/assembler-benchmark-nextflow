"""Fixed-input repeat plans and conservative sequence-repeatability diagnostics."""
import collections
import hashlib
from .common import fasta, fingerprint, load, reverse_complement
from .scoring import equivalent

def repeat_settings(config):
    panel = config.get('determinism')
    if not panel:
        return None
    threads = panel.get('threads', [])
    repeats = panel.get('repeats')
    if not threads or any((type(value) is not int or value < 1 for value in threads)) or len(set(threads)) != len(threads):
        raise ValueError('Determinism threads must be unique positive integers')
    if type(repeats) is not int or repeats < 2:
        raise ValueError('Determinism requires at least two identical-input executions')
    scenarios = panel.get('scenarios', [])
    if not scenarios or len(set(scenarios)) != len(scenarios):
        raise ValueError('Determinism requires unique scenario identifiers')
    modes = panel.get('modes')
    if modes is not None:
        if not isinstance(modes, dict) or set(modes) != set(config['tools']):
            raise ValueError('Determinism modes must list each configured tool exactly once')
        for tool, selected in modes.items():
            allowed = {'default', 'deterministic'} if tool in ('flye', 'flye-meta') else {'default'}
            if not isinstance(selected, list) or not selected or any((not isinstance(mode, str) or mode not in allowed for mode in selected)) or (len(set(selected)) != len(selected)):
                raise ValueError(f'Unsupported or duplicate determinism mode for {tool}')
    return panel

def execution_id(threads, repeat, mode=None):
    if type(threads) is not int or threads < 1 or type(repeat) is not int or (repeat < 1):
        raise ValueError('Execution threads and repeat must be positive integers')
    if mode is not None and mode not in ('default', 'deterministic'):
        raise ValueError('Unknown execution mode')
    prefix = f'mode-{mode}-' if mode is not None else ''
    return prefix + f'threads-{threads}-repeat-{repeat}'

def assembly_tasks(config, scenarios):
    panel = repeat_settings(config)
    if not panel:
        return [{'scenario': case['id'], 'tool': tool} for case in scenarios for tool in config['tools']]
    return [{'scenario': case['id'], 'tool': tool, 'threads': threads, 'repeat': repeat, **({'mode': mode} if mode is not None else {}), 'run_id': execution_id(threads, repeat, mode)} for case in scenarios for tool in config['tools'] for mode in panel.get('modes', {}).get(tool, [None]) for threads in panel['threads'] for repeat in range(1, panel['repeats'] + 1)]

def sequence_signature(case, truth_path, assembly_path):
    """Ignore names/order/strands; rotate only exact known circles.

    Non-exact/unclassified contigs retain their ends. This avoids treating every
    output as circular or hiding terminal-overlap/sequence errors. Signatures
    are anchored to the reference, and compared only within one scenario.
    """
    truth = fasta(truth_path)
    circles = [truth[r['refseq_accession']] for r in case['replicons'] if r['topology'] == 'circular']
    contigs = []
    for sequence in fasta(assembly_path).values():
        canonical = min(sequence, reverse_complement(sequence))
        policy = 'strand-only; ends retained'
        for reference in circles:
            if equivalent(reference, sequence, 'circular'):
                canonical = reference
                policy = 'exact circular truth; rotation and strand ignored'
                break
        contigs.append({'length_bp': len(sequence), 'sha256': hashlib.sha256(canonical.encode()).hexdigest(), 'normalisation': policy})
    contigs.sort(key=lambda item: (item['length_bp'], item['sha256'], item['normalisation']))
    return {'sha256': fingerprint(contigs), 'contigs': contigs, 'policy': 'Ignore names, order and strands; rotation only for exact truth-matched circles. Duplicates retained. Not a topology assessment.'}

def biological_signature(evaluation):
    rows = [{'accession': row['accession'], 'status': row['status'], 'exact_contig_count': len(row['exact_contigs']), 'extra_full_copy_contig_count': len(row['extra_full_copy_contigs']), 'topology_status': row['topology_status']} for row in evaluation['replicons']]
    return fingerprint({'status': evaluation['status'], 'replicons': sorted(rows, key=lambda row: row['accession']), 'contig_count': evaluation['contig_count']})
METRICS = (('byte', 'assembly_sha256'), ('normalised_sequence', 'normalised_assembly_sha256'), ('biological', 'biological_sha256'))
