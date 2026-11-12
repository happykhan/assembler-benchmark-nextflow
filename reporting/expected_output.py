"""Draw the declared reference molecules, never an inferred assembly topology."""
import html
import math
from .reference_origins import reference_colour

def expected_molecules(case, record):
    molecules = case.get('replicons', [])
    if record.get('tool') == 'plassembler':
        return [m for m in molecules if m.get('molecule_type') == 'plasmid']
    return list(molecules)

def render_expected_output(case, record):
    e = lambda value: html.escape(str(value), quote=True)
    molecules = expected_molecules(case, record)
    title = 'Expected plasmid output' if record.get('tool') == 'plassembler' else 'Expected final output'
    body = f'<section class="expected-output" aria-labelledby="expected-output-title"><h3 id="expected-output-title">{title}</h3>'
    if not molecules:
        text = 'No plasmids expected in the final output.' if record.get('tool') == 'plassembler' else 'No reference inventory recorded for this case.'
        return body + f'<p>{text}</p></section>'
    chromosomes = sum((m.get('molecule_type') == 'chromosome' for m in molecules))
    plasmids = sum((m.get('molecule_type') == 'plasmid' for m in molecules))
    parts = ([f'{chromosomes} chromosome' + ('s' if chromosomes != 1 else '')] if chromosomes else []) + ([f'{plasmids} plasmid' + ('s' if plasmids != 1 else '')] if plasmids else [])
    body += '<p>' + e(' + '.join(parts) or f'{len(molecules)} reference molecules') + ' · separate molecules</p>'
    columns = min(3, len(molecules))
    width, height = (columns * 150, math.ceil(len(molecules) / columns) * 168)
    maximum = max((m.get('length_bp', 0) for m in molecules), default=0) or 1
    description = '; '.join((f"{m.get('replicon_name', 'Reference molecule')}: {m.get('length_bp', 'unknown size')} bp, {m.get('topology', 'unknown topology')}" for m in molecules))
    body += f'<svg class="expected-molecules" viewBox="0 0 {width} {height}" role="img" aria-label="{e(description)}"><title>Expected reference molecules; schematic sizes, not an observed assembly graph</title>'
    for index, molecule in enumerate(molecules):
        x, y = (75 + index % columns * 150, 60 + index // columns * 168)
        name = molecule.get('replicon_name') or molecule.get('refseq_accession') or 'Reference molecule'
        length = molecule.get('length_bp')
        size = f'{length:,} bp' if isinstance(length, int) else 'Size not recorded'
        radius = 13 + 36 * (max(0, length or 0) / maximum) ** 0.35
        topology = molecule.get('topology', 'unknown')
        kind = 'chromosome' if molecule.get('molecule_type') == 'chromosome' else 'plasmid'
        prepared = record.get('report_evidence')
        if prepared:
            reference = next((r for r in prepared['reference_origins']['references'] if r['id'] == molecule.get('refseq_accession')))
            colour, light = (reference['colour'], reference['light_colour'])
        else:
            colour, light = reference_colour(molecule)
        body += f'<g class="expected-molecule {kind}" style="--reference-colour:{colour};--reference-light:{light}"><title>{e(name)} · {e(size)} · {e(topology)}</title>'
        if topology == 'circular':
            body += f'<circle cx="{x}" cy="{y}" r="{radius:.2f}" />'
        else:
            dash = ' stroke-dasharray="5 4"' if topology != 'linear' else ''
            body += f'<path d="M{x - radius:.2f} {y} H{x + radius:.2f}"{dash} />'
        body += f'''<text x="{x}" y="{y + 70}" text-anchor="middle">{e(name[:19] + '…' if len(name) > 20 else name)}</text><text class="expected-size" x="{x}" y="{y + 89}" text-anchor="middle">{e(size)}</text></g>'''
    body += '</svg>'
    body += '<details><summary>Reference accessions</summary><ul>'
    for molecule in molecules:
        body += f"<li>{e(molecule.get('replicon_name', 'Reference molecule'))}: <code>{e(molecule.get('refseq_accession', 'Not recorded'))}</code> · {e(molecule.get('topology', 'unknown'))}</li>"
    return body + '</ul></details></section>'
