"""Independent arithmetic audit of saved PAF, without the pipeline assessor."""
import argparse,hashlib,json,math,re
from pathlib import Path


def audit(bundle):
    bundle=Path(bundle)
    records=json.loads((bundle/'results.json').read_text())['results']
    checked=[]
    for result in records:
        if result['assessment']['status']!='completed':continue
        if result['assessment']['method']!='wick-longest-alignment-v1':continue
        source=bundle/result['evidence_directory']/'alignment.paf'
        if hashlib.sha256(source.read_bytes()).hexdigest()!=result['assessment']['paf_sha256']:
            raise ValueError('Saved PAF checksum differs')
        rows=[line.split('\t') for line in source.read_text().splitlines() if line]
        for molecule in result['replicons']:
            matches=[f for f in rows if f[5]==molecule['accession']]
            for fields in matches:
                assert int(fields[6])==3*molecule['length_bp']
            best=sorted(enumerate(matches),key=lambda pair:(-(int(pair[1][8])-int(pair[1][7])),int(pair[1][7]),pair[0]))
            best=best[0][1] if best else None
            span=int(best[8])-int(best[7]) if best else 0
            ratio=span/molecule['length_bp']
            assert span==molecule['longest_alignment_span_bp']
            assert math.isclose(ratio,molecule['contiguity'],abs_tol=1e-12)
            assert (ratio>=.99)==molecule['complete']
            measured=bool(best and (span>100000 or span>molecule['length_bp']/4))
            assert measured==molecule['identity_measured']
            if measured:
                assert math.isclose(int(best[9])/int(best[10]),molecule['identity'],abs_tol=1e-12)
                cigar=next(t[5:] for t in best[12:] if t.startswith('cg:Z:'))
                indel=max([int(n) for n,operation in re.findall(r'(\d+)([MIDNSHP=X])',cigar) if operation in 'ID'] or [0])
                assert indel==molecule['max_indel_bp']
            else:
                assert molecule['identity'] is None and molecule['max_indel_bp'] is None
            checked.append({'case_id':result['case']['id'],'assembler':result['assembler'],
                'accession':molecule['accession'],'longest_span':span,'contiguity':ratio,
                'complete':molecule['complete'],'identity_measured':measured})
    if not checked:raise ValueError('No measured primary results to audit')
    return {'schema_version':1,'status':'pass','method':'Independent saved-PAF arithmetic; no pipeline scoring imports or new alignment.',
            'molecule_checks':len(checked),'rows':checked}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=audit(a.bundle);a.out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(r['status'],r['molecule_checks'])
