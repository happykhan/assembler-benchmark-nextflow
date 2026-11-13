"""Current-package website: presentation only, with compact prepared artifacts."""
from collections import defaultdict
import copy
import csv
from html import escape
from html.parser import HTMLParser
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import unquote,urljoin,urlsplit
import uuid

from benchlib.current_results import load_current,render_metric_table

ASSETS=Path(__file__).with_name('current_assets')
STATUS={'measured':'Measured','execution_failure':'Assembly failed','assessment_failure':'Assessment failed','not_applicable':'Not applicable','not_run':'Not run'}
TOOLS={'flye':'Flye','raven':'Raven','skesa':'SKESA','spades':'SPAdes','plassembler':'Plassembler','miniasm':'Miniasm','miniasm-plus':'Miniasm + Minipolish'}
COLOURS=['#275dad','#aa5d12','#8a4678','#19766c','#9e423a','#56682f']
PUBLIC_ROLES={'graph_model':{'.json'},'alignment_coordinates':{'.tsv'},'alignment_plot':{'.svg','.png','.webp'}}
RESOURCE_NAMES={'workflow_wall_seconds','assembler_peak_ram','assembly_wall_seconds','assessment_wall_seconds','mapper_peak_ram'}


def _save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n')


def _colour(record):
    value=record['workflow'].get('colour','')
    if re.fullmatch(r'#[0-9a-fA-F]{6}',value):return value
    import hashlib
    index=int(hashlib.sha256(record['workflow']['id'].encode()).hexdigest()[:8],16)%len(COLOURS)
    return COLOURS[index]


def _workflow(record):
    row=record['workflow']
    return row.get('title') or TOOLS.get(row.get('tool'),row['id'].replace('-',' ').capitalize())


def _case(record):
    return record['case'].get('title',record['case']['id']).replace('_',' ')


def _dataset(record):
    reference=record.get('input',{}).get('reference',{})
    return reference.get('organism') or record['case'].get('dataset_title') or record['case']['dataset_id'].replace('-',' ')


def _number(value):
    if value is None:return 'Unmeasured'
    if isinstance(value,bool):return 'Yes' if value else 'No'
    if isinstance(value,int):return f'{value:,}'
    if isinstance(value,float):return f'{value:,.4g}'
    return str(value)


def _metric_name(name):
    labels={'reference_breadth':'Reference breadth','longest_alignment_contiguity':'Longest-alignment contiguity','longest_alignment_identity':'Longest-alignment identity','longest_alignment_max_indel':'Longest-alignment maximum indel','contig_count':'Contig count','assembly_length':'Assembly length','contig_n50':'Contig N50','contig_ng50':'Contig NG50','workflow_wall_seconds':'Workflow wall time','assembler_peak_ram':'Peak assembler RAM'}
    return labels.get(name,name.replace('_',' ').capitalize())


def _summary(record):
    metrics=[m for m in record['metrics'] if m.get('primary')]
    if not metrics:metrics=[m for m in record['metrics'] if m['name'] not in RESOURCE_NAMES][:2]
    if not metrics:return escape(record.get('reason','No measurements recorded'))
    return '<br>'.join('<span>'+escape(_metric_name(m['name']))+': <strong>'+escape(_number(m.get('value')))+'</strong> '+escape(m['unit'])+'</span>' for m in metrics[:3])


def _page(title,body,prefix='',active='',publication=None):
    notice=''
    if publication:
        title += ' · Nextflow pilot'
        notice='<aside class="pilot-notice" aria-label="Pilot validation scope"><strong>Nextflow pilot validation</strong><p>'+escape(publication['summary'])+'</p><p>'+escape(publication['scope'])+'</p></aside>'
    nav=''.join('<a '+('aria-current="page" ' if key==active else '')+'href="'+prefix+url+'">'+label+'</a>' for key,url,label in [('broad','broad/index.html','Broad benchmarks'),('scenarios','scenarios/index.html','Targeted scenarios'),('assemblers','assemblers/index.html','Assemblers')])
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(title)+' · Assembly Benchmarks</title><script>try{let t=localStorage.getItem("gx-theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}</script><link rel="stylesheet" href="'+prefix+'assets/site.css"><script defer src="'+prefix+'assets/site.js"></script></head><body><a class="skip" href="#main">Skip to content</a><header class="site-header"><a class="brand" href="'+prefix+'index.html">Assembly Benchmarks</a><nav aria-label="Main navigation">'+nav+'</nav><button class="theme-button" type="button" data-theme-toggle>Dark theme</button></header><main id="main">'+notice+body+'</main><footer>Single-isolate bacterial genomes · Current measurements, explicit methods</footer></body></html>'


