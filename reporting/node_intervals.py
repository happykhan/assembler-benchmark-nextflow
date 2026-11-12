"""Validate and present recorded graph-node intervals; never run sequence analyses."""
import copy
import math
import re
HASH = re.compile('[0-9a-f]{64}\\Z')

def _interval(value, length):
    if not isinstance(value, list) or len(value) != 2 or (not all((type(v) is int for v in value))) or (not 0 <= value[0] < value[1] <= length):
        raise ValueError('Invalid recorded interval')

def build_node_intervals(evidence, nodes, references, source_hashes):
    """Partition saved interval supports, retaining original alignment rows.

    Overlap between different references or any explicitly ambiguous support is
    grey. Gaps have no recorded support; they are never inferred to be absent.
    An upstream explicit supported assignment is required for single-origin colour.
    """
    if not evidence:
        return {}
    if evidence.get('schema_version') != 1 or evidence.get('evidence_type') != 'graph_node_to_reference' or evidence.get('coordinate_system') != '0-based half-open':
        raise ValueError('Unsupported graph-node interval evidence')
    hashes = evidence.get('input_hashes') or {}
    for key in ('assembly_sha256', 'truth_sha256', 'gfa_sha256'):
        if not HASH.fullmatch(str(source_hashes.get(key, ''))) or hashes.get(key) != source_hashes[key]:
            raise ValueError('Graph-node interval evidence source hashes differ')
    source = evidence.get('source') or {}
    if not isinstance(source.get('name'), str) or not source['name'] or (not HASH.fullmatch(str(source.get('sha256', '')))):
        raise ValueError('Recorded interval source requires a name and SHA-256')
    lengths = {n['id']: n.get('length_bp') for n in nodes}
    refs = {r['id']: r.get('length_bp') for r in references}
    grouped, seen = ({}, set())
    rows = evidence.get('alignments')
    if not isinstance(rows, list):
        raise ValueError('Recorded alignments must be a list')
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or (not row['id']) or (row['id'] in seen):
            raise ValueError('Recorded alignment IDs must be unique')
        seen.add(row['id'])
        node, ref = (row.get('node_id'), row.get('reference_id'))
        if type(lengths.get(node)) is not int or type(refs.get(ref)) is not int:
            raise ValueError('Recorded alignment needs a known node and reference length')
        _interval(row.get('node_interval'), lengths[node])
        _interval(row.get('reference_interval'), refs[ref])
        if row.get('strand') not in ('+', '-') or row.get('assignment_status') not in ('supported', 'ambiguous'):
            raise ValueError('Recorded alignment needs explicit strand and assignment status')
        quality = row.get('match_quality')
        if not isinstance(quality, dict) or not quality:
            raise ValueError('Recorded alignment needs matching quality evidence')
        for key, value in quality.items():
            if not isinstance(key, str) or type(value) not in (int, float) or (not math.isfinite(value)) or (value < 0):
                raise ValueError('Matching quality values must be finite nonnegative numbers')
            if key == 'identity_fraction' and value > 1:
                raise ValueError('Identity fraction exceeds one')
        grouped.setdefault(node, []).append(copy.deepcopy(row))
    result = {}
    for node, alignments in grouped.items():
        length = lengths[node]
        bounds = sorted({0, length} | {v for row in alignments for v in row['node_interval']})
        intervals = []
        for start, end in zip(bounds, bounds[1:]):
            active = [r for r in alignments if r['node_interval'][0] <= start and end <= r['node_interval'][1]]
            ids = sorted({r['reference_id'] for r in active})
            status = 'unresolved' if not active else 'supported' if len(ids) == 1 and all((r['assignment_status'] == 'supported' for r in active)) else 'ambiguous'
            intervals.append({'node_interval': [start, end], 'status': status, 'reference_id': ids[0] if status == 'supported' else None, 'candidate_reference_ids': ids, 'alignment_ids': [r['id'] for r in active]})
        result[node] = {'length_bp': length, 'coordinate_system': '0-based half-open', 'intervals': intervals, 'alignments': alignments, 'source': copy.deepcopy(source), 'input_hashes': copy.deepcopy(hashes)}
    return result
