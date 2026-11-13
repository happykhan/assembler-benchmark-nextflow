#!/usr/bin/env python3
"""Internal input-scoped call to the common preparation program."""
import argparse
import json
from pathlib import Path
import sys
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from benchlib.preparation import plan_preparation,execute_work_list
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--input',required=True);p.add_argument('--dependencies',required=True)
p.add_argument('--cache-dir',required=True);p.add_argument('--offline',action='store_true')
a=p.parse_args();spec=json.loads(a.input)
w=plan_preparation(json.loads(a.dependencies),a.cache_dir,PROJECT,offline=a.offline,input_ids=[spec['id']],kinds=['reference','reference_archive','published_reads','real_reads','simulator_profile','assessment_resource','file'])
Path('admitted.json').write_text(json.dumps(execute_work_list(w,offline=a.offline),indent=2,sort_keys=True)+'\n')
