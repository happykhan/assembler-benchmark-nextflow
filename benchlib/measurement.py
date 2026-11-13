"""Measured assembly statistics and saved alignment evidence; no assembly execution."""
import csv
from html import escape
import json
from pathlib import Path
import subprocess
import time
from .assessment import outcome,parse_paf,read_fasta,summarise
from .io import digest
from .process import measured_run

def save(path,value):
    Path(path).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')


def union_breadth(rows,length):
    intervals=[]
    for row in rows:
        start,end=row['reference_start'],row['reference_end'];span=end-start
        if span>=length:return 1.0
        start%=length;end=start+span
        intervals.append((start,min(end,length)))
        if end>length:intervals.append((0,end-length))
    total=0;right=0
    for left,end in sorted(intervals):
        total+=max(0,end-max(left,right));right=max(right,end)
    return total/length


def n50(lengths,target=None):
    target=sum(lengths) if target is None else target;total=0
    for length in sorted(lengths,reverse=True):
        total+=length
        if 2*total>=target:return length
    return None


def metric(name,value,unit,method,**extra):
    return dict(name=name,value=value,unit=unit,method=method,**extra)


def prepare_visuals(directory, references, queries, rows, graph=None):
    directory=Path(directory)
    with (directory/'alignments.tsv').open('w',newline='') as stream:
        writer=csv.writer(stream,delimiter='\t');writer.writerow(['query','reference','query_start','query_end','reference_start','reference_end','strand'])
        for r in rows:writer.writerow([r[k] for k in ['query','reference','query_start','query_end','reference_start','reference_end','strand']])
    height=max(220,220*len(references));svg=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 {height}"><rect width="100%" height="100%" fill="white"/>']
    offsets={};total=0
    for name,sequence in queries.items():offsets[name]=total;total+=len(sequence)
    for i,(name,sequence) in enumerate(references.items()):
        y=220*i+35;svg.append(f'<text x="40" y="{y}" font-family="sans-serif" font-size="13">{escape(name)} · tripled reference / concatenated contigs</text><path d="M40 {y+10}v160h820" fill="none" stroke="#888"/>')
        for r in rows:
            if r['reference']!=name:continue
            qs,qe=r['query_start'],r['query_end']
            if r['strand']=='-':qs,qe=qe,qs
            x1=40+820*r['reference_start']/(3*len(sequence));x2=40+820*r['reference_end']/(3*len(sequence))
            y1=y+170-160*(offsets[r['query']]+qs)/max(total,1);y2=y+170-160*(offsets[r['query']]+qe)/max(total,1)
            svg.append(f'<line x1="{x1:.3f}" x2="{x2:.3f}" y1="{y1:.3f}" y2="{y2:.3f}" stroke="#4c78a8"/>')
    (directory/'dotplot.svg').write_text(''.join(svg)+'</svg>')
    if graph is not None and Path(graph).is_file():
        nodes=[];edges=[]
        for line in Path(graph).read_text().splitlines():
            fields=line.split('\t')
            if fields[0]=='S' and len(fields)>=3:
                length=len(fields[2]) if fields[2]!='*' else next((int(t[5:]) for t in fields[3:] if t.startswith('LN:i:')),None)
                nodes.append({'id':fields[1],'length_bp':length})
            elif fields[0]=='L' and len(fields)>=6:edges.append({'source':fields[1],'source_orientation':fields[2],'target':fields[3],'target_orientation':fields[4]})
        save(directory/'graph.json',{'status':'available' if nodes else 'empty','nodes':nodes,'edges':edges,
            'scope':'Recorded GFA topology; reference origins and physical topology are not inferred.'})


