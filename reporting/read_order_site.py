"""Freeze and display completed read-order comparisons; no sequence analysis."""
import copy
import html
import re
import shutil
from pathlib import Path
from .common import ROOT, digest, load, save

def report_page(summary, temporary):
    """Reuse the saved-report renderer inside the existing GenomicX page shell."""
    from .read_order_report import render
    from .report import page
    public = copy.deepcopy(summary)
    for tool in public['tools']:
        for row in tool['runs']:
            row['command'] = ['<workdir>/runs/' + str(arg).split('/runs/', 1)[1] if '/runs/' in str(arg) else str(arg) for arg in row.get('command', [])]
    temporary = Path(temporary)
    render(public, temporary, public=True)
    document = (temporary / 'index.html').read_text()
    body = document.split('<main>', 1)[1].split('</main>', 1)[0]
    source = summary['input_admission']['source']
    orders = summary['input_admission']['orders']
    context = '<p>Frozen input: <code>' + html.escape(source['case_id']) + '</code>'
    if orders:
        context += ' · ' + f"{orders[0]['record_count']:,}" + ' reads per order'
    context += '.</p>'
    body = body.replace('<h2>Summary</h2>', context + '<h2>Summary</h2>', 1)
    body = body.replace('href="runs.tsv"', 'href="/data/read-order/runs.tsv"')
    body = body.replace('href="orders.tsv"', 'href="/data/read-order/orders.tsv"')
    body = body.replace('class="scroll"', 'class="table-scroll" role="region" tabindex="0" aria-label="Read-order comparison table"')
    body = body.replace('Pairwise output agreement: blue', 'Ends-retained pairwise output agreement: blue')
    body = body.replace('class="same"', 'class="overview-cell heat-4"')
    body = body.replace('class="different"', 'class="overview-cell heat-0"')
    body = body.replace('class="unavailable"', 'class="overview-cell neutral"')
    return page('S7 · Read-order sensitivity', '<div class="read-order-report">' + body + '</div>', '../', 'scenarios')

def headline_row(summary, tools):
    """Add output-agreement labels without changing exact/repeatability counts."""
    e = lambda value: html.escape(str(value), quote=True)
    saved = {tool['tool']: tool for tool in summary['tools']}
    row = '<tr data-read-order="true"><th scope="row"><a href="/scenarios/s7.html">S7 · Read-order sensitivity</a><small>Output agreement</small></th>'
    for tool in tools:
        identifier = tool['id'] if isinstance(tool, dict) else tool
        record = saved.get(identifier)
        if record is None:
            row += '<td class="overview-cell neutral"><strong>Not assessed</strong></td>'
            continue
        circle, ends = (record['circular_representation'], record['end_sensitive'])
        if circle['complete']:
            verdict = circle['verdict']
            context = 'Circular starts normalised'
        else:
            verdict = ends['verdict']
            context = 'Ends retained; circular view unavailable'
        if verdict == 'No order effect observed':
            label, tone = (verdict, 'heat-4')
        elif verdict.startswith('Within-order variability'):
            label, tone = ('Within-order variability', 'heat-1')
            context = 'Order-specific effect unresolved'
        elif verdict == 'Order-associated output difference':
            label, tone = ('Order-associated difference', 'heat-0')
        else:
            label, tone = (verdict, 'neutral')
        row += f'<td class="overview-cell {tone}"><a href="/scenarios/s7.html#{e(identifier)}"><strong>{e(label)}</strong></a><small>{e(context)}</small></td>'
    return row + '</tr>'

def install_read_order(bundle, output, tools):
    """Install one compact scenario page and two TSV downloads from frozen metadata."""
    import tempfile
    bundle, output = (Path(bundle), Path(output))
    summary = load(bundle / 'read_order/summary.json')
    with tempfile.TemporaryDirectory(prefix='.s7-render-', dir=output.parent) as temporary:
        temporary = Path(temporary)
        document = report_page(summary, temporary)
        (output / 'scenarios/s7.html').write_text(document)
        destination = output / 'data/read-order'
        destination.mkdir(parents=True, exist_ok=True)
        for name in ('runs.tsv', 'orders.tsv'):
            shutil.copy2(temporary / name, destination / name)
    home = output / 'index.html'
    text = home.read_text()
    text = re.sub('<tr data-read-order="true">.*?</tr>', '', text, flags=re.S)
    pattern = '(<table class="overview-heatmap">.*?<tbody>)(.*?)(</tbody>)'
    text, count = re.subn(pattern, lambda match: match[1] + match[2] + headline_row(summary, tools) + match[3], text, count=1, flags=re.S)
    if count != 1:
        raise ValueError('Diagnostic scenario matrix was not found')
    text = text.replace('Recovery counts by scenario family; S3 counts repeated-run agreement', 'Recovery counts by scenario family; S3 and S7 compare output agreement')
    home.write_text(text)
    catalogue = output / 'scenarios/index.html'
    text = catalogue.read_text()
    if 'data-read-order-link' not in text:
        text = text.replace('</main>', '<section data-read-order-link><h2>S7 · Read-order sensitivity</h2><p><a href="/scenarios/s7.html">48 completed executions · shuffled copies of the same reads · output-agreement results</a></p></section></main>')
    catalogue.write_text(text)
    return output / 'scenarios/s7.html'
