import csv, hashlib, json, sys
from pathlib import Path
root=Path(sys.argv[1]); out=root/sys.argv[2]; bundle=out/'bundle'
manifest=json.loads((bundle/'manifest.json').read_text())
assert manifest['complete'] and manifest['expected_slots']==4 and manifest['result_count']==4
for name, expected in manifest['files'].items():
 assert hashlib.sha256((bundle/name).read_bytes()).hexdigest()==expected,name
records=json.loads((bundle/'results.json').read_text())['results']
assert len(records)==4 and all(r['execution']['status']=='completed' and r['assessment']['status']=='completed' for r in records)
plan=json.loads((bundle/'slot-plan.json').read_text())
receipt=json.loads((bundle/'environment-preparation.json').read_text())
assert receipt['status']=='prepared' and receipt['plan_sha256']==plan['plan_sha256']
with (out/'nextflow-trace.tsv').open() as f: trace=list(csv.DictReader(f,delimiter='\t'))
assert len(trace)==13 and all(r['status'] in ('COMPLETED','CACHED') for r in trace)
print(json.dumps({'bundle_complete': True, 'result_count':4,'verified_files':len(manifest['files']), 'trace_tasks':13,
 'trace_statuses':{s:sum(r['status']==s for r in trace) for s in sorted({r['status'] for r in trace})},
 'runtime_image':receipt.get('runtime_image'), 'prepared_environments':[e['environment'] for e in receipt['environments']],
 'slots':[{'case':r['case']['id'],'assembler':r['assembler'],'execution':r['execution']['status'],'assessment':r['assessment']['status'],'sequence_outcome':r['sequence_outcome']} for r in records],
 'manifest_sha256':hashlib.sha256((bundle/'manifest.json').read_bytes()).hexdigest(),
 'read_sha256':{r['case']['id']:r['execution']['reads_sha256'] for r in records}},indent=2))
