#!/usr/bin/env python3
"""Add a complete beta Standard bundle to the existing benchmark website."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from reporting.beta_site import render_beta

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--bundle',type=Path,required=True)
p.add_argument('--base-site',type=Path,required=True)
p.add_argument('--out-dir',type=Path,required=True)
a=p.parse_args()
print(render_beta(a.bundle,a.base_site,a.out_dir))
