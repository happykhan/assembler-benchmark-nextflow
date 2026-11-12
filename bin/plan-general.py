#!/usr/bin/env python3
"""Freeze the selected published Wick/Holt general benchmark without downloads."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchlib.general_planning import build_general_plan, load_collection

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[1])
p.add_argument('--preset', default='standard')
p.add_argument('--groups', default='')
p.add_argument('--cases', default='')
p.add_argument('--assemblers', default='')
p.add_argument('--out', type=Path)
p.add_argument('--list', action='store_true')
a = p.parse_args()
if a.list:
    selection, _ = load_collection(a.project)
    result = {'track': 'general', 'collection_id': selection['panel_id'], 'cases': selection['datasets'],
              'reported_tools': ['flye', 'raven', 'plassembler', 'miniasm-plus'],
              'input_policy': 'published_frozen_bytes_no_resimulation'}
else:
    result = build_general_plan(a.project, a.preset, a.groups, a.cases, a.assemblers)
if a.out:
    with a.out.open('x') as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + '\n')
else:
    print(json.dumps(result, indent=2, sort_keys=True))
