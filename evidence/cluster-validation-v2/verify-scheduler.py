"""Read-only Slurm corroboration of this validation's Nextflow task inventory."""
import argparse
import csv
import getpass
import io
import json
from pathlib import Path
import re
import subprocess


def verify(trace):
    with Path(trace).open() as stream: rows=list(csv.DictReader(stream,delimiter='\t'))
    selected=[r for r in rows if r['name'] not in ('PREPARE_RUN','LIST_CHOICES')]
    ids={r['native_id'] for r in selected}
    if not ids or any(not re.fullmatch('[0-9]+',v) for v in ids):
        raise ValueError('Missing or invalid Slurm task identifiers')
    fields=['JobIDRaw','JobName%200','State%40','ExitCode','AllocCPUS','ReqMem','Timelimit','ElapsedRaw']
    command=['sacct','-X','-n','-P','-u',getpass.getuser(),'-j',','.join(sorted(ids)),
             '--format='+','.join(fields)]
    output=subprocess.check_output(command,universal_newlines=True)
    columns=['job_id','job_name','state','exit_code','allocated_cpus','requested_memory','time_limit','elapsed_seconds']
    accounted=[dict(zip(columns,row)) for row in csv.reader(io.StringIO(output),delimiter='|') if row]
    if {r['job_id'] for r in accounted}!=ids:
        raise ValueError('Slurm accounting does not cover the exact task inventory')
    if any(r['state']!='COMPLETED' or r['exit_code']!='0:0' or not r['job_name'].startswith('nf-') for r in accounted):
        raise ValueError('Non-successful or unrelated scheduler allocation in final trace')
    return {'schema_version':1,'status':'verified','jobs':len(ids),'rows':accounted},output


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('trace',type=Path)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--accounting',type=Path,required=True)
    a=p.parse_args()
    result,raw=verify(a.trace)
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    a.accounting.write_text(raw)
    print(json.dumps({'status':result['status'],'jobs':result['jobs']}))
