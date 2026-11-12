#!/usr/bin/env python3
"""Build a standalone website from sealed results, without source repositories."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reporting.archive import render_website
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--bundle', required=True, type=Path)
parser.add_argument('--out-dir', required=True, type=Path)
args = parser.parse_args()
print(render_website(args.bundle, args.out_dir))
