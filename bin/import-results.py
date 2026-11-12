#!/usr/bin/env python3
"""Admit an existing sealed result bundle; no compute jobs or sequence work."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reporting.archive import import_archive
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', required=True, type=Path)
parser.add_argument('--out-dir', required=True, type=Path)
args = parser.parse_args()
print(json.dumps(import_archive(args.source, args.out_dir), sort_keys=True))
