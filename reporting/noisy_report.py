"""S6 reports keep exact equality separate from tolerant recovery of noisy reads."""
import collections
import copy
import csv
import datetime
import json
import math
import re
import shutil
from .assets import ensure_assets
from .common import ROOT, load, save
from .result_pages import enrich_graph_artifacts, result_href, write_result_pages
from .report import LABELS, STATUSES, badge, batch_progress, e, execution_evidence, explained_records, finding_panel, interpretation_guide, page, run_summary, write_archives, write_release_overview
CAUTION = 'An exact sequence failure alone does not show that a plasmid was lost. Residual sequence errors can prevent exact equality; tolerant recovery is assessed separately.'

def legacy_noise_note(case):
    plasmids = [m for m in case.get('replicons', []) if m.get('molecule_type') == 'plasmid']
    if case.get('category') == 'S6' and any((isinstance(m.get('length_bp'), int) and m['length_bp'] < 20000 for m in plasmids)):
        return '<p class="muted">Historical small-plasmid noise test: this input combines simulated read errors with a plasmid below 20 kb. The <a href="/scenarios/s6.html">revised S6 panel</a> uses larger plasmids to separate those challenges. This saved run and its score are unchanged.</p>'
    return ''

def display_title(case):
    profile = case.get('error_profile', {}).get('id')
    labels = {'matched-exact': 'Matched error-free control', 'generic-stress': 'Generic simulated errors', 'ont2023-shaped': 'Historical ONT-shaped errors'}
    title = case['title']
    return title.replace(' · ' + profile + ' ·', ' · ' + labels[profile] + ' ·', 1) if profile in labels else title

def tolerant_status(row):
    status = (row.get('tolerant_assessment') or {}).get('status', 'unscored')
    return status if status in ('pass', 'fail', 'error') else 'unscored'

def tolerant_badge(row):
    status = tolerant_status(row)
    return badge(status) if status != 'unscored' else badge('not_run').replace('Not run', 'Unscored')