def assess(prepared,execution_dir,slot,directory):
    started=time.monotonic();prepared=Path(prepared);execution_dir=Path(execution_dir);directory=Path(directory);directory.mkdir(parents=True)
    case=slot['case'];workflow=slot['workflow'];execution=json.loads((execution_dir/'execution.json').read_text());inputs=json.loads((prepared/'input.json').read_text())
    provenance=json.loads((prepared/inputs['reference_metadata']).read_text())
    record={'schema_version':2,'case':case,'workflow':workflow,'status':'execution_failure' if execution['status']!='completed' else 'assessment_failure',
        'metrics':[],'sequence_outcome':None,'experiment':{'description':case.get('title',case['id']),'recipe':case['recipe']},
        'input':{'id':inputs['id'],'layout':inputs['layout'],'observed':inputs['observed'],'reference':provenance},
        'provenance':{'input_sha256':digest(prepared/'input.json'),'execution_sha256':digest(execution_dir/'execution.json')},
        'execution':execution}
    try:
        # Bind measurement to the exact retained execution and prepared input.
        if execution.get('input_id') != inputs['id'] or execution.get('input_sha256') != digest(prepared/'input.json'):
            raise ValueError('Execution/prepared input binding differs')
        if case.get('input_id', inputs['id']) != inputs['id']:
            raise ValueError('Case/prepared input identity differs')
        if execution['status']!='completed':
            record['reason']=execution.get('reason','Assembly execution failed')
        else:
            assembly=execution_dir/execution['assembly']
            if digest(assembly)!=execution['assembly_sha256']:raise ValueError('Retained assembly changed')
            reference=prepared/inputs['reference']
            if digest(reference)!=provenance['reference_sha256']:raise ValueError('Reference changed')
            references=read_fasta(reference);queries=read_fasta(assembly) if assembly.stat().st_size else {}
            tripled=directory/'tripled-reference.fasta';tripled.write_text(''.join('>'+name+'\n'+sequence*3+'\n' for name,sequence in references.items()))
            command=['minimap2','-c','--cs=long','-t','1','-x','asm20','-r','10000','-g','10000','-z','1000,500','tripled-reference.fasta','../'+execution_dir.name+'/assembly.fasta']
            if not (directory/command[-1]).is_file():command[-1]=str(assembly.resolve())
            if queries:
                measurement=measured_run(command,directory/'alignment.paf',directory/'mapper.log',directory)
                if measurement['exit_code']:raise ValueError('Assessment mapper failed')
            else:(directory/'alignment.paf').write_text('');measurement={}
            rows=parse_paf(directory/'alignment.paf',references,queries)
            types={m['accession']:m['type'] for m in provenance['molecules']}
            molecules=summarise(references,rows,types);metrics=[]
            for m in molecules:
                accession=m['accession'];matched=[r for r in rows if r['reference']==accession]
                metrics.append(metric('reference_breadth',union_breadth(matched,m['length_bp']),'fraction','minimap2-reference-union-v1',reference=accession,primary=case['read_technology']=='short'))
                for name,value,unit in [('longest_alignment_contiguity',m['contiguity'],'fraction_uncapped'),('longest_alignment_identity',m['identity'],'fraction'),('longest_alignment_max_indel',m['max_indel_bp'],'bp')]:
                    metrics.append(metric(name,value,unit,'wick-longest-alignment-v1',reference=accession,primary=name=='longest_alignment_contiguity' and case['read_technology']=='long'))
            lengths=[len(s) for s in queries.values()]
            for name,value,unit in [('contig_count',len(lengths),'count'),('assembly_length',sum(lengths),'bp'),('contig_n50',n50(lengths),'bp'),('contig_ng50',n50(lengths,sum(map(len,references.values()))),'bp')]:
                metrics.append(metric(name,value,unit,'assembly-length-statistics-v1'))
            record.update(status='measured',metrics=metrics,molecules=molecules,
                sequence_outcome=outcome(molecules,len(queries)) if case['read_technology']=='long' else None,
                assessment={'method':'wick-longest-alignment-v1' if case['read_technology']=='long' else 'reference-breadth-fragmented-v1',
                    'mapper_version':subprocess.check_output(['minimap2','--version'],text=True).strip(),
                    'reference_breadth_scope':'Union of saved alignment intervals modulo original reference length; overlaps counted once.',
                    'structural_correctness':None,'measurement':measurement})
            prepare_visuals(directory,references,queries,rows,execution_dir/execution['graph'] if execution.get('graph') else None)
    except Exception as error:
        record.update(status='assessment_failure',sequence_outcome=None,metrics=[],reason=type(error).__name__+': '+str(error))
    elapsed=time.monotonic()-started
    record['metrics']+=[metric('workflow_wall_seconds',execution.get('wall_seconds',0)+elapsed,'s','process-wall-time-v1'),
        metric('assembler_peak_ram',execution.get('process_tree_peak_rss_bytes'),'bytes','sampled-process-tree-rss-v1')]
    save(directory/'result.json',record)
    return record
