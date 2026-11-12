"""Website templates for backend overview models."""
import html
from pathlib import Path
from .common import save
from .overview_model import FAMILIES, TOOLS, ERRORS, build_overview

def _e(value):
    return html.escape(str(value), quote=True)

def _cell(counts, href=None):
    if 'repeatability' in counts:
        return _repeatability_cell(counts['repeatability'], href)
    tone = 'neutral' if counts['denominator'] == 0 else 'pass' if counts['fail'] == 0 else 'fail' if counts['pass'] == 0 else 'mixed'
    text = '<strong>Not assessed</strong>' if counts['total'] == 0 else f"<strong>{counts['pass']} pass · {counts['fail']} fail</strong>"
    if href:
        text = f'<a href="{_e(href)}">{text}</a>'
    extra = ([f"{counts['errors']} errors"] if counts['errors'] else []) + ([f"{counts['unscored']} unscored"] if counts['unscored'] else [])
    if extra:
        text += '<small>' + ' · '.join(extra) + '</small>'
    heat = '' if counts['pass_fraction'] is None else f" heat-{min(4, int(counts['pass_fraction'] * 5))}"
    return f'''<td class="overview-cell {tone}{heat}" data-pass="{counts['pass']}" data-fail="{counts['fail']}" data-denominator="{counts['denominator']}">{text}</td>'''

def _repeatability_cell(counts, href=None):
    same, different = (counts['identical'], counts['different'])
    denominator = same + different
    tone = 'neutral' if not denominator else 'pass' if not different else 'fail' if not same else 'mixed'
    text = '<strong>Not assessed</strong>' if counts['total'] == 0 else f'<strong>{same} identical · {different} different</strong>'
    if href:
        text = f'<a href="{_e(href)}">{text}</a>'
    if counts['not_assessed']:
        text += f"<small>{counts['not_assessed']} not assessed</small>"
    heat = f' heat-{min(4, int(same / denominator * 5))}' if denominator else ''
    return f'<td class="overview-cell {tone}{heat}" data-identical="{same}" data-different="{different}" data-denominator="{denominator}">{text}</td>'

def _agreement(group, metric):
    value = group.get(metric + '_identical')
    if group.get('complete') is not True or group.get('inputs_identical') is not True or type(value) is not bool:
        return 'Not assessed'
    return 'Identical' if value else 'Different'

def _repeatability_tables(item, tools):
    body = '<p>Counts compare normalised sequences within each input, assembler, mode and thread setting. Reference recovery is shown separately below.</p>'
    if item.get('repeatability_groups') and all((g['mode'] == 'default' for g in item['repeatability_groups'])):
        body += '<p>Saved comparisons use default mode. Deterministic-mode results have not been collected.</p>'
    body += '<div class="table-scroll"><table><caption>Repeatability by reference genome</caption><thead><tr><th scope="col">Genome</th>'
    body += ''.join((f"""<th scope="col">{_e(t['label'])}</th>""" for t in tools)) + '</tr></thead><tbody>'
    for genome in item['genomes']:
        body += f"""<tr><th scope="row">{_e(genome['organism'])}<small>{_e(genome['assembly_accession'] or 'Accession not recorded')}</small></th>"""
        body += ''.join((_cell(t) for t in genome['tools'])) + '</tr>'
    body += '</tbody></table></div>'
    only_supplementary = bool(item.get('repeatability_groups')) and all((g.get('cohort_role') == 'supplementary' for g in item['repeatability_groups']))
    if only_supplementary:
        body += '<p>The revised larger-plasmid repeatability case has not been assessed.</p><details><summary>Supplementary repeatability comparisons</summary>'
    for kind, heading in (('within_thread', 'Repeated runs at the same thread setting'), ('across_threads', 'Agreement across thread settings')):
        body += f'<h2>{heading}</h2><div class="table-scroll"><table data-table-kind="repeats"><thead><tr><th scope="col">Input</th><th scope="col">Assembler</th><th scope="col">Mode</th><th scope="col">Threads</th><th scope="col">Completed / expected</th><th scope="col">File bytes</th><th scope="col">Normalised sequences</th><th scope="col">Reference-recovery outcomes</th></tr></thead><tbody>'
        groups = [g for g in item.get('repeatability_groups', []) if g['comparison'] == kind]
        for g in groups:
            threads = ', '.join(map(str, g['threads'])) if isinstance(g.get('threads'), list) else str(g.get('threads', 'Not recorded'))
            runs = f"{g.get('scored_runs', '—')} / {g.get('expected_runs', '—')}" if kind == 'within_thread' else 'All saved repeats' if g.get('complete') else 'Incomplete'
            body += f"""<tr><th scope="row">{_e(g['title'])}""" + (f"<small>Supplementary: {_e(g.get('cohort_reason'))}</small>" if g.get('cohort_role') == 'supplementary' else '') + f"</th><td>{_e(TOOLS[g['tool']])}</td><td>{_e(g['mode'].replace('_', ' ').title())}</td><td>{_e(threads)}</td><td>{_e(runs)}</td>"
            body += ''.join((f'<td>{_agreement(g, key)}</td>' for key in ('byte', 'normalised_sequence', 'biological'))) + '</tr>'
        if not groups:
            body += '<tr><td colspan="8">No saved comparisons.</td></tr>'
        body += '</tbody></table></div>'
    if only_supplementary:
        body += '</details>'
    body += '<p class="muted">Normalisation ignores contig names, order and strand. Circular rotation is ignored only for exact reference-matched circles; other contig ends and duplicates are retained. Different normalised signatures therefore do not establish a particular sequence change. Incomplete groups or unverified inputs are not assessed. Identical observations do not guarantee determinism.</p>'
    return body

