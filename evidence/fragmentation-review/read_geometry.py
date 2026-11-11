#!/usr/bin/env python3
"""Read-only interval geometry of frozen error-free reads."""
import argparse
import hashlib
import json
from pathlib import Path
import re

HEADER = re.compile(rb'(?:^|\s)([A-Z0-9_.]+),([+-])strand,(\d+)-(\d+)(?:\s|$)')

def split_interval(start, length, size):
    end = start + length
    if length >= size:
        return [(0, size)]
    return [(start, end)] if end <= size else [(start, size), (0, end-size)]

def union_and_gaps(intervals, size):
    merged = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    gaps, last = [], 0
    for start, end in merged:
        if start > last:
            gaps.append([last, start])
        last = max(last, end)
    if last < size:
        gaps.append([last, size])
    count = len(gaps)
    if len(gaps)>1 and gaps[0][0]==0 and gaps[-1][1]==size:
        count -= 1
    return {'covered_bases': sum(b-a for a,b in merged),
            'uncovered_bases': sum(b-a for a,b in gaps),
            'linearised_gaps': gaps, 'circular_gap_count': count}

def audit(directory):
    simulation=json.loads((directory/'simulation.json').read_text())
    provenance=json.loads((directory/'reference.json').read_text())
    size=provenance['molecules'][0]['length_bp']
    accession=provenance['molecules'][0]['accession'].encode()
    intervals, bases, digest = [], 0, hashlib.sha256()
    with (directory/'reads.fastq').open('rb') as handle:
        while True:
            lines=[handle.readline() for _ in range(4)]
            if not lines[0]: break
            for line in lines: digest.update(line)
            header,seq,plus,qual=lines
            length=len(seq.rstrip(b'\r\n'))
            m=HEADER.search(header)
            if not m or m[1]!=accession or length!=len(qual.rstrip(b'\r\n')):
                raise ValueError('FASTQ/reference binding differs')
            strand,start,end=m[2],int(m[3]),int(m[4])
            if length>end-start: raise ValueError('Fragment length differs')
            forward=start if strand==b'+' else (size-start-length)%size
            intervals.append((forward,length));bases+=length
    if digest.hexdigest()!=simulation['reads_sha256'] or bases!=simulation['target_bases']:
        raise ValueError('Frozen input/budget differs')
    result={'case_id':simulation['case']['id'],'accession':accession.decode(),
            'reference_length':size,'reads_sha256':digest.hexdigest(),
            'read_count':len(intervals),'read_bases':bases,'thresholds':{}}
    for overlap in (0,8000):
        transformed=[]
        for start,length in intervals:
            if length>=overlap: transformed.extend(split_interval(start,length-overlap,size))
        stats=union_and_gaps(transformed,size)
        stats['eligible_reads']=sum(n>=overlap for _,n in intervals)
        stats['mean_transformed_interval_depth']=sum(max(n-overlap,0) for _,n in intervals)/size
        result['thresholds'][str(overlap)]=stats
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();dirs=[]
    for pattern in ('df/d3e3ba*','8d/dac1d9*'):
        found=list((a.root/'work/standard-baseline-v1').glob(pattern))
        if len(found)!=1: raise ValueError('Frozen directory absent/ambiguous')
        dirs.extend(found)
    result={'schema_version':1,'method':'Exact-coordinate interval geometry. Threshold M uses transformed intervals [start,end-M] for reads length>=M on the reference circle. M=0 measures base coverage; M=8000 diagnoses strict overlap connectivity, not Flye internals.',
            'limitations':['Approximate/repeat overlaps and graph heuristics are not modelled; this does not prove individual break causes.'],
            'results':[audit(d) for d in dirs]}
    with a.out.open('x') as out: json.dump(result,out,indent=2,sort_keys=True)
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
