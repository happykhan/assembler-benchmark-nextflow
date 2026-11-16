#!/usr/bin/env python3
"""Compose a verified Standard report while pinning supplementary batch URLs."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from reporting.publication import compose_standard

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--base',type=Path,required=True)
p.add_argument('--standard',type=Path,required=True)
p.add_argument('--outdir',type=Path,required=True)
p.add_argument('--archive-origin',required=True)
p.add_argument('--archive-deployment-id',required=True)
p.add_argument('--evidence',type=Path,required=True)
a=p.parse_args()
report=compose_standard(a.base,a.standard,a.outdir,archive={'origin':a.archive_origin,'deployment_id':a.archive_deployment_id})
a.evidence.parent.mkdir(parents=True,exist_ok=True)
a.evidence.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('published_files','base_files','archived_files')},sort_keys=True))
