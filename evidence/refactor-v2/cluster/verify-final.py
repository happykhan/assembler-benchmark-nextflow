import csv,json,sys,hashlib,subprocess
from pathlib import Path
from collections import Counter
root=Path('/well/aanensen/users/rva470/assembler-benchmark-refactor-20261113')
sys.path.insert(0,str(root/'pipeline-final'))
from benchlib.current_results import load_current
from benchlib.catalogue import build_plan
records=load_current(root/'snapshot-final',with_packages=True)
plan=build_plan(root/'pipeline-final',collections='quick,real-validation,reproducibility-validation',workflows='raven-default,skesa-default,flye-default',catalogue_path=root/'final-validation-catalogue.json')
expected={s['result_id']:s for s in plan['slots']+plan['exclusions']}
assert {r['result_id'] for r in records}==set(expected)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
bindings=[]
for r in records:
 slot=expected[r['result_id']]
 assert r['case']['science_key']==slot['case']['science_key']
 assert r['workflow']['version']==slot['workflow']['version']
 assert r['workflow']['configuration']==slot['workflow']['configuration']
 if r['status']=='not_applicable':
  assert slot['status']=='not_applicable';continue
 assert r['status']=='measured'
 package=root/'snapshot-final'/r['package']
 dep=root/'snapshot-final'/'dependencies'/r['case']['input_id']/'input.json'
 inp=json.loads(dep.read_text());execution=r['execution']
 assert sha(dep)==r['provenance']['input_sha256']==execution['input_sha256']
 assert execution['input_id']==inp['id']==r['case']['input_id']
 assert all(execution['read_sha256'][name]==inp['file_sha256'][name] for name in inp['files'])
 raw_execution=(json.dumps(execution,indent=2,sort_keys=True)+'\n').encode()
 assert hashlib.sha256(raw_execution).hexdigest()==r['provenance']['execution_sha256']
 assert sha(package/r['artifacts']['assembly.fasta']['path'])==execution['assembly_sha256']
 assert r['input']['declaration']['dataset']['id']==slot['case']['dataset_id']
 bindings.append({'result_id':r['result_id'],'case_id':r['case']['id'],'workflow_id':r['workflow']['id'],'version':r['workflow']['version'],'source_kind':r['case']['source_kind'],'read_technology':r['case']['read_technology'],'scientific_repeat_id':r['case'].get('scientific_repeat_id'),'input_id':inp['id'],'assembly_sha256':execution['assembly_sha256'],'sequence_outcome':r.get('sequence_outcome')})
checks={}
for label in ['cache-assessment','cache-render','cache-added','cache-publication','cache-input-wrapper']:
 rows=list(csv.DictReader((root/(label+'.trace.tsv')).open(),delimiter='\t'))
 assert all(r['status'] in ('CACHED','COMPLETED') and r['exit']=='0' for r in rows)
 science=[r for r in rows if r['name'].startswith(('ASSEMBLE','ASSESS','PREPARE_INPUT'))]
 checks[label]={r['name']:r['status'] for r in science}
 if label=='cache-assessment':
  assert all(r['status']=='CACHED' for r in science if r['name'].startswith('ASSEMBLE'))
 elif label in ('cache-render','cache-publication','cache-input-wrapper'):
  assert all(r['status']=='CACHED' for r in science if r['name'].startswith(('ASSEMBLE','ASSESS')))
 elif label=='cache-added':
  assert all(r['status']=='CACHED' for r in science if r['name'].startswith('PREPARE_INPUT') or (r['name'].startswith(('ASSEMBLE','ASSESS')) and 'flye-default' not in r['name']))
rows=list(csv.DictReader((root/'final-mixed.trace.tsv').open(),delimiter='\t'))
assert len(rows)==41 and all(r['status']=='COMPLETED' and r['exit']=='0' for r in rows)
ids=sorted({r['native_id'] for r in rows if r['name']!='SETUP'})
accounting=subprocess.check_output(['sacct','-X','-P','-n','-j',','.join(ids),'--format=JobIDRaw,State,ExitCode'],text=True)
terminal={f[0]:{'state':f[1],'exit':f[2]} for line in accounting.splitlines() if (f:=line.split('|'))[0] in ids}
assert set(terminal)==set(ids) and all(r['state']=='COMPLETED' and r['exit']=='0:0' for r in terminal.values()),terminal
out={'schema_version':2,'status':'pass','scope':'Small engineering/matched-real validation only; no full scientific panel','mixed':{'inputs':len(plan['inputs']),'eligible':plan['expected_slots'],'not_applicable':plan['not_applicable_slots'],'task_count':len(rows),'scheduler_allocations':len(terminal),'status_counts':dict(Counter(r['status'] for r in records))},'verified_bindings':bindings,'cache_checks':checks,'terminal_scheduler_states':terminal,'note':'Technical repeat file hashes are evidence only; reference completeness is not an output-agreement verdict.'}
(root/'final-acceptance.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
(root/'final-accounting.tsv').write_text(accounting)
print(json.dumps({'status':'pass','mixed':out['mixed'],'verified_execution_input_bindings':len(bindings)}))
