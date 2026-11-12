"""Independent arithmetic/integrity audit of a retained real-pilot bundle."""
import hashlib
import json
import math
from pathlib import Path
import re
import sys


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def fasta(path):
    records={}; name=None
    for line in Path(path).read_text().splitlines():
        if line.startswith('>'):name=line[1:].split()[0];records[name]=[]
        elif line.strip():records[name].append(line.strip())
    return {name:''.join(parts) for name,parts in records.items()}


def verify(bundle):
    bundle=Path(bundle)
    manifest=json.loads((bundle/'manifest.json').read_text())
    assert manifest['complete'] and manifest['expected_slots']==2 and manifest['result_count']==2
    for name,checksum in manifest['files'].items():assert digest(bundle/name)==checksum,name
    actual={p.relative_to(bundle).as_posix() for p in bundle.rglob('*') if p.is_file()}
    assert actual==set(manifest['files'])|{'manifest.json'}
    plan=json.loads((bundle/'slot-plan.json').read_text())
    assert digest(bundle/'slot-plan.json')==manifest['plan_sha256'] and plan['track']=='real'
    records=json.loads((bundle/'results.json').read_text())['results']
    expected={(x['case_id'],x['assembler']) for x in plan['slots']}
    assert {(r['case']['id'],r['assembler']) for r in records}==expected
    summary=[]
    for record in records:
        case=record['case']['id']; tool=record['assembler']; execution=record['execution']
        inputs=plan['read_inputs'][case]
        assert execution['status']=='completed' and execution['automatic_retries']==0
        assert execution['reads_sha256']==inputs['reads_sha256']
        assert execution['expected_version']==execution['version'].split()[0] or execution['expected_version'] in execution['version']
        directory=bundle/record['evidence_directory']
        assert digest(directory/'result.json')==record['source_result_sha256']
        metadata=json.loads((directory/'input-provenance.json').read_text())
        assert metadata['track']=='real' and metadata['run_accession']==inputs['run_accession']
        assert metadata['sample_accession']==inputs['sample_accession']
        assert metadata['admission_sha256']==inputs['admission_sha256']
        assert metadata['read_count']==inputs['read_count'] and metadata['total_bases']==inputs['total_bases']
        assert metadata['reads_sha256']==inputs['reads_sha256']
        assembly_path=bundle/'assemblies'/case/tool/'assembly.fasta'
        assert digest(assembly_path)==execution['assembly_sha256']
        assembly=fasta(assembly_path)
        ref=plan['references'][record['case']['reference_id']]
        lengths={x['accession']:x['length_bp'] for x in ref['molecules']}
        assert len(lengths)==5 and sum(x['type']=='plasmid' for x in ref['molecules'])==4
        best={}
        for line in (directory/'alignment.paf').read_text().splitlines():
            f=line.split('\t'); acc=f[5]; span=int(f[8])-int(f[7])
            assert int(f[6])==3*lengths[acc] and int(f[1])==len(assembly[f[0]])
            if acc not in best or (span,-int(f[7]))>(best[acc][0],-int(best[acc][1][7])):best[acc]=(span,f)
        assert len(record['replicons'])==5
        for molecule in record['replicons']:
            acc=molecule['accession']; span=best.get(acc,(0,None))[0]
            assert math.isclose(molecule['contiguity'],span/lengths[acc],abs_tol=1e-12)
            assert molecule['complete']==(100*span>=99*lengths[acc])
            measured=bool(span and (span>100000 or 4*span>lengths[acc]))
            assert molecule['identity_measured']==measured
            if measured:
                f=best[acc][1];assert math.isclose(molecule['identity'],int(f[9])/int(f[10]),abs_tol=1e-12)
                cigar=next(x[5:] for x in f[12:] if x.startswith('cg:Z:'))
                largest=max([int(n) for n,op in re.findall(r'(\d+)([A-Z=])',cigar) if op in 'ID'] or [0])
                assert molecule['max_indel_bp']==largest
        hits={acc:{} for acc in lengths}; seen=set()
        for line in (directory/'paper-alignment.paf').read_text().splitlines():
            f=line.split('\t'); acc=f[0];seen.add(acc)
            assert int(f[1])==lengths[acc]
            if f[5]!='*':hits[acc][f[5]]=hits[acc].get(f[5],0)+int(f[10])
        assert seen==set(lengths)
        assert record['paper_assessment']['status']=='completed' and len(record['paper_assessment']['replicons'])==4
        for paper in record['paper_assessment']['replicons']:
            acc=paper['accession']; groups=hits[acc]
            passing=[q for q,blocks in groups.items() if blocks*10>lengths[acc]*9]
            fragmented=not passing and sum(groups.values())*10>lengths[acc]*9
            assert paper['recovered']==bool(passing or fragmented)
            assert paper['fragmented_recovery']==fragmented
            assert paper['duplicate_recovering_contigs']==(len(passing)>1)
            assert paper['summed_alignment_blocks_bp']==sum(groups.values())
            assert paper['chromosome_incorporation_heuristic']==(bool(passing or fragmented) and any(len(assembly[q])>1000000 for q in (passing or list(groups))))
        diag=record['input_diagnostics']; assert diag['reads_sha256']==inputs['reads_sha256']
        assert diag['reference_sha256']==ref['canonical_fasta_sha256']
        intervals={acc:[] for acc in lengths}; names={acc:set() for acc in lengths}; spans={acc:0 for acc in lengths}
        with (bundle/'input-diagnostics'/case/'read-alignment.paf').open() as stream:
            for line in stream:
                f=line.split('\t');acc=f[5];a,b=int(f[7]),int(f[8]);intervals[acc].append((a,b));names[acc].add(f[0]);spans[acc]+=b-a
        assert len(diag['molecules'])==5
        for molecule in diag['molecules']:
            acc=molecule['accession']; covered=finish=0
            for a,b in sorted(intervals[acc]):covered+=max(0,b-max(a,finish));finish=max(finish,b)
            assert molecule['covered_reference_bases']==covered
            assert molecule['distinct_mapped_read_ids']==len(names[acc])
            assert math.isclose(molecule['mean_aligned_target_depth'],spans[acc]/lengths[acc],abs_tol=1e-12)
        summary.append({'assembler':tool,'assembly_sha256':execution['assembly_sha256'],'contigs':len(assembly),
            'execution_status':execution['status'],'primary_status':record['assessment']['status'],
            'sequence_outcome':record['sequence_outcome'],'paper_status':record['paper_assessment']['status'],
            'strict_complete_plasmids':sum(x['complete'] for x in record['replicons'] if x['molecule_type']=='plasmid'),
            'paper_recovered_plasmids':sum(x['recovered'] for x in record['paper_assessment']['replicons']),
            'molecules':record['replicons'],'paper_replicons':record['paper_assessment']['replicons'],
            'read_support':diag['molecules']})
    return {'bundle_complete':True,'slots_verified':2,'files_verified':len(manifest['files']),
            'manifest_sha256':digest(bundle/'manifest.json'),'plan_sha256':plan['plan_sha256'],
            'reads_sha256':plan['read_inputs'][plan['cases'][0]['id']]['reads_sha256'],
            'independent_arithmetic_verified':True,'results':summary}


if __name__=='__main__':print(json.dumps(verify(sys.argv[1]),indent=2))
