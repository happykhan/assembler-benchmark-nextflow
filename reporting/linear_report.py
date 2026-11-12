"""Display the measured reference-repeat intervals supplied by the backend."""

def reference_repeat_table(case):
    from .report import e
    molecules = [r for r in case.get('replicons', []) if r.get('terminal_repeat_evidence', {}).get('inter_arm_alignment')]
    if not molecules:
        return ''
    body = '<h2 id="reference-repeats">Reference terminal repeats</h2><p>NUCmer comparison of the reference’s left and right halves. Coordinates are 1-based inclusive.</p>'
    body += '<div class="table-scroll" role="region" aria-label="Reference repeat intervals" tabindex="0"><table><thead><tr><th>Molecule</th><th>Left interval</th><th>Right interval</th><th>Orientation</th><th>Identity</th><th>Right-tip offset</th></tr></thead><tbody>'
    for molecule in molecules:
        evidence = molecule['terminal_repeat_evidence']['inter_arm_alignment']
        match = evidence.get('selected_left_terminal_inverted_alignment')
        accession = molecule.get('genbank_accession', molecule['refseq_accession'])
        body += f"""<tr><th scope="row">{e(molecule['molecule_type'])} · {e(accession)}</th>"""
        if not match:
            body += '<td colspan="5">No inter-arm alignment at the recorded settings</td></tr>'
            continue

        def interval(value):
            return f'{value[0] + 1:,}–{value[1]:,}'
        body += f"<td>{interval(match['left_interval'])}</td><td>{interval(match['right_interval'])}</td><td>Inverted</td><td>{match['identity_percent']:.2f}%</td><td>{match['right_terminal_offset_bp']:,} bp</td></tr>"
    return body + '</tbody></table></div>'
