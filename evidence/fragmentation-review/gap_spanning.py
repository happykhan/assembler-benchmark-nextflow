#!/usr/bin/env python3
"""Read-only spanning counts for independently identified Lactococcus gaps."""
import argparse
import hashlib
import json
from pathlib import Path
from read_geometry import HEADER

GAPS = {'flye-2.9.6': [(537339,538743),(1984040,1986322)],
        'raven-1.8.3': [(452960,453836)]}

def contains(start,length,a,b,size):
    return any(start+k*size<=a and start+length+k*size>=b for k in (-1,0,1))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    directory=next((args.root/'work/standard-baseline-v1/df').glob('d3e3ba*'))
    sim=json.loads((directory/'simulation.json').read_text())
    prov=json.loads((directory/'reference.json').read_text())
    size=prov['molecules'][0]['length_bp'];accession=prov['molecules'][0]['accession'].encode()
    intervals=[];h=hashlib.sha256()
    with (directory/'reads.fastq').open('rb') as f:
        while True:
            rows=[f.readline() for _ in range(4)]
            if not rows[0]:break
            for line in rows:h.update(line)
            m=HEADER.search(rows[0]);n=len(rows[1].rstrip(b'\r\n'))
            if not m or m[1]!=accession:raise ValueError('Reference binding differs')
            start=int(m[3]);forward=start if m[2]==b'+' else (size-start-n)%size
            intervals.append((forward,n))
    if h.hexdigest()!=sim['reads_sha256']:raise ValueError('Frozen reads changed')
    result={'schema_version':1,'case_id':sim['case']['id'],'reads_sha256':h.hexdigest(),
            'reference_length':size,'read_count':len(intervals),
            'gap_basis':'Independently exact-placed source assembly contigs;0based half-open reference gaps.',
            'limitations':['Flanks are geometric distances, not verified unique anchors; repeat resolvability and assembler-internal filtering are not established.'],
            'results':[]}
    for assembler,gaps in GAPS.items():
        for a,b in gaps:
            result['results'].append({'assembler':assembler,'gap':[a,b],'gap_length':b-a,
                'spanning_reads':{str(flank):sum(contains(s,n,a-flank,b+flank,size) for s,n in intervals)
                                  for flank in (0,1000)}})
    with args.out.open('x') as f:json.dump(result,f,indent=2,sort_keys=True)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
