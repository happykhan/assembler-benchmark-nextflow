"""Read-only verification of the frozen Standard selection and saved assessments.

Usage: python verify_snapshot.py SNAPSHOT FROZEN_PLAN_JSON OUTPUT_JSON
Run only after Nextflow has completed and its terminal scheduler accounting is
verified. This checks packages and bindings; it does not rerun scientific tools.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from benchlib.assessment import read_fasta,parse_paf,summarise,outcome
from benchlib.catalogue import result_identity
from benchlib.current_results import load_current


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(root,plan):
    root=Path(root)
    records=load_current(root,with_packages=True)
    slots={result_identity(s['case']['id'],s['workflow']['id'],s['case'].get('scientific_repeat_id')):s for s in plan['slots']}
    assert len(slots)==110 and len(plan['inputs'])==55 and not plan['exclusions']
    selection=json.loads((root/'selection.json').read_text())
    assert selection['complete'] and selection['assessment_complete']
    assert selection['plan_sha256']==plan['plan_sha256']
    assert set(selection['expected_result_ids'])==set(slots)=={r['result_id'] for r in records}
    checks=[]
    for r in records:
        slot=slots[r['result_id']];case=r['case'];execution=r['execution']
        assert case==slot['case']
        for field in ['id','version','configuration','resources']:
            assert r['workflow'][field]==slot['workflow'][field]
        assert execution['actual_version']==r['workflow']['version']
        assert execution['automatic_retries']==0
        package=root/r['package'];receipt_path=root/'dependencies'/case['input_id']/'input.json'
        receipt=json.loads(receipt_path.read_text());input_hash=digest(receipt_path)
        assert receipt['id']==execution['input_id']==case['input_id']
        assert input_hash==execution['input_sha256']==r['provenance']['input_sha256']
        assert execution['read_sha256']=={name:receipt['file_sha256'][name] for name in receipt['files']}
        execution_hash=hashlib.sha256((json.dumps(execution,indent=2,sort_keys=True)+'\n').encode()).hexdigest()
        assert execution_hash==r['provenance']['execution_sha256']
        assert receipt['recipe']==case['recipe'] and receipt['observed']==r['input']['observed']
        assert all(m['topology']=='circular' for m in r['input']['reference']['molecules'])
        assert r['status'] in ('measured','execution_failure')
        if r['status']=='measured':
            assert execution['status']=='completed' and execution['exit_code']==0
            assert r['assessment']['method']=='wick-longest-alignment-v1'
            assert r['assessment']['measurement'].get('exit_code',0)==0
            assembly=package/r['artifacts']['assembly.fasta']['path']
            assert digest(assembly)==execution['assembly_sha256']
            ref_id=next(d for d in r['dependencies'] if d.startswith('reference-'))
            reference=root/'dependencies'/ref_id/'reference.fasta'
            assert digest(reference)==r['input']['reference']['reference_sha256']
            references=read_fasta(reference);queries=read_fasta(assembly)
            rows=parse_paf(package/r['artifacts']['alignment.paf']['path'],references,queries)
            types={m['accession']:m['type'] for m in r['input']['reference']['molecules']}
            replay=summarise(references,rows,types)
            assert replay==r['molecules']
            assert outcome(replay,len(queries))==r['sequence_outcome']
        else:
            assert execution['status']!='completed' and r['sequence_outcome'] is None
        metrics={m['name']:m['value'] for m in r['metrics']}
        assert metrics['workflow_wall_seconds']>=execution['wall_seconds']
        assert metrics['assembler_peak_ram']==execution['process_tree_peak_rss_bytes']
        checks.append({'result_id':r['result_id'],'input_id':case['input_id'],'input_sha256':input_hash,
            'execution_sha256':execution_hash,'status':r['status'],'sequence_outcome':r['sequence_outcome']})
    return {'status':'pass','plan_sha256':plan['plan_sha256'],'results_verified':len(records),
        'unique_inputs_verified':len({r['case']['input_id'] for r in records}),
        'status_counts':dict(Counter(r['status'] for r in records)),
        'sequence_outcomes':dict(Counter(r['sequence_outcome'] for r in records if r['status']=='measured')),
        'saved_paf_replays':sum(r['status']=='measured' for r in records),'bindings':checks}


if __name__=='__main__':
    root,plan_path,output=map(Path,sys.argv[1:])
    report=verify(root,json.loads(plan_path.read_text()))
    output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='bindings'},sort_keys=True))
