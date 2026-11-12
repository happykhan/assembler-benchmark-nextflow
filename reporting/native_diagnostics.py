"""Present exact-copy and agreement endpoints without the Wick threshold."""
from html import escape
import json


def render_diagnostics(records, expected_slots, run_id):
    rows = []
    for record in records:
        case = record['case']
        diagnostic = record.get('track') == 'diagnostic'
        category = case.get('category', case.get('diagnostic_case', {}).get('category', case.get('group')))
        primary = record.get('agreement', {}).get('status', 'Not assessed across runs') if category in ('S3', 'S7') else record.get('sequence_outcome') or 'Unscored'
        secondary = record.get('secondary_reference_status')
        measurements = []
        for molecule in record.get('replicons', []):
            if diagnostic:
                measurements.append(str(molecule.get('accession')) + ': exact ' + str(molecule.get('status')) + '; exact contigs ' + ', '.join(molecule.get('exact_contigs') or []))
            else:
                measurements.append(str(molecule.get('accession')) + ': longest-alignment fraction ' + str(molecule.get('contiguity')))
        values = [case['id'], case.get('group', category), record['assembler'], record['execution']['status'],
                  record['assessment']['status'], record['assessment'].get('method'), primary,
                  secondary if secondary is not None else 'Not applicable', '; '.join(measurements) or 'No completed sequence measurement']
        rows.append('<tr>' + ''.join('<td>' + escape(str(value)) + '</td>' for value in values) + '</tr>')
    headers = ['Case', 'Group', 'Assembler', 'Execution', 'Assessment', 'Method', 'Primary endpoint', 'Secondary reference verdict', 'Recorded molecule evidence']
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Diagnostic benchmark</title><style>body{font:16px system-ui;margin:1rem;line-height:1.5}.scroll{overflow:auto}th,td{padding:.7rem;text-align:left;border-bottom:1px solid #aaa}</style></head><body><main><h1>Diagnostic scenarios</h1><p>' + escape(str(run_id)) + f' · {len(records)}/{expected_slots} recorded slots</p><p>Diagnostic exact-copy endpoints and supplementary measurements remain distinct from Wick longest-alignment completion. S7 output agreement is assessed across orders and repeats; its secondary reference verdict does not determine agreement. Failed or missing measurements never establish sequence absence.</p><p><a href="results.tsv">Results TSV</a> · <a href="results.json">Complete evidence JSON</a></p><div class="scroll"><table><thead><tr>' + ''.join('<th>' + h + '</th>' for h in headers) + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div></main></body></html>'
