"""Read-only dependency inventory and atomic cache admission; stdlib only."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tarfile
import time
import urllib.parse
import urllib.request
import uuid

FILE_KINDS = {'reference', 'reference_archive', 'real_reads', 'published_reads',
              'simulator_profile', 'assessment_resource', 'file'}
RUNTIME_KINDS = {'software', 'software_environment', 'container_image'}


class PreparationError(RuntimeError):
    """A dependency cannot be admitted; no accepted input was replaced."""


def file_sha256(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def _target(cache, relative):
    name = Path(relative)
    if name.is_absolute() or '..' in name.parts or not name.parts:
        raise ValueError('Dependency target must be cache-relative: ' + str(relative))
    target = cache / name
    try:
        target.resolve().relative_to(cache)
    except ValueError:
        raise ValueError('Dependency target escapes the cache: ' + str(relative))
    if target.is_symlink():
        raise ValueError('Dependency target must not be a symlink')
    return target


def _receipt_path(cache, relative):
    key = hashlib.sha256(str(relative).encode('utf-8')).hexdigest()
    return cache / '.receipts' / (key + '.json')


def _save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.partial-' + uuid.uuid4().hex)
    with temporary.open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(str(temporary), str(path))


@contextmanager
def item_lock(cache, relative, timeout_seconds=7200, poll_seconds=0.1):
    """Atomic mkdir works across GPFS clients; never steal an uncertain lock."""
    if timeout_seconds < 0 or poll_seconds <= 0:
        raise ValueError('Invalid lock wait settings')
    key = hashlib.sha256(str(relative).encode('utf-8')).hexdigest()
    directory = cache / '.locks' / (key + '.lock')
    directory.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            directory.mkdir();break
        except FileExistsError:
            if time.monotonic() >= deadline:
                try: owner = (directory / 'owner.json').read_text()[:2048]
                except OSError: owner = 'Owner metadata unavailable.'
                raise TimeoutError('Dependency lock did not clear: ' + str(directory)
                                   + '; ' + owner + '; no lock was removed')
            time.sleep(min(poll_seconds, max(0, deadline-time.monotonic())))
    owner_path = directory / 'owner.json'
    owner = {'token':token, 'pid':os.getpid(), 'host':socket.gethostname(),
             'slurm_job_id':os.environ.get('SLURM_JOB_ID'), 'created_unix':time.time()}
    with owner_path.open('x') as stream:
        json.dump(owner, stream);stream.flush();os.fsync(stream.fileno())
    try:
        yield owner
    finally:
        if json.loads(owner_path.read_text()).get('token') != token:
            raise PreparationError('Lock ownership changed; refusing to release ' + str(directory))
        owner_path.unlink();directory.rmdir()


def _source(item, project):
    source = item.get('source')
    if isinstance(source, str):
        source = {'url':source} if urllib.parse.urlsplit(source).scheme else {'path':source}
    if source is None:
        source = {'url':item['url']} if item.get('url') else {'path':item['path']} if item.get('path') else {}
    if not isinstance(source, dict) or bool(source.get('url')) == bool(source.get('path')):
        raise ValueError('File dependency needs one source.url or source.path: ' + item['id'])
    source = dict(source)
    if source.get('path'):
        path = Path(source['path']).expanduser()
        source['path'] = str((project/path).resolve() if not path.is_absolute() else path.resolve())
    else:
        parts = urllib.parse.urlsplit(source['url'])
        if parts.scheme == 'file' and parts.netloc in ('','localhost'):
            source = {'path':urllib.request.url2pathname(parts.path)}
        elif parts.scheme not in ('http','https'):
            raise ValueError('Only HTTP(S) and local sources are supported')
    return source


def _expected(item):
    checksum, size = item.get('sha256'), item.get('size_bytes')
    if checksum is not None and (not isinstance(checksum,str) or len(checksum)!=64
                                or any(c not in '0123456789abcdef' for c in checksum)):
        raise ValueError('Invalid dependency SHA256: ' + item['id'])
    if size is not None and (type(size) is not int or size<0):
        raise ValueError('Invalid dependency size: ' + item['id'])
    return checksum,size


def _inspect_file(item, cache, project):
    target = _target(cache,item['target']);source = _source(item,project)
    checksum,size = _expected(item)
    if source.get('url') and checksum is None:
        return {'status':'invalid','reason':'Remote file requires a pinned SHA256'}
    if not target.exists():
        reason = 'Not present in cache'
        if source.get('path') and not Path(source['path']).is_file():
            reason = 'Local source file is missing: ' + source['path']
        return {'status':'missing','reason':reason}
    if not target.is_file() or size is not None and target.stat().st_size!=size:
        return {'status':'invalid','reason':'Cached file type or byte count differs'}
    actual = file_sha256(target)
    if checksum is not None:
        if actual!=checksum:return {'status':'invalid','reason':'Cached SHA256 differs from manifest'}
    else:
        try:receipt = json.loads(_receipt_path(cache,item['target']).read_text())
        except (OSError,ValueError):return {'status':'invalid','reason':'Unpinned local input has no admission receipt'}
        if receipt.get('sha256')!=actual or receipt.get('source')!=source:
            return {'status':'invalid','reason':'Cached bytes/source differ from admission receipt'}
        if source.get('path') and Path(source['path']).is_file() and file_sha256(source['path'])!=actual:
            return {'status':'invalid','reason':'Local source changed after admission'}
    return {'status':'cached','observed_sha256':actual,'observed_size_bytes':target.stat().st_size}


def bootstrap_inventory(plan):
    """Inspect executable paths only; never invoke an installer or a runtime."""
    names = {'python3'}
    for item in plan.get('dependencies',[]):
        if item.get('kind') in ('software','software_environment'):
            if item.get('manager')=='native':names.update(['python','minimap2']+list(item.get('executables',[])))
            else:names.add(item.get('manager','pixi'))
        elif item.get('kind')=='container_image':names.add(item.get('runtime','apptainer'))
    names.update(plan.get('bootstrap_executables',[]))
    records = []
    for name in sorted(names):
        path = sys.executable if name=='python3' else shutil.which(name)
        available = bool(path) and (name!='python3' or sys.version_info>=(3,9))
        row = {'id':name,'kind':'bootstrap','status':'cached' if available else 'missing',
               'path':path,'reason':None if available else 'Required executable/version is unavailable'}
        if name=='python3':row.update(version='.'.join(map(str,sys.version_info[:3])),minimum_version='3.9')
        records.append(row)
    return records


def _selected_dependencies(plan, input_ids=None, kinds=None):
    if not isinstance(plan,dict) or not isinstance(plan.get('dependencies'),list):
        raise ValueError('A resolved common plan must declare a dependencies list')
    dependencies = {}
    for item in plan.get('dependencies',[]):
        if not isinstance(item,dict) or not isinstance(item.get('id'),str) or not item['id']:
            raise ValueError('Dependency needs a non-empty ID')
        if item['id'] in dependencies and dependencies[item['id']]!=item:
            raise ValueError('Conflicting dependency definitions: ' + item['id'])
        dependencies[item['id']] = item
    selected,required_by = set(dependencies),{}
    if input_ids is not None:
        indexed = {row['id']:row for row in plan.get('inputs',[])}
        if set(input_ids)-set(indexed):raise ValueError('Unknown selected input ID')
        selected = set()
        inputs = [indexed[key] for key in input_ids]
    else:inputs = plan.get('inputs',[])
    for row in inputs:
        for key in row.get('dependencies',[]):
            selected.add(key);required_by.setdefault(key,[]).append(row['id'])
    pending = list(selected)
    while pending:
        key = pending.pop()
        if key not in dependencies:raise ValueError('Unknown dependency ID: ' + key)
        for child in dependencies[key].get('dependencies',[]):
            if child not in selected:selected.add(child);pending.append(child)
    if kinds is not None:selected = {key for key in selected if dependencies[key].get('kind','file') in set(kinds)}
    return [dict(dependencies[key],required_by=sorted(set(required_by.get(key,dependencies[key].get('required_by',[]))))) for key in sorted(selected)]


def plan_preparation(plan, cache_dir, project=None, inspectors=None, offline=False, input_ids=None, kinds=None):
    """Build a serialisable work list without writes, network or installations.

    Runtime inspectors are read-only ``(item, project, cache) -> inventory``
    functions. They must return cached/missing/invalid. Missing handlers are
    reportable dependencies, not imports of scientific software.
    """
    cache = Path(cache_dir).expanduser().resolve();project = Path(project or '.').expanduser().resolve()
    inspectors = inspectors or {};items = []
    selected = _selected_dependencies(plan,input_ids,kinds)
    for declaration in selected:
        item = {k:v for k,v in declaration.items() if k not in
                ('status','reason','target_path','action','observed_sha256','observed_size_bytes')}
        kind = item.get('kind','file')
        if kind in FILE_KINDS:
            if not item.get('target'):raise ValueError('File dependency needs a cache-relative target: '+item['id'])
            item.update(source=_source(item,project),target_path=str(_target(cache,item['target'])),
                        action='admit_file',**_inspect_file(item,cache,project))
        elif kind in inspectors:item.update(action='prepare_runtime',**inspectors[kind](item,project,cache))
        elif kind in RUNTIME_KINDS:item.update(status='missing',action='prepare_runtime',reason='Runtime inventory handler is unavailable')
        else:item.update(status='missing',action='deferred_to_compute',reason='Needs a declared compute preparation handler')
        if item['status'] not in ('cached','missing','invalid'):raise ValueError('Invalid inventory status: '+item['id'])
        items.append(item)
    bootstrap = bootstrap_inventory(dict(plan,dependencies=selected))
    return {'schema_version':2,'kind':'benchmark-preparation-work-list','cache_dir':str(cache),'project':str(project),
            'offline':bool(offline),'items':items,'bootstrap':bootstrap,
            'ready':all(r['status']=='cached' for r in items+bootstrap),
            'known_download_bytes':sum(r.get('size_bytes') or 0 for r in items if r['status']=='missing' and r.get('source',{}).get('url')),
            'simulation_policy':'Simulation and assembly are compute tasks, never download preparation.'}


def _http_range(source, offset, length, timeout):
    total = source['range']['total_size']
    if type(offset) is not int or type(length) is not int or offset<0 or length<1 or offset+length>total:
        raise PreparationError('Requested archive range is invalid')
    request = urllib.request.Request(source['url'],headers={'Range':'bytes=%s-%s'%(offset,offset+length-1)})
    response = urllib.request.urlopen(request,timeout=timeout)
    expected = 'bytes %s-%s/%s'%(offset,offset+length-1,total)
    if response.status!=206 or response.headers.get('Content-Range')!=expected:
        response.close()
        raise PreparationError('Server did not honour the exact archive range')
    return response


def _transfer(source, output, size, timeout):
    if source.get('range'):
        header = source.get('tar_header')
        if header:
            with _http_range(source,header['offset'],512,timeout) as stream:data = stream.read(513)
            if len(data)!=512 or hashlib.sha256(data).hexdigest()!=header['sha256']:
                raise PreparationError('Published TAR header checksum differs')
            member = tarfile.TarInfo.frombuf(data,'utf-8','strict')
            if not member.isfile() or member.name!=header['name'] or member.size!=size:
                raise PreparationError('Published TAR member identity differs')
        bounds = source['range']
        if size!=bounds['length']:
            raise PreparationError('Archive range length differs from declared item size')
        original = _http_range(source,bounds['offset'],bounds['length'],timeout)
    elif source.get('path'):original = Path(source['path']).open('rb')
    else:original = urllib.request.urlopen(source['url'],timeout=timeout)
    with original:
        count = 0
        while True:
            block = original.read(min(1024*1024,size-count+1) if size is not None else 1024*1024)
            if not block:break
            count += len(block)
            if size is not None and count>size:
                raise PreparationError('Transfer exceeds declared byte count')
            output.write(block)


def _admit_file(item, cache, project, offline, timeout_seconds):
    with item_lock(cache,item['target'],timeout_seconds=timeout_seconds):
        inventory = _inspect_file(item,cache,project)
        if inventory['status']=='cached':return inventory
        if inventory['status']=='invalid':
            raise PreparationError('Invalid dependency '+item['id']+': '+inventory['reason'])
        source = _source(item,project)
        if source.get('url') and offline:
            raise PreparationError('Offline dependency is missing: '+item['id']+'; no network attempted')
        target = _target(cache,item['target']);target.parent.mkdir(parents=True,exist_ok=True)
        temporary = target.with_name(target.name+'.partial-'+uuid.uuid4().hex)
        checksum,size = _expected(item)
        # Interrupted/failed candidates remain distinguishable from admitted files.
        with temporary.open('xb') as output:
            _transfer(source,output,size,item.get('timeout_seconds',120))
            output.flush();os.fsync(output.fileno())
        observed = file_sha256(temporary)
        if checksum is not None and observed!=checksum or size is not None and temporary.stat().st_size!=size:
            raise PreparationError('Transferred bytes differ from manifest: '+item['id'])
        try:os.link(str(temporary),str(target))
        except FileExistsError:
            raise PreparationError('Cache item appeared outside its admission lock: '+item['id'])
        _save(_receipt_path(cache,item['target']),{'schema_version':2,'id':item['id'],'kind':item.get('kind','file'),
            'target':item['target'],'source':source,'sha256':observed,'size_bytes':target.stat().st_size})
        temporary.unlink()
        return _inspect_file(item,cache,project)


def execute_work_list(work_list, offline=None, handlers=None, lock_timeout_seconds=7200):
    """Execute admissions and explicit runtime handlers, never simulation/assembly.

    Runtime callbacks use ``(item, project, cache, offline=False) -> inventory``.
    Offline callbacks may inspect existing software or explicitly install from
    package caches; they must not silently fetch from network sources.
    """
    if work_list.get('kind')!='benchmark-preparation-work-list':raise ValueError('Expected a preparation work list')
    offline = work_list.get('offline',False) if offline is None else bool(offline)
    cache,project = Path(work_list['cache_dir']).resolve(),Path(work_list['project']).resolve()
    handlers = handlers or {}
    missing = [r['id'] for r in work_list.get('bootstrap',[]) if r['status']!='cached']
    if missing:raise PreparationError('Unavailable bootstrap dependencies: '+', '.join(missing))
    for item in work_list['items']:
        state = _inspect_file(item,cache,project) if item.get('kind','file') in FILE_KINDS else item
        if state['status']=='invalid':raise PreparationError('Invalid dependency '+item['id']+': '+state.get('reason',''))
        if (offline and item.get('kind','file') in FILE_KINDS and state['status']!='cached'
                and _source(item,project).get('url')):
            raise PreparationError('Offline dependency is missing: '+item['id']+'; no network attempted')
    completed = []
    for declaration in work_list['items']:
        item = dict(declaration);kind = item.get('kind','file')
        if kind in FILE_KINDS:result = _admit_file(item,cache,project,offline,lock_timeout_seconds)
        elif kind in handlers:result = handlers[kind](item,project,cache,offline=offline)
        elif item['status']=='cached':result = {'status':'cached'}
        else:raise PreparationError('No execution handler for '+item['id']+'; '+item['action'])
        item.update(result)
        if item.get('status')!='cached':raise PreparationError('Dependency was not admitted: '+item['id'])
        completed.append(item)
    return dict(work_list,offline=offline,items=completed,ready=True,status='prepared')
