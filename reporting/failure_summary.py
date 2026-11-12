"""Compact failure facts from existing source-bound reviews; no sequence analysis."""
import copy

def review_matches_execution(record):
    review = record.get('sequence_review') or {}
    return review.get('status') == 'verified' and review.get('strict_status') == record.get('status') and (record.get('status') in {'pass', 'fail'}) and all((review.get(key) == record.get(key) and record.get(key) for key in ('scenario_id', 'tool'))) and all((record.get(key) and (review.get('hashes') or {}).get(key) == record[key] for key in ('assembly_sha256', 'truth_sha256')))

def failure_summary(record, plot=None):
    if record.get('status') != 'fail':
        return None
    review = record.get('sequence_review') or {}
    bound = review_matches_execution(record)
    result = {'schema_version': 1, 'observation_confidence': 'confirmed' if bound else 'unresolved', 'location_status': 'not_recorded', 'facts': [], 'source': None, 'summary': 'The exact endpoint failed; the sequence difference has not been localised in a source-bound review.', 'mechanism_confidence': 'unresolved'}
    if not bound:
        from .recorded_mismatches import mismatch_summary
        return mismatch_summary(record, plot) or result
    result.update(summary=review.get('summary') or 'A saved sequence review is available.', source=review.get('source_document') or 'sequence_review')
    validation = review.get('validation') or {}
    fields = [('excess_bp', 'Recorded excess', 'bp'), ('reference_length', 'Reference length', 'bp'), ('query_length', 'Output length', 'bp'), ('reference_interval_0based_half_open', 'Reference interval', 'interval'), ('reference_deletion_interval_0based_half_open', 'Reference deletion interval', 'interval'), ('query_intervals_0based_half_open', 'Output intervals', 'intervals')]
    for key, label, kind in fields:
        value = validation.get(key)
        if value is None:
            continue
        if kind == 'bp' and (type(value) is not int or value < 0):
            continue
        intervals = [value] if kind == 'interval' else value if kind == 'intervals' else None
        if intervals is not None:
            if not isinstance(intervals, list) or not intervals or any((not isinstance(span, list) or len(span) != 2 or any((type(v) is not int for v in span)) or (not 0 <= span[0] < span[1]) for span in intervals)):
                continue
            result['location_status'] = 'recorded'
        result['facts'].append({'label': label, 'value': copy.deepcopy(value), 'kind': kind, 'source': 'sequence_review.validation.' + key})
    return result
