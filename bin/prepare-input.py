#!/usr/bin/env python3
"""Internal scientific input generation; dependency admission is separate."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from benchlib.inputs_v2 import prepare_input
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--input',required=True);p.add_argument('--dependencies',required=True);p.add_argument('--cache-dir',required=True)
a=p.parse_args()
prepare_input(json.loads(a.input),json.loads(a.dependencies),a.cache_dir,Path('prepared'))
