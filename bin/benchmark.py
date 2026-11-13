#!/usr/bin/env python3
"""Publish, summarise and export current results without scientific execution."""
import argparse
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))


def read(path):return json.loads(Path(path).read_text())
def write(path,value):Path(path).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')


def publish(args):
    from benchlib.current_results import publish_result
    record=read(Path(args.assessment)/'result.json');slot=json.loads(args.slot);record.update(case=slot['case'],workflow=slot['workflow']);execution=Path(args.execution);assessment=Path(args.assessment);prepared=Path(args.prepared)
    from benchlib.descriptions import input_description
    record['input']['declaration']=input_description(slot['input_definition'])
    artifacts={}
    for filename,role in [('assembly.fasta','assembly'),('assembly.gfa','assembly_graph'),('stdout.log','stdout'),('stderr.log','stderr')]:
        path=execution/filename
        if path.is_file():artifacts[filename]={'source':path,'role':role}
    for filename,role in [('alignment.paf','alignment'),('alignments.tsv','alignment_coordinates'),('dotplot.svg','alignment_plot'),('graph.json','graph_model'),('mapper.log','assessment_log')]:
        path=assessment/filename
        if path.is_file():artifacts[filename]={'source':path,'role':role}
    # Multi-stage workflows retain raw-phase evidence once in their result package.
    for path in (execution/'tool-output').rglob('*') if (execution/'tool-output').exists() else []:
        if path.is_file() and path.suffix in ('.fasta','.gfa','.json','.log'):
            artifacts['workflow/'+path.relative_to(execution/'tool-output').as_posix()]={'source':path,'role':'workflow_phase'}
    inputs=read(prepared/'input.json');ref=prepared/inputs['reference'];provenance=read(prepared/inputs['reference_metadata'])
    reference_id='reference-'+provenance['reference_sha256'][:24]
    dependencies={reference_id:{'record':provenance,'files':{'reference.fasta':ref}},
                  inputs['id']:{'record':{'id':inputs['id'],'description':'Prepared input metadata; large reads remain in the shared scientific cache.',
                    'read_technology':inputs['read_technology'],'source_kind':inputs['source_kind'],'layout':inputs['layout'],
                    'recipe':inputs['recipe'],'observed':inputs['observed']},'files':{'input.json':prepared/'input.json'}}}
    entry=publish_result(args.outdir,record,artifacts=artifacts,dependencies=dependencies)
    write('published.json',entry)


def exclusions(args):
    from benchlib.current_results import publish_result
    slot=json.loads(args.slot)
    record={'schema_version':2,'case':slot['case'],'workflow':slot['workflow'],'status':'not_applicable',
            'metrics':[],'sequence_outcome':None,'reason':slot['reason'],
            'experiment':{'description':slot['case'].get('title',slot['case']['id']),'recipe':slot['case']['recipe']}}
    write('published.json',publish_result(args.outdir,record))


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('publish');p.add_argument('--prepared',required=True);p.add_argument('--execution',required=True);p.add_argument('--assessment',required=True);p.add_argument('--slot',required=True);p.add_argument('--outdir',required=True)
    p=commands.add_parser('exclude');p.add_argument('--slot',required=True);p.add_argument('--outdir',required=True)
    p=commands.add_parser('aggregate');p.add_argument('--outdir',required=True);p.add_argument('--definitions',required=True)
    p=commands.add_parser('subset');p.add_argument('--outdir',required=True);p.add_argument('--destination',required=True);p.add_argument('--cases',default='')
    args=parser.parse_args()
    if args.command=='publish':publish(args)
    elif args.command=='exclude':exclusions(args)
    elif args.command=='aggregate':
        from benchlib.current_results import refresh_summaries,set_catalogue_metadata
        from benchlib.selection_status import publish_selection_status
        definitions=json.loads(args.definitions)
        set_catalogue_metadata(args.outdir,{k:definitions[k] for k in ('collections','scenarios')});refresh_summaries(args.outdir)
        write('aggregated.json',publish_selection_status(args.outdir,definitions['selection']))
    elif args.command=='subset':
        from benchlib.current_results import export_subset
        export_subset(args.outdir,args.destination,case_ids=args.cases.split(',') if args.cases else None)


if __name__=='__main__':main()
