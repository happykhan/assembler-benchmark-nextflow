#!/usr/bin/env python3
"""Internal assessment of retained assembly; never invokes an assembler."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from benchlib.measurement import assess
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--prepared',required=True);p.add_argument('--execution',required=True);p.add_argument('--slot',required=True)
a=p.parse_args();assess(a.prepared,a.execution,json.loads(a.slot),'assessment')
