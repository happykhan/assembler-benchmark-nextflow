#!/usr/bin/env python3
"""Native Nextflow comparison task for S3/S7, with explicit expected denominators."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from diagnostic_core.comparison import compare_results
from diagnostic_core.common import save
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--results',type=Path,nargs='+',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    save(args.out,compare_results([json.loads(p.read_text()) for p in args.results],json.loads(args.plan.read_text())))
