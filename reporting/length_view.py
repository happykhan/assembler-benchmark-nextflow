"""Presentation of backend length measurements; no metric calculation."""
from html import escape

def render_lengths(metrics):
    if not metrics:
        return ''
    e = lambda value: escape(str(value), quote=True)
    groups = [('graph_segments', 'Graph segments'), ('scored_contigs', 'Scored output contigs')]
    labels = [('count', 'Number'), ('total_bp', 'Total length'), ('minimum_bp', 'Shortest'), ('median_bp', 'Median'), ('maximum_bp', 'Longest'), ('n50_bp', 'N50'), ('n90_bp', 'N90')]
    body = '<section aria-labelledby="length-metrics"><h2 id="length-metrics">Graph and contig lengths</h2><div class="table-scroll"><table><thead><tr><th scope="col">Metric</th>'
    body += ''.join((f'<th scope="col">{title}</th>' for _, title in groups)) + '</tr></thead><tbody>'
    for key, label in labels:
        body += f'<tr><th scope="row">{label}</th>'
        for group, _ in groups:
            value = metrics[group].get(key)
            formatted = 'Not measured' if value is None else f'{value:,.0f}' if float(value).is_integer() else f'{value:,.1f}'
            body += f"<td>{formatted}{(' bp' if value is not None and key != 'count' else '')}</td>"
        body += '</tr>'
    body += '</tbody></table></div>'
    for key, title in groups:
        group = metrics[key]
        if group['status'] != 'complete':
            body += f"<p>{title}: {e(group.get('reason') or 'Partial inventory; full length statistics are not assessed.')}</p>"
        source = group.get('source', {})
        if source:
            body += f"""<p class="muted">{title} source: {e(source.get('filename', source.get('kind', 'recorded metadata')))} · {e(source.get('role', 'not recorded'))}.</p>"""
        if group.get('items'):
            body += f'<details><summary>{title}: individual lengths</summary><div class="table-scroll"><table data-table-kind="lengths"><thead><tr><th scope="col">Identifier</th><th scope="col">Length</th></tr></thead><tbody>'
            for row in group['items']:
                length = f"{row['length_bp']:,} bp" if row.get('length_bp') is not None else 'Unknown'
                body += f"""<tr><th scope="row">{e(row['id'])}</th><td>{length}</td></tr>"""
            body += '</tbody></table></div></details>'
    return body + f"""<p class="muted">{e(metrics['scope'])}</p></section>"""
