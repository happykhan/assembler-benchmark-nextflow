"""Generate a static, evidence-backed result matrix and scenario pages."""
import copy
import csv
import datetime
import html
import shutil
from pathlib import Path
from .result_model import case_title
from .assets import ensure_assets
from .common import ROOT, digest, fingerprint, load, save
from .evidence_model import diagnostic_policy, alignment_classification, candidate_labels, diagnostic_state, diagnostic_summary, molecule_explanation
from .result_pages import enrich_graph_artifacts, result_href, write_result_pages
LABELS = {'flye': 'Flye (default)', 'flye-meta': 'Flye (--meta)', 'raven': 'Raven', 'plassembler': 'Plassembler long'}
LABELS['miniasm'] = 'Miniasm (unpolished)'
LABELS['miniasm-plus'] = 'Miniasm + Minipolish'
STATUSES = {'pass': 'Pass', 'fail': 'Fail', 'not_run': 'Not run', 'pending': 'Queued', 'running': 'Running', 'error': 'Job error', 'timeout': 'Fail — did not complete', 'invalid_input': 'Invalid input'}
CATEGORIES = {'S5': ('Linear plasmids and terminal repeats', 'Linear references with standard and long read-length targets. Input sequences retain their recorded ends.'), 'S1': ('Error-free recovery', 'Chromosome-only controls, individual native plasmids and complete deposited complements. These cases establish the baseline for each reference.'), 'S4': ('Small plasmids and read length', 'Compare short, baseline and long read-length targets for small plasmids individually and in their native complements. Achieved read lengths are capped to one molecule circumference; targets describe simulation settings, not nanopore chemistry.'), 'S2': ('Relative plasmid coverage', 'Hold chromosome depth and read properties fixed, and vary plasmid depth at 0.8×, 1×, 1.2×, 3× and 5× relative to it. These are coverage ratios, not measured biological copy numbers.')}

def e(value):
    return html.escape(str(value))

def badge(status):
    return f'<span class="status {e(status)}" data-benchmark-status="{e(status)}">{e(STATUSES[status])}</span>'

def site_root(output):
    """Public base for root and batch directories, including slashless index URLs."""
    output = Path(output)
    return f'/batches/{output.name}/' if output.parent.name == 'batches' else '/'

def page(title, body, prefix='', active='overview', base_href=None):
    links = [('overview', 'index.html', 'Results'), ('scenarios', 'scenarios/index.html', 'Scenarios'), ('aggregate', 'aggregate.html', 'Aggregate plots'), ('methods', 'methods.html', 'Methods')]
    base = f'<base href="{e(base_href)}">' if base_href is not None else ''
    nav = ''.join(('<a {} href="{}">{}</a>'.format('aria-current=page' if key == active else '', '/aggregate.html' if key == 'aggregate' else prefix + url, label) for key, url, label in links))
    return f'''<!doctype html><html lang="en" data-theme="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n{base}<title>{e(title)} · Ploptimizer</title><meta name="description" content="Long-read plasmid assembly benchmark: scenarios, exact recovery outcomes and execution evidence.">\n<script>try{{var theme=localStorage.getItem('gx-theme');if(theme==='light'||theme==='dark')document.documentElement.dataset.theme=theme;}}catch{{}}</script>\n<link rel="stylesheet" href="{prefix}assets/genomicx.css"><script defer src="{prefix}assets/genomicx.js"></script></head><body><a class="skip" href="#main">Skip to content</a>\n<div id="genomicx-nav"><header class="fallback-nav"><a href="{prefix}index.html">Ploptimizer</a><nav aria-label="Main navigation">{nav}</nav></header></div>\n<main id="main">{body}</main></body></html>'''

def result_status(record, scheduler_state):
    status = record.get('status', 'not_run')
    terminal_errors = ('FAILED', 'CANCELLED', 'OUT_OF_MEMORY', 'NODE_FAIL', 'BOOT_FAIL', 'DEADLINE', 'PREEMPTED', 'DEPENDENCY')
    if status in ('pass', 'fail', 'error', 'timeout', 'invalid_input'):
        return status
    if scheduler_state.startswith('TIMEOUT'):
        return 'timeout'
    if scheduler_state.startswith(terminal_errors) or scheduler_state.startswith('COMPLETED'):
        return 'error'
    if scheduler_state.startswith(('RUNNING', 'COMPLETING')):
        return 'running'
    if scheduler_state:
        return 'pending'
    return status

