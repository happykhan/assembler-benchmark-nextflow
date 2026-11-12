"""Static broad-performance views consume the exported backend model only."""
import html
import json
import math
import shlex
from .performance_bundle import TOOLS, OUTCOMES

def e(value):
    return html.escape(str(value), quote=True)

def number(value, unit='', scale=1, digits=2):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or (not math.isfinite(value)):
        return 'Not measured'
    text = f'{value * scale:,.{digits}f}' if digits else f'{value * scale:,.0f}'
    return text + unit

def state_text(model):
    count, expected = (model['recorded_executions'], model['expected_executions'])
    if count == expected:
        return f'{count} of {expected} results recorded.'
    state = {'preparing': 'Preparing published inputs', 'submitted': 'Jobs submitted', 'running': 'Benchmark running', 'collecting': 'Collecting results'}.get(model['state'], 'Results pending')
    return f'{state}. {count} of {expected} results recorded.'

def summary_fragment(model):
    body = '<section aria-labelledby="performance-title"><h2 id="performance-title">General performance</h2>'
    body += f"<p>{model['dataset_count']} published simulated datasets · four primary workflows. {e(state_text(model))}</p>"
    body += '<div class="table-scroll" role="region" aria-label="Broad assembly completion" tabindex="0"><table class="overview-heatmap" data-matrix-label="general performance"><caption>Wick-style completion: one alignment covers at least 99% of a reference molecule</caption><thead><tr><th scope="col">Outcome</th>'
    body += ''.join((f"""<th scope="col">{e(t['label'])}</th>""" for t in model['tools'])) + '</tr></thead><tbody>'
    for outcome in [*model['outcomes'], {'id': 'pending', 'label': 'Awaiting result'}]:
        body += f"""<tr><th scope="row">{e(outcome['label'])}</th>"""
        for tool in model['tools']:
            count = tool[outcome['id']]
            tone = 'pass' if outcome['id'] == 'fully_complete' and count else 'fail' if outcome['id'] in {'did_not_complete', 'execution_error'} and count else 'neutral'
            body += f'<td class="overview-cell {tone}"><a href="performance.html#runs">{count}</a></td>'
        body += '</tr>'
    return body + '</tbody></table></div><p><a href="performance.html">Datasets and individual results</a> · <a href="aggregate.html">Performance plots</a> · <a href="performance-methods.html">Methods</a></p></section>'

def performance_page(model):
    from .report import page
    body = '<h1>General performance</h1>' + summary_fragment(model).replace('<h2 id="performance-title">General performance</h2>', '<h2 id="performance-title">Completion summary</h2>')
    body += '<h2 id="runs">Individual results</h2>'
    datasets = {d['id']: d for d in model['datasets']}
    if not model['results']:
        body += '<p>No completed results have been published for this panel yet. The selected datasets are listed below.</p>'
    else:
        body += '<div class="table-scroll"><table data-table-kind="performance-runs"><thead><tr><th scope="col">Dataset</th><th scope="col">Assembler</th><th scope="col">Completion</th><th scope="col">Workflow time</th><th scope="col">Peak RAM</th></tr></thead><tbody>'
        for row in model['results']:
            dataset = datasets[row['dataset_id']]
            target = e(row['dataset_id']) + '--' + e(row['tool'])
            body += f"""<tr><td><a href="#dataset-{e(row['dataset_id'])}">{e(row['dataset_id'])}</a><small>{e(dataset.get('organism', ''))}</small></td><td><a href="#{target}">{e(TOOLS[row['tool']])}</a></td><td>{e(OUTCOMES[row['genome_outcome']])}</td><td>{number(row.get('elapsed_seconds'), ' s')}</td><td>{number(row.get('peak_memory_kb'), ' GiB', 1 / 1048576)}</td></tr>"""
        body += '</tbody></table></div>'
    body += '<h2>Input datasets</h2><p>Original Wick and Holt simulated reads, reused without regenerating or reordering them.</p><div class="table-scroll"><table data-table-kind="performance-inputs"><thead><tr><th scope="col">Dataset</th><th scope="col">Organism</th><th scope="col">Plasmids</th><th scope="col">Read N50</th><th scope="col">Mean depth</th><th scope="col">Target identity</th></tr></thead><tbody>'
    for dataset in model['datasets']:
        stats, parameters = (dataset.get('published_read_statistics', {}), dataset.get('badread_parameters', {}))
        body += f"""<tr><td><a href="#dataset-{e(dataset['id'])}">{e(dataset['id'])}</a></td><td>{e(dataset.get('organism', 'Not recorded'))}</td><td>{e(dataset.get('plasmid_count', 'Not recorded'))}</td><td>{number(stats.get('read_n50_bp'), ' bp', digits=0)}</td><td>{number(stats.get('mean_depth'), '×')}</td><td>{number(parameters.get('identity_mean'), '%')}</td></tr>"""
    body += '</tbody></table></div><h2>Dataset details</h2>'
    for dataset in model['datasets']:
        body += dataset_detail(dataset, [r for r in model['results'] if r['dataset_id'] == dataset['id']])
    return page('General performance', body)