def _write_page(output,route,title,body,active=''):
    path=output/route;path.parent.mkdir(parents=True,exist_ok=True)
    prefix='../'*len(Path(route).parts[:-1])
    publication=json.loads((output/'publication.json').read_text()) if (output/'publication.json').is_file() else None
    path.write_text(_page(title,body,prefix,active,publication))


def _tsv(records):
    stream=io.StringIO();writer=csv.writer(stream,delimiter='\t')
    pilot=any(r.get('publication') for r in records)
    writer.writerow(['result_id','case_id','dataset_id','workflow_id','version','read_technology','source_kind','scientific_repeat_id','status','metric','value','unit','method','context']+(['publication_kind','publication_scope'] if pilot else []))
    for record in records:
        for metric in record['metrics'] or [{}]:
            context={k:v for k,v in metric.items() if k not in ('name','value','unit','method')}
            writer.writerow([record['result_id'],record['case']['id'],record['case']['dataset_id'],record['workflow']['id'],record['workflow']['version'],record['case']['read_technology'],record['case']['source_kind'],record['case'].get('scientific_repeat_id'),record['status'],metric.get('name'),metric.get('value'),metric.get('unit'),metric.get('method'),json.dumps(context,sort_keys=True)]+([record.get('publication',{}).get('kind',''),record.get('publication',{}).get('scope','')] if pilot else []))
    return stream.getvalue()


def _copy_public_artifacts(root,output,record):
    package=root/record['package'];copied={}
    for name,item in record.get('artifacts',{}).items():
        role=item.get('role');suffix=Path(item['path']).suffix.lower()
        if suffix not in PUBLIC_ROLES.get(role,set()):continue
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Invalid public artifact name')
        source=package/item['path']
        if source.stat().st_size>5*1024*1024:continue
        if suffix=='.svg' and re.search(r'<script|<foreignObject|\bon\w+\s*=|(?:href|src)\s*=\s*[\"\'](?:https?:|file:)',source.read_text(),re.I):
            raise ValueError('Prepared SVG contains active or external content')
        destination=output/'artifacts'/record['result_id']/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
        copied[name]={**item,'path':'../artifacts/'+record['result_id']+'/'+relative.as_posix()}
    return copied


def _public_record(root,output,record):
    result={k:copy.deepcopy(v) for k,v in record.items() if k not in ('package','artifacts','dependencies','dependency_packages')}
    result['artifacts']=_copy_public_artifacts(root,output,record)
    result['omitted_artifacts']=[{'name':name,'role':item.get('role')} for name,item in record.get('artifacts',{}).items() if name not in result['artifacts']]
    return result


def _filters(records):
    workflows={r['workflow']['id']:_workflow(r) for r in records}
    definitions=[('technology','Read technology',[('short','Short reads'),('long','Long reads')]),('source','Data source',[('real','Real'),('simulated','Simulated')]),('workflow','Assembler',sorted(workflows.items(),key=lambda p:p[1])),('status','Result status',list(STATUS.items()))]
    body='<div class="filters">'
    for key,label,options in definitions:
        body+='<div><label for="filter-'+key+'">'+label+'</label><select id="filter-'+key+'" data-filter="'+key+'"><option value="">All</option>'+''.join('<option value="'+escape(value,quote=True)+'">'+escape(text)+'</option>' for value,text in options)+'</select></div>'
    return body+'<div class="filter-search"><label for="filter-search">Search cases</label><input id="filter-search" type="search" data-filter="search" placeholder="Genome or condition"></div></div><p class="result-count" data-result-count aria-live="polite"></p>'


