#!/usr/bin/env python3
"""Union reference positions aligned to query bases, excluding query gaps."""
import hashlib
import json
from pathlib import Path
from exact_placement import coverage

BASE = Path(__file__).parent/'mummer'


def modulo(start,end,size):
    rows = []
    while start<end:
        origin = start%size
        take = min(end-start,size-origin)
        rows.append((origin,origin+take))
        start += take
    return rows


def delta_bases(path,size):
    positions = []
    alignment = None
    r = consumed_q = None
    for line in path.read_text().splitlines()[2:]:
        if line.startswith('>'):
            continue
        fields = line.split()
        if len(fields)==7:
            alignment = list(map(int,fields))
            rs,re,qs,qe = alignment[:4]
            assert rs<=re
            r,consumed_q = rs-1,0
        elif len(fields)==1:
            d = int(fields[0])
            assert alignment is not None
            if d:
                matches = abs(d)-1
                positions.extend(modulo(r,r+matches,size))
                r += matches
                consumed_q += matches
                if d>0:
                    # Positive delta is a reference base opposite a query gap.
                    r += 1
                else:
                    consumed_q += 1
            else:
                rs,re,qs,qe = alignment[:4]
                remaining_r = re-r
                remaining_q = abs(qe-qs)+1-consumed_q
                assert remaining_r==remaining_q,(path,alignment,remaining_r,remaining_q)
                positions.extend(modulo(r,re,size))
                alignment = None
    assert alignment is None
    return coverage(positions,size)


def main():
    source = BASE/'summary.json'
    output = {'method':__doc__, 'source_summary_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
              'delta_convention':'Positive delta is a gap in query; coordinate consumption independently checked against every alignment endpoint.',
              'results':[]}
    for row in json.loads(source.read_text())['results']:
        result = {'case_id':row['case_id'],'assembler':row['assembler'],'checks':[]}
        for check in row['checks']:
            path = BASE/row['case_id']/row['assembler']/str(check['reference_copies'])/'query-best.delta'
            result['checks'].append({'reference_copies':check['reference_copies'],
                                    'delta_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                                    'aligned_reference_base_coverage':delta_bases(path,row['reference_length_bp'])})
        output['results'].append(result)
    Path(__file__).with_name('mummer-covered-bases.json').write_text(json.dumps(output,indent=2)+'\n')
    for r in output['results']:
        print(r['case_id'],r['assembler'],[(c['aligned_reference_base_coverage']['coverage_fraction'],c['aligned_reference_base_coverage']['gaps']) for c in r['checks']])


if __name__=='__main__':
    main()
