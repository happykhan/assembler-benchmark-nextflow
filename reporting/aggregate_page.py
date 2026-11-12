"""Present precomputed aggregate figures; no metric calculation in the website."""
import html

def aggregate_page(index, attribution):
    from .report import page
    e = lambda value: html.escape(str(value), quote=True)
    body = '<h1>Aggregate plots</h1>\n<p>Saved benchmark results by scenario and cohort, with downloadable figures and source data.</p>\n\n<div class="downloads"><a href="data/aggregates/data.json">Plot data JSON</a><a href="data/aggregates/executions.tsv">Executions TSV</a><a href="data/aggregates/molecules.tsv">Molecules TSV</a><a href="data/aggregates/inputs.tsv">Inputs TSV</a></div>'
    for i, group in enumerate(index['groups']):
        scope = 'revised baseline' if group['family'] == 'S1' and group['cohort_role'] == 'primary' else group['cohort_role']
        body += f'''<details class="aggregate-group" id="{e(group['id'])}" name="aggregate-cohort" {('open' if i == 0 else '')}><summary>{e(group['family'])} · {e(scope)} · {group['execution_count']} executions</summary>'''
        if group['family'] == 'S3':
            body += '<p>Repeated executions measure output agreement. They are excluded from the recovery and resource distributions on this page.</p>'
        else:
            body += '<details><summary>Counting rules</summary><p>Each point represents a saved execution or required molecule, as labelled. Reused inputs and multiple plasmids are not independent genomes; no confidence interval or universal ranking is implied.</p></details>'
        for figure in [f for f in index['figures'] if f['group_id'] == group['id']]:
            url = 'data/aggregates/' + figure['svg']
            image_url = url + '?v=' + figure.get('svg_sha256', '')[:12]
            body += f'''<figure class="aggregate-figure"><h2>{e(figure['title'])}</h2><a href="{e(url)}"><img loading="lazy" src="{e(image_url)}" alt="{e(figure['title'])} for {e(group['family'])} {e(group['cohort_role'])}; {e(figure['caption'])}"></a><figcaption>{e(figure['caption'])} <a href="{e(url)}">SVG</a> · <a href="data/aggregates/{e(figure['png'])}">PNG</a></figcaption></figure>'''
        body += '</details>'
    body += '<h2>What differs from Wick’s assessment?</h2>\n<p>Primary panels and supplementary historical results are shown separately. Plot formats are inspired by Wick and Holt; values are Ploptimizer measurements.</p>\n<p>Our exact-copy endpoint and retained-reference breadth answer different questions from his longest-single-alignment contiguity. The identity plots use our recorded alignment-weighted identity. We do not have compatible circularisation-gap/overlap or maximum-indel distributions, so those panels are not presented as measured results.</p>\n<details><summary>Wick and Holt’s original figures</summary><p>Original study results, not Ploptimizer measurements. Ryan R. Wick and Kathryn E. Holt; CC BY 4.0. Links are pinned to the reviewed repository revision.</p><ul>'
    for figure in attribution['figures']:
        body += f'''<li><a href="{e(figure['url'])}">{e(figure['title'])}</a></li>'''
    body += f'''</ul><p><a href="{e(attribution['study'])}">Study, version 4</a> · <a href="{e(attribution['repository'])}">Source repository and licence</a></p></details>'''
    return page('Aggregate plots', body, active='aggregate')
