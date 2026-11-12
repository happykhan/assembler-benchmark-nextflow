"""Conservative, separately versioned tolerant endpoint for two small plasmids."""

import importlib
import importlib.metadata
import math
import re

from .common import fasta, fingerprint, reverse_complement

ENDPOINT_VERSION = 'small-plasmid-tolerant-v1'
SUPPORTED_ACCESSIONS = {'NC_017662.1', 'NC_009653.1'}
DEFAULT_POLICY = {
    'minimum_reference_coverage': 0.99,
    'minimum_alignment_identity': 0.995,
    'minimum_length_ratio': 0.98,
    'maximum_length_ratio': 1.02,
    'second_copy_recovery_threshold': 0.95,
    'maximum_reference_length': 10000,
    'maximum_contig_count': 256,
    'maximum_assembly_bases': 20000000,
}
LIMITATIONS = ('Sequence-only endpoint for pRK2/pKPN7; strict scores are unchanged. '
               'No physical topology or circularity claim. Repeats, possible embedded copies and '
               'unresolved structural assignments are unscored. Copy exclusion is conservative '
               'at the stated identity threshold, not an exhaustive low-identity homology search.')


def _policy(policy):
    settings = {**DEFAULT_POLICY, **(policy or {})}
    if set(settings) != set(DEFAULT_POLICY):
        raise ValueError('Unknown tolerant policy key')
    for key in ('minimum_reference_coverage', 'minimum_alignment_identity', 'second_copy_recovery_threshold'):
        if not isinstance(settings[key], (int, float)) or not math.isfinite(settings[key]) or not 0 < settings[key] <= 1:
            raise ValueError('Invalid tolerant coverage/identity fraction')
    if not 0 < settings['minimum_length_ratio'] <= 1 <= settings['maximum_length_ratio'] <= 2:
        raise ValueError('Invalid dedicated-contig length interval')
    if settings['second_copy_recovery_threshold'] > settings['minimum_reference_coverage']:
        raise ValueError('Copy detection cannot require greater coverage than recovery')
    for key in ('maximum_reference_length', 'maximum_contig_count', 'maximum_assembly_bases'):
        if type(settings[key]) is not int or settings[key] < 1:
            raise ValueError('Invalid tolerant work limit')
    for key in ('maximum_reference_length', 'maximum_contig_count', 'maximum_assembly_bases'):
        if settings[key] > DEFAULT_POLICY[key]:
            raise ValueError('This endpoint release cannot increase its hard work limits')
    return settings


