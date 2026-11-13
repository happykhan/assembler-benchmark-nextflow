#!/usr/bin/env python3
"""Inspect owned finished work by default; --execute explicitly removes it."""
import argparse
import json
from pathlib import Path
import sys

if sys.version_info < (3,9):
    raise SystemExit('This workflow needs Python 3.9+ on the submission host; set --bootstrap_python /path/to/python3.11.')

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from benchlib.cleanup import cleanup_work, finish_work, register_work


def main(argv=None):
    values=list(sys.argv[1:] if argv is None else argv)
    if not values or values[0].startswith('-'):values.insert(0,'inspect')
    p=argparse.ArgumentParser(description=__doc__)
    commands=p.add_subparsers(dest='command',required=True)
    inspect=commands.add_parser('inspect',help='Dry-run by default; never follows shared-data links')
    inspect.add_argument('--work-dir',type=Path,required=True)
    inspect.add_argument('--execute',action='store_true',help='Remove only this finished owned operational work root; disables its resume')
    begin=commands.add_parser('begin',help='Controller lifecycle hook; does not delete files')
    begin.add_argument('--work-dir',type=Path,required=True)
    begin.add_argument('--cache-dir',type=Path,required=True)
    begin.add_argument('--outdir',type=Path,required=True)
    begin.add_argument('--project',type=Path,default=PROJECT)
    begin.add_argument('--run-id',required=True)
    begin.add_argument('--controller-pid',type=int)
    begin.add_argument('--controller-host')
    begin.add_argument('--allow-unowned-existing',action='store_true')
    finish=commands.add_parser('finish',help='Controller completion hook; does not delete files')
    finish.add_argument('--work-dir',type=Path,required=True)
    finish.add_argument('--run-id',required=True)
    outcome=finish.add_mutually_exclusive_group(required=True)
    outcome.add_argument('--success',action='store_true');outcome.add_argument('--failed',action='store_true')
    args=p.parse_args(values)
    try:
        if args.command=='inspect':result=cleanup_work(args.work_dir,execute=args.execute)
        elif args.command=='begin':result=register_work(args.work_dir,args.cache_dir,args.outdir,args.project,args.run_id,
            controller_pid=args.controller_pid,controller_host=args.controller_host,allow_unowned_existing=args.allow_unowned_existing)
        else:result=finish_work(args.work_dir,args.run_id,args.success)
        print(json.dumps(result,indent=2,sort_keys=True))
    except (OSError,ValueError,KeyError) as error:p.exit(2,'Cleanup refused: '+str(error)+'\n')


if __name__=='__main__':main()
