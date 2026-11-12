"""Evidence-first views of saved assessments; no sequence analysis or rescoring."""
import html
import math
from .result_model import assessed_molecules, verdict

def e(value):
    return html.escape(str(value), quote=True)

def failure_facts(record):
    from .failure_summary import failure_summary
    summary = (record.get('report_evidence') or {}).get('failure_summary')
    if summary is None:
        summary = failure_summary(record)
    if not summary:
        return ''
    if not summary['facts']:
        return '<p class="failure-location">Difference location: not recorded in the saved evidence.</p>'
    caption = 'Directly checked against the original saved FASTA files.' if summary.get('evidence_kind') == 'direct_saved_sequence_comparison' else 'Recorded in the saved alignment metadata.' if summary.get('evidence_kind') == 'saved_alignment_counts' else 'Confirmed by the saved review.'
    body = '<div class="failure-facts"><h3>Recorded difference</h3><p>' + caption + '</p><dl class="result-facts">'
    for fact in summary['facts']:
        if fact['kind'] == 'bp':
            value = f"{fact['value']:,} bp"
        elif fact['kind'] in ('count', 'text'):
            value = str(fact['value'])
        else:
            spans = [fact['value']] if fact['kind'] == 'interval' else fact['value']
            value = '; '.join((f'{a:,}–{b:,} bp' for a, b in spans))
        body += f"<dt>{e(fact['label'])}</dt><dd>{e(value)}</dd>"
    body += '</dl>'
    if summary.get('events'):
        body += '<h3>Confirmed substitutions</h3><p>Positions are 1-based. Changes are reference → output, on the reference-forward strand.</p><dl class="result-facts">'
        for event in summary['events']:
            body += f"<dt>{e(event['reference_id'])}:{event['reference_position_1based']:,}</dt><dd><strong>{e(event['reference_base'])} → {e(event['output_base_reference_forward'])}</strong> · output {e(event['query_id'])}:{event['query_position_1based']:,}</dd>"
        body += '</dl>'
    elif summary['location_status'] == 'recorded':
        body += '<p class="muted">Coordinates are 0-based; the end is excluded.</p>'
    if summary.get('base_changes_status') == 'not_recorded':
        body += '<p>Mismatch positions and base changes: not recorded.</p>'
    body += '<details><summary>Difference evidence source</summary><p>' + e(summary['source']) + '</p><ul>'
    body += ''.join(('<li>' + e(fact['label']) + ': <code>' + e(fact['source']) + '</code></li>' for fact in summary['facts']))
    body += '</ul>'
    if summary.get('source_sha256'):
        body += '<p>Saved PAF SHA-256</p><code class="checksum">' + e(summary['source_sha256']) + '</code>'
    if summary.get('base_review_source'):
        body += '<p>Direct base review: ' + e(summary['base_review_source']) + '</p><code class="checksum">' + e(summary['base_review_sha256']) + '</code>'
    return body + '</details></div>'

def outcome_section(record):
    heading, explanation = verdict(record)
    body = f'''<section class="result-outcome" data-exact-status="{e(record['status'])}" aria-labelledby="outcome-title"><h2 id="outcome-title">{e(heading)}</h2><p>{e(explanation)}</p>'''
    if record['status'] not in {'pass', 'fail'}:
        return body + '</section>'
    body += failure_facts(record)
    evaluation = record.get('evaluation') or {}
    molecules = evaluation.get('replicons', [])
    relevant = {m.get('accession') for m in assessed_molecules(record)}
    evidence = (record.get('diagnostics') or {}).get('evidence') or {}
    mapped = {m.get('accession'): m for m in evidence.get('replicons', [])}
    displayed = [m for m in molecules if record.get('tool') != 'plassembler' or m.get('molecule_type') == 'plasmid']
    for molecule in sorted(displayed, key=lambda m: m.get('accession') not in relevant):
        accession = molecule.get('accession')
        row = mapped.get(accession, {})
        length = molecule.get('length_bp')
        size = f'{length:,} bp' if isinstance(length, int) else 'Length not recorded'
        context = ' · supporting context' if accession not in relevant else ''
        fraction = row.get('recovered_fraction')
        body += f"""<section class="molecule-outcome"><h3>{e(molecule.get('name', accession or 'Reference molecule'))}<small>{e(size + context)}</small></h3>"""
        exact = molecule.get('exact_contigs', [])
        exact_text = ' · '.join(exact) if exact else 'No exact copy recorded'
        if exact and molecule.get('status') == 'fail':
            exact_text += '. ' + molecule.get('reason', 'The exact-copy count or assignment fails the saved criterion.')
        exact_label = 'Pass' if molecule.get('status') == 'pass' else 'Fail' if molecule.get('status') == 'fail' else 'Unscored'
        body += f'<div class="molecule-evidence"><div><span class="evidence-label">Exact molecule</span><strong>{e(exact_label)}</strong><p>{e(exact_text)}</p></div><div><span class="evidence-label">Aligned reference sequence</span>'
        if isinstance(fraction, (float, int)) and math.isfinite(fraction) and (0 <= fraction <= 1):
            percentage = 100 * fraction
            body += f'<strong>{percentage:.2f}%</strong><div class="coverage-track" role="img" aria-label="{percentage:.2f}% retained reference coverage"><span style="width:{percentage:.6f}%"></span></div>'
            count = row.get('contig_count')
            text = 'No alignment retained by the saved filters.' if fraction == 0 else f'Across {count} contig(s).' if count is not None else 'Retained alignment coverage.'
            body += f'<p>{e(text)}</p>'
        else:
            body += '<strong>Not measured</strong><p>No completed mapping measurement is recorded.</p>'
        body += '</div></div></section>'
    if mapped:
        body += '<p class="evidence-note">Bars show total aligned coverage, not genomic positions. An alignment is not an exact-copy test.</p>'
    if record['status'] == 'fail':
        review = record.get('sequence_review') or {}
        from .failure_summary import review_matches_execution
        if not review_matches_execution(record):
            has_zero = any((mapped.get(m.get('accession'), {}).get('recovered_fraction') == 0 for m in assessed_molecules(record) if m.get('status') == 'fail'))
            body += '<p class="cause-status"><strong>Why did the assembler do this?</strong> Not established by the saved evidence.'
            if has_zero:
                body += ' Zero retained alignment does not establish that the sequence is absent; its location or loss remains unresolved.'
            body += '</p>'
        else:
            body += '<p class="cause-status">The checked mismatch is described above. The assembler’s internal cause remains unresolved.</p>'
    return body + '</section>'