def dataset_detail(dataset, rows):
    body = f"""<details id="dataset-{e(dataset['id'])}"><summary>{e(dataset['id'])} · {e(dataset.get('organism', ''))}</summary>"""
    body += '<h3>Reference molecules</h3><div class="table-scroll"><table><thead><tr><th scope="col">Accession</th><th scope="col">Molecule</th><th scope="col">Length</th></tr></thead><tbody>'
    for molecule in dataset.get('replicons', []):
        body += f"<tr><td>{e(molecule['refseq_accession'])}</td><td>{e(molecule['molecule_type'])}</td><td>{number(molecule['length_bp'], ' bp', digits=0)}</td></tr>"
    body += '</tbody></table></div>'
    if not rows:
        body += '<p>Results pending for this dataset.</p>'
    for row in rows:
        body += f'''<h3 id="{e(dataset['id'])}--{e(row['tool'])}">{e(TOOLS[row['tool']])} · {e(OUTCOMES[row['genome_outcome']])}</h3>'''
        body += f"<p>Workflow time: {number(row.get('elapsed_seconds'), ' s')} · Peak RAM: {number(row.get('peak_memory_kb'), ' GiB', 1 / 1048576)}</p>"
        failure = row.get('error') or row.get('reason')
        if failure:
            body += f'<p>{e(failure)}</p>'
        if row.get('replicons'):
            body += '<div class="table-scroll"><table><thead><tr><th scope="col">Reference</th><th scope="col">Contiguity</th><th scope="col">Identity</th><th scope="col">Maximum indel</th><th scope="col">Longest matching contig</th></tr></thead><tbody>'
            for molecule in row['replicons']:
                body += f"<tr><td>{e(molecule.get('accession', molecule.get('name', 'Reference')))}</td><td>{number(molecule.get('contiguity'), '%', 100)}</td><td>{number(molecule.get('identity'), '%', 100, 4)}</td><td>{number(molecule.get('max_indel_bp'), ' bp', digits=0)}</td><td>{e(molecule.get('contig_id') or 'Not measured')}</td></tr>"
            body += '</tbody></table></div>'
        body += '<details><summary>Commands and provenance</summary>'
        commands = row.get('commands') or ([row['command']] if row.get('command') else [])
        commands = commands.items() if isinstance(commands, dict) else [(f'Command {i + 1}', value) for i, value in enumerate(commands)]
        for label, command in commands:
            if isinstance(command, dict):
                command = command.get('command', [])
            command = [public_argument(value) for value in command] if isinstance(command, list) else public_argument(command)
            text = shlex.join(command) if isinstance(command, list) else command
            body += f"<h4>{e(str(label).replace('_', ' ').capitalize())}</h4><pre><code>{e(text)}</code></pre>"
        metadata = {k: row[k] for k in ('version', 'versions', 'mapper_version', 'threads', 'provenance', 'execution_status') if k in row}
        body += f'<pre><code>{e(json.dumps(public_metadata(metadata), indent=2))}</code></pre></details>'
    body += '<details><summary>Published simulation recipe</summary><pre><code>' + e(dataset.get('badread_command_as_published', 'Not recorded')) + '</code></pre></details></details>'
    return body

def public_argument(value):
    value = str(value)
    return '<workdir>/runs/' + value.split('/runs/', 1)[1] if '/runs/' in value else value

def public_metadata(value):
    if isinstance(value, dict):
        return {key: public_metadata(item) for key, item in value.items()}
    if isinstance(value, list):
        return [public_metadata(item) for item in value]
    return public_argument(value) if isinstance(value, str) else value