def numeric_metrics(value, prefix=''):
    """Preserve recorded field names; never infer quality or units from numbers."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from numeric_metrics(item, f'{prefix}.{key}'.strip('.'))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from numeric_metrics(item, f'{prefix}[{index}]')
    elif isinstance(value, (float, int)) and (not isinstance(value, bool)) and math.isfinite(value):
        yield (prefix, format(value, '.8g'))
METRIC_LABELS = {'anchor_count': ('Reference markers selected', 'count', 'Number of short reference sequences defined for the copy screen.'), 'anchor_length_bp': ('Length of each marker', 'bp', 'Length of each reference marker used by the copy screen.'), 'possible_copy_guard': ('Matching markers that trigger review', 'count', 'Review threshold for another contig; this is not an observed copy count.'), 'matching_reference_anchors': ('Matching reference markers', 'count', 'Markers found in this contig; matches alone do not establish another complete copy.'), 'length_bp': ('Reference length', 'bp', ''), 'reference_coverage': ('Reference covered', 'fraction', ''), 'reference_coverage_lower_bound': ('Reference coverage lower bound', 'fraction', 'Conservative coverage bound recorded by the tolerant evaluator.'), 'alignment_identity': ('Alignment identity', 'fraction', ''), 'alignment_identity_lower_bound': ('Alignment identity lower bound', 'fraction', 'Conservative identity bound recorded by the tolerant evaluator.'), 'length_ratio': ('Contig length / reference length', 'ratio', ''), 'aligned_reference_bp': ('Aligned reference bases', 'bp', ''), 'reference_span_bp': ('Reference alignment span', 'bp', ''), 'reference_start_0based': ('Reference start', 'count', '0-based coordinate: the first reference base is position 0.'), 'alignment_columns': ('Alignment columns', 'count', ''), 'edit_distance': ('Sequence edits', 'count', 'Substitutions, insertions and deletions counted by the saved alignment.'), 'matches': ('Matching bases', 'count', ''), 'substitutions': ('Base substitutions', 'count', ''), 'insertions': ('Inserted bases', 'bp', ''), 'deletions': ('Deleted bases', 'bp', '')}

def metric_display(value, path, raw):
    """Name the recorded molecule/contig and format only explicitly known units."""
    tokens = re.findall('([^.[\\]]+)|\\[(\\d+)\\]', path)
    current, context = (value, [])
    for index, (key, number) in enumerate(tokens):
        if number:
            current = current[int(number)]
            name = current.get('name') or current.get('accession') or current.get('contig') if isinstance(current, dict) else None
            collection = tokens[index - 1][0]
            item_label = {'replicons': 'Reference', 'dedicated_candidates': 'Candidate', 'placements': 'Alignment', 'second_copy_evidence': 'Additional-copy candidate', 'ambiguous_evidence': 'Unresolved candidate'}.get(collection, collection.replace('_', ' ').capitalize())
            context.append(str(name or f'{item_label} {int(number) + 1}'))
        else:
            current = current[key]
            if index < len(tokens) - 1 and key not in ('replicons', 'metrics', 'copy_screen') and (not isinstance(current, list)):
                context.append(key.replace('_', ' ').capitalize())
    key = tokens[-1][0]
    title, unit, help_text = METRIC_LABELS.get(key, (key.replace('_', ' ').capitalize(), None, ''))
    if unit == 'bp':
        number = f'{current:,.0f} bp' if float(current).is_integer() else f'{current:,g} bp'
    elif unit == 'fraction':
        number = f'{current * 100:.4f}'.rstrip('0').rstrip('.') + '%'
    elif unit == 'ratio':
        number = f'{current:.6g}×'
    elif unit == 'count':
        number = f'{current:,}'
    else:
        number = raw
    return (' · '.join((part for part in context + [title] if part)), number, help_text)

def metrics_table(value, label):
    rows = list(numeric_metrics(value))
    if not rows:
        return '<p>No continuous measurements have been recorded for this stage.</p>'
    measurements, settings = ([], [])
    for path, raw in rows:
        title, number, help_text = metric_display(value, path, raw)
        help_html = f'<small class="row-summary">{e(help_text)}</small>' if help_text else ''
        row = f'<tr><th scope="row">{e(title)}{help_html}</th><td>{e(number)}</td></tr>'
        (settings if '.copy_screen.' in path else measurements).append(row)

    def table(items, title, heading='Measurement'):
        return f'<div class="table-scroll" role="region" aria-label="{e(title)}" tabindex="0"><table><thead><tr><th scope="col">{e(heading)}</th><th scope="col">Recorded value</th></tr></thead><tbody>' + ''.join(items) + '</tbody></table></div>'
    body = table(measurements, label) if measurements else ''
    if settings:
        body += '<details><summary>Additional-copy screening settings</summary><p>Settings for screening other contigs for a possible additional copy; these are configuration values, not observed recovery measurements.</p>' + table(settings, 'Additional-copy screening settings', 'Setting') + '</details>'
    raw_rows = ''.join((f'<tr><th scope="row">{e(path)}</th><td>{e(raw)}</td></tr>' for path, raw in rows))
    body += '<details><summary>Source field names and values</summary><p>Recorded values before display formatting; no read-quality estimate is inferred.</p><div class="table-scroll" role="region" aria-label="Source field names and values" tabindex="0"><table><thead><tr><th scope="col">Source field</th><th scope="col">Raw value</th></tr></thead><tbody>' + raw_rows + '</tbody></table></div></details>'
    return f'<details><summary>{e(label)} ({len(rows)} measurements)</summary>{body}</details>' if len(rows) > 30 else body

def build_noisy(config, batch=None, output=None, document=None, include_history=True, render_context=None):
    if document is None or render_context is None:
        raise ValueError("Rendering requires sealed prepared evidence and report models")
    document = copy.deepcopy(document)
    output = output or ROOT / 'dist'
    generated = ensure_assets(ROOT)
    for name in ('assets', 'scenarios', 'data'):
        shutil.rmtree(output / name, ignore_errors=True)
        (output / name).mkdir(parents=True, exist_ok=True)
    shutil.copytree(generated, output / 'assets', dirs_exist_ok=True)
    config, cases, rows = (document['config'], document['scenarios'], document['results'])
    rows = explained_records(rows, cases)
    document['results'] = rows
    document = enrich_graph_artifacts(document, batch)
    rows = document['results']
    save(output / 'data/results.json', document)
    with (output / 'data/results.tsv').open('w', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerow(['scenario', 'tool', 'status', 'exact_status', 'tolerant_status', 'tolerant_metrics_json'])
        writer.writerows([[row['scenario_id'], row['tool'], row['status'], row['status'], tolerant_status(row), json.dumps({key: (row.get('tolerant_assessment') or {})[key] for key in ('metrics', 'replicons') if key in (row.get('tolerant_assessment') or {})}, sort_keys=True)] for row in rows])
    write_result_pages(document, output, batch)
    exact = collections.Counter((row['status'] for row in rows))
    tolerant = collections.Counter((tolerant_status(row) for row in rows))
    body = '<div class="page-heading"><h1>Can assemblers recover plasmids from noisy reads?</h1><p>S6 compares matched error-free controls and simulated error profiles using separate exact and tolerant assessments.</p></div>'
    body += f"""<p class="run-summary">{len(cases)} scenarios · {len(rows)} assembler comparisons. Exact: {exact['pass']} pass · {exact['fail']} fail · {len(rows) - exact['pass'] - exact['fail']} unscored. Tolerant: {tolerant['pass']} pass · {tolerant['fail']} fail · {len(rows) - tolerant['pass'] - tolerant['fail']} unscored.</p>"""
    body += f'<p class="run-summary">Assembly stage: {e(batch_progress(rows))}</p>' + interpretation_guide()
    body += f'<div class="notice"><strong>Two separate endpoints</strong>{CAUTION} Pending or failed evaluators do not count as tolerant assembly failures.</div><div class="table-scroll" role="region" aria-label="Noisy-read result matrix" tabindex="0"><table class="matrix"><caption>Each cell retains the exact endpoint and the tolerant endpoint. Open the scenario for measurements, policies and recorded stage status.</caption><thead><tr><th scope="col">Scenario</th>'
    body += ''.join((f'<th scope="col">{e(LABELS[tool])}</th>' for tool in config['tools'])) + '</tr></thead><tbody>'
    for case in cases:
        body += f"""<tr><th scope="row"><a href="scenarios/{e(case['id'])}.html">{e(display_title(case))}</a><span class="row-summary">S6 · {e(case['organism'])}</span></th>"""
        for tool in config['tools']:
            row = next((row for row in rows if row['scenario_id'] == case['id'] and row['tool'] == tool))
            body += f'''<td data-tool="{e(tool)}" data-status="{e(row['status'])}"><a class="result-link" href="{e(result_href(row))}">Exact: {badge(row['status'])}</a><span class="row-summary">Tolerant: {tolerant_badge(row)}</span></td>'''
        body += '</tr>'
    body += f"""</tbody></table></div><div class="downloads"><a href="data/results.json">Download JSON</a><a href="data/results.tsv">Download TSV</a><span>Updated {e(document['generated_at'])} · Batch {e(document['batch'] or 'not submitted')}</span></div>"""
    if document.get('assessment_stage') is not None:
        body += '<h2>Recorded tolerant-evaluator stage</h2>' + f"<p>{e(document['assessment_stage'].get('scheduler_state', 'See recorded counts below'))}</p>" + metrics_table(document['assessment_stage'], 'Tolerant-evaluator stage')
    (output / 'index.html').write_text(page('Noisy-read results', body))
    listing = '<h1>S6 · Simulated read errors</h1><p class="intro">Controlled error profiles use frozen reference truth. They do not establish a validated match to a particular nanopore chemistry, basecaller or library preparation.</p><ul class="scenario-list">'
    for case in cases:
        listing += f'''<li><a href="{e(case['id'])}.html">{e(display_title(case))}</a><span>{e(case['simulation']['model'])}</span></li>'''
        (output / 'scenarios' / (case['id'] + '.html')).write_text(page(display_title(case), noisy_scenario(case, document, output), '../', 'scenarios'))
    (output / 'scenarios/index.html').write_text(page('Noisy-read scenarios', listing + '</ul>', '../', 'scenarios'))
    methods = f'<h1>Noisy-read methods</h1><p>{CAUTION}</p><h2>Frozen simulation inputs</h2><p>Read generation uses the versioned scenario profile and reference truth. Observed input measurements and hashes are recorded with each scenario. Simulator targets are not substitutes for observed read quality.</p><h2>Exact and tolerant endpoints</h2><p>Exact recovery requires a unique dedicated reference-equivalent molecule. Tolerant assessments use their own recorded policy and continuous metrics. Until that evaluator supplies a result, tolerant recovery is unscored. Evaluator errors remain separate from biological failures.</p><h2>Interpretation limits</h2><p>Simulated errors alone do not model extraction losses, size selection or a verified chemistry/basecaller combination. Aligned sequence does not by itself establish correct topology or unique molecule recovery. Inspect per-tool evidence and the frozen policy before comparing outcomes.</p>'
    policy = config.get('tolerant_policy', {})
    keys = ('minimum_reference_coverage', 'minimum_alignment_identity', 'minimum_length_ratio', 'maximum_length_ratio', 'second_copy_recovery_threshold')
    if all((key in policy for key in keys)):
        methods += f"""<h2>Bounded tolerant criterion</h2><p>The first version supports circular pRK2 and pKPN7. It requires one dedicated contig with at least {policy['minimum_reference_coverage']:.0%} reference coverage, {policy['minimum_alignment_identity']:.1%} alignment identity and length between {policy['minimum_length_ratio']:.0%} and {policy['maximum_length_ratio']:.0%} of truth. Another near-complete copy at {policy['second_copy_recovery_threshold']:.0%} coverage prevents a pass. Unresolved repeat, embedded-copy or structural assignment is unscored. Chromosome recovery and physical topology are outside this tolerant endpoint.</p><p><a href="https://github.com/SPREAD-Hackathon/ploptimizer/blob/main/assembly-benchmark/TOLERANT_ENDPOINT.md">Read the full versioned endpoint and validation limits</a>.</p>"""
    (output / 'methods.html').write_text(page('Noisy-read methods', methods, active='methods'))
    (output / 'about.html').write_text(page('About', '<h1>About the noisy-read panel</h1><p>Ploptimizer runs controlled assembly comparisons on BMRC through Slurm and Pixi. This static report preserves the recorded exact and tolerant assessments.</p><p><a href="methods.html">Methods</a></p>', active='about'))
    write_archives(output, document, include_history, render_context)
    write_release_overview(output, document, include_history, render_context)
    save(output / 'vercel.json', {'cleanUrls': True})
    (output / '.vercelignore').write_text('.env*\n.vercel\n.gitignore\n')
    if batch:
        shutil.rmtree(batch / 'site', ignore_errors=True)
        shutil.copytree(output, batch / 'site', ignore=shutil.ignore_patterns('.vercel', '.env*', '.gitignore'))
    return output

def noisy_scenario(case, document, output):
    manifest = document.get('inputs', {}).get(case['id'], {})
    body = f"""<a class="back" href="s6.html">S6 family results</a><h1>{e(display_title(case))}</h1><p class="intro">S6 · Controlled read errors · {e(case['organism'])}</p><p>Simulation model: <code>{e(case['simulation']['model'])}</code>. Batch <code>{e(document['batch'] or 'not submitted')}</code>.</p><div class="notice">{CAUTION}</div><h2>Input evidence</h2>"""
    body = legacy_noise_note(case) + body
    settings = {'simulation': case['simulation'], 'error_profile': case.get('error_profile')}
    body += '<details><summary>Frozen simulation settings</summary><div class="table-scroll" role="region" aria-label="Frozen simulation settings" tabindex="0"><pre><code>' + e(json.dumps(settings, indent=2, sort_keys=True)) + '</code></pre></div></details>'
    body += f"<p>Recorded simulation status: {e(manifest.get('status', 'not collected'))}.</p>"
    holds = [(row.get('accession', 'molecule'), reason) for row in manifest.get('replicons', []) for reason in row.get('validation_holds', [])]
    if holds:
        body += '<p>Input admission is on hold. These are simulation checks, not assembler failures.</p><ul>' + ''.join((f'<li>{e(accession)}: {e(reason)}</li>' for accession, reason in holds)) + '</ul>'
    for key in ('reads_sha256', 'truth_sha256'):
        if manifest.get(key):
            body += f'<p>{e(key)}:</p><code class="checksum">{e(manifest[key])}</code>'
    body += metrics_table({key: value for key, value in manifest.items() if key not in ('case', 'simulation')}, 'Recorded input measurements')
    rows = [row for row in document['results'] if row['scenario_id'] == case['id']]
    body += '<h2>Recorded runs</h2>' + run_summary(rows, case, output=output, show_tolerant=True)
    return body + '<p><a href="../methods.html">Methods and endpoint limits</a></p>'

def tolerant_details(row):
    assessment = row.get('tolerant_assessment') or {}
    body = ''
    if assessment:
        fallback = 'Tolerant evaluation failed; no tolerant recovery conclusion is available.' if tolerant_status(row) == 'error' else 'Tolerant assessment is not complete; no tolerant recovery conclusion is available.' if tolerant_status(row) == 'unscored' else 'Separate tolerant assessment; inspect its policy and measurements below.'
        body += f"<p>{e(assessment.get('endpoint') or assessment.get('reason') or fallback)}</p>"
        if assessment.get('error'):
            body += f"<p>{e(assessment['error'])}</p>"
        molecules = assessment.get('replicons', [])
        if molecules:
            body += '<h3>Tolerant molecule assessments</h3><ul>'
            for molecule in molecules:
                status = tolerant_badge({'tolerant_assessment': molecule})
                body += f"<li>{e(molecule.get('name') or molecule.get('accession') or 'Reference molecule')}: {status} · {e(molecule.get('reason', 'Inspect recorded molecule measurements.'))}</li>"
            body += '</ul>'
        body += metrics_table({key: assessment[key] for key in ('metrics', 'replicons') if key in assessment}, 'Tolerant recovery measurements')
        if assessment.get('endpoint_version') or assessment.get('limitations'):
            body += f"""<p class="muted">{e(assessment.get('endpoint_version', ''))} {e(assessment.get('limitations', ''))}</p>"""
        if assessment.get('policy'):
            body += '<details><summary>Tolerant assessment policy</summary><div class="table-scroll" role="region" aria-label="Tolerant assessment policy" tabindex="0"><pre><code>' + e(json.dumps(assessment['policy'], indent=2, sort_keys=True)) + '</code></pre></div></details>'
    else:
        body += '<p>Awaiting tolerant evaluator. No tolerant recovery conclusion is available.</p>'
    return body
