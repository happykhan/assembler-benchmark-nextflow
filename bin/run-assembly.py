#!/usr/bin/env python3
"""Internal typed assembly stage; user entry point is Nextflow."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from benchlib.assembly import assemble
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--prepared',required=True);p.add_argument('--workflow',required=True)
a=p.parse_args();assemble(a.prepared,json.loads(a.workflow),'execution',Path(__file__).resolve().parents[1])
