#!/usr/bin/env python3
"""Verify a completed native Nextflow run without rerunning scientific tools."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from reporting.archive import validate_archive
from reporting.site_gate import check_site
from benchlib.report import verify_plan_binding, record_complete
from benchlib.io import digest


def verify(directory):
    directory=Path(directory)
    bundle=directory/'bundle'
    manifest,kind=validate_archive(bundle)
    if kind!='nextflow' or not manifest.get('complete'):
        raise ValueError('A complete native result bundle is required')
    plan=json.loads((bundle/'slot-plan.json').read_text())
    receipt=json.loads((bundle/'environment-preparation.json').read_text())
    if receipt.get('plan_sha256')!=plan['plan_sha256'] or receipt.get('status') not in ('prepared','externally_prepared'):
        raise ValueError('Runtime receipt is not bound to the frozen plan')
    records=json.loads((bundle/'results.json').read_text())['results']
    expected={(s['case_id'],s['assembler']) for s in plan['slots']}
    actual={(r['case']['id'],r['assembler']) for r in records}
    if actual!=expected or len(records)!=len(expected) or len(records)!=manifest['expected_slots']:
        raise ValueError('Outcome inventory differs from the selected slots')
    for record in records:
        verify_plan_binding(record,plan)
        if not record_complete(record):
            raise ValueError('Unresolved execution/assessment slot')
        if record['execution']['status']!='completed' and record.get('sequence_outcome') is not None:
            raise ValueError('Failed execution was assigned a sequence verdict')
    with (directory/'nextflow-trace.tsv').open() as stream:
        trace=list(csv.DictReader(stream,delimiter='\t'))
    if not trace or any(row['status'] not in ('COMPLETED','CACHED') or row['exit'] not in ('0','-') for row in trace):
        raise ValueError('Nextflow trace contains non-successful or incomplete tasks')
    if not any(row['name']=='RENDER_WEBSITE' for row in trace):
        raise ValueError('Website rendering did not complete')
    site=check_site(directory/'website')
    if site['errors']:
        raise ValueError('Website link/size gate failed: '+str(site['errors']))
    return {'schema_version':1,'status':'verified','run_id':manifest['run_id'],
        'expected_slots':len(expected),'reported_outcomes':len(records),
        'verified_bundle_files':len(manifest['files']),'bundle_manifest_sha256':digest(bundle/'manifest.json'),
        'trace_tasks':len(trace),'trace_statuses':dict(Counter(r['status'] for r in trace)),
        'execution_statuses':dict(Counter(r['execution']['status'] for r in records)),
        'assessment_statuses':dict(Counter(r['assessment']['status'] for r in records)),
        'sequence_outcomes':dict(Counter(str(r.get('sequence_outcome')) for r in records)),
        'execution_sha256':{r['case']['id']+'__'+r['assembler']:r['provenance']['execution_sha256'] for r in records},
        'read_sha256':{r['case']['id']:r['execution']['reads_sha256'] for r in records},
        'site':site,'scheduler_accounting':'Must be checked separately against the Slurm task IDs.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    p.add_argument('--out',type=Path)
    a=p.parse_args()
    try:
        result=verify(a.directory)
    except (OSError,ValueError,KeyError) as error:
        p.exit(2,'Verification failed: '+str(error)+'\n')
    text=json.dumps(result,indent=2,sort_keys=True)+'\n'
    if a.out:a.out.write_text(text)
    else:print(text,end='')
