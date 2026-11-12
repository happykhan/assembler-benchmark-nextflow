#!/usr/bin/env python3
"""Internal Nextflow task: verify and stage one exact published input."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchlib.general_inputs import prepare_general_input
from benchlib.general_planning import validate_general_plan

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[1])
p.add_argument('--case-json', required=True)
p.add_argument('--plan', type=Path, required=True)
p.add_argument('--cache', type=Path, required=True)
p.add_argument('--outdir', type=Path, default=Path('.'))
p.add_argument('--offline', action='store_true')
a = p.parse_args()
plan = validate_general_plan(a.project, json.loads(a.plan.read_text()))
case = json.loads(a.case_json)
if case not in plan['cases']:
    raise ValueError('Case is not bound to frozen general plan')
prepare_general_input(case, plan['read_inputs'][case['id']], a.cache, a.outdir, a.offline)