def render_home(model, prefix=''):
    """Body fragment; caller retains its existing page shell and assets."""
    body = f"""<h1>Assembly benchmark</h1><p class="overview-intro">Recovery and repeatability · {model.get('all_counts', model['counts'])['total']} run records · {len(model['tools'])} assembler configurations</p>"""
    if model.get('baseline_policy'):
        families = 'S1–S3 and S6' if 'S6' in model['baseline_policy'].get('families', []) else 'S1–S3'
        body += f'<p>{families}: plasmids ≥20 kb. Earlier small-plasmid inputs are supplementary.</p>'
    if model['missing_batches']:
        body += '<p class="notice">Some selected batches are unavailable. Counts are incomplete.</p>'
    body += '<div class="table-scroll" role="region" aria-label="Scenario family outcomes" tabindex="0"><table class="overview-heatmap"><caption>Recovery counts by scenario family; S3 counts repeated-run agreement</caption><thead><tr><th scope="col">Scenario family</th>'
    body += ''.join((f"""<th scope="col">{_e(t['label'])}</th>""" for t in model['tools'])) + '</tr></thead><tbody>'
    for family in model['families']:
        if model['scope'] == 'archived_batch' and (not family['counts']['total']):
            continue
        href = prefix + family['href']
        body += f'''<tr><th scope="row"><a href="{_e(href)}">{family['id']} · {_e(family['title'])}</a>'''
        if family['id'] == 'S3':
            body += '<small>Repeatability · normalised sequences</small>'
        body += '</th>'
        body += ''.join((_cell(tool, href) for tool in family['tools'])) + '</tr>'
    return body + '</tbody></table></div><p class="overview-legend"><span>Orange: more failures or differences</span><span>Blue: more passes or identical groups</span></p>'

