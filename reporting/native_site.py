"""Static native routes from sealed records and prepared presentation metadata.

Cohorts keep their own endpoints. Graphs live on individual result pages, never
on the homepage. Rendering neither reparses scientific inputs nor rescores them.
"""
from collections import Counter, defaultdict
import csv
from html import escape
import hashlib
import io
import json
from pathlib import Path
import re
import shutil

from .common import ROOT, digest, load, save
from .assets import ensure_assets
from .site_gate import require_site, write_site_receipt

FAMILIES = {'S1': 'Exact recovery controls', 'S2': 'Relative plasmid coverage',
            'S3': 'Repeatability', 'S4': 'Small plasmids and read length',
            'S5': 'Linear plasmids and terminal repeats', 'S6': 'Historical noisy reads',
            'S7': 'Read-order output agreement'}


def result_route(record):
    identity = json.dumps([record['case']['id'], record['assembler']], separators=(',', ':'))
    return 'results/' + hashlib.sha256(identity.encode()).hexdigest()[:24] + '.html'


def cohort(record):
    track = record.get('track', 'simulated')
    return track if track in ('general', 'diagnostic', 'real') else 'simulated'


def family(record):
    case = record['case']
    return case.get('category', case.get('group', 'unclassified'))


def page(title, body):
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + escape(title) + '</title><link rel="stylesheet" href="/assets/genomicx.css"><script defer src="/assets/genomicx.js"></script><style>main{max-width:1400px;margin:auto;padding:1rem}.scroll{overflow:auto}th,td{padding:.65rem;text-align:left;vertical-align:top;border-bottom:1px solid #999}img{max-width:100%}nav{display:flex;gap:1rem;flex-wrap:wrap}table{width:100%;border-collapse:collapse}</style></head><body><nav aria-label="Benchmark navigation"><a href="/index.html">Overview</a><a href="/performance.html">General performance</a><a href="/aggregate.html">General aggregate</a><a href="/scenarios/index.html">Diagnostic scenarios</a><a href="/simulated.html">Simulated baseline</a><a href="/real.html">Real data</a></nav><main><h1>' + escape(title) + '</h1>' + body + '</main></body></html>'


def download(path):
    return '<p><a href="/' + escape(path, quote=True) + '">Results TSV for this cohort</a></p>'


def detailed_table(records, run_id):
    if not records:
        return '<p>No results were supplied for this cohort. Missing results do not establish sequence absence.</p>'
    # Reuse the producer's endpoint-specific table, without changing any values.
    if all('resources' in r and 'preset' in r for r in records):
        from benchlib.report import render_html
        document = render_html(records, len(records), run_id)
        body = document.split('<main>', 1)[1].split('</main>', 1)[0]
        body = re.sub(r'<h1>.*?</h1>', '', body, count=1, flags=re.S)
        body = re.sub(r'<p><a href="results.tsv">.*?</p>', '', body, count=1, flags=re.S)
        # Raw FASTA/log/JSON downloads remain in the complete sealed archive.
        body = re.sub(r'<a href="([^"]+)">(.*?)</a>', lambda m: m.group(0) if m.group(1).startswith(('https:', 'http:', '#')) else m.group(2) + ' (in results archive)', body, flags=re.S)
    else:
        body = '<p>Saved result records; unavailable measurements are not inferred.</p>'
    links = '<h2>Individual execution evidence</h2><ul>' + ''.join('<li><a href="/' + result_route(r) + '">' + escape(r['case']['id'] + ' · ' + r['assembler']) + '</a></li>' for r in records) + '</ul>'
    return body + links


def outcome_label(record):
    execution = record.get('execution', {}).get('status')
    assessment = record.get('assessment', {}).get('status')
    if execution == 'infrastructure_error':
        return 'Infrastructure error'
    if execution == 'software_error':
        return 'Software error'
    if execution == 'resource_error':
        return 'Did not complete'
    if assessment == 'error':
        return 'Assessment error'
    return record.get('sequence_outcome') or 'Unmeasured'


def summary_table(records):
    tools = sorted({r['assembler'] for r in records})
    outcomes = sorted({outcome_label(r) for r in records})
    body = '<div class="scroll"><table><caption>General cohort only. Counts retain the declared sequence endpoint; execution and assessment errors stay unscored.</caption><thead><tr><th>Assembler</th>' + ''.join('<th>' + escape(str(o)) + '</th>' for o in outcomes) + '<th>Recorded slots</th></tr></thead><tbody>'
    for tool in tools:
        selected = [r for r in records if r['assembler'] == tool]
        counts = Counter(outcome_label(r) for r in selected)
        body += '<tr><th>' + escape(tool) + '</th>' + ''.join('<td>' + str(counts[o]) + '</td>' for o in outcomes) + '<td>' + str(len(selected)) + '</td></tr>'
    return body + '</tbody></table></div>'


