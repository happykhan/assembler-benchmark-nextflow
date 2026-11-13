#!/usr/bin/env python3
"""Internal Nextflow selection/preflight entry point."""
import argparse
from pathlib import Path
import sys
if sys.version_info < (3,9):
    raise SystemExit('This workflow needs Python 3.9+ on the submission host; set --bootstrap_python /path/to/python3.11.')

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from benchlib.setup import setup

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--selection',required=True);p.add_argument('--catalogue',type=Path)
p.add_argument('--cache-dir',required=True);p.add_argument('--offline',action='store_true');p.add_argument('--plan-only',action='store_true')
p.add_argument('--runtime',default='pixi',choices=['pixi','native'])
p.add_argument('--container-runtime',choices=['docker','singularity','apptainer']);p.add_argument('--container-image')
setup(p.parse_args(),PROJECT)
