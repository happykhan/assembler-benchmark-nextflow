#!/usr/bin/env python3
"""Native Nextflow task: admitted reference -> exact diagnostic reads, or frozen S7 order."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from diagnostic_core.preparation import prepare

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--case-json')
    source.add_argument('--case',type=Path)
    parser.add_argument('--reference-dir',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,default=Path('.'))
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--frozen-input-dir',type=Path)
    args=parser.parse_args()
    meta=json.loads(args.case_json if args.case_json is not None else args.case.read_text())
    prepare(meta,args.reference_dir,args.out_dir,args.offline,args.frozen_input_dir)