def aggregate_page(records, output):
    body = '<p>General benchmark only. Diagnostic, simulated validation and real-pilot outcomes are excluded. Points are retained measurements, not a combined ranking.</p>' + summary_table(records)
    for name, title, select in [
            ('contiguity', 'Recorded molecule contiguity (uncapped)', lambda r: [m.get('contiguity') for m in r.get('replicons', [])]),
            ('wall-time', 'Workflow wall time (seconds)', lambda r: [r.get('resources', {}).get('workflow_wall_seconds')]),
            ('peak-ram', 'Assembler process-tree peak RAM (MiB)', lambda r: [(r.get('resources', {}).get('assembler_process_tree_peak_rss_bytes') or 0) / 1024**2 if r.get('resources', {}).get('assembler_process_tree_peak_rss_bytes') is not None else None])]:
        values = [(r['assembler'], value) for r in records for value in select(r) if isinstance(value, (int, float)) and not isinstance(value, bool)]
        target = output / 'figures' / ('general-' + name + '.svg')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(measurement_svg(values, title))
        body += '<h2>' + escape(title) + '</h2><p>' + str(len(values)) + ' measured values. Missing measurements are omitted.</p><img src="/figures/general-' + name + '.svg" alt="' + escape(title, quote=True) + '">'
    return body


def measurement_svg(values, title):
    tools = sorted({tool for tool, _ in values})
    ceiling = max([v for _, v in values] or [1]) or 1
    height = max(130, 100 + 50 * len(tools))
    text = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 ' + str(height) + '" role="img"><rect width="100%" height="100%" fill="white"/><g fill="#20242a" font-family="sans-serif" font-size="13"><text x="20" y="24">' + escape(title) + '</text>'
    for i, tool in enumerate(tools):
        y = 65 + i * 50
        text += '<text x="20" y="' + str(y + 4) + '">' + escape(tool) + '</text><path d="M230 ' + str(y) + 'h620" stroke="#ddd"/>'
        for current, value in values:
            if current == tool:
                text += '<circle cx="' + str(230 + 620 * value / ceiling) + '" cy="' + str(y) + '" r="3" fill="#326eae" fill-opacity=".6"><title>' + escape(str(value)) + '</title></circle>'
    return text + '<text x="230" y="' + str(height - 12) + '">0</text><text x="760" y="' + str(height - 12) + '">' + escape(f'{ceiling:,.3g}') + '</text></g></svg>'


def copy_prepared(source, output, relative, inventory):
    path = Path(relative)
    target = source / path
    if path.is_absolute() or '..' in path.parts or path.as_posix() not in inventory or not target.is_file():
        raise ValueError('Prepared presentation file is not bound by the archive: ' + str(relative))
    destination = output / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(target, destination)
    return target


def evidence_section(source, output, prepared, inventory):
    body = ''
    for index, graph in enumerate(prepared.get('graphs', [])):
        target = copy_prepared(source, output, graph['file'], inventory)
        model = load(target)
        payload = json.dumps(model, separators=(',', ':')).replace('<', r'\u003c').replace('>', r'\u003e').replace('&', r'\u0026')
        identity = f'graph-{index}'
        body += '<p><a href="/' + escape(graph['file'], quote=True) + '">Collected graph metadata JSON</a></p>'
        body += '<h2>Recorded assembly graph</h2><script type="application/json" id="' + identity + '">' + payload + '</script><div data-assembly-graph="' + identity + '"><p>Recorded GFA topology; reference origins are unassigned where no validated evidence exists.</p></div>'
    alignment = prepared.get('alignments')
    if alignment:
        for key in ('coordinates', 'figure'):
            copy_prepared(source, output, alignment[key], inventory)
        body += '<h2>Saved alignment coordinates</h2><p>' + escape(alignment['coordinate_system']) + '</p><img alt="Saved alignment dot plot" src="/' + escape(alignment['figure'], quote=True) + '"><p><a href="/' + escape(alignment['coordinates'], quote=True) + '">Recorded coordinates TSV</a></p>'
    return body or '<p>No prepared graph or alignment figure was collected. Missing evidence does not establish sequence absence.</p>'


def write_cohort_tsv(source, output, relative, records):
    selected = {(r['case']['id'], r['assembler']) for r in records}
    with (source / 'results.tsv').open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        fields = reader.fieldnames
        rows = list(reader)
    target = output / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter='\t')
        writer.writeheader()
        # Existing older native TSVs may omit assembler/case identity fields;
        # they are suitable only for a single-cohort document.
        for row in rows:
            if (row.get('case_id', row.get('case')), row.get('assembler')) in selected:
                writer.writerow(row)


