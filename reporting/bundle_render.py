"""Website adapter for validated bundles; no cluster or sequence-analysis stage."""
import shutil
import zipfile
from pathlib import Path
from .bundle import load_bundle, result_id
from .common import load

def render_bundle(bundle, output):
    bundle, output = (Path(bundle).resolve(), Path(output).resolve())
    if output == bundle or bundle in output.parents or output in bundle.parents:
        raise ValueError('Bundle and website destinations must be separate directories')
    if output.exists() and any(output.iterdir()) and (not (output / '.results-render.json').exists()):
        from .common import ROOT
        if output != ROOT / 'dist':
            raise ValueError('Render destination must be empty or a previously generated bundle website')
    manifest, documents = load_bundle(bundle)
    context = {'documents': {d['batch']: d for d in documents}, 'overview': load(bundle / 'overview.json'), 'models': {d['batch']: load(bundle / 'models' / f"{d['batch']}.json") for d in documents}}
    primary = context['documents'][manifest['primary_batch']]
    from .report import build
    build(primary['config'], output=output, document=primary, include_history=True, render_context=context)
    for document in documents:
        batch = document['batch']
        destination = output if batch == manifest['primary_batch'] else output / 'batches' / batch
        for record in document['results']:
            slug = result_id(record)
            source = bundle / 'reports' / batch
            target = destination / 'data/results'
            target.mkdir(parents=True, exist_ok=True)
            report = (source / f'{slug}.md').read_text().replace(f'../../batches/{batch}.json', '../results.json')
            (target / f'{slug}-report.md').write_text(report)
            if record['report_evidence']['dotplot']['status'] == 'available':
                shutil.copy2(source / f'{slug}-alignment.svg', target / f'{slug}-alignment.svg')
                shutil.copy2(source / f'{slug}-alignments.tsv', target / f'{slug}-alignments.tsv')
                if record['report_evidence']['dotplot'].get('nucmer_status') == 'available':
                    shutil.copy2(source / f'{slug}-original-show-coords.tsv', target / f'{slug}-original-show-coords.tsv')
    for name in ('summary.tsv', 'molecules.tsv', 'evidence-availability.tsv', 'evidence-coverage.json', 'length-metrics.tsv'):
        if (bundle / name).is_file():
            shutil.copy2(bundle / name, output / 'data' / name)
    if (bundle / 'aggregates/index.json').is_file():
        from .aggregate_page import aggregate_page
        shutil.copytree(bundle / 'aggregates', output / 'data/aggregates', dirs_exist_ok=True)
        diagnostic_page = aggregate_page(load(bundle / 'aggregates/index.json'), load(bundle / 'aggregates/wick-figures.json'))
        (output / 'aggregate.html').write_text(diagnostic_page)
        if (bundle / 'performance/model.json').is_file():
            (output / 'diagnostic-plots.html').write_text(diagnostic_page.replace('Aggregate plots', 'Diagnostic scenario plots'))
    if (bundle / 'performance/model.json').is_file():
        from .performance_pages import performance_page, methods_page, performance_aggregate_page, summary_fragment
        performance = load(bundle / 'performance/model.json')
        plots = load(bundle / 'performance/plots/index.json')
        (output / 'performance.html').write_text(performance_page(performance))
        (output / 'performance-methods.html').write_text(methods_page(performance))
        (output / 'aggregate.html').write_text(performance_aggregate_page(performance, plots))
        destination = output / 'data/performance'
        destination.mkdir(parents=True, exist_ok=True)
        for source in (bundle / 'performance/plots').rglob('*'):
            if source.is_file() and source.suffix in {'.svg', '.png', '.tsv'}:
                target = destination / source.relative_to(bundle / 'performance/plots')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        home = output / 'index.html'
        home.write_text(home.read_text().replace('<h1>Assembly benchmark</h1>', '<h1>Assembly benchmark</h1>' + summary_fragment(performance) + '<h2>Diagnostic scenarios</h2>', 1))
        catalogue = output / 'scenarios/index.html'
        if (output / 'diagnostic-plots.html').is_file():
            catalogue.write_text(catalogue.read_text().replace('</main>', '<p><a href="/diagnostic-plots.html">Diagnostic scenario plots</a></p></main>'))
    if (bundle / 'read_order/summary.json').is_file():
        from .read_order_site import install_read_order
        install_read_order(bundle, output, context['overview']['tools'])
    home = output / 'index.html'
    content = home.read_text().replace('</main>', '<div class="downloads"><a href="data/summary.tsv">Execution summary TSV</a><a href="data/molecules.tsv">Molecule evidence TSV</a></div></main>')
    if (bundle / 'evidence-availability.tsv').is_file():
        content = content.replace('Molecule evidence TSV</a>', 'Molecule evidence TSV</a><a href="data/evidence-availability.tsv">Evidence availability TSV</a>')
    if (bundle / 'length-metrics.tsv').is_file():
        content = content.replace('Execution summary TSV</a>', 'Execution summary TSV</a><a href="data/length-metrics.tsv">Graph and contig lengths TSV</a>')
    home.write_text(content)
    from .common import save, digest
    save(output / '.results-render.json', {'schema_version': 1, 'bundle_manifest_sha256': digest(bundle / 'manifest.json')})
    from .web_downloads import package_downloads
    package_downloads(output)
    from .site_gate import require_site, write_site_receipt
    require_site(output)
    write_site_receipt(output)
    return output
