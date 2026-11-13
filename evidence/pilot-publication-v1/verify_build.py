"""Read-only combined static-site link and payload verification."""
import json
from pathlib import Path
import sys
from urllib.parse import urljoin,urlsplit,unquote
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from reporting.current_site import _Links

root=Path(sys.argv[1]).resolve();pages={};errors=[];count=0
for p in root.rglob('*.html'):
 parser=_Links();parser.feed(p.read_text());pages[p]=parser
for p,parser in pages.items():
 for link in parser.links:
  url=urlsplit(urljoin('https://site.invalid/'+p.relative_to(root).as_posix(),link))
  if url.netloc!='site.invalid':continue
  target=root/unquote(url.path).lstrip('/');count+=1
  if target.is_dir():target=target/'index.html'
  if not target.is_file() and not target.suffix:target=target.with_suffix('.html')
  if not target.is_file() and (url.path in ('/history','/history.html') or (url.path.startswith('/batches/') and url.path.endswith(('/history','/history.html')))):target=root/'index.html'
  if not target.is_file():errors.append({'page':p.relative_to(root).as_posix(),'missing':link})
  elif url.fragment and target in pages and url.fragment not in pages[target].ids:errors.append({'page':p.relative_to(root).as_posix(),'missing_anchor':link})
print(json.dumps({'pages':len(pages),'links_checked':count,'errors':errors},indent=2))
if errors:sys.exit(1)