def methods_page(model):
    from .report import page
    body = '<h1>General performance methods</h1>\n<p>This track follows Wick and Holt’s broad assembler comparison, using 50 of their published simulated datasets and four current workflows. It is separate from the controlled diagnostic scenarios.</p>\n<h2>Inputs</h2><p>The frozen selection contains 25 genomes with plasmids and 25 without, with 50 plasmids in total. The published read files are reused byte-for-byte. Read length, depth, identity and artefact settings vary across datasets according to the original sampling design.</p>\n<p>The original simulation treats every reference molecule as circular. That is the simulation assumption, including references whose native topology may differ. The published source already replaced ambiguous reference bases; these are the deposited simulation references.</p>\n<h2>Completion and sequence accuracy</h2><p>Contigs are aligned to tripled references. Contiguity is the span of the longest single reference alignment divided by the original molecule length; it can exceed 100%. A molecule is complete at 99% contiguity. A fully complete dataset has complete chromosomes and plasmids. Chromosome-complete results have all chromosomes complete but at least one incomplete plasmid.</p>\n<p>Identity and maximum indel come from the longest alignment only when its span exceeds 100 kb or one quarter of that reference. Otherwise they are not measured. These alignment-based completion measures differ from the diagnostic suite’s exact-copy test.</p>\n<h2>Workflows and resources</h2><p>The four workflows are Flye, Raven, Plassembler and Miniasm + Minipolish. Miniasm’s raw overlap/layout phase is an intermediate of the fourth workflow. Its time is included with polishing; it is not counted as a fifth workflow. Plassembler is assessed using its final plasmids and its actual retained chromosome.</p>\n<p>Workflow time includes input verification and exact assessment, with raw Miniasm and polishing times combined for Miniasm + Minipolish. Downloads and scheduler waiting are excluded. Peak RAM is measured for the assembler process tree; sequential phases use their larger peak. Incomplete executions and tool or assessment errors remain visible separately from completed assemblies.</p>\n<h2>Sources</h2><p><a href="https://doi.org/10.12688/f1000research.21782.4">Wick and Holt, study version 4</a> · <a href="https://github.com/rrwick/Long-read-assembler-comparison">Original methods and code</a> · <a href="https://doi.org/10.26180/5df6f5d06cf04">Published read sets</a> · <a href="https://doi.org/10.26180/5df6e99ff3eed">Published references</a>. Source material is attributed under CC BY 4.0. Modern assembler versions are recorded per execution; this is not a reproduction of the historical software environment.</p>'
    if model.get('source_pool_note'):
        body += f"<details><summary>Sampling provenance</summary><p>{e(model['source_pool_note'])}</p><p>Source revision: <code>{e(model.get('source_revision', 'Not recorded'))}</code></p></details>"
    return page('General performance methods', body, active='methods')

def performance_aggregate_page(model, index):
    from .report import page
    body = '<h1>General performance plots</h1><p>Completion, sequence accuracy and resources across the broad dataset panel.</p>'
    body += f'<p>{e(state_text(model))} <a href="performance.html">Datasets and individual results</a> · <a href="performance-methods.html">Methods</a></p>'
    if not index.get('figures'):
        body += '<p>Plots will appear when measured results are published. No benchmark measurements are available for this panel yet.</p>'
    for figure in index.get('figures', []):
        svg = 'data/performance/' + figure['svg']
        png = 'data/performance/' + figure['png'] if figure.get('png') else None
        body += f'''<figure class="aggregate-figure"><h2>{e(figure['title'])}</h2><a href="{e(svg)}"><img loading="lazy" src="{e(svg)}" alt="{e(figure.get('caption', figure['title']))}"></a><figcaption>{e(figure.get('caption', ''))} <a href="{e(svg)}">SVG</a>'''
        if png:
            body += f' · <a href="{e(png)}">PNG</a>'
        body += '</figcaption></figure>'
    if index.get('tables'):
        body += '<h2>Source tables</h2><div class="downloads">'
        for table in index['tables']:
            name = table if isinstance(table, str) else table.get('path', table.get('file'))
            title = name if isinstance(table, str) else table.get('title', name)
            body += f'<a href="data/performance/{e(name)}">{e(title)}</a>'
        body += '</div>'
    return page('General performance plots', body, active='aggregate')