def render_family(model, family, prefix='../'):
    """Concise family summary and run links, without explanations or graphs."""
    item = next((f for f in model['families'] if f['id'] == family), None)
    if item is None:
        raise ValueError('Unknown scenario family')
    body = f'''<p><a href="{_e(prefix)}index.html">All scenario families</a></p><h1>{family} · {_e(item['title'])}</h1><p>{_e(item['description'])}</p>'''
    if item.get('supplementary_counts', {}).get('total') and family not in {'S5', 'S6'}:
        body += '<p>Headline counts exclude supplementary small-plasmid inputs. Their original results remain below.</p>'
    if family == 'S1' and model.get('baseline_policy'):
        body += '<p>The baseline tests chromosome-only controls and recovery of one or several plasmids ≥20 kb. The tables show recorded results.</p>'
    if family == 'S2' and model.get('baseline_policy') and (not item['counts']['total']):
        body += '<p>The revised larger-plasmid coverage panel has not been assessed.</p>'
    if family == 'S5' and model.get('baseline_policy') and (not item['counts']['total']):
        status = model.get('panel_statuses', {}).get('S5', {})
        message = 'The 24-execution replacement panel has been submitted; results and dot plots are pending.' if status.get('state') == 'submitted' else 'The replacement panel has not been run.'
        body += f'<p>{message} It selects complete assemblies of S. canus NBC_00277, S. prunicolor NBC_01021 and S. albidoflavus NBC 01661, including their deposited plasmids.</p>'
    if family == 'S6' and model.get('baseline_policy') and (not item['counts']['total']):
        status = model.get('panel_statuses', {}).get('S6', {})
        if status.get('state') == 'submitted':
            body += '<p>The 24-execution replacement panel has been submitted. Verified results will appear when the evidence is complete. Inputs are SE11 + pSE11-1 (100,021 bp) and MGH78578 + pKPN3 (175,879 bp), each with its chromosome.</p>'
        else:
            body += '<p>The revised large-plasmid read-error panel has not been run. Planned inputs are SE11 + pSE11-1 (100,021 bp) and MGH78578 + pKPN3 (175,879 bp), each with its chromosome.</p>'
    if family == 'S6' and item['counts']['total']:
        metric = 'Repeatability' if family == 'S3' else 'Tolerant recovery'
        body += f'<p>{metric} is a separate endpoint. The tables below show exact status only; individual result links retain the detailed evidence.</p>'
    if family == 'S3':
        body += _repeatability_tables(item, model['tools'])
        body += '<details><summary>Reference recovery for individual runs</summary>'
    elif item['genomes']:
        body += '<div class="table-scroll"><table><caption>Exact outcomes for each reference genome</caption><thead><tr><th scope="col">Genome</th>'
        body += ''.join((f"""<th scope="col">{_e(t['label'])}</th>""" for t in model['tools'])) + '</tr></thead><tbody>'
        for genome in item['genomes']:
            body += f"""<tr><th scope="row">{_e(genome['organism'])}<small>{_e(genome['assembly_accession'] or 'Accession not recorded')}</small></th>"""
            body += ''.join((_cell(t) for t in genome['tools'])) + '</tr>'
        body += '</tbody></table></div>'
    primary = [row for row in item['records'] if row.get('cohort_role') != 'supplementary']
    supplementary = [row for row in item['records'] if row.get('cohort_role') == 'supplementary']
    if primary or family not in {'S5', 'S6'}:
        body += '<h2>Individual runs</h2>' + _run_table(primary, prefix)
    if family == 'S3':
        body += '</details>'
    if supplementary:
        body += f'<details><summary>Supplementary results · {len(supplementary)} runs</summary>'
        body += '<p>Previous isolated SCP1/SLP2 controls; original scores and evidence are retained.</p>' if family == 'S5' else '<p>Inputs contain plasmids below 20 kb; these runs retain their original scenario, score and evidence.</p>'
        body += _run_table(supplementary, prefix) + '</details>'
    return body

def _run_table(rows, prefix):
    body = '<div class="table-scroll"><table data-table-kind="runs"><thead><tr><th scope="col">Genome / case</th><th scope="col">Assembler / version</th><th scope="col">Threads / repeat</th><th scope="col">Exact status</th></tr></thead><tbody>'
    for row in rows:
        run = f"{(row['threads'] if row['threads'] is not None else 'Not recorded')} threads · {row['run_id'] or 'Single run'}"
        body += f'''<tr data-batch="{_e(row['batch'])}"><th scope="row">{_e(row['organism'])}<small>{_e(row['title'])}</small></th><td><a href="{_e(prefix + row['href'])}">{_e(TOOLS[row['tool']])}<small>{_e(row['version'])}</small></a></td><td>{_e(run)}</td><td><span class="status {_e(row['status'])}">{_e(row['status'].replace('_', ' ').title())}</span></td></tr>'''
    if not rows:
        body += '<tr><td colspan="4">No runs in this selected cohort.</td></tr>'
    return body + '</tbody></table></div>'

def write_overview(documents, output, *, cohort=None, archived_batch=None, root_batch=None, model=None):
    """Write navigation views and separate derived JSON; preserve scientific files."""
    from .report import page, site_root
    output = Path(output)
    (output / 'scenarios').mkdir(parents=True, exist_ok=True)
    (output / 'data').mkdir(parents=True, exist_ok=True)
    if model is None:
        model = build_overview(documents, cohort=cohort, archived_batch=archived_batch, root_batch=root_batch)
    (output / 'index.html').write_text(page('Results', render_home(model), base_href=site_root(output)))
    for family in model['families']:
        (output / family['href']).write_text(page(family['title'], render_family(model, family['id']), prefix='../', active='scenarios'))
    save(output / 'data/overview.json', model)
    return model