def _table(records):
    body='<div class="table-scroll" tabindex="0" role="region" aria-label="Assembly comparison"><table class="comparison-table"><thead><tr><th>Dataset / condition</th><th>Assembler</th><th>Reads</th><th>Source</th><th>Status</th><th>Measurements</th><th>Details</th></tr></thead><tbody>'
    for r in records:
        case=r['case'];workflow=r['workflow'];context=[]
        if case.get('sampling_seed') is not None:context.append('Seed '+str(case['sampling_seed']))
        repeat=case.get('scientific_repeat')
        if repeat:context.append(str(repeat['kind']).replace('_',' ')+' '+str(repeat['index']))
        search=' '.join([_dataset(r),_case(r),case['id'],_workflow(r)])
        attrs={'result-id':r['result_id'],'technology':case['read_technology'],'source':case['source_kind'],'workflow':workflow['id'],'status':r['status'],'search':search.lower()}
        body+='<tr '+''.join('data-'+key+'="'+escape(value,quote=True)+'" ' for key,value in attrs.items())+'>'
        body+='<th scope="row">'+escape(_dataset(r))+'<span class="secondary">'+escape(_case(r))+('</span><span class="secondary">'+escape(' · '.join(context)) if context else '')+'</span></th>'
        body+='<td><span class="workflow-label"><span class="workflow-dot" style="--workflow-colour:'+_colour(r)+'"></span>'+escape(_workflow(r))+'</span><span class="secondary">'+escape(workflow['version'])+'</span></td>'
        body+='<td>'+escape(case['read_technology'].capitalize())+'</td><td>'+escape(case['source_kind'].capitalize())+'</td><td><span class="status status-'+r['status'].replace('_','-')+'">'+STATUS[r['status']]+'</span></td>'
        body+='<td class="primary-measurements">'+_summary(r)+'</td><td><a href="../results/'+r['result_id']+'.html">View result<span class="sr-only"> '+escape(_case(r)+' '+_workflow(r))+'</span></a></td></tr>'
    return body+'</tbody></table></div><p class="empty-filter" hidden>No current results match these filters. Clear a filter or change your search.</p>'


def _plots(records):
    grouped=defaultdict(list)
    for record in records:
        for metric in record['metrics']:
            if record['status']!='measured' and metric['name'] not in RESOURCE_NAMES:continue
            value=metric.get('value')
            if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value):
                grouped[(metric['name'],metric['unit'],metric['method'])].append((record,metric))
    scientific=[key for key in grouped if key[0] not in RESOURCE_NAMES]
    primary=[key for key in scientific if any(m.get('primary') for _,m in grouped[key])]
    chosen=(primary or scientific)[:4]
    resource=[key for key in grouped if key[0] in RESOURCE_NAMES][:2]
    body=''
    for title,keys in [('Assembly measurements',chosen),('Resource use',resource)]:
        if not keys:continue
        body+='<section><h2>'+title+'</h2><p class="section-description">Each point is a current case or scientific repeat. Methods are kept separate; unmeasured values are omitted.</p><div class="plot-grid">'
        for key in keys:
            values=grouped[key];minimum=min(v['value'] for _,v in values);maximum=max(v['value'] for _,v in values)
            lower=min(0,minimum);upper=maximum if maximum>lower else lower+1
            body+='<figure class="metric-plot"><figcaption><strong>'+escape(_metric_name(key[0]))+'</strong><span>'+escape(key[1])+' · '+escape(key[2])+'</span></figcaption>'
            workflows=sorted({r['workflow']['id'] for r,_ in values})
            for workflow in workflows:
                points=[(r,m) for r,m in values if r['workflow']['id']==workflow];example=points[0][0]
                body+='<div class="plot-series"><span class="workflow-label"><span class="workflow-dot" style="--workflow-colour:'+_colour(example)+'"></span>'+escape(_workflow(example))+'</span><div class="plot-track">'
                for index,(r,m) in enumerate(points):
                    position=3+94*(m['value']-lower)/(upper-lower);offset=9+(index%4)*5
                    label=_case(r)+' · '+_number(m['value'])+' '+key[1]
                    body+='<a class="plot-point" href="../results/'+r['result_id']+'.html" data-plot-result="'+r['result_id']+'" style="--position:'+f'{position:.3f}'+'%;--offset:'+str(offset)+'px;--workflow-colour:'+_colour(r)+'" title="'+escape(label,quote=True)+'" aria-label="'+escape(label,quote=True)+'"></a>'
                body+='</div></div>'
            body+='<div class="plot-scale"><span>'+escape(_number(lower))+'</span><span>'+escape(_number(upper))+'</span></div><p class="plot-empty secondary" hidden>No measured values match this selection.</p></figure>'
        body+='</div></section>'
    return body


