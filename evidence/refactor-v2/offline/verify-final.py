from pathlib import Path
from collections import Counter
import csv,json,hashlib
root=Path('/well/aanensen/users/rva470/assembler-benchmark-refactor-20261113')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert (root/'offline-final.exit').read_text().strip()=='0'
initial=json.loads((root/'offline-final-initial-cache.json').read_text())
assert initial['prepared_inputs_present'] is False
assert initial['reference_entries']==['references/archives']
rows=list(csv.DictReader((root/'offline-final.trace.tsv').open(),delimiter='\t'))
assert rows and all(r['status']=='COMPLETED' and r['exit']=='0' for r in rows)
tasks=[]
for row in rows:
 short=row['hash'];p=next((root/'work-offline-final'/short.split('/')[0]).glob(short.split('/')[1]+'*'))
 command=(p/'.command.sh').read_text();wrapper=(p/'.command.run').read_text()
 blocked='preparation-probe/network-blocker' in command
 stage=row['name'].split(' ')[0];science=stage in ('PREPARE_INPUT','ASSEMBLE','ASSESS')
 assert blocked,(stage,p)
 if science:
  assert 'apptainer exec' in wrapper
  assert '702f3a3c966aa63a0a57906466ec33ce9a463b532446f5584498fa429d069fd8.sif' in wrapper
 tasks.append({'process':row['name'],'scheduler_id':row['native_id'],'status':row['status'],'exit':row['exit'],
 'runtime':row['realtime'],'peak_rss':row['peak_rss'],'network_blocker_in_command':blocked,
 'containerised':science,'command_sha256':sha(p/'.command.sh'),'wrapper_sha256':sha(p/'.command.run')})
inputs=[]
for p in sorted((root/'cache-offline-final/inputs').glob('*/*/input.json')):
 receipt=json.loads(p.read_text())
 assert sha(p)==p.with_name('input.sha256').read_text().strip()
 assert all(sha(p.parent/name)==value for name,value in receipt['file_sha256'].items())
 inputs.append({'input_id':receipt['id'],'method':receipt['recipe']['method'],'receipt_sha256':sha(p),
 'file_sha256':receipt['file_sha256'],'observed':receipt['observed'],'software_versions':receipt['software_versions']})
assert {r['method'] for r in inputs}=={'native-error-free-v2','art-illumina-v1'}
records=[json.loads(p.read_text()) for p in (root/'current-offline-final/packages').glob('*/*/result.json')]
counts=Counter(r['status'] for r in records);assert counts=={'measured':2,'not_applicable':2},counts
snapshot=root/'pipeline-offline-final'
source_hashes={str(p.relative_to(snapshot)):sha(p) for p in snapshot.rglob('*') if p.is_file() and '.pixi' not in p.parts and '__pycache__' not in p.parts}
proof={'validation_note':'An initial SETUP-only probe failed because the isolated source copy omitted assets/references.json; copied the complete assets directory before scientific tasks began. The fresh scientific cache remained empty until this successful run. Earlier logs retained separately.', 'source_sha256':source_hashes,'schema_version':2,'scope':'Two Quick simulated inputs only; no full panel','exit':0,'cache':str(root/'cache-offline-final'),
 'initial_cache':initial,'task_count':len(tasks),'tasks':tasks,'inputs':inputs,'result_status_counts':dict(counts),
 'results':[{'case':r['case']['id'],'workflow':r['workflow']['id'],'status':r['status'],'sequence_outcome':r.get('sequence_outcome')} for r in records],
 'network_evidence':'Every task command starts its substantive program through inherited seccomp network-blocker; scientific tasks execute inside the admitted SIF. Controller is not blocked because Slurm requires network.',
 'limitation':'Quick uses a 200kb reference slice; this proves cold scientific preparation and execution, not Standard performance or full-panel scientific validity.'}
(root/'offline-final-verification.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({'task_count':len(tasks),'inputs':[r['method'] for r in inputs],'results':dict(counts)}))
