#!/usr/bin/env python3
"""Inspect or prepare the declared cache used by Nextflow. Never simulate reads."""
import argparse
import importlib
import json
from pathlib import Path
import sys

if sys.version_info < (3,9):
    sys.exit('Preparation requires Python 3.9 or newer as a bootstrap dependency; scientific tools are not required.')

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from benchlib.preparation import PreparationError, execute_work_list, plan_preparation


def runtime_handlers():
    try:runtime = importlib.import_module('benchlib.runtime_v2')
    except ImportError as error:
        if getattr(error,'name',None) not in ('benchlib.runtime_v2',None):raise
        return {},{}
    inspect,prepare = getattr(runtime,'inspect_dependency',None),getattr(runtime,'prepare_dependency',None)
    kinds = ('software','software_environment','container_image')
    return ({k:inspect for k in kinds} if inspect else {},{k:prepare for k in kinds} if prepare else {})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,help='Frozen common-catalogue plan JSON')
    parser.add_argument('--work-list',type=Path,help='Previously inspected work-list JSON')
    parser.add_argument('--project',type=Path)
    parser.add_argument('--cache-dir',type=Path)
    parser.add_argument('--catalogue',type=Path,help='Alternative common catalogue JSON')
    for key in ('cases','scenarios','collections','workflows','inputs','kinds'):parser.add_argument('--'+key,default='')
    parser.add_argument('--all',action='store_true',dest='all_eligible')
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--runtime',choices=['pixi','native'])
    parser.add_argument('--container-runtime',choices=['docker','singularity','apptainer'])
    parser.add_argument('--container-image')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run',action='store_true',help='Inspect only; no downloads or installations (default)')
    mode.add_argument('--execute',action='store_true',help='Execute file/runtime preparation, not simulation')
    parser.add_argument('--out',type=Path,help='Write JSON instead of stdout')
    args = parser.parse_args()
    if args.work_list and (args.runtime or args.container_runtime or args.container_image):
        parser.error('Saved work lists already declare their runtime; do not change it')
    if args.plan and args.work_list:parser.error('Choose --plan or --work-list')
    if (args.plan or args.work_list) and (args.cases or args.scenarios or args.collections or args.workflows
                                        or args.all_eligible or args.catalogue):
        parser.error('Resolved plans/work lists cannot be combined with catalogue selectors; use --inputs or --kinds')
    if args.work_list and args.inputs:parser.error('--inputs requires the original --plan, not a saved work list')
    try:
        inspectors,handlers = runtime_handlers()
        if args.work_list:
            previous = json.loads(args.work_list.read_text())
            plan = {'dependencies':previous['items'],
                    'bootstrap_executables':[r['id'] for r in previous.get('bootstrap',[])]}
            work = plan_preparation(plan,args.cache_dir or previous['cache_dir'],
                                    args.project or previous['project'],inspectors,
                                    offline=args.offline or previous.get('offline',False),
                                    kinds=[v for v in args.kinds.split(',') if v] or None)
        else:
            project = args.project or PROJECT
            if args.plan:plan = json.loads(args.plan.read_text())
            else:
                from benchlib.catalogue import build_plan
                plan = build_plan(project,cases=args.cases,scenarios=args.scenarios,collections=args.collections,
                                  workflows=args.workflows,all_eligible=args.all_eligible,catalogue_path=args.catalogue)
            if not args.plan or args.runtime or args.container_runtime:
                from benchlib.runtime_v2 import runtime_plan
                plan=runtime_plan(plan,project,args.runtime or 'pixi',args.container_runtime,args.container_image)
            work = plan_preparation(plan,args.cache_dir or Path('cache'),project,inspectors,offline=args.offline,
                                    input_ids=[v for v in args.inputs.split(',') if v] or None,
                                    kinds=[v for v in args.kinds.split(',') if v] or None)
        if args.execute:work = execute_work_list(work,offline=work.get('offline',False),handlers=handlers)
        text = json.dumps(work,indent=2,sort_keys=True)+'\n'
        if args.out:
            args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(text)
        else:print(text,end='')
    except (OSError,ValueError,PreparationError,TimeoutError) as error:
        parser.exit(2,'Preparation refused: '+str(error)+'\n')


if __name__=='__main__':main()
