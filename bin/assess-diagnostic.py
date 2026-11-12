#!/usr/bin/env python3
"""Assess a native diagnostic execution without changing its frozen exact endpoint."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from diagnostic_core.assessment import assess

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','reference-provenance','input-provenance','assembly','execution','out'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--case-json',required=True)
    parser.add_argument('--assembler',required=True)
    parser.add_argument('--paf',type=Path)
    parser.add_argument('--cpus',type=int,default=1)
    parser.add_argument('--skip-mapping',action='store_true',help='Omit supplementary mapping; exact assessment still runs')
    parser.add_argument('--circularity-json',type=Path)
    args=parser.parse_args()
    if args.cpus<1:
        parser.error('--cpus must be positive')
    assess(json.loads(args.case_json),args.reference,args.reference_provenance,args.input_provenance,
           args.assembly,args.execution,args.assembler,args.out,args.paf,
           json.loads(args.circularity_json.read_text()) if args.circularity_json else None,
           run_mapping=not args.skip_mapping,cpus=args.cpus)