def render_native(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError('Results and website directories must be separate')
    if output.exists() and any(output.iterdir()) and not (output / '.results-render.json').exists():
        raise ValueError('Website destination must be empty or a previous generated website')
    output.mkdir(parents=True, exist_ok=True)
    # Only this renderer's marked output may be rebuilt. Remove stale cohort and
    # result routes when a new sealed selection replaces a previous render.
    for path in output.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    shutil.copytree(ensure_assets(ROOT), output / 'assets')
    document = load(source / 'results.json')
    records = document['results']
    groups = {name: [r for r in records if cohort(r) == name] for name in ('general', 'diagnostic', 'simulated', 'real')}
    run_id = document['run_id']
    prepared_path = source / 'presentation/index.json'
    prepared = {(r['case_id'], r['assembler']): r for r in load(prepared_path)['results']} if prepared_path.is_file() else {}
    inventory = load(source / 'manifest.json')['files']
    shutil.copyfile(source / 'results.tsv', output / 'results.tsv')
    for name, selected in groups.items():
        write_cohort_tsv(source, output, f'data/cohorts/{name}.tsv', selected)
    general = groups['general']
    home = '<p>' + escape(run_id) + '</p>'
    if general:
        home += '<h2>General benchmark</h2><p>' + str(len(general)) + ' recorded general slots. Other cohorts are excluded from this table.</p>' + summary_table(general) + '<p><a href="/performance.html">Individual general outcomes</a> · <a href="/aggregate.html">General aggregate figures</a></p>' + download('data/cohorts/general.tsv')
    else:
        home += '<p>No general benchmark outcomes were supplied in this bundle.</p>'
    home += '<h2>Separate cohorts</h2><ul>' + ''.join('<li><a href="/' + route + '">' + label + '</a>: ' + str(len(groups[key])) + ' recorded slots</li>' for key, route, label in [('diagnostic', 'scenarios/index.html', 'Diagnostic scenarios'), ('simulated', 'simulated.html', 'Simulated validation'), ('real', 'real.html', 'Real-data pilots')]) + '</ul>'
    (output / 'index.html').write_text(page('Assembly benchmark', home))
    (output / 'performance.html').write_text(page('General assembler performance', '<p>General cohort only; fixed Wick longest-alignment completion.</p>' + download('data/cohorts/general.tsv') + detailed_table(general, run_id)))
    (output / 'aggregate.html').write_text(page('General aggregate measurements', download('data/cohorts/general.tsv') + aggregate_page(general, output)))
    (output / 'scenarios').mkdir(exist_ok=True)
    diagnostic_groups = defaultdict(list)
    for record in groups['diagnostic']:
        diagnostic_groups[family(record)].append(record)
    catalog = '<p>Diagnostic scientific endpoints are separate from the general comparison.</p><ul>'
    for identifier in sorted(set(FAMILIES) | set(diagnostic_groups)):
        selected = diagnostic_groups[identifier]
        if not re.fullmatch(r'[A-Za-z0-9_-]+', identifier):
            raise ValueError('Unsafe diagnostic family identifier')
        route = 'scenarios/' + identifier.lower() + '.html'
        title = identifier + ' · ' + FAMILIES.get(identifier, 'Diagnostic scenario')
        tsv = 'data/cohorts/' + identifier.lower() + '.tsv'
        write_cohort_tsv(source, output, tsv, selected)
        (output / route).write_text(page(title, download(tsv) + detailed_table(selected, run_id)))
        catalog += '<li><a href="/' + route + '">' + escape(title) + '</a>: ' + str(len(selected)) + ' recorded slots</li>'
    (output / 'scenarios/index.html').write_text(page('Diagnostic scenarios', catalog + '</ul>' + download('data/cohorts/diagnostic.tsv')))
    for name, title in [('simulated', 'Simulated baseline and workflow checks'), ('real', 'Real-data small-plasmid pilots')]:
        (output / (name + '.html')).write_text(page(title, download('data/cohorts/' + name + '.tsv') + detailed_table(groups[name], run_id)))
    (output / 'results').mkdir(exist_ok=True)
    for record in records:
        title = record['case']['id'] + ' · ' + record['assembler']
        body = '<p>Cohort: ' + escape(cohort(record)) + '. Endpoint: ' + escape(str(record.get('assessment', {}).get('method', 'Not recorded'))) + '.</p>'
        # A one-record table is presentation only. Its link back to itself is
        # harmless and keeps the scientific producer's endpoint labels intact.
        body += detailed_table([record], run_id)
        body += evidence_section(source, output, prepared.get((record['case']['id'], record['assembler']), {}), inventory)
        (output / result_route(record)).write_text(page(title, body))
    save(output / '.results-render.json', {'schema_version': 1, 'producer': 'nextflow', 'bundle_manifest_sha256': digest(source / 'manifest.json')})
    require_site(output)
    write_site_receipt(output)
    return output