def _comparison(output,kind,identity,definition,records):
    title=definition.get('title',identity.replace('-',' ').capitalize());question=definition.get('question','Compare current measurements for these cases.')
    body='<header class="page-heading"><h1>'+escape(title)+'</h1><p class="intro">'+escape(question)+'</p></header>'
    scope=definition.get('scientific_scope',definition.get('scope'))
    if scope:body+='<p class="scope"><strong>Dataset scope.</strong> '+escape(scope if isinstance(scope,str) else json.dumps(scope,sort_keys=True))+'</p>'
    conditions=definition.get('conditions')
    if conditions:body+='<details class="conditions"><summary>Conditions</summary><pre>'+escape(json.dumps(conditions,indent=2,sort_keys=True))+'</pre></details>'
    key=kind+'-'+identity
    (output/'data/views').mkdir(parents=True,exist_ok=True);(output/'data/views'/(key+'.tsv')).write_text(_tsv(records))
    body+='<p class="download-line"><a href="../data/views/'+key+'.tsv">Download these measurements (TSV)</a></p>'
    if records:
        body+='<section class="comparison" data-comparison>'+_filters(records)+_plots(records)+'<h2 id="comparison">Comparison</h2>'+_table(records)+'</section>'
    else:body+='<section class="empty-state"><h2>Not run</h2><p>No current result packages have been supplied for this selection. This does not indicate assembly success or failure.</p></section>'
    route=('broad/' if kind=='collection' else 'scenarios/' if kind=='scenario' else 'assemblers/')+identity+'.html'
    _write_page(output,route,title,body,'broad' if kind=='collection' else 'scenarios' if kind=='scenario' else 'assemblers')


def _listing(definitions,records,field,prefix):
    body='<div class="collection-list">'
    for identity,definition in definitions.items():
        selected=[r for r in records if identity in r['case'][field]]
        technologies=sorted({r['case']['read_technology'] for r in selected});sources=sorted({r['case']['source_kind'] for r in selected})
        scope=' · '.join([str(len(selected))+' current results']+[v+' reads' for v in technologies]+sources) if selected else 'Not run'
        body+='<article><h3><a href="'+prefix+identity+'.html">'+escape(definition.get('title',identity))+'</a></h3><p>'+escape(definition.get('question',''))+'</p><p class="secondary">'+escape(scope)+'</p></article>'
    return body+'</div>'


def _graph(model):
    nodes=model.get('nodes',[]);edges=model.get('edges',[])
    if not nodes:return '<p>The retained graph contains no segments.</p>'
    shown=nodes[:500];positions={};parts=[];count=len(shown)
    for index,node in enumerate(shown):
        angle=2*math.pi*index/max(count,1);positions[str(node['id'])]=(180+95*math.cos(angle) if count>1 else 180,120+75*math.sin(angle) if count>1 else 120)
    for edge in edges:
        a=positions.get(str(edge['source']));b=positions.get(str(edge['target']))
        if a and b:parts.append(f'<line class="graph-edge" x1="{a[0]:.2f}" y1="{a[1]:.2f}" x2="{b[0]:.2f}" y2="{b[1]:.2f}"/>')
    for node in shown:
        identity=str(node['id']);x,y=positions[identity];label=identity+' · '+_number(node.get('length_bp'))+' bp'
        parts.append('<g class="graph-node" data-node-id="'+escape(identity,quote=True)+'"><title>'+escape(label)+'</title>'+f'<circle cx="{x:.2f}" cy="{y:.2f}" r="7"/>'+(f'<text x="{x+11:.2f}" y="{y+4:.2f}">'+escape(identity)+'</text>' if count<=30 else '')+'</g>')
    body='<div class="graph-viewer" data-graph><div class="graph-toolbar"><button type="button" data-graph-action="in">Zoom in</button><button type="button" data-graph-action="out">Zoom out</button><button type="button" data-graph-action="reset">Fit graph</button></div><label for="graph-segment">Inspect segment</label><select id="graph-segment" data-graph-select><option value="">All segments</option>'+''.join('<option value="'+escape(str(n['id']),quote=True)+'">'+escape(str(n['id'])+' · '+_number(n.get('length_bp'))+' bp')+'</option>' for n in shown)+'</select>'
    if count>500:body+='<p>Preview: first 500 of '+str(count)+' recorded segments. Download the full graph metadata for the complete topology.</p>'
    return body+'<svg class="graph-canvas" viewBox="0 0 360 240" role="img" aria-label="Recorded assembly segments and links"><g data-graph-transform>'+''.join(parts)+'</g></svg><p class="secondary">'+str(len(nodes))+' segments · '+str(len(edges))+' links. Drag the background to pan.</p></div>'


