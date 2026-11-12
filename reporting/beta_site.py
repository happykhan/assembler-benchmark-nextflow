"""Add a compact beta report to the existing website without replacing cohorts."""
import csv
from html import escape
import json
from pathlib import Path
import shutil

from .archive import validate_archive
from .common import digest, save
from .native_site import measurement_svg, outcome_label
from .report import page
from .site_gate import require_site, write_site_receipt

GROUPS = {'gc-composition':'GC / composition', 'read-quality':'Read length / coverage',
          'plasmids':'Plasmid depth', 'repeats-structure':'Long-read contrast'}


def write_tsv(path, rows, columns):
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns,delimiter='\t',extrasaction='ignore')
        writer.writeheader();writer.writerows(rows)


def render_beta(bundle, base_site, output):
    bundle, base_site, output = map(lambda p:Path(p).resolve(),(bundle,base_site,output))
    manifest,kind=validate_archive(bundle)
    if kind!='nextflow' or not manifest.get('complete'):
        raise ValueError('Beta publication requires a complete Nextflow bundle')
    document=json.loads((bundle/'results.json').read_text())
    records=document['results']
    if not records or any(r.get('track','simulated')!='simulated' or r.get('preset')!='standard' for r in records):
        raise ValueError('Beta report accepts only simulated Standard records')
    if output.exists() or output==base_site or base_site in output.parents or output in base_site.parents:
        raise ValueError('Use a fresh publication directory separate from the existing site')
    plan=json.loads((bundle/'slot-plan.json').read_text())
    shutil.copytree(base_site,output,ignore=shutil.ignore_patterns('.vercel','.site-files.json','.results-render.json','.DS_Store'))
    beta=output/'beta';beta.mkdir(exist_ok=True)
    rows=[];molecules=[]
    for r in records:
        case=r['case'];ref=plan['references'][case['reference_id']]
        evidence=bundle/r['evidence_directory']
        simulation=json.loads((evidence/'simulation.json').read_text())
        observed=simulation['observed'];resources=r.get('resources',{})
        condition=case['id'].removeprefix('beta-'+case['reference_id']+'-').rsplit('-seed-',1)[0]
        rows.append({'case_id':case['id'],'reference':ref.get('organism',ref['id']),
            'condition':condition,'seed':case['seed'],'assembler':r['assembler'],
            'groups':','.join(case.get('groups',[case['group']])),
            'outcome':outcome_label(r),'execution_status':r['execution']['status'],
            'assessment_status':r['assessment']['status'],'observed_read_bases':observed['total_bases'],
            'observed_read_count':observed['read_count'],'observed_read_n50':observed['n50'],
            'short_base_fraction':observed.get('short_mode_base_fraction',0),
            'short_read_fraction':observed.get('short_mode_read_fraction',0),
            'workflow_wall_seconds':resources.get('workflow_wall_seconds'),
            'peak_ram_bytes':resources.get('assembler_process_tree_peak_rss_bytes')})
        for m in r.get('replicons',[]):
            molecules.append(dict(case_id=case['id'],reference=rows[-1]['reference'],condition=condition,
                                  seed=case['seed'],assembler=r['assembler'],**m))
    rows.sort(key=lambda r:(r['reference'],r['condition'],r['seed'],r['assembler']))
    write_tsv(beta/'results.tsv',rows,list(rows[0]))
    molecule_columns=['case_id','reference','condition','seed','assembler','accession','molecule_type',
                      'length_bp','contiguity','complete','identity_measured','identity','max_indel_bp']
    write_tsv(beta/'molecules.tsv',molecules,molecule_columns)
    save(beta/'summary.json',{'label':'Beta Standard','run_id':document['run_id'],
                            'results':rows,'molecules':molecules})
    body='<header><p class="eyebrow">Nextflow · Beta</p><h1>Simulated Standard</h1><p>Whole native genomes, five sampling seeds and error-free read contrasts. These beta results are separate from the published general benchmark and historical scenarios.</p></header>'
    body+=f'<p><strong>{len(rows)} recorded outcomes</strong> · {len(plan["cases"])} input sets · {len(plan["reference_ids"])} references. No overall ranking.</p>'
    body+='<p><a href="/beta/results.tsv">Download run results (TSV)</a> · <a href="/beta/molecules.tsv">Download molecule measurements (TSV)</a> · <a href="/beta/summary.json">Results JSON</a></p>'
    body+='<h2>Reference panel</h2><div class="beta-scroll" tabindex="0" role="region" aria-label="Reference panel"><table><thead><tr><th>Reference</th><th>Native molecules</th><th>Chromosome GC</th></tr></thead><tbody>'
    for ref in plan['references'].values():
        chr=next(m for m in ref['molecules'] if m['type']=='chromosome')
        body+=f'<tr><td>{escape(ref.get("organism",ref["id"]))}</td><td>{len(ref["molecules"])}</td><td>{100*chr["gc_bases"]/chr["length_bp"]:.2f}%</td></tr>'
    body+='</tbody></table></div><p>GC strata are descriptive: species, genome size and repeats also differ. The long-read contrast measures recovery; structural correctness and repeat bridging are not scored here.</p>'
    body+='<h2>Run results</h2><div class="beta-controls"><div><label for="beta-group">Scenario</label><select id="beta-group"><option value="">All scenarios</option>'+''.join(f'<option value="{key}">{label}</option>' for key,label in GROUPS.items())+'</select></div><div><label for="beta-search">Search</label><input id="beta-search" type="search" placeholder="Reference, assembler or condition"></div></div><p id="beta-count" aria-live="polite"></p>'
    body+='<div class="beta-scroll" tabindex="0" role="region" aria-label="Beta run results"><table><thead><tr>'+''.join('<th>'+s+'</th>' for s in ['Reference','Condition','Seed','Workflow','Sequence outcome','Read N50','Wall time (s)'])+'</tr></thead><tbody id="beta-rows">'
    for r in rows:
        cells=[r['reference'],r['condition'].replace('-',' '),r['seed'],r['assembler'],r['outcome'],f"{r['observed_read_n50']:,}",round(r['workflow_wall_seconds'],1) if r['workflow_wall_seconds'] is not None else 'Unmeasured']
        body+='<tr data-groups="'+escape(r['groups'],quote=True)+'">'+''.join('<td>'+escape(str(c))+'</td>' for c in cells)+'</tr>'
    body+='</tbody></table></div><h2>Molecule recovery</h2><p>Each point is a recorded molecule across all beta conditions and seeds. Completion requires at least 99% of the reference in one alignment against a tripled reference; contiguity is uncapped. This does not measure structural correctness. Failed measurements remain unscored.</p>'
    values=[(r['assembler'],r['contiguity']) for r in molecules if isinstance(r.get('contiguity'),(int,float))]
    (beta/'contiguity.svg').write_text(measurement_svg(values,'Molecule contiguity — all beta conditions'))
    body+='<img src="/beta/contiguity.svg" alt="Recorded molecule contiguity across all beta conditions"><h2>Simulation recipe</h2><p>Uniform circular starts, error-free sequence and gamma-distributed fragment lengths. Fragments are capped at one native molecule length; final reads are trimmed to exact per-molecule base budgets. Bimodal arms hold total bases constant and report read and base proportions separately. Qualities are synthetic Q40; sequencing errors and biases are deferred.</p>'
    body+='<p>Execution and assessment failures are shown separately from sequence recovery. Workflow time includes verification, assembly and assessment; preparation and scheduler waiting are excluded. <a href="/index.html">Return to the published benchmark</a>.</p>'
    html=page('Beta Standard',body,prefix='/',active='beta')
    html=html.replace('</head>','<style>.beta-scroll{overflow:auto}table{border-collapse:collapse;width:100%}th,td{padding:.65rem;text-align:left;white-space:nowrap}th{border-bottom:1px solid currentColor}.beta-controls{display:flex;gap:1rem;flex-wrap:wrap}.beta-controls>div{display:grid;gap:.35rem}select,input{font:inherit;padding:.5rem}img{max-width:100%}[hidden]{display:none!important}</style><script defer src="/beta/filters.js"></script></head>')
    (beta/'index.html').write_text(html)
    (beta/'filters.js').write_text("const group=document.getElementById('beta-group'),search=document.getElementById('beta-search'),rows=[...document.querySelectorAll('#beta-rows tr')];function filter(){let n=0;for(const row of rows){row.hidden=!( (!group.value||row.dataset.groups.split(',').includes(group.value)) && row.textContent.toLowerCase().includes(search.value.toLowerCase()));if(!row.hidden)n++;}document.getElementById('beta-count').textContent=n+' of '+rows.length+' outcomes';}group.addEventListener('change',filter);search.addEventListener('input',filter);filter();\n")
    home=output/'index.html';home.write_text(home.read_text().replace('<main id="main">','<main id="main"><p><a href="/beta/">New: simulated Standard beta results</a></p>',1))
    save(output/'.beta-publication.json',{'bundle_manifest_sha256':digest(bundle/'manifest.json'),
        'outcomes':len(rows),'base_site':str(base_site),'label':'Beta Standard'})
    require_site(output);write_site_receipt(output)
    return output
