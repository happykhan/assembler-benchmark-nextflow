#!/usr/bin/env python3
"""Independent seed placements and same-length sequence comparisons."""
import gzip
import hashlib
import json
from pathlib import Path
from exact_placement import ROOT, BUNDLE, fasta, rc, placements, intervals, coverage


def candidates(query, reference, anchor=256):
    votes = {}
    offsets = sorted({0, len(query)//4, len(query)//2, 3*len(query)//4, len(query)-anchor})
    for offset in offsets:
        sequence = query[offset:offset+anchor]
        start = 0
        while True:
            match = (reference*2).find(sequence, start)
            if match < 0 or match >= len(reference):
                break
            candidate = (match-offset)%len(reference)
            votes.setdefault(candidate, []).append(offset)
            start = match+1
    return sorted(votes.items(), key=lambda row:(-len(row[1]),row[0]))


def main():
    registry = {r['id']:r for r in json.loads((ROOT/'assets/references.json').read_text())['references']}
    data = json.loads((BUNDLE/'results.json').read_text())['results']
    output = {'method':'Independent256bp exact anchor vote, followed by direct base-by-base comparison at candidate circular coordinates; no PAF or pipeline parser', 'results':[]}
    for result in data:
        case = result['case']
        reference = next(iter(fasta(gzip.decompress((ROOT/'references'/(case['reference_id']+'.source.gz')).read_bytes()).decode()).values()))
        assembly = fasta((BUNDLE/'assemblies'/case['id']/result['assembler']/'assembly.fasta').read_text())
        rows, placed = [], []
        for name, sequence in assembly.items():
            exact = placements(sequence,reference)
            if len(exact)==1:
                placed.extend(exact[0]['reference_intervals'])
                rows.append({'id':name,'length_bp':len(sequence),'exact':True,'placement':exact[0]})
                continue
            tested = []
            for strand, query in [('+',sequence),('-',rc(sequence))]:
                for start, offsets in candidates(query,reference)[:5]:
                    expected = (reference*2)[start:start+len(query)]
                    mismatches = [{'query_offset_0based':i,'reference_position_0based':(start+i)%len(reference),
                                   'reference_base':a,'assembly_base':b}
                                  for i,(a,b) in enumerate(zip(expected,query)) if a!=b]
                    tested.append({'start_0based':start,'strand':strand,'anchor_offsets':offsets,
                                   'reference_intervals':intervals(start,len(query),len(reference)),
                                   'hamming_distance':len(mismatches),
                                   'mismatches':mismatches if len(mismatches)<=20 else None})
            tested.sort(key=lambda x:x['hamming_distance'])
            best = tested[0] if tested else None
            rows.append({'id':name,'length_bp':len(sequence),'exact':False,'best_same_length_placement':best})
            if best and best['hamming_distance']<=1:
                placed.extend(best['reference_intervals'])
        output['results'].append({'case_id':case['id'],'assembler':result['assembler'],
                                  'reference_length_bp':len(reference),'contigs':rows,
                                  'coverage_from_exact_or_single_substitution_placements':coverage(placed,len(reference))})
    Path(__file__).with_name('anchor-placement.json').write_text(json.dumps(output,indent=2)+'\n')
    for row in output['results']:
        print(row['case_id'],row['assembler'],row['coverage_from_exact_or_single_substitution_placements'])
        for c in row['contigs']:
            if not c['exact']:print(c)


if __name__=='__main__':
    main()