def _details(root,output,record):
    title=_case(record)+' · '+_workflow(record);status=STATUS[record['status']]
    body='<header class="page-heading"><p><a href="../index.html">All benchmarks</a></p><h1>'+escape(title)+'</h1><p class="intro">'+escape(record['case']['read_technology'].capitalize()+' reads · '+record['case']['source_kind'].capitalize()+' data')+'</p></header><p><span class="status status-'+record['status'].replace('_','-')+'">'+status+'</span></p>'
    if record.get('reason'):body+='<p class="'+('notice' if record['status']!='measured' else 'secondary')+'">'+escape(record['reason'])+'</p>'
    body+='<p class="download-line"><a href="'+record['result_id']+'.json">Result JSON</a> · <a href="'+record['result_id']+'.tsv">Measurements TSV</a></p>'
    body+='<section><h2>Experiment and input</h2><p>'+escape(str(record.get('experiment',{}).get('description',record['case'].get('description',_case(record)))))+'</p><dl class="facts"><div><dt>Dataset</dt><dd>'+escape(_dataset(record))+'</dd></div><div><dt>Assembler</dt><dd>'+escape(_workflow(record)+' '+record['workflow']['version'])+'</dd></div><div><dt>Configuration</dt><dd>'+escape(json.dumps(record['workflow'].get('configuration',{}),sort_keys=True))+'</dd></div>'
    observed=record.get('input',{}).get('observed',{})
    for key,label in [('read_count','Reads'),('pair_count','Read pairs'),('total_bases','Sequenced bases'),('n50','Read N50')]:
        if key in observed and observed[key] is not None:body+='<div><dt>'+label+'</dt><dd>'+escape(_number(observed[key]))+'</dd></div>'
    repeat=record['case'].get('scientific_repeat')
    if repeat:body+='<div><dt>Scientific repeat</dt><dd>'+escape(str(repeat['kind'])+' '+str(repeat['index']))+'</dd></div>'
    body+='</dl><details class="conditions"><summary>Input recipe and provenance</summary><pre>'+escape(json.dumps({'recipe':record['case'].get('recipe',{}),'input':record.get('input',{}),'provenance':record.get('provenance',{})},indent=2,sort_keys=True))+'</pre></details></section>'
    display_metrics=[{**m,'name':_metric_name(m['name']),'unit':m['unit'].replace('_',' ')} for m in record['metrics']]
    body+='<section><h2>Measurements and methods</h2>'+render_metric_table(display_metrics)+'</section>'
    artifacts=record['artifacts'];graphs=[a for a in artifacts.values() if a.get('role')=='graph_model']
    body+='<section><h2>Assembly graph</h2>'
    if graphs:
        graph=graphs[0];source=output/'results'/graph['path'];model=json.loads(source.resolve().read_text());body+=_graph(model)+'<p><a href="'+escape(graph['path'],quote=True)+'">Graph metadata JSON</a></p>'
    else:body+='<p>No prepared graph view is available for this result.</p>'
    body+='</section><section><h2>Saved alignments</h2>'
    plots=[a for a in artifacts.values() if a.get('role')=='alignment_plot'];coordinates=[a for a in artifacts.values() if a.get('role')=='alignment_coordinates']
    if plots:
        for plot in plots:body+='<figure class="alignment-plot"><img src="'+escape(plot['path'],quote=True)+'" alt="Saved alignment coordinates for '+escape(_case(record),quote=True)+'"><figcaption>Prepared from the retained assessment coordinates.</figcaption></figure>'
    else:body+='<p>No alignment plot was supplied for this result.</p>'
    if coordinates:body+='<p>'+''.join('<a href="'+escape(item['path'],quote=True)+'">Alignment coordinates TSV</a>' for item in coordinates)+'</p>'
    body+='</section>'
    if record.get('omitted_artifacts'):body+='<p class="secondary">Additional scientific artifacts are retained in the standalone result package.</p>'
    _write_page(output,'results/'+record['result_id']+'.html',title,body)
    _save(output/'results'/(record['result_id']+'.json'),record)
    (output/'results'/(record['result_id']+'.tsv')).write_text(_tsv([record]))