def _metrics(cigar, query_length, target_length, reference_length, edit_distance):
    operations = re.findall(r'([1-9][0-9]*)([=XID])', cigar or '')
    if not operations or ''.join(n + op for n, op in operations) != cigar:
        raise ValueError('Invalid edlib extended CIGAR')
    counts = {op: sum(int(n) for n, item in operations if item == op) for op in '=XID'}
    if counts['='] + counts['X'] + counts['I'] != query_length or counts['='] + counts['X'] + counts['D'] != target_length:
        raise ValueError('Edlib CIGAR consumption disagrees with alignment window')
    if counts['X'] + counts['I'] + counts['D'] != edit_distance:
        raise ValueError('Edlib CIGAR disagrees with edit distance')
    # Every optimal path at this span has identity >=1-d/max(Q,T). The largest
    # possible number of target deletions is floor((d-(Q-T))/2), irrespective of
    # how equivalent gap placements are represented in repetitive sequence.
    maximum_deletions = max(0, (edit_distance - (query_length - target_length)) // 2)
    return {'reference_coverage': (counts['='] + counts['X']) / reference_length,
            'alignment_identity': counts['='] / sum(counts.values()),
            'reference_coverage_lower_bound': max(0, target_length - maximum_deletions) / reference_length,
            'alignment_identity_lower_bound': 1 - edit_distance / max(query_length, target_length),
            'matches': counts['='], 'substitutions': counts['X'], 'insertions': counts['I'], 'deletions': counts['D'],
            'aligned_reference_bp': counts['='] + counts['X'], 'alignment_columns': sum(counts.values())}


def _fit(sequence, reference, edlib, settings, minimum_coverage):
    """Fit an entire bounded contig, preserving all query ends and one circle."""
    length = len(reference)
    k = math.floor((1 - settings['minimum_alignment_identity']) * length / settings['minimum_alignment_identity'] + 1e-9)
    doubled = reference + reference
    results = []
    for strand, oriented in (('+', sequence), ('-', reverse_complement(sequence))):
        found = edlib.align(oriented, doubled, mode='HW', task='locations', k=k)
        if found['editDistance'] >= 0:
            results.append((found['editDistance'], strand, oriented, found['locations']))
    if not results:
        return {'status': 'none', 'reason': 'No whole-contig circular alignment within identity edit bound'}
    best = min(item[0] for item in results)
    placements, seen = [], set()
    for distance, strand, oriented, locations in results:
        if distance != best:
            continue
        if len(locations) > 128:
            return {'status': 'ambiguous', 'reason': 'Too many equally optimal circular placements'}
        for start, end in locations:
            span = end - start + 1
            key = (strand, start % length, span)
            if key in seen:
                continue
            seen.add(key)
            if span > length or span <= 0:
                return {'status': 'ambiguous', 'reason': 'Best path traverses more than one circumference; terminal overlap or structural ambiguity'}
            target = doubled[start:end + 1]
            path = edlib.align(oriented, target, mode='NW', task='path', k=k)
            if path['editDistance'] != distance:
                raise ValueError('Edlib infix location and bounded global path disagree')
            metrics = _metrics(path['cigar'], len(oriented), span, length, distance)
            placements.append({'strand': strand, 'reference_start_0based': start % length,
                               'reference_span_bp': span, 'edit_distance': distance, 'cigar': path['cigar'], **metrics})
    if not placements:
        return {'status': 'ambiguous', 'reason': 'No usable optimal placement'}
    measured = all(row['reference_coverage'] + 1e-12 >= minimum_coverage and row['alignment_identity'] + 1e-12 >= settings['minimum_alignment_identity'] for row in placements)
    certified = all(row['reference_coverage_lower_bound'] + 1e-12 >= minimum_coverage and row['alignment_identity_lower_bound'] + 1e-12 >= settings['minimum_alignment_identity'] for row in placements)
    return {'status': 'match' if measured and certified else 'ambiguous' if measured else 'none',
            'reason': 'Whole-contig collinear alignment' if measured and certified else 'Alignment below thresholds or equivalent-path bounds unresolved',
            'length_ratio': len(sequence) / length, 'placements': placements,
            'reference_coverage': min(row['reference_coverage'] for row in placements),
            'alignment_identity': min(row['alignment_identity'] for row in placements),
            'reference_coverage_lower_bound': min(row['reference_coverage_lower_bound'] for row in placements),
            'alignment_identity_lower_bound': min(row['alignment_identity_lower_bound'] for row in placements)}


def _anchor_screen(reference, settings):
    length = len(reference)
    count = min(64, length // 32)
    if count < 8:
        return None
    anchors = [reference[(index * length) // count:(index * length) // count + 32] for index in range(count)]
    if len(set(anchors)) != len(anchors) or any(reverse_complement(seed) in anchors[:index] for index, seed in enumerate(anchors)):
        return None
    errors = math.floor((1 - settings['minimum_alignment_identity']) * length / settings['minimum_alignment_identity'] + 1e-9)
    # A collinear >=95% near-copy loses at most this many spaced anchors to
    # terminal clipping and edits. Use a lower guard, returning unscored rather
    # than claiming absence when a sizeable ambiguous anchor set survives.
    guaranteed = count - math.ceil((1 - settings['second_copy_recovery_threshold']) * count) - 2 - errors
    if guaranteed < 2:
        return None
    return {'anchors': anchors, 'possible_copy_guard': max(1, guaranteed // 2),
            'anchor_length_bp': 32, 'anchor_count': count,
            'scope': 'Conservative screen for contiguous collinear near-copies at the stated identity; positive screens need assignment, never become passes.'}


def _row(replicon, reference, contigs, edlib, settings):
    row = {'accession': replicon['refseq_accession'], 'name': replicon['replicon_name'],
           'length_bp': len(reference), 'status': 'unscored', 'topology_status': 'not_assessed',
           'dedicated_candidates': [], 'second_copy_evidence': [], 'ambiguous_evidence': []}
    if replicon['refseq_accession'] not in SUPPORTED_ACCESSIONS or replicon['topology'] != 'circular':
        return {**row, 'reason': 'Unsupported plasmid accession or topology in this endpoint release'}
    if len(reference) != replicon['length_bp'] or len(reference) > settings['maximum_reference_length']:
        return {**row, 'reason': 'Reference length mismatch or supported size exceeded'}
    screen = _anchor_screen(reference, settings)
    if screen is None:
        return {**row, 'reason': 'Repetitive reference or copy-exclusion bounds unsupported'}
    row['copy_screen'] = {key: value for key, value in screen.items() if key != 'anchors'}
    fits = {}
    for name, sequence in contigs.items():
        ratio = len(sequence) / len(reference)
        if settings['minimum_length_ratio'] - 1e-12 <= ratio <= settings['maximum_length_ratio'] + 1e-12:
            fitted = _fit(sequence, reference, edlib, settings, settings['minimum_reference_coverage'])
            fits[name] = fitted
            if fitted['status'] == 'match':
                row['dedicated_candidates'].append({'contig': name, **fitted})
            elif fitted['status'] == 'ambiguous':
                row['ambiguous_evidence'].append({'contig': name, **fitted})
    if len(row['dedicated_candidates']) > 1:
        return {**row, 'status': 'fail', 'reason': 'Multiple near-complete dedicated copies'}
    if not row['dedicated_candidates']:
        return {**row, 'status': 'unscored' if row['ambiguous_evidence'] else 'fail',
                'reason': 'No certified dedicated contig; structural ambiguity remains' if row['ambiguous_evidence'] else 'No dedicated whole-contig recovery meets thresholds'}
    selected = row['dedicated_candidates'][0]['contig']
    for name, sequence in contigs.items():
        if name == selected:
            continue
        ratio = len(sequence) / len(reference)
        if settings['second_copy_recovery_threshold'] - 1e-12 <= ratio <= settings['maximum_length_ratio'] + 1e-12:
            fitted = _fit(sequence, reference, edlib, settings, settings['second_copy_recovery_threshold'])
            if fitted['status'] == 'match':
                row['second_copy_evidence'].append({'contig': name, **fitted})
                continue
        hits = sum(seed in sequence or reverse_complement(seed) in sequence for seed in screen['anchors'])
        if hits >= screen['possible_copy_guard']:
            row['ambiguous_evidence'].append({'contig': name, 'matching_reference_anchors': hits,
                                               'reason': 'Possible embedded copy, join, fragment or shared repeat requires structural assignment'})
    if row['second_copy_evidence']:
        return {**row, 'status': 'fail', 'reason': 'Another contig contains a near-complete copy at the copy thresholds'}
    if row['ambiguous_evidence']:
        return {**row, 'status': 'unscored', 'reason': 'Copy exclusion or structural assignment unresolved'}
    candidate = row['dedicated_candidates'][0]
    return {**row, 'status': 'pass', 'reason': 'One certified collinear dedicated contig; no competing copy screen triggered',
            **{key: candidate[key] for key in ('reference_coverage', 'alignment_identity', 'length_ratio', 'reference_coverage_lower_bound', 'alignment_identity_lower_bound')}}


def evaluate_tolerant(case, truth_path, assembly_path, plasmid_only=False, policy=None):
    """Return pass/fail/unscored; never alter or import the strict evaluator."""
    settings = _policy(policy)
    base = {'schema_version': 1, 'endpoint_version': ENDPOINT_VERSION, 'policy': settings,
            'policy_fingerprint': fingerprint(settings), 'plasmid_only_output': bool(plasmid_only),
            'status': 'unscored', 'replicons': [], 'limitations': LIMITATIONS}
    try:
        truth, contigs = fasta(truth_path), fasta(assembly_path)
        plasmids = [replicon for replicon in case['replicons'] if replicon['molecule_type'] == 'plasmid']
        if not plasmids:
            return {**base, 'reason': 'Chromosome-only controls are outside this small-plasmid endpoint'}
        if len(contigs) > settings['maximum_contig_count'] or sum(map(len, contigs.values())) > settings['maximum_assembly_bases']:
            return {**base, 'reason': 'Assembly exceeds bounded endpoint work limits'}
        if any(not sequence or set(sequence) - set('ACGT') for sequence in truth.values()) or any(not sequence or set(sequence) - set('ACGT') for sequence in contigs.values()):
            return {**base, 'reason': 'Nonempty unambiguous ACGT sequences required'}
        edlib = importlib.import_module('edlib')
        try:
            base['edlib_version'] = importlib.metadata.version('edlib')
        except importlib.metadata.PackageNotFoundError:
            base['edlib_version'] = 'unknown'
        rows = [_row(replicon, truth[replicon['refseq_accession']], contigs, edlib, settings) for replicon in plasmids]
        assignments = {}
        for row in rows:
            for candidate in row['dedicated_candidates']:
                assignments.setdefault(candidate['contig'], []).append(row)
        for assigned in assignments.values():
            if len(assigned) > 1:
                for row in assigned:
                    row.update(status='unscored', reason='One output contig is compatible with multiple truth plasmids; assignment unresolved')
        status = 'fail' if any(row['status'] == 'fail' for row in rows) else 'unscored' if any(row['status'] == 'unscored' for row in rows) else 'pass'
        return {**base, 'status': status, 'replicons': rows, 'plasmid_passes': sum(row['status'] == 'pass' for row in rows),
                'plasmid_total': len(rows), 'contig_count': len(contigs),
                'reason': 'All supported plasmids pass' if status == 'pass' else 'See per-plasmid evidence and uncertainty'}
    except (ImportError, OSError, ValueError, KeyError) as error:
        return {**base, 'reason': f'Endpoint unavailable or input audit failed: {type(error).__name__}: {error}'}
