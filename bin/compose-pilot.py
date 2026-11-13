#!/usr/bin/env python3
"""Add labelled pilot reports to a verified static website; never run science."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from reporting.publication import compose_pilot
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--base',type=Path,required=True);p.add_argument('--pilot',type=Path,required=True)
p.add_argument('--outdir',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
a=p.parse_args();report=compose_pilot(a.base,a.pilot,a.outdir)
a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('base_files','published_files')},sort_keys=True))