class _Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.ids=set()
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if attrs.get('id'):self.ids.add(attrs['id'])
        if tag in ('a','link') and attrs.get('href'):self.links.append(attrs['href'])
        if tag in ('script','img') and attrs.get('src'):self.links.append(attrs['src'])


def validate_site(directory):
    root=Path(directory).resolve();files=[p for p in root.rglob('*') if p.is_file()];errors=[];checked=0;pages={}
    for path in files:
        if path.is_symlink() or path.stat().st_size>5*1024*1024:errors.append('Invalid public file: '+str(path.relative_to(root)))
        if path.suffix.lower() in ('.fastq','.fq','.fasta','.fa','.fna','.gfa','.paf','.log','.gz'):errors.append('Bulky scientific artifact in public build: '+str(path.relative_to(root)))
        if path.suffix=='.html':parser=_Links();parser.feed(path.read_text());pages[path]=parser
    for path,parser in pages.items():
        for link in parser.links:
            url=urlsplit(urljoin('https://site.invalid/'+path.relative_to(root).as_posix(),link))
            if url.netloc!='site.invalid':continue
            target=root/unquote(url.path).lstrip('/');target=target/'index.html' if url.path.endswith('/') else target
            checked+=1
            if not target.resolve().is_relative_to(root) or not target.is_file():errors.append('Missing local link: '+link)
            elif url.fragment and target in pages and url.fragment not in pages[target].ids:errors.append('Missing local anchor: '+link)
    total=sum(p.stat().st_size for p in files)
    if total>64*1024*1024:errors.append('Public build exceeds 64 MiB')
    if len(files)>1500:errors.append('Public build exceeds 1,500 files')
    return {'status':'pass' if not errors else 'fail','files':len(files),'bytes':total,'local_links_checked':checked,'errors':errors}


