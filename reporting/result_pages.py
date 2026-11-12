"""Per-execution evidence pages and source-labelled assembly graph inspection."""
import copy
import json
import re
import shutil
from .result_model import case_title
from .identities import result_slug, result_href

def write_download(path, document):
    """Keep large metadata downloads compact without changing their JSON content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=True, separators=(',', ':')) + '\n')

def graph_artifact(record, execution_path=None):
    if record.get('graph_artifacts'):
        artifact = copy.deepcopy(record['graph_artifacts'])
        attached_hash = artifact.get('input_hashes', {}).get('assembly_sha256')
        if attached_hash and record.get('assembly_sha256') and (attached_hash != record['assembly_sha256']):
            return {'status': 'not_collected', 'reason': 'Collected graph metadata do not match this assembly hash; no graph or circularity claims are displayed.'}
        return artifact
    if execution_path and (execution_path.parent / 'graph_artifacts.json').is_file():
        from .graph_artifacts import attach_graph_artifacts
        return attach_graph_artifacts(record, execution_path).get('graph_artifacts', {})
    return {'schema_version': 1, 'status': 'not_collected', 'reason': 'No assembly graph or assembler circularity report was collected for this result. Missing metadata do not establish a linear molecule or a graph with no links.'}

def execution_path(batch, record):
    if batch is None:
        return None
    directory = batch / 'results' / record['scenario_id'] / record['tool']
    if record.get('run_id'):
        directory = directory / 'repeats' / record['run_id']
    return directory / 'execution.json'

def source_description(source):
    from .report import e
    source = source or {}
    role = source.get('role', 'not recorded')
    label = {'final': 'final tool output', 'initial_flye': 'initial Flye component', 'unicycler_component': 'Unicycler component', 'partial_output': 'partial output from a stopped run'}.get(role, role)
    body = f"<p>Source: <strong>{e(source.get('filename', 'not recorded'))}</strong> · role: {e(label)}.</p>"
    if source.get('file_sha256'):
        body += f"""<details><summary>Source-file SHA-256</summary><code class="checksum">{e(source['file_sha256'])}</code></details>"""
    return body

def contig_section(record, artifact):
    from .report import e
    info = artifact.get('assembly_info') or {}
    body = '<h2 id="contigs">Contigs and assembler-reported circularity</h2>'
    if info.get('status') == 'available':
        body += source_description(info.get('source'))
        collapsed = len(info.get('contigs', [])) > 20
        if collapsed:
            body += f"<details><summary>Show all {len(info['contigs']):,} reported contigs</summary>"
        body += '<div class="table-scroll" role="region" aria-label="Reported contig inventory" tabindex="0"><table data-table-kind="contigs"><thead><tr><th scope="col">Reported contig</th><th scope="col">Reference origin</th><th scope="col">Length</th><th scope="col">Reported circularity</th><th scope="col">Reported coverage</th></tr></thead><tbody>'
        for contig in info.get('contigs', []):
            length = f"{contig['length_bp']:,} bp" if contig.get('length_bp') is not None else 'Not reported'
            labels = {'circular': 'Reported circular', 'not_circular': 'Not reported circular', 'linear': 'Reported linear', 'unknown': 'Unknown'}
            claim = labels.get(contig.get('reported_circularity'), 'Unknown')
            if contig.get('reported_circularity_raw') is not None:
                claim += ' (source value: ' + str(contig['reported_circularity_raw']) + ')'
            coverage = contig.get('reported_coverage')
            coverage = 'Not reported' if coverage is None else str(coverage)
            origin = (record.get('report_evidence') or {}).get('contig_origins', {}).get(contig['id'], {})
            status = origin.get('status', 'unassigned')
            supported = status in {'exact', 'aligned'}
            reference = (origin.get('references') or [{}])[0]
            names = ' / '.join((row['name'] for row in origin.get('references', []))) or 'Unassigned'
            label = {'exact': 'Exact sequence match', 'aligned': 'Alignment only', 'ambiguous': 'Ambiguous; multiple references', 'unassigned': 'No supported assignment'}[status]
            colour = reference.get('colour', '#92969d') if supported else '#92969d'
            light = reference.get('light_colour', '#686c73') if supported else '#686c73'
            cell = f'<span class="contig-origin" style="--reference-colour:{colour};--reference-light:{light}"><i aria-hidden="true"></i>{e(names)}</span><small class="contig-match-label">{e(label)}</small>'
            if origin.get('evidence'):
                cell += '<details><summary>Matching evidence</summary><ul>'
                cell += ''.join((f"<li>{e(item['reference_id'])} · {e(item['kind'].replace('_', ' '))} · <code>{e(item['source'])}</code></li>" for item in origin['evidence']))
                cell += '</ul></details>'
            if record.get('tool') == 'plassembler' and contig['id'] == 'chromosome' and (info.get('source', {}).get('kind') == 'plassembler_summary'):
                cell = '<span class="contig-origin-name">Artificial workflow placeholder</span><small>Plassembler no-chromosome mode; not an input molecule</small>' if record.get('workflow_mode') == 'plasmid_only_no_chromosome' else '<span class="contig-origin-name">Chromosome (tool label)</span><small>Separate output · outside plasmid score</small>'
            body += f"""<tr><th scope="row">{e(contig['id'])}</th><td>{cell}</td><td>{e(length)}</td><td>{e(claim)}</td><td>{e(coverage)}</td></tr>"""
        body += '</tbody></table></div>'
        if collapsed:
            body += '</details>'
        if not info.get('contigs'):
            body += '<p>The collected report contains no contig rows.</p>'
    else:
        if info.get('source', {}).get('file_sha256'):
            body += source_description(info['source'])
        if info.get('reason'):
            body += f"<p>Report interpretation: {e(info.get('status', 'unknown'))} · {e(info['reason'])}.</p>"
        body += '<p>No assembler circularity report or complete contig inventory is available here. Circularity is <strong>unknown</strong>; it is not labelled linear.</p>'
        score = record.get('evaluation') or {}
        if score.get('contig_count') is not None:
            scope = 'final plasmid output' if record['tool'] == 'plassembler' else 'scored output'
            body += f"<p>The saved exact evaluator recorded {score['contig_count']} contig(s) in the {scope}. That count does not provide their reported circularity.</p>"
        names = sorted({name for row in score.get('replicons', []) for name in row.get('exact_contigs', [])} | set(score.get('unclassified_contigs', [])))
        if names:
            body += '<details><summary>Contig names referenced by the saved evaluator</summary><p>This is a partial name inventory, not a graph-to-contig assignment or a topology report.</p><ul>' + ''.join((f'<li><code>{e(name)}</code></li>' for name in names)) + '</ul></details>'
    return body

def result_body(case, record, artifact, output, family=None):
    from .report import LABELS, badge, diagnostic_table, e, execution_evidence, finding_panel
    from .result_summary import outcome_section
    from .expected_output import render_expected_output
    from .command_view import render_command
    slug = result_slug(record)
    family_link = f'<a href="../scenarios/{e(family.lower())}.html">{e(family)} results</a> · ' if family else ''
    body = f"""<nav class="result-breadcrumb" aria-label="Result navigation">{family_link}<a href="../scenarios/{e(case['id'])}.html#{e(record['tool'])}">Input details</a></nav><h1>{e(LABELS[record['tool']])}</h1><p class="result-subtitle">{e(case_title(case))}</p>"""
    if family == 'S5' and case.get('truth_type') == 'isolated_linear_reference_record':
        body += '<p class="muted">Historical isolated-plasmid control. The <a href="/scenarios/s5.html">active S5 panel</a> uses complete Streptomyces genomes.</p>'
    if family == 'S6':
        from .noisy_report import legacy_noise_note
        body += legacy_noise_note(case)
    body += outcome_section(record)
    if record.get('tool') == 'miniasm-plus' and record.get('initial_miniasm_evaluation'):
        initial = record['initial_miniasm_evaluation']
        body += f"<p>Unpolished Miniasm endpoint: <strong>{e(initial['status'].capitalize())}</strong>. This result scores the final Minipolish output; the unpolished source is retained separately.</p>"
    if family == 'S5':
        from .linear_report import reference_repeat_table
        body += reference_repeat_table(case)
    if record.get('tool') == 'plassembler':
        scope = ['The score and graph cover final plasmids only.' + (' The input also contains a chromosome.' if any((m.get('molecule_type') == 'chromosome' for m in case.get('replicons', []))) else '')]
        if record.get('retained_chromosome_sha256'):
            scope.append('Plassembler retained the chromosome separately.')
        chromosomes = [m for m in (record.get('initial_flye_evaluation') or {}).get('replicons', []) if m.get('molecule_type') == 'chromosome']
        if chromosomes:
            scope.append('Initial Flye stage: ' + '; '.join((f"{e(m.get('name', 'chromosome'))} — {('exact match' if m.get('status') == 'pass' else 'not recovered exactly')}" for m in chromosomes)) + '.')
        body += '<p class="result-scope">' + ' '.join(scope) + '</p>'
    links = [('#run-details', 'Run details'), ('#contigs', 'Output contigs'), ('#assembly-graph', 'Assembly graph')]
    if (record.get('report_evidence') or {}).get('dotplot', {}).get('status') == 'available':
        links.append(('#saved-alignment-plot', 'Alignment dot plot'))
    if (record.get('report_evidence') or {}).get('length_metrics'):
        links.append(('#length-metrics', 'Lengths'))
    links.append(('#assessment-audit', 'Assessment details'))
    body += '<nav class="result-jumps" aria-label="Result evidence">' + ' · '.join((f'<a href="{href}">{label}</a>' for href, label in links)) + '</nav>'
    if record.get('tolerant_assessment'):
        from .noisy_report import tolerant_badge
        body += f'<p>Separate tolerant endpoint: {tolerant_badge(record)}. Exact and tolerant outcomes retain their own definitions.</p>'
    facts = [('Scenario', case['id']), ('Execution', record.get('run_id', 'Single execution')), ('Tool version', record.get('version', 'Not collected')), ('Tool threads', record.get('threads', 'Not collected'))]
    for key, label in (('started_at', 'Started'), ('finished_at', 'Finished')):
        if record.get(key):
            facts.append((label, record[key]))
    if record.get('elapsed_seconds') is not None:
        facts.append(('Elapsed', f"{record['elapsed_seconds']:.1f} seconds"))
    body += '<details class="result-metadata" id="run-details"><summary>Run details, command and provenance</summary>' + render_command(record, case, collapsed=False) + '<h3>Run details and provenance</h3><dl class="result-facts">' + ''.join((f'<dt>{e(key)}</dt><dd>{e(value)}</dd>' for key, value in facts)) + '</dl></details>'
    if family == 'S6' or record.get('tolerant_assessment'):
        from .noisy_report import tolerant_details
        body += '<h2>Tolerant recovery measurements</h2>' + tolerant_details(record)
    if artifact.get('failed_execution_provenance'):
        body += '<div class="notice"><strong>Retained intermediate output</strong><p>This graph and its tool claims come from a stopped run. No completed primary assembly was verified; the original execution error remains unchanged.</p></div>'
    graph = artifact.get('graph') or {}
    body += '<h2 id="assembly-graph">Expected vs assembled</h2><p>Compare the reference molecules with the recorded graph. One molecule can use several linked graph segments; visual shape alone does not determine the exact score.</p><div class="graph-comparison">' + render_expected_output(case, record) + '<section class="observed-output" aria-labelledby="observed-output-title"><h3 id="observed-output-title">Recorded assembly graph</h3>'
    if graph.get('status') == 'available':
        body += '<noscript>' + source_description(graph.get('source'))
        body += f"<p>{len(graph.get('nodes', []))} GFA segments · {len(graph.get('edges', []))} link records. This is a graph inventory, not a count of biological plasmids.</p></noscript>"
    from .reference_origins import build_reference_origins
    presentation = {key: copy.deepcopy(artifact[key]) for key in ('graph', 'reason') if key in artifact}
    prepared = record.get('report_evidence')
    from .graph_availability import graph_availability
    availability = (prepared or {}).get('graph_availability') or graph_availability(record, artifact)
    presentation['availability'] = availability
    presentation['reference_origins'] = prepared['reference_origins'] if prepared else build_reference_origins(case, record, artifact)
    payload = json.dumps(presentation, ensure_ascii=True, separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    body += f"""<script type="application/json" id="assembly-graph-data">{payload}</script><div data-assembly-graph="assembly-graph-data"><p>{e(availability['title'])}. {e(availability['description'])}</p></div>"""
    body += '</section></div>'
    if prepared:
        plot = prepared['dotplot']
        body += f'<h2 id="saved-alignment-plot">Saved alignment evidence</h2>'
        if plot['status'] == 'available':
            if prepared.get('checked_facts'):
                body += '<dl class="result-facts">' + ''.join((f"<dt>{e(fact['label'])}</dt><dd>{e(fact['value'])}</dd>" for fact in prepared['checked_facts'])) + '</dl>'
            scope = plot.get('display_scope') or 'The lower panels show only the terminal intervals already recorded in the review.'
            body += f"""<p>{e(plot['method'])}. {e(scope)} Individual changed bases and assembler-internal causes are separate evidence.</p><figure><img class="saved-alignment-plot" src="../data/results/{e(slug)}-alignment.svg" alt="Saved alignment coordinate plot" /></figure><p><a href="../data/results/{e(slug)}-alignments.tsv">Saved alignment coordinates (TSV)</a> · <a href="../data/results/{e(slug)}-alignment.svg">Open full-size plot (SVG)</a></p>"""
            if plot.get('nucmer_status') == 'available':
                body += f'<p><a href="../data/results/{e(slug)}-original-show-coords.tsv">Original show-coords table (1-based inclusive)</a></p>'
        else:
            body += f"<p>{e(plot['reason'])}</p>"
        body += f'<p><a href="../data/results/{e(slug)}-report.md">Standalone detailed report (Markdown)</a></p>'
    from .length_view import render_lengths
    body += render_lengths((prepared or {}).get('length_metrics'))
    if record.get('tool') == 'plassembler' and any((row.get('id') == 'chromosome' for row in (artifact.get('assembly_info') or {}).get('contigs', []))):
        body += '<p>The tool summary below also lists its separate chromosome output; that row is not a segment missing from the plasmid graph.</p>'
    body += contig_section(record, artifact)
    public = execution_evidence(record, case)
    public['graph_artifacts'] = artifact
    public['reference_origins'] = presentation['reference_origins']
    write_download(output / 'data/results' / (slug + '.json'), public)
    write_download(output / 'data/results' / (slug + '-graph.json'), artifact)
    body += f'<div class="downloads"><a href="../data/results/{e(slug)}.json">Execution and assessment JSON</a><a href="../data/results/{e(slug)}-graph.json">Collected graph metadata JSON</a><a href="../methods.html">Methods and endpoint limits</a></div>'
    body += '<details id="assessment-audit" class="assessment-audit"><summary>Recorded assessment, mapping and sources</summary>' + finding_panel(record, case)
    if record.get('diagnostics'):
        body += diagnostic_table(record['diagnostics'], plasmid_only=record['tool'] == 'plassembler', evaluation=record.get('evaluation'), prepared=prepared)
    if record.get('evaluation'):
        body += '<details><summary>Recorded exact criterion</summary><p>' + e(record['evaluation'].get('endpoint', 'See the saved scoring record')) + '</p><p>Graph presentation does not change this endpoint or establish molecular topology.</p></details>'
    return body + '</details>'

def write_result_pages(document, output, batch=None):
    from .report import LABELS, page
    directory = output / 'results'
    shutil.rmtree(output / 'data/results', ignore_errors=True)
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True)
    cases = {case['id']: case for case in document['scenarios']}
    for record in document['results']:
        case = cases[record['scenario_id']]
        artifact = graph_artifact(record, execution_path(batch, record))
        family = 'S3' if document.get('config', {}).get('determinism') else case.get('category')
        body = result_body(case, record, artifact, output, family=family)
        (directory / (result_slug(record) + '.html')).write_text(page(LABELS[record['tool']] + ' · result', body, '../', 'scenarios'))

def enrich_graph_artifacts(document, batch=None):
    """Freeze checked sidecars into copied snapshots so archives keep their graphs."""
    result = copy.deepcopy(document)
    if document.get('report_bundle_version') == 1:
        return result
    for record in result['results']:
        record['graph_artifacts'] = graph_artifact(record, execution_path(batch, record))
    if result.get('determinism'):
        result['determinism']['executions'] = result['results']
    return result
