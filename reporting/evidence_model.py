"""Backend descriptions of saved mapping evidence; no sequence analysis."""
from diagnostic_core.diagnostics import DEFAULT_POLICY

def diagnostic_policy(diagnostic):
    return {**DEFAULT_POLICY, **diagnostic.get('policy', {}), **diagnostic.get('evidence', {}).get('policy', {})}

def alignment_classification(row, policy):
    fraction = row['recovered_fraction']
    if fraction <= 0 or row.get('candidate_flags', {}).get('no_supported_alignment'):
        return ('none', 'No retained alignment')
    if fraction >= 1 - 1e-09:
        return ('full', 'Full aligned recovery')
    if fraction >= policy['complete_fraction']:
        return ('near_full', 'Near-full aligned recovery')
    return ('partial', 'Partial aligned recovery')

def candidate_labels(row):
    flags = row.get('candidate_flags', {})
    return [label for key, label in (('fragmented', 'fragmentation'), ('duplicated', 'duplication'), ('joined', 'join')) if flags.get(key)]

def diagnostic_state(diagnostic):
    if not diagnostic:
        return 'Recovery diagnostics not available'
    status = diagnostic.get('status')
    if status in ('running', 'pending', 'queued'):
        return 'Recovery mapping pending' if status != 'running' else 'Recovery mapping running'
    if status == 'error':
        return 'Mapper diagnostic error'
    if status == 'skipped':
        return 'Recovery mapping skipped'
    return 'Recovery diagnostics not available'

def diagnostic_summary(record, case):
    """A compact mapping explanation, never a replacement for strict pass/fail."""
    if record.get('report_evidence'):
        return record['report_evidence']['summary']
    if record.get('sequence_review'):
        return 'Verified: ' + record['sequence_review']['summary']
    finding = record.get('explanation') or {}
    if finding.get('summary') and finding.get('source') != 'mapping_diagnostics':
        prefix = {'confirmed': 'Observed', 'suspected': 'Suspected', 'unresolved': 'Unresolved'}.get(finding.get('confidence'), 'Unresolved')
        return prefix + ': ' + finding['summary']
    diagnostic = record.get('diagnostics')
    if not diagnostic or diagnostic.get('status') != 'complete':
        if not diagnostic and record['status'] in ('not_run', 'pending', 'running'):
            return 'Awaiting assembly assessment'
        return diagnostic_state(diagnostic)
    plasmids = {row['refseq_accession'] for row in case['replicons'] if row['molecule_type'] == 'plasmid'}
    if not plasmids and record['tool'] == 'plassembler':
        return 'Final plasmid output only; chromosome assessed separately'
    expected = plasmids or {row['refseq_accession'] for row in case['replicons']}
    rows = [row for row in diagnostic['evidence']['replicons'] if row['accession'] in expected]
    failed = {row['accession'] for row in record.get('evaluation', {}).get('replicons', []) if row['status'] == 'fail' and row['accession'] in expected}
    if failed:
        rows = [row for row in rows if row['accession'] in failed]
    if not rows:
        return 'No matching molecule evidence collected'
    labels = list(dict.fromkeys((alignment_classification(row, diagnostic_policy(diagnostic))[1] for row in rows)))
    flags = list(dict.fromkeys((label for row in rows for label in candidate_labels(row))))
    summary = '; '.join(labels)
    if record['status'] == 'fail' and any((alignment_classification(row, diagnostic_policy(diagnostic))[0] in ('full', 'near_full') for row in rows)):
        summary += '; exact recovery failed'
    if any((alignment_classification(row, diagnostic_policy(diagnostic))[0] == 'none' for row in rows)):
        summary += '; absence not established'
    if flags:
        summary += '; candidate ' + ', '.join(flags)
    if finding:
        prefix = {'confirmed': 'Observed', 'suspected': 'Suspected', 'unresolved': 'Unresolved'}.get(finding.get('confidence'), 'Unresolved')
        summary = prefix + ': ' + summary
    return summary

def molecule_explanation(row, policy, strict=None):
    kind, label = alignment_classification(row, policy)
    if kind == 'none':
        molecule = 'plasmid' if row['molecule_type'] == 'plasmid' else 'chromosome'
        text = f'No retained alignment under this mapping policy. This is not evidence of {molecule} absence: filtering or alignment heuristics can hide short, shared or repetitive sequence.'
    else:
        text = f"{label}: {row['aligned_reference_bp']:,}/{row['length_bp']:,} reference bases ({row['recovered_fraction']:.2%}) are covered by retained alignments"
        if row.get('alignment_identity') is not None:
            text += f", with {row['alignment_identity']:.3%} alignment identity"
        text += '.'
        if strict and strict['status'] == 'fail':
            text += ' The exact endpoint still fails; mapped coverage does not establish an exact, unique dedicated molecule.'
        elif strict and strict['status'] == 'pass':
            text += ' The separate strict sequence endpoint passes.'
    labels = candidate_labels(row)
    if labels:
        text += ' Candidate ' + ', '.join(labels) + ' evidence needs review; these flags can overlap and are not confirmed structural errors.'
    return text