def build(config, batch=None, output=None, document=None, include_history=True, render_context=None):
    if document is None or render_context is None:
        raise ValueError("Rendering requires sealed prepared evidence and report models")
    if config.get('noisy_panel') or (document and document['config'].get('noisy_panel')):
        from .noisy_report import build_noisy
        return build_noisy(config, batch, output, document, include_history, render_context)
    if config.get('determinism') or (document and document['config'].get('determinism')):
        from .repeat_report import build_repeat
        return build_repeat(config, batch, output, document, include_history, render_context)
    output = output or ROOT / 'dist'
    generated_assets = ensure_assets(ROOT)
    for name in ('assets', 'scenarios', 'data'):
        if (output / name).exists():
            shutil.rmtree(output / name)
    (output / 'assets').mkdir(parents=True, exist_ok=True)
    (output / 'scenarios').mkdir(exist_ok=True)
    (output / 'data').mkdir(exist_ok=True)
    shutil.copytree(generated_assets, output / 'assets', dirs_exist_ok=True)
    snapshot = ROOT / 'published/latest.json'
    document = copy.deepcopy(document or load(snapshot))
    config = document['config']
    cases = document['scenarios']
    results = document['results']
    generated = document['generated_at']
    results = explained_records(results, cases)
    document['results'] = results
    document = enrich_graph_artifacts(document, batch)
    results = document['results']
    save(output / 'data/results.json', document)
    with (output / 'data/results.tsv').open('w', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerow(['scenario', 'tool', 'status', 'plasmid_passes', 'plasmid_total', 'elapsed_seconds', 'peak_memory_kb'])
        for row in results:
            score = row.get('evaluation', {})
            writer.writerow([row['scenario_id'], row['tool'], row['status'], score.get('plasmid_passes'), score.get('plasmid_total'), row.get('elapsed_seconds'), row.get('peak_memory_kb')])
    write_diagnostic_tsv(output, cases, results)
    write_result_pages(document, output, batch)
    counts = {tool: {status: sum((r['tool'] == tool and r['status'] == status for r in results)) for status in STATUSES} for tool in config['tools']}
    completed = sum((r['status'] in ('pass', 'fail') for r in results))
    valid_inputs = sum((item['status'] == 'valid' for item in document.get('inputs', {}).values()))
    headline = f'{completed} of {len(results)} comparisons scored · {len(cases)} scenarios · {valid_inputs} inputs ready'
    body = f'<div class="page-heading"><h1>Assembly benchmark results</h1><p>Whole-scenario exact recovery under error-free reads. Chromosome-only controls use their declared endpoints; these counts describe this batch, not a general assembler ranking.</p></div><p class="run-summary">Batch total: {headline}</p>'
    body += f'<p class="run-summary">{e(batch_progress(results))}</p>'
    body += interpretation_guide()
    body += '<div class="notice"><strong>What counts as an exact pass?</strong> In plasmid-containing cases, every expected plasmid must appear exactly once as a complete, separate sequence. A circular sequence may start anywhere or be reverse-complemented. An exact fail means no unique, complete reference-equivalent molecule; it does not mean no plasmid sequence. Recovery evidence and possible explanations are separate from the score.</div>'
    category_options = ''.join((f'<option value="{key}">{key} · {e(CATEGORIES[key][0])}</option>' for key in sorted({c['category'] for c in cases})))
    body += f'<div class="filters"><label>Scenario category<select id="category-filter" disabled><option value="">All categories</option>{category_options}</select></label><label>Species<select id="species-filter" disabled><option value="">All species</option><option value="Escherichia">E. coli</option><option value="Klebsiella">K. pneumoniae</option></select></label><span id="filter-count" aria-live="polite">{len(cases)} scenarios shown</span></div>'
    body += '<div class="table-scroll" role="region" aria-label="Assembler result matrix" tabindex="0"><table class="matrix"><caption>Pass/fail counts use the exact endpoint. Text below each result describes supporting evidence, not a second score. Open a result to inspect its measurements and explanation. The chromosome-only control uses a separate endpoint.</caption><thead><tr><th scope="col">Scenario</th>'
    for tool in config['tools']:
        c = counts[tool]
        unresolved = len(cases) - c['pass'] - c['fail']
        body += f'''<th scope="col">{e(LABELS[tool])}<span class="column-summary" data-summary-tool="{tool}">{c['pass']} pass · {c['fail']} fail · {unresolved} unscored</span></th>'''
    body += '</tr></thead><tbody>'
    for case in cases:
        plasmids = [r for r in case['replicons'] if r['molecule_type'] == 'plasmid']
        sizes = ', '.join((f"{r['length_bp'] / 1000:.1f} kb" for r in plasmids)) or 'Negative control'
        noun = 'plasmid' if len(plasmids) == 1 else 'plasmids'
        body += f'''<tr data-category="{case['category']}" data-species="{case['organism'].split()[0]}"><th scope="row"><a href="scenarios/{e(case['id'])}.html">{e(case_title(case))}</a><span class="row-summary"><span class="category-label">{case['category']}</span> · {len(plasmids)} {noun} · {e(sizes)}</span></th>'''
        for tool in config['tools']:
            row = next((r for r in results if r['scenario_id'] == case['id'] and r['tool'] == tool))
            body += f'''<td data-tool="{tool}" data-status="{row['status']}"><a class="result-link" href="{e(result_href(row))}">Exact: {badge(row['status'])}</a><span class="row-summary">{e(diagnostic_summary(row, case))}</span></td>'''
        body += '</tr>'
    body += '</tbody></table></div><p class="legend">Pass and fail are completed sequence assessments. Queued, running, invalid inputs and job errors are unscored; they are never counted as scientific failures.</p>'
    body += f"""<div class="downloads"><a href="data/results.json">Download JSON</a><a href="data/results.tsv">Download TSV</a><a href="data/recovery-evidence.tsv">Recovery evidence TSV</a><span>Updated {e(generated)} · Batch {e(document['batch'] or 'not submitted')}</span></div>"""
    (output / 'index.html').write_text(page('Results', body))
    category = '<h1>Scenarios</h1><p class="intro">Controlled cases with known reference molecules. Start with exact reads, then add complexity one factor at a time.</p>'
    for key in sorted({case['category'] for case in cases}):
        name, description = CATEGORIES[key]
        category += f'<h2>{key} · {e(name)}</h2><p>{e(description)}</p><ul class="scenario-list">'
        for case in (c for c in cases if c['category'] == key):
            category += f'''<li><a href="{case['id']}.html">{e(case_title(case))}</a><span>{e(case['truth_type'].replace('_', ' '))}</span></li>'''
        category += '</ul>'
    for case in cases:
        rows = [r for r in results if r['scenario_id'] == case['id']]
        (output / 'scenarios' / (case['id'] + '.html')).write_text(page(case_title(case), scenario_page(case, rows, batch, document.get('inputs', {}).get(case['id']), output, document['batch']), '../', 'scenarios'))
    category += '<p><a href="../index.html">Return to the results overview</a> to explore all scenario families.</p>'
    (output / 'scenarios/index.html').write_text(page('Scenarios', category, '../', 'scenarios', base_href=site_root(output) + 'scenarios/'))
    methods = (ROOT / 'website/methods.html').read_text()
    (output / 'methods.html').write_text(page('Methods', methods, active='methods'))
    about = '<h1>About Ploptimizer</h1><p class="intro">A benchmark for the assembly problems that disappear inside whole-genome summary scores.</p><p>We assess whether long-read assembly workflows recover chromosomes and plasmids correctly, starting with E. coli and K. pneumoniae. Controlled reference subsets, coverage panels and explicit sequence endpoints make individual failures inspectable.</p><p>The results matrix links to the inputs, tool configuration, run evidence and limitations for each scenario. Runs execute on the BMRC cluster using Slurm and Pixi; this site presents static result snapshots.</p><p><a href="methods.html">Read the methods</a> or <a href="https://github.com/SPREAD-Hackathon/ploptimizer/tree/main/assembly-benchmark">inspect the source and brief</a>.</p>'
    (output / 'about.html').write_text(page('About', about, active='about'))
    write_archives(output, document, include_history, render_context)
    write_release_overview(output, document, include_history, render_context)
    save(output / 'vercel.json', {'cleanUrls': True, 'redirects': [{'source': source, 'destination': '/', 'permanent': True} for source in ('/history', '/history.html', '/batches/:batch/history', '/batches/:batch/history.html')]})
    (output / '.vercelignore').write_text('.env*\n.vercel\n.gitignore\n')
    if batch:
        destination = batch / 'site'
        shutil.rmtree(destination, ignore_errors=True)
        shutil.copytree(output, destination, dirs_exist_ok=True, ignore=shutil.ignore_patterns('.vercel', '.env*', '.gitignore'))
    return output

def scenario_page(case, rows, batch, manifest=None, output=None, batch_id=None):
    settings = case['simulation']
    category_name, category_description = CATEGORIES[case['category']]
    body = f'''<a class="back" href="{case['category'].lower()}.html">{case['category']} family results</a><h1>{e(case_title(case))}</h1><p class="intro">{case['category']} · {e(category_name)} · {e(case['organism'])}</p><p>{e(category_description)}</p>'''
    if batch_id:
        body += f'<p class="muted">Batch <code>{e(batch_id)}</code></p>'
    if case['category'] == 'S5':
        body += '<h2>What this case tests</h2><p>Can the isolated linear plasmid be recovered as one exact sequence with both physical ends intact? This input has no chromosome and does not represent a native host complement. Circular rotation is not accepted.</p>'
    else:
        body += '<h2>What this case tests</h2><p>Can each expected plasmid be recovered once as an exact, dedicated molecule alongside the chromosome? For the chromosome-only control, the endpoint checks the expected chromosome/no-plasmid output instead.</p>'
    source_url = case.get('reference_url') or f"https://www.ncbi.nlm.nih.gov/datasets/genome/{case['assembly_accession']}/"
    source_label = case.get('reference_accession') or case['assembly_accession']
    body += f'''<p>Source: <a href="{e(source_url)}">{e(source_label)}</a>. This case is a {e(case['truth_type'].replace('_', ' '))}. The reference inventory is sequence-checked during preparation; independent biological validation remains a separate curation task.</p>'''
    input_path = batch / 'cases' / case['id'] / 'input.json' if batch else None
    if manifest is None:
        manifest = load(input_path) if input_path and input_path.exists() else None
    stats = {r['accession']: r for r in manifest['replicons']} if manifest else {}
    if case['category'] == 'S5':
        anchor = min(case['replicons'][0]['length_bp'], settings['linear_terminal_read_length'])
        body += f"<h2>Read generation</h2><p>Error-free linear sampling with lognormal length target {settings['length_mean']:,} bp (SD {settings['length_sd']:,} bp), clipped to {settings['length_min']:,}–{settings['length_max']:,} bp and molecule length. Two declared {anchor:,} bp reads anchor each physical end, one per orientation; remaining starts and strands are random. Reads never wrap across ends. Target depth is {settings['chromosome_depth'] * settings['plasmid_relative_depth']}×; complete input breadth and both terminal anchors are required. Seed {settings['seed']}. These terminal reads define an ideal-data control, not a library-preparation model.</p>"
    else:
        body += f"<h2>Read generation</h2><p>Exact sequence sampling; lognormal length targets with mean {settings['length_mean']:,} bp and SD {settings['length_sd']:,} bp, clipped to {settings['length_min']:,}–{settings['length_max']:,} bp and one circumference. Random starts and both strands; no sequencing errors, adapters or chimeras. Q{settings['fastq_phred']} is a synthetic FASTQ placeholder. Small molecules have a shorter achieved distribution.</p><p>Target chromosome depth {settings['chromosome_depth']}×; plasmid relative depth {settings['plasmid_relative_depth']}×. Seed {settings['seed']}. Sampling stops after the target is reached, allowing up to one read of overshoot per molecule.</p>"
    body += '<div class="table-scroll" tabindex="0" role="region" aria-label="Reference molecules"><table><thead><tr><th scope="col">Molecule</th><th scope="col">Accession</th><th scope="col">Size</th><th scope="col">Achieved depth</th><th scope="col">Breadth</th><th scope="col">Read count</th><th scope="col">Read length mean / range</th></tr></thead><tbody>'
    for r in case['replicons']:
        observed = stats.get(r['refseq_accession'])
        depth = f"{observed['achieved_depth']:.2f}×" if observed else 'Not generated'
        breadth = f"{observed['breadth']:.2%}" if observed else 'Not generated'
        read_count = f"{observed['read_count']:,}" if observed else 'Not generated'
        lengths = f"{observed['mean_read_length']:,.0f} / {observed['minimum_read_length']:,}–{observed['maximum_read_length']:,} bp" if observed else 'Not generated'
        body += f"""<tr><th scope="row">{e(r['replicon_name'])}</th><td><a href="https://www.ncbi.nlm.nih.gov/nuccore/{r['refseq_accession']}">{r['refseq_accession']}</a></td><td>{r['length_bp']:,} bp</td><td>{depth}</td><td>{breadth}</td><td>{read_count}</td><td>{lengths}</td></tr>"""
    body += '</tbody></table></div><h2>Recorded runs</h2>'
    body += run_summary(rows, case, output=output)
    if manifest:
        body += f"""<h2>Input evidence</h2><p>Input validation: <strong>{e(manifest['status'])}</strong>. Read-file SHA-256:</p><code class="checksum">{manifest['reads_sha256']}</code>"""
    body += '<p><a href="../methods.html">Read the scoring rules and limitations</a></p>'
    return body

def write_archives(output, document, include_history=True, render_context=None):
    """Keep source result routes without publishing a batch-history index."""
    (output / 'history.html').unlink(missing_ok=True)
    if not include_history:
        return
    shutil.rmtree(output / 'batches', ignore_errors=True)
    archives = render_context['documents'].values() if render_context is not None else (load(path) for path in sorted((ROOT / 'published').glob('*.json'), reverse=True) if path.name != 'latest.json')
    for archived in archives:
        if archived['batch'] == document['batch']:
            continue
        build(archived['config'], output=output / 'batches' / archived['batch'], document=archived, include_history=False, render_context=render_context)

def diagnostic_table(diagnostic, plasmid_only=False, evaluation=None, prepared=None):
    if diagnostic.get('status') != 'complete':
        body = f'<p>{e(diagnostic_state(diagnostic))}. Supplementary recovery evidence is unavailable; the strict score is unchanged.</p>'
        if diagnostic.get('error') or diagnostic.get('reason'):
            body += f"""<p class="muted">{e(diagnostic.get('error') or diagnostic['reason'])}</p>"""
        return body
    policy = diagnostic_policy(diagnostic)
    body = '<h4>Aligned recovery evidence</h4><p class="muted">Supplementary mapping evidence; the exact pass/fail score is unchanged. Candidate flags need review and do not establish topology or a structural error.</p>'
    if plasmid_only:
        body += '<p class="muted">Final plasmid output only; retained chromosome recovery is assessed separately.</p>'
    rows = [row for row in diagnostic['evidence']['replicons'] if not (plasmid_only and row['molecule_type'] == 'chromosome')]
    prepared_rows = {row['exact']['accession']: row for row in prepared['molecules']} if prepared else {}
    scores = {row['accession']: row for row in (evaluation or {}).get('replicons', [])}
    if rows:
        body += '<ul>'
        for row in rows:
            description = prepared_rows[row['accession']]['mapping_description'] if prepared else molecule_explanation(row, policy, scores.get(row['accession']))
            body += f"<li><strong>{e(row['name'])}</strong>: {e(description)}</li>"
        body += '</ul>'
    else:
        body += '<p>No plasmids are expected in this control. The final plasmid output does not assess chromosome recovery.</p>' if plasmid_only else '<p>No molecule-level mapping evidence has been collected.</p>'
    body += '<details><summary>Alignment measurements, thresholds and limitations</summary><div class="table-scroll" role="region" aria-label="Aligned recovery evidence" tabindex="0"><table><thead><tr><th scope="col">Molecule</th><th scope="col">Aligned reference</th><th scope="col">Alignment identity</th><th scope="col">Supporting contigs</th><th scope="col">Candidate evidence</th></tr></thead><tbody>'
    for row in rows:
        identity = f"{row['alignment_identity']:.3%}" if row['alignment_identity'] is not None else 'Not estimated'
        labels = prepared_rows[row['accession']]['candidate_labels'] if prepared else candidate_labels(row)
        kind = prepared_rows[row['accession']]['mapping_kind'] if prepared else alignment_classification(row, policy)[0]
        flags = 'Candidate ' + ', '.join(labels) if labels else 'No retained alignment' if kind == 'none' else 'No flags under this policy'
        body += f"""<tr><th scope="row">{e(row['name'])}</th><td>{row['aligned_reference_bp']:,}/{row['length_bp']:,} bp ({row['recovered_fraction']:.2%})</td><td>{identity}</td><td>{row['contig_count']}</td><td>{e(flags)}</td></tr>"""
    body += '</tbody></table></div>'
    body += f"""<p class="muted">Retained alignments require mapQ ≥{policy['minimum_mapq']}, at least {policy['minimum_aligned_bp']} aligned reference bases and identity ≥{policy['minimum_identity']:.0%}; secondary, ambiguous-base and non-base-aligned records are excluded. Near-full means ≥{policy['complete_fraction']:.0%} aligned reference coverage, not exact recovery. Candidate fragmentation requires multiple contigs, best-contig coverage below {policy['complete_fraction']:.0%} and a union gain of at least {policy['fragmentation_gain_fraction']:.0%}; candidate duplication requires overlapping reference coverage ≥{policy['duplication_fraction']:.0%}; candidate joins use distinct reference molecules on query segments overlapping by at most {policy['maximum_query_overlap_fraction']:.0%}. These flags do not establish a structural error.</p>"""
    body += f"""<p class="muted">Mapper: {e(diagnostic.get('mapper_version', 'unknown'))}. {e(diagnostic['evidence']['limitations'])}</p></details>"""
    return body

def attach_diagnostics(record, path):
    diagnostic_path = path.parent / 'diagnostics.json' if path else None
    if record and diagnostic_path and diagnostic_path.exists():
        diagnostic = load(diagnostic_path)
        hashes = diagnostic.get('input_hashes', {})
        if hashes.get('execution_sha256') == digest(path) and hashes.get('assembly_sha256') == record.get('assembly_sha256'):
            record['diagnostics'] = {key: value for key, value in diagnostic.items() if key != 'command'}
    return record

def write_diagnostic_tsv(output, cases, results):
    """Export molecule-level mapping evidence with explicit unavailable states."""
    by_id = {case['id']: case for case in cases}
    fields = ('scenario_id', 'tool', 'accession', 'molecule_name', 'molecule_type', 'strict_status', 'diagnostics_status', 'aligned_reference_fraction', 'alignment_identity', 'contig_count', 'candidate_fragmentation', 'candidate_duplication', 'candidate_join', 'no_retained_alignment', 'minimum_mapq', 'minimum_aligned_bp', 'minimum_identity', 'near_full_fraction')
    with (output / 'data/recovery-evidence.tsv').open('w', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerow(fields)
        for record in results:
            diagnostic = record.get('diagnostics') or {}
            available = diagnostic.get('status') == 'complete'
            observed = {row['accession']: row for row in diagnostic.get('evidence', {}).get('replicons', [])} if available else {}
            scores = {row['accession']: row['status'] for row in record.get('evaluation', {}).get('replicons', [])}
            policy = diagnostic_policy(diagnostic)
            for molecule in by_id[record['scenario_id']]['replicons']:
                if record['tool'] == 'plassembler' and molecule['molecule_type'] == 'chromosome':
                    continue
                accession = molecule['refseq_accession']
                row = observed.get(accession, {})
                flags = row.get('candidate_flags', {})
                writer.writerow([record['scenario_id'], record['tool'], accession, molecule['replicon_name'], molecule['molecule_type'], scores.get(accession), diagnostic.get('status', 'not_available'), row.get('recovered_fraction'), row.get('alignment_identity'), row.get('contig_count'), flags.get('fragmented'), flags.get('duplicated'), flags.get('joined'), flags.get('no_supported_alignment'), *[policy[key] if available else None for key in ('minimum_mapq', 'minimum_aligned_bp', 'minimum_identity', 'complete_fraction')]])

def batch_progress(rows, noun='comparisons'):
    """Describe execution completeness without counting infrastructure errors as fails."""
    if not rows:
        return 'No comparisons recorded.'
    scored = sum((row['status'] in ('pass', 'fail') for row in rows))
    active = sum((row['status'] in ('pending', 'running') for row in rows))
    unrun = sum((row['status'] == 'not_run' for row in rows))
    errors = len(rows) - scored - active - unrun
    if scored == len(rows):
        return f'Complete: all {len(rows)} {noun} have a sequence assessment.'
    if active:
        return f'In progress: {scored} assessed; {active} queued or running; {errors} unscored execution outcomes; {unrun} not run.'
    if unrun:
        return f'{scored} assessed; {unrun} not run; {errors} unscored execution outcomes.'
    return f'Runs finished: {scored} sequence assessments; {errors} execution errors, timeouts or invalid inputs remain unscored.'

def interpretation_guide():
    return '<details><summary>How to read exact scores, recovery evidence and explanations</summary><ul><li><strong>Exact pass/fail:</strong> whether the saved output meets the declared sequence endpoint. A fail can still contain most or all plasmid sequence.</li><li><strong>Full or near-full aligned recovery:</strong> mapping supports retained sequence; errors, extra copies or joins can still prevent an exact dedicated molecule.</li><li><strong>No retained alignment:</strong> the mapper found no alignment passing this policy. Short or repeated sequence can be filtered; absence is not established.</li><li><strong>Candidate fragmentation, duplication or join:</strong> a mapping pattern to review, not a confirmed structural error. More than one flag can apply.</li><li><strong>Verified observation, suspected explanation or unresolved:</strong> how strongly the saved evidence supports the explanation. A verified sequence observation does not automatically establish its software-internal cause.</li></ul><p>Job errors, invalid inputs and missing assessments are unscored. Open the scenario for input checks, individual molecules and downloadable evidence.</p></details>'

def finding_panel(record, case=None, compact=False):
    """Present evidence certainty separately from the immutable scientific endpoint."""
    if record['status'] in ('not_run', 'pending', 'running'):
        return '<p class="muted">No completed result to explain yet.</p>'
    finding = record.get('explanation')
    if not finding:
        from .explanations import explain_result
        finding = explain_result(record, case=case)
    labels = {'confirmed': 'Verified observation', 'suspected': 'Suspected explanation', 'unresolved': 'Unresolved explanation'}
    label = labels.get(finding.get('confidence'), 'Unresolved explanation')
    body = f"<p><strong>{e(label)}:</strong> {e(finding.get('symptom', 'No recorded explanation'))}</p>"
    if finding.get('interpretation'):
        body += f"<p>{e(finding['interpretation'])}</p>"
    evidence = finding.get('evidence') or []
    if evidence:
        body += '<details><summary>Supporting evidence</summary><ul>'
        for item in evidence:
            text = item.get('text', '') if isinstance(item, dict) else str(item)
            source = item.get('source') if isinstance(item, dict) else None
            body += f'<li>{e(text)}' + (f' <span class="muted">Source: {e(source)}</span>' if source else '') + '</li>'
        body += '</ul></details>'
    if finding.get('confidence_scope'):
        body += f"""<p class="muted">Evidence scope: {e(finding['confidence_scope'])}</p>"""
    if record['status'] != 'pass' and finding.get('mechanism_confidence') == 'unresolved':
        body += '<p class="muted">The software-internal cause remains unresolved.</p>'
    review = record.get('sequence_review') or {}
    source = review.get('source_document')
    if source in {'FAILURE_REVIEW.md', 'FLYE_HYPOTHESES.md', 'RAVEN_CAUSE_REVIEW.md'}:
        body += f"""<p><a href="https://github.com/SPREAD-Hackathon/ploptimizer/blob/main/assembly-benchmark/{source}">Read the checked evidence review</a>. {e(review.get('scope', 'This observation applies to the matching saved artefact.'))}</p>"""
    if compact:
        return f'<details><summary>{e(label)}: inspect this execution</summary>{body}</details>'
    return '<div class="notice"><strong>What this result shows</strong>' + body + '</div>'

def execution_evidence(record, case=None):
    """Add a reproducible explanation to downloads without rewriting source records."""
    public = {key: value for key, value in record.items() if key not in ('host', 'assembly_file', 'command', 'graph_artifacts')}
    public['command'] = ['<workdir>' + str(value)[str(value).index('/runs/'):] if '/runs/' in str(value) else str(value).replace(str(ROOT), '<workdir>') for value in record.get('command', [])]
    if record.get('assembly_workflow'):
        public['assembly_workflow'] = copy.deepcopy(record['assembly_workflow'])
        for step in public['assembly_workflow'].get('steps', []):

            def redact(value):
                value = str(value)
                return '<workdir>' + value[value.index('/runs/'):] if '/runs/' in value else value.replace(str(ROOT), '<workdir>')
            step['command'] = [redact(arg) for arg in step.get('command', [])]
            if step.get('stdout_file'):
                step['stdout_file'] = redact(step['stdout_file'])
    if not public.get('explanation'):
        from .explanations import explain_result
        public['explanation'] = explain_result(record, case=case)
    return public

def explained_records(rows, cases):
    """Fill missing presentation metadata; retain existing log-backed explanations."""
    by_id = {case['id']: case for case in cases}
    result = []
    for row in rows:
        if row.get('report_evidence'):
            result.append(row)
            continue
        reviewed = row.get('sequence_review', {}).get('status') == 'verified'
        if row.get('explanation') and (not (reviewed and row['explanation'].get('source') != 'curated_review')):
            result.append(row)
        else:
            from .explanations import attach_explanation
            result.append(attach_explanation(row, case=by_id.get(row['scenario_id'])))
    return result

def run_summary(rows, case, prefix='../', output=None, show_tolerant=False):
    """Concise case view; narratives and topology stay on result pages."""
    heading = '<th scope="col">Tolerant status</th>' if show_tolerant else ''
    body = '<div class="table-scroll" role="region" aria-label="Recorded run summary" tabindex="0"><table class="run-summary-table" data-table-kind="case"><caption>Recorded execution outcomes. Open a result for its scoring, explanation, contigs and graph.</caption><thead><tr><th scope="col">Assembler / version</th><th scope="col">Threads / repeat</th><th scope="col">Exact status</th>' + heading + '<th scope="col">Elapsed</th><th scope="col">Result</th></tr></thead><tbody>'
    seen = set()
    for row in rows:
        anchor = row['tool'] if row['tool'] not in seen else row['tool'] + '-' + row.get('run_id', str(len(seen)))
        seen.add(row['tool'])
        threads = str(row['threads']) + ' threads' if row.get('threads') is not None else 'Not recorded'
        if row.get('repeat') is not None:
            threads += ' · repeat ' + str(row['repeat'])
        elapsed = f"{row['elapsed_seconds']:.1f} s" if row.get('elapsed_seconds') is not None else 'Not recorded'
        body += f'''<tr id="{e(anchor)}"><th scope="row">{e(LABELS[row['tool']])}<small>{e(row.get('version') or 'Version not recorded')}</small></th><td>{e(threads)}</td><td>{badge(row['status'])}</td>'''
        if show_tolerant:
            from .noisy_report import tolerant_badge
            body += '<td>' + tolerant_badge(row) + '</td>'
        body += f'<td>{elapsed}</td><td><a href="{e(result_href(row, prefix))}">Result details</a>'
        if output is not None:
            suffix = '-' + row['run_id'] if row.get('run_id') else ''
            name = case['id'] + '-' + row['tool'] + suffix + '.json'
            save(output / 'data' / name, execution_evidence(row, case))
            body += f' · <a href="{e(prefix)}data/{e(name)}">JSON</a>'
        body += '</td></tr>'
    return body + '</tbody></table></div>'

def write_release_overview(output, document, include_history=True, render_context=None):
    """Replace navigation pages, preserving scientific files and individual results."""
    if not document.get('batch'):
        return None
    from .overview import FAMILIES, build_overview, render_home, write_overview
    families = ['S3'] if document['config'].get('determinism') else [key for key in FAMILIES if any((case.get('category') == key for case in document['scenarios']))]
    local = {'schema_version': 1, 'primary_batches': [document['batch']], 'families': families, 'tools': document['config']['tools']}
    if document['config'].get('determinism') or document['config'].get('noisy_panel'):
        shutil.copy2(output / 'index.html', output / 'batch-details.html')
    else:
        local_model = render_context['models'][document['batch']] if render_context is not None else build_overview([document], cohort=local, archived_batch=document['batch'])
        (output / 'batch-details.html').write_text(page('Batch summary', render_home(local_model)))
    documents = {document['batch']: document}
    if include_history:
        archives = render_context['documents'].values() if render_context is not None else (load(path) for path in sorted((ROOT / 'published').glob('*.json')) if path.name != 'latest.json')
        for archived in archives:
            if archived['batch'] not in documents:
                documents[archived['batch']] = archived
    model = write_overview(list(documents.values()), output, cohort=None if include_history else local, archived_batch=None if include_history else document['batch'], model=(render_context['overview'] if include_history else render_context['models'][document['batch']]) if render_context is not None else None)
    catalog = '<h1>Scenario families</h1><p>Choose a family for genome, assembler and execution summaries.</p><ul class="scenario-list">'
    for family in model['families']:
        href = family['href'].removeprefix('scenarios/')
        catalog += f'''<li><a href="{e(href)}">{family['id']} · {e(family['title'])}</a><span>{family['counts']['total']} runs</span></li>'''
    catalog += '</ul>'
    if document['scenarios']:
        catalog += '<details><summary>Individual input cases in this batch</summary><ul class="scenario-list">'
        catalog += ''.join((f'''<li><a href="{e(case['id'])}.html">{e(case_title(case))}</a></li>''' for case in document['scenarios'])) + '</ul></details>'
    (output / 'scenarios/index.html').write_text(page('Scenario families', catalog, '../', 'scenarios', base_href=site_root(output) + 'scenarios/'))
    return model
