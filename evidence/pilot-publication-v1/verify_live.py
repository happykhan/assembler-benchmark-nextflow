"""Verify published bytes without invoking scientific tools."""
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,sys,time,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parent
manifest=json.loads((root/'build.json').read_text());base='https://ploptimizer-assembly-benchmark.vercel.app/'
protected=['index.html','performance.html','aggregate.html','scenarios/s5.html','scenarios/s6.html','scenarios/s7.html','beta/index.html','data/summary.tsv','data/molecules.tsv']
selected={k:v for k,v in manifest['published_files'].items() if k.startswith('pilot/') or k in protected}
def check(item):
 path,expected=item
 for attempt in range(3):
  try:
   with urllib.request.urlopen(base+path,timeout=40) as response:
    data=response.read();status=response.status
   actual=hashlib.sha256(data).hexdigest()
   return {'path':path,'status':status,'bytes':len(data),'sha256':actual,'matches':actual==expected}
  except Exception as error:
   if attempt==2:return {'path':path,'matches':False,'error':str(error)}
   time.sleep(1)
with ThreadPoolExecutor(max_workers=8) as pool:checks=list(pool.map(check,selected.items()))
report={'status':'pass' if all(x['matches'] for x in checks) else 'fail','url':base,'files_verified':len(checks),'pilot_files_verified':sum(c['path'].startswith('pilot/') for c in checks),'checks':checks}
(root/'live-files.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='checks'}))
if report['status']!='pass':
 print([x for x in checks if not x['matches']]);sys.exit(1)