def _render(root,output,pilot=False):
    catalogue=json.loads((root/'catalogue.json').read_text());records=load_current(root,with_packages=True)
    records.sort(key=lambda r:(_dataset(r),_case(r),r['workflow']['id'],r['case'].get('scientific_repeat_id') or ''))
    publication=None
    if pilot:
        measured=[r for r in records if r['status']=='measured']
        inputs={r['case']['input_id'] for r in records}
        repeats=sum(bool(r['case'].get('scientific_repeat_id')) for r in measured)
        publication={'kind':'pilot','measured_results':len(measured),'not_applicable':sum(r['status']=='not_applicable' for r in records),'unique_inputs':len(inputs),'technical_repeat_results':repeats,
            'summary':f"{len(measured)} measured results · {sum(r['status']=='not_applicable' for r in records)} not applicable combinations · {len(inputs)} inputs.",
            'scope':'Small workflow-validation selection; not a full scientific panel or an assembler ranking.'}
        if repeats:publication['scope']+=f' {repeats} technical-repeat results reuse the same prepared input; they are not independent biological samples.'
        if any(r['case'].get('recipe',{}).get('input_policy')=='declared_real_subset' for r in measured):
            publication['scope']+=' The real-read pilot uses a declared subset and a matched reference comparator, not independently established error-free truth.'
        _save(output/'publication.json',publication)
    (output/'assets').mkdir(parents=True)
    for source in ASSETS.iterdir():
        if source.is_file():shutil.copyfile(source,output/'assets'/source.name)
    public=[_public_record(root,output,r) for r in records]
    if publication:
        for record in public:record['publication']=publication
    definitions={field:copy.deepcopy(catalogue.get(field,{})) for field in ['collections','scenarios']}
    for field in definitions:
        for identity in sorted({identity for r in records for identity in r['case'][field]}):
            definitions[field].setdefault(identity,{'id':identity,'title':identity.replace('-',' ').capitalize()})
    body='<header class="page-heading home-heading"><h1>Genome assembly benchmarks</h1><p class="intro">Compare current results across dataset collections and focused assembly challenges.</p><p>Single-isolate bacterial genomes. Short and long reads, real and simulated inputs, with explicit methods and applicable workflows.</p></header>'
    body+='<section><h2><a href="broad/index.html">Broad benchmarks</a></h2><p class="section-description">Performance across declared dataset collections.</p>'+_listing(definitions['collections'],public,'collections','broad/')+'</section>'
    body+='<section><h2><a href="scenarios/index.html">Targeted scenarios</a></h2><p class="section-description">Specific scientific questions, controlled conditions and shared baselines.</p>'+_listing(definitions['scenarios'],public,'scenarios','scenarios/')+'</section>'
    if publication:
        body=body.replace('<h1>Genome assembly benchmarks</h1>','<h1>Nextflow pilot reports</h1>').replace('Compare current results across dataset collections and focused assembly challenges.','Small-scale validation of the new Nextflow workflow, with measured outputs and explicit scope.')
    _write_page(output,'index.html','Nextflow pilot reports' if publication else 'Genome assembly benchmarks',body)
    for field,kind,route,title in [('collections','collection','broad','Broad benchmarks'),('scenarios','scenario','scenarios','Targeted scenarios')]:
        body='<header class="page-heading"><h1>'+title+'</h1><p class="intro">'+('Collections retain their own dataset scope and eligible workflows.' if field=='collections' else 'Choose a focused question to inspect its conditions and current measurements.')+'</p></header>'+_listing(definitions[field],public,field,'')
        _write_page(output,route+'/index.html',title,body,route)
        for identity,definition in definitions[field].items():
            _comparison(output,kind,identity,definition,[r for r in public if identity in r['case'][field]])
    workflows={r['workflow']['id']:_workflow(r) for r in public}
    body='<header class="page-heading"><h1>Assemblers</h1><p class="intro">Inspect a current configuration across its applicable tests.</p></header><div class="collection-list">'
    for identity,title in sorted(workflows.items(),key=lambda v:v[1]):
        selected=[r for r in public if r['workflow']['id']==identity];versions=sorted({r['workflow']['version'] for r in selected})
        body+='<article><h3><a href="'+identity+'.html">'+escape(title)+'</a></h3><p>'+escape(identity)+' · Recorded versions: '+escape(', '.join(versions))+'</p></article>'
        _comparison(output,'workflow',identity,{'title':title,'question':'How does this configuration perform across its applicable current tests?','scientific_scope':'Actual versions, read technologies, source kinds and metric methods are shown for each result.'},selected)
    _write_page(output,'assemblers/index.html','Assemblers',body+'</div>','assemblers')
    (output/'data').mkdir(exist_ok=True);(output/'data/measurements.tsv').write_text(_tsv(public))
    for record in public:_details(root,output,record)
    index={'schema_version':2,'kind':'current_site','collections':definitions['collections'],'scenarios':definitions['scenarios'],
        'results':[{'result_id':r['result_id'],'case_id':r['case']['id'],'workflow_id':r['workflow']['id'],'record':'results/'+r['result_id']+'.json','report':'results/'+r['result_id']+'.html'} for r in public]}
    if publication:index['publication']=publication
    _save(output/'catalogue.json',index)
    import hashlib
    report=validate_site(output)
    if report['errors']:raise ValueError('Public site validation failed: '+str(report['errors']))
    _save(output/'.current-site.json',{'schema_version':2,'kind':'current_site','result_count':len(public),'source_catalogue_sha256':hashlib.sha256((root/'catalogue.json').read_bytes()).hexdigest(),'validation':report})
    return report


def render_current(results,outdir,*,pilot=False):
    """Render current packages only; an optional scientific-output-independent step."""
    root,output=Path(results).resolve(),Path(outdir).resolve()
    if root==output or output in root.parents:raise ValueError('Website cannot overwrite its scientific results')
    if root in output.parents and output.relative_to(root).parts[0] in ('packages','dependencies'):
        raise ValueError('Website cannot overwrite owned scientific packages')
    if output.exists():
        marker=output/'.current-site.json'
        if not marker.is_file() or json.loads(marker.read_text()).get('kind')!='current_site':
            raise ValueError('Existing website directory is not owned by this renderer')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.current-site-',dir=output.parent) as temporary:
        staged=Path(temporary)/'site';staged.mkdir();report=_render(root,staged,pilot=pilot)
        previous=output.with_name('.'+output.name+'-obsolete-'+uuid.uuid4().hex)
        if output.exists():output.rename(previous)
        try:staged.rename(output)
        except BaseException:
            if previous.exists():previous.rename(output)
            raise
        if previous.exists():shutil.rmtree(previous)
    return report
