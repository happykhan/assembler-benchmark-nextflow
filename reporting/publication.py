"""Compose labelled current reports with a preserved static benchmark website."""
import hashlib
from html import escape
import json
from pathlib import Path
import re
import os
from urllib.parse import urlsplit,urlunsplit,unquote
import shutil

from .current_site import validate_site


def public_files(root):
    root=Path(root)
    return {p.relative_to(root).as_posix():p for p in root.rglob('*') if p.is_file() and not any(part.startswith('.') for part in p.relative_to(root).parts)}


def compact_report(root):
    """Share identical prepared visual/download files without changing bytes."""
    root=Path(root);seen={};aliases={}
    for name,path in sorted(public_files(root).items()):
        if not name.startswith(('artifacts/','data/views/')):continue
        key=(path.suffix,hashlib.sha256(path.read_bytes()).hexdigest())
        if key in seen:aliases[name]=seen[key]
        else:seen[key]=name
    def rewrite(value,current):
        if not isinstance(value,str):return value
        url=urlsplit(value)
        if url.scheme or url.netloc or not url.path:return value
        target=os.path.normpath(str(Path(current).parent/unquote(url.path)))
        if target not in aliases:return value
        relative=Path(os.path.relpath(aliases[target],Path(current).parent)).as_posix()
        return urlunsplit(('', '', relative,url.query,url.fragment))
    def visit(value,current):
        if isinstance(value,dict):return {k:visit(v,current) for k,v in value.items()}
        if isinstance(value,list):return [visit(v,current) for v in value]
        return rewrite(value,current)
    for name,path in public_files(root).items():
        if path.suffix=='.html':
            path.write_text(re.sub(r'((?:href|src)=")([^"]+)(")',lambda m:m[1]+rewrite(m[2],name)+m[3],path.read_text()))
        elif path.suffix=='.json' and name not in aliases:
            path.write_text(json.dumps(visit(json.loads(path.read_text()),name),indent=2,sort_keys=True)+'\n')
    for name in aliases:(root/name).unlink()
    # The publication declaration is already embedded in catalogue/result JSON,
    # every page and every TSV; this sidecar is only a rendering input.
    (root/'publication.json').unlink()
    validation=validate_site(root)
    if validation['errors']:raise ValueError('Compacted report is invalid: '+str(validation['errors']))
    return aliases


def _compose(base,report,output,kind,archive=None):
    base,report,output=map(lambda p:Path(p).resolve(),(base,report,output))
    if output.exists() or any(source==output or source in output.parents or output in source.parents for source in (base,report)):
        raise ValueError('Publication output must be a fresh directory outside both sources')
    validation=validate_site(report)
    if validation['errors']:raise ValueError('Report website is invalid: '+str(validation['errors']))
    publication=json.loads((report/'publication.json').read_text())
    if publication.get('kind')!=kind:raise ValueError('Publication requires explicit '+kind+' labels')
    original=public_files(base);original={name:p for name,p in original.items() if not name.startswith(kind+'/')}
    archived={}
    if archive:
        origin=urlsplit(archive['origin'])
        if origin.scheme!='https' or not origin.netloc or origin.path not in ('','/') or origin.query or origin.fragment or origin.username:
            raise ValueError('Archive requires a public HTTPS origin without credentials')
        if not archive.get('deployment_id'):raise ValueError('Archive requires its pinned deployment identity')
        archived={name:p for name,p in original.items() if name.startswith('batches/')}
        original={name:p for name,p in original.items() if name not in archived}
    if 'index.html' not in original or 'vercel.json' not in original:raise ValueError('Verified base must include homepage and routing configuration')
    output.mkdir(parents=True)
    for name,path in original.items():
        if path.is_symlink():raise ValueError('Public base must use regular files')
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    for name,path in public_files(report).items():
        target=output/kind/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    aliases=compact_report(output/kind)
    homepage=output/'index.html';text=homepage.read_text()
    text=re.sub(r'<section id="nextflow-'+kind+'-entry".*?</section>','',text,flags=re.S)
    entry='<section id="nextflow-pilot-entry" aria-labelledby="nextflow-pilot-title"><h2 id="nextflow-pilot-title"><a href="pilot/">Nextflow pilot reports</a></h2><p>Small validation run: '+str(publication['measured_results'])+' measured results from '+str(publication['unique_inputs'])+' inputs; '+str(publication['not_applicable'])+' combinations not applicable. Includes simulated fixtures, a real-read subset and technical repeats. Not a full panel or an assembler ranking.</p></section>'
    if kind=='standard':
        entry='<section id="nextflow-standard-entry" aria-labelledby="nextflow-standard-title"><h2 id="nextflow-standard-title"><a href="standard/">Nextflow Standard simulated benchmark</a></h2><p>'+escape(publication['summary'])+'</p><p>Error-free long-read simulations with '+str(len(publication['sampling_seeds']))+' sampling seeds. Explore the complete selection and its methods. Pilot validation and the published real-data benchmark remain separate.</p></section>'
    if archive:
        config=json.loads((output/'vercel.json').read_text())
        rewrites=config.setdefault('rewrites',[])
        rewrites[:]=[r for r in rewrites if r.get('source')!='/batches/:path*']
        rewrites.append({'source':'/batches/:path*','destination':archive['origin'].rstrip('/')+'/batches/:path*'})
        (output/'vercel.json').write_text(json.dumps(config,indent=2,sort_keys=True)+'\n')
    if '</h1>' not in text:raise ValueError('Homepage has no publication entry point')
    homepage.write_text(text.replace('</h1>','</h1>'+entry,1))
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    changed=['index.html']+(['vercel.json'] if archive else [])
    preserved=[name for name,path in original.items() if name not in changed and digest(path)==digest(output/name)]
    if len(preserved)!=len(original)-len(changed):raise ValueError('An existing benchmark artifact changed')
    files=public_files(output);total=sum(p.stat().st_size for p in files.values());largest=max(p.stat().st_size for p in files.values())
    if len(files)>1500 or total>64*1024*1024 or largest>5*1024*1024:raise ValueError('Combined publication exceeds deployment limits')
    return {'status':'pass','files':len(files),'bytes':total,'largest_file_bytes':largest,'preserved_base_files':len(preserved),
            'changed_base_files':changed,kind+'_shared_file_aliases':aliases,kind:publication,'base_files':{name:digest(path) for name,path in original.items()},
            'archive':archive,'archived_files':{name:digest(path) for name,path in archived.items()},
            'published_files':{name:digest(path) for name,path in files.items()}}


def compose_pilot(base,pilot,output):
    return _compose(base,pilot,output,'pilot')


def compose_standard(base,standard,output,*,archive):
    """Pin old supplementary batches separately to keep the public payload small."""
    return _compose(base,standard,output,'standard',archive=archive)
