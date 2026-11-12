"""Read scalar counts from saved PAF metadata; never process sequence letters."""
import re

def recorded_edit_fields(tags, qspan, rspan, matches, block):
    """Allow only NM counts and a single gap-free M run; ignore all other tags."""
    nm = [tag[5:] for tag in tags if tag.startswith(b'NM:i:')]
    cigar = [tag[5:] for tag in tags if tag.startswith(b'cg:Z:')]
    fields = {}
    if len(nm) == 1 and re.fullmatch(b'[0-9]{1,16}', nm[0]):
        value = int(nm[0])
        if value <= block:
            fields['edit_distance'] = value
    if len(cigar) == 1 and re.fullmatch(b'[1-9][0-9]{0,15}M', cigar[0]):
        bases = int(cigar[0][:-1])
        if bases == qspan == rspan == block:
            fields['gap_free_aligned_bp'] = bases
            if fields.get('edit_distance') == block - matches:
                fields['recorded_mismatches'] = fields['edit_distance']
    return fields

def _complete_partition(rows, interval, length):
    cursor = 0
    for start, end in sorted((row[interval] for row in rows)):
        if start != cursor or end <= start:
            return False
        cursor = end
    return cursor == length

def mismatch_summary(record, plot):
    """Summarise only complete, disjoint, single-pair, gap-free saved alignments."""
    if not plot or plot.get('status') != 'available' or plot.get('source_kind') != 'recorded_paf':
        return None
    hashes = plot.get('input_hashes') or {}
    if any((not record.get(k) or hashes.get(k) != record[k] for k in ('assembly_sha256', 'truth_sha256'))):
        return None
    if not hashes.get('paf_sha256') or hashes['paf_sha256'] != (record.get('diagnostics') or {}).get('paf_sha256'):
        return None
    rows = plot.get('alignments') or []
    if not rows or any((type(r.get('recorded_mismatches')) is not int for r in rows)):
        return None
    if len({(r['query_id'], r['reference_id'], r['query_length'], r['reference_length'], r['strand']) for r in rows}) != 1:
        return None
    from .result_model import assessed_molecules
    failed = [m for m in assessed_molecules(record) if m.get('status') == 'fail']
    if len(failed) != 1:
        return None
    molecule = failed[0]
    if molecule.get('accession') != rows[0]['reference_id'] or molecule.get('exact_contigs') or molecule.get('extra_full_copy_contigs'):
        return None
    length = rows[0]['reference_length']
    if not molecule or molecule.get('length_bp') != length or rows[0]['query_length'] != length:
        return None
    if not all((_complete_partition(rows, key, length) for key in ('query_interval', 'reference_interval'))):
        return None
    count = sum((r['recorded_mismatches'] for r in rows))
    if count <= 0:
        return None
    source = plot['source']
    facts = [{'label': 'Base mismatches', 'value': count, 'kind': 'count', 'source': source + ' · NM counts and gap-free CIGAR metadata'}, {'label': 'Reference length', 'value': length, 'kind': 'bp', 'source': source + ' · reference_length'}, {'label': 'Final output length', 'value': length, 'kind': 'bp', 'source': source + ' · query_length'}, {'label': 'Insertions / deletions', 'value': 'None in the saved gap-free alignments', 'kind': 'text', 'source': source + ' · gap-free CIGAR metadata'}]
    initial = (record.get('initial_flye_evaluation') or {}).get('replicons', [])
    if any((m.get('accession') == molecule['accession'] and m.get('status') == 'pass' and m.get('exact_contigs') for m in initial)):
        facts.append({'label': 'Initial Flye stage', 'value': 'Exact match recorded', 'kind': 'text', 'source': 'initial_flye_evaluation.replicons'})
    return {'schema_version': 1, 'evidence_kind': 'saved_alignment_counts', 'observation_confidence': 'confirmed', 'summary': f'Full-length contig with {count:,} base mismatch' + ('es' if count != 1 else '') + ' reported in the saved alignment.', 'location_status': 'not_recorded', 'base_changes_status': 'not_recorded', 'facts': facts, 'source': source, 'source_sha256': hashes['paf_sha256'], 'mechanism_confidence': 'unresolved', 'scope': 'Recorded counts across complete non-overlapping query/reference spans; no per-base positions or sequence changes extracted.'}
