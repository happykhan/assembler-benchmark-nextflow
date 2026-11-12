"""Render S7 backend measurements without running comparisons."""
import csv
import html
import json
from pathlib import Path
LABELS = {'flye': 'Flye (default)', 'flye-meta': 'Flye (--meta)', 'raven': 'Raven', 'plassembler': 'Plassembler long'}

def render(summary, output, public=False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if public and (output / 'summary.json').exists():
        (output / 'summary.json').unlink()
    if not public:
        (output / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    with (output / 'runs.tsv').open('w', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerow(['tool', 'order', 'repeat', 'execution_status', 'version', 'end_sensitive_sha256', 'circular_representation_sha256', 'contig_count', 'total_length_bp', 'reference_recovery_secondary'])
        for tool in summary['tools']:
            for row in tool['runs']:
                s = row['signature']
                execution_status = 'completed' if row['status'] in ('pass', 'fail') else row['status']
                writer.writerow([row['tool'], row['order_id'], row['repeat'], execution_status, row.get('version'), s.get('end_sensitive_sha256'), s.get('circular_representation_sha256'), s.get('contig_count'), s.get('total_length_bp'), row['secondary_reference_status']])
    with (output / 'orders.tsv').open('w', newline='') as stream:
        fields = ['id', 'shuffle_seed', 'record_count', 'record_multiset_sha256', 'record_order_sha256', 'reads_sha256', 'permutation_sha256']
        writer = csv.DictWriter(stream, fields, delimiter='\t', extrasaction='ignore')
        writer.writeheader()
        writer.writerows(summary['input_admission']['orders'])
    e = lambda value: html.escape(str(value))
    body = '<h1>S7 · Read-order sensitivity</h1><p>Does changing only the order of identical reads change the output?</p><p>Four orders × three repeats × four configurations: 48 executions.</p><p><a href="summary.json">Backend JSON</a> · <a href="runs.tsv">Run table</a> · <a href="orders.tsv">Input evidence</a></p>'
    if public:
        body = body.replace('<a href="summary.json">Backend JSON</a> · ', '')
        body = '<p><a href="/scenarios">Scenarios</a></p>' + body
    body += '<h2>Summary</h2><div class="scroll"><table><tr><th>Assembler</th><th>Ends retained</th><th>Circular representation</th></tr>'
    for tool in summary['tools']:
        circle_verdict = tool['circular_representation']['verdict']
        if tool['end_sensitive']['complete'] and (not tool['circular_representation']['complete']):
            circle_verdict = 'Unavailable — circularity is not recorded for every contig'
        body += f"""<tr><th><a href="#{e(tool['tool'])}">{e(LABELS[tool['tool']])}</a></th><td>{e(tool['end_sensitive']['verdict'])}</td><td>{e(circle_verdict)}</td></tr>"""
    body += '</table></div><p>Reference recovery is supporting context and never determines S7 agreement. Identical wrong outputs can still be repeatable.</p>'
    for tool in summary['tools']:
        rows = tool['runs']
        body += f'''<section id="{e(tool['tool'])}"><h2>{e(LABELS[tool['tool']])}</h2><p>Configuration: {e(LABELS[tool['tool']])} · {tool['threads']} threads</p><p>Pairwise output agreement: blue = identical, orange = different, grey = unavailable.</p><div class="scroll"><table class="matrix"><tr><th>Run</th>'''
        body += ''.join((f"<th>{e(r['order_id'])}<br>r{r['repeat']}</th>" for r in rows)) + '</tr>'
        for left in rows:
            body += f"<tr><th>{e(left['order_id'])} · r{left['repeat']}</th>"
            for right in rows:
                a = left['signature'].get('end_sensitive_sha256')
                b = right['signature'].get('end_sensitive_sha256')
                state = 'unavailable' if not a or not b else 'same' if a == b else 'different'
                body += f'''<td class="{state}">{ {'same': '=', 'different': '≠', 'unavailable': '—'}[state]}</td>'''
            body += '</tr>'
        body += '</table></div><h3>Runs and commands</h3>'
        for row in rows:
            s = row['signature']
            status = 'Completed' if row['status'] in ('pass', 'fail') else 'Fail — did not complete' if row['status'] in ('error', 'timeout') else row['status'].title()
            body += f"<details><summary>{e(row['order_id'])} · repeat {row['repeat']} · {e(status)}</summary>"
            if s:
                body += f"<p>{s['contig_count']} contigs · {s['total_length_bp']:,} bp · {e(s['scope'])}</p>"
            if s.get('circularity_source_evidence'):
                body += '<p>Retained chromosome circularity: saved initial Flye label, associated by exact complete sequence identity. No reference was used.</p>'
            body += '<p>Version: ' + e(row.get('version') or 'not recorded') + '</p>'
            if row.get('error') or row.get('comparison_error'):
                body += '<p>' + e(row.get('error') or row['comparison_error']) + '</p>'
            body += '<pre>' + e(' '.join(row.get('command') or [])) + '</pre><p>Reference recovery (secondary): ' + e(row['secondary_reference_status']) + '</p></details>'
        body += '</section>'
    body += '<h2>Methods</h2><p>Each permutation is frozen once and shared unchanged between repeats. Input checks preserve the complete read-record multiset, including duplicate multiplicities and qualities. Sequence comparisons ignore names, output order and strand while retaining duplicate copies and sequence changes. Ends are retained in the primary comparison. The independent circular view allows rotation only for tool-reported circles; unknown topology leaves that view unassessed. Plassembler comparisons include final plasmids and its verified retained chromosome. Neither signature uses the reference.</p><p>Variation within a fixed read order prevents attribution of between-order differences specifically to read order. Missing executions leave the comparison incomplete.</p>'
    style = 'body{font:17px/1.6 system-ui;background:#191d22;color:#e9ebef;max-width:1200px;margin:auto;padding:24px}a{color:#a8c8f5}h1,h2,h3{line-height:1.2}section{margin-top:48px}table{border-collapse:collapse;width:100%}th,td{padding:12px;border:1px solid #4a505b;text-align:left}th{background:#252a32}.scroll{overflow:auto;margin:24px 0}.matrix{font-size:13px}.matrix td{text-align:center;min-width:36px}.same{background:#17496a}.different{background:#775126}.unavailable{background:#3a3f47}details{border-top:1px solid #4a505b;padding:12px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}@media(max-width:600px){body{padding:16px}h1{font-size:30px}}'
    (output / 'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>S7 · Read-order sensitivity · Ploptimizer</title><style>' + style + '</style><main>' + body + '</main></html>')
    return output
