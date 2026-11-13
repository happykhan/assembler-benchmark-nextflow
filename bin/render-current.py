#!/usr/bin/env python3
"""Build the optional compact website from declared current result packages."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from reporting.current_site import render_current

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--results',type=Path,required=True)
p.add_argument('--outdir',type=Path,required=True)
a=p.parse_args()
print(json.dumps(render_current(a.results,a.outdir),sort_keys=True))
