#!/usr/bin/env python3
"""Internal Miniasm workflow entry point; public runs use Nextflow."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchlib.miniasm import run
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--reads', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--threads', type=int, required=True)
p.add_argument('--polish', action='store_true')
p.add_argument('--expected-versions-json', required=True)
a = p.parse_args()
run(a.reads, a.output, a.threads, a.polish, json.loads(a.expected_versions_json))
