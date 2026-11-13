"""Deliberate cleanup of owned, finished Nextflow work roots only."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import time
import uuid

MARKER = '.benchmark-work-v2.json'


def _save(path,value):
    temporary=path.with_name(path.name+'.partial-'+uuid.uuid4().hex)
    with temporary.open('x') as stream:
        json.dump(value,stream,sort_keys=True,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


def _overlap(first,second):
    return first==second or first in second.parents or second in first.parents


def _paths(work_dir,cache_dir,results_dir,project):
    raw=Path(work_dir).expanduser().absolute()
    if raw.is_symlink():raise ValueError('Work root cannot be a symbolic link')
    work=raw.resolve();cache=Path(cache_dir).expanduser().resolve();results=Path(results_dir).expanduser().resolve();project=Path(project).resolve()
    for protected in (Path('/'),Path.home().resolve(),project):
        if work==protected or work in protected.parents:raise ValueError('Work root is a protected directory or ancestor')
    if _overlap(work,cache):raise ValueError('Work root overlaps the shared scientific cache')
    if _overlap(work,results):raise ValueError('Work root overlaps current results')
    return work,cache,results,project


@contextmanager
def _locked(work):
    work.parent.mkdir(parents=True,exist_ok=True)
    lock=work.parent/('.'+work.name+'.benchmark-lifecycle.lock')
    descriptor=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'a') as stream:
        try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as error:raise ValueError('Another workflow lifecycle or cleanup operation owns this work root') from error
        yield


def _load(work):
    marker=work/MARKER
    if not work.is_dir() or marker.is_symlink() or not marker.is_file():raise ValueError('Work root is unowned; no current-format ownership marker')
    try:data=json.loads(marker.read_text())
    except (ValueError,OSError) as error:raise ValueError('Invalid work ownership marker') from error
    if data.get('schema_version')!=2 or data.get('kind')!='owned_nextflow_work':raise ValueError('Unknown work ownership format')
    if data.get('work_dir')!=str(work):raise ValueError('Work ownership marker names a different root')
    info=work.stat()
    if data.get('device')!=info.st_dev or data.get('inode')!=info.st_ino:raise ValueError('Work root identity changed after registration')
    return data


def _same_host(host):
    # Local identity only: never perform DNS lookup during offline cleanup.
    return host in {socket.gethostname(),os.uname().nodename}


def _alive(pid):
    if type(pid) is not int or pid<=0:raise ValueError('Invalid recorded controller PID')
    try:os.kill(pid,0)
    except ProcessLookupError:return False
    except PermissionError:return True
    return True


def _controller_ended(data):
    controller=data.get('controller',{})
    if not _same_host(controller.get('host')):raise ValueError('Controller state is unknown on this host; clean from the recorded controller host')
    if _alive(controller.get('pid')):raise ValueError('Nextflow controller is still active')


def register_work(work_dir,cache_dir,results_dir,project,run_id,controller_pid=None,controller_host=None,allow_unowned_existing=False):
    """Start hook: mark fresh work, never adopt a nonempty unowned directory."""
    work,cache,results,project=_paths(work_dir,cache_dir,results_dir,project)
    if not isinstance(run_id,str) or not run_id:raise ValueError('Run identity is required')
    pid=controller_pid if controller_pid is not None else os.getppid();host=controller_host or socket.gethostname()
    if type(pid) is not int or pid<=0 or not isinstance(host,str) or not host:raise ValueError('Controller identity is required')
    with _locked(work):
        if work.exists() and not (work/MARKER).exists() and any(work.iterdir()):
            if allow_unowned_existing:return {'status':'unmanaged','work_dir':str(work),'reason':'Existing unowned work is preserved; guarded cleanup unavailable'}
            raise ValueError('Nonempty unowned work root cannot be adopted')
        old=_load(work) if (work/MARKER).exists() else None
        if old:
            if old.get('state')=='active':raise ValueError('Work root is already owned by an active run')
            _controller_ended(old)
            if any(old.get(key)!=str(value) for key,value in [('cache_dir',cache),('results_dir',results),('project',project)]):
                raise ValueError('Owned work has different cache/results/project bindings')
        work.mkdir(parents=True,exist_ok=True);info=work.stat()
        data={'schema_version':2,'kind':'owned_nextflow_work','ownership_id':old['ownership_id'] if old else uuid.uuid4().hex,
            'run_id':run_id,'work_dir':str(work),'cache_dir':str(cache),'results_dir':str(results),'project':str(project),
            'device':info.st_dev,'inode':info.st_ino,'state':'active','controller':{'pid':pid,'host':host},'started_unix':time.time()}
        _save(work/MARKER,data)
    return {'status':'registered','work_dir':str(work),'run_id':run_id}


def finish_work(work_dir,run_id,success):
    work=Path(work_dir).absolute()
    if work.is_symlink():raise ValueError('Work root cannot be a symbolic link')
    work=work.resolve()
    with _locked(work):
        data=_load(work)
        if data.get('run_id')!=run_id:raise ValueError('Finish hook does not own this run')
        if data.get('state')!='active':raise ValueError('Run is not active')
        data.update(state='finished' if success else 'failed',success=bool(success),finished_unix=time.time())
        _save(work/MARKER,data)
    return {'status':data['state'],'run_id':run_id}


def _plan(work_dir):
    raw=Path(work_dir).absolute()
    if raw.is_symlink():raise ValueError('Work root cannot be a symbolic link')
    work=raw.resolve();data=_load(work)
    work,cache,results,project=_paths(work,data['cache_dir'],data['results_dir'],data['project'])
    if data.get('state')!='finished' or data.get('success') is not True:raise ValueError('Only successfully finished work can be cleaned; active/failed work retained')
    _controller_ended(data)
    if (results/'catalogue.json').exists():
        from .current_results import load_current
        load_current(results,verify_artifacts=True)
    files=links=logical=0
    for root,dirs,names in os.walk(work,followlinks=False):
        for name in list(dirs):
            path=Path(root)/name
            if path.is_symlink():links+=1;dirs.remove(name)
        for name in names:
            info=(Path(root)/name).lstat()
            if stat.S_ISLNK(info.st_mode):links+=1
            elif stat.S_ISREG(info.st_mode):files+=1;logical+=info.st_size
            else:raise ValueError('Work contains a special file; cleanup requires review')
    return {'schema_version':2,'status':'planned','work_dir':str(work),'run_id':data['run_id'],
        'regular_files':files,'symlinks':links,'logical_file_bytes':logical,
        'shared_cache_protected':str(cache),'current_results_protected':str(results),
        'warning':'Removing owned work disables Nextflow resume for these task directories. Shared-cache symlink targets are never traversed.'}


def cleanup_work(work_dir,execute=False):
    """Dry-run by default; revalidate under the external lifecycle lock."""
    raw=Path(work_dir).absolute()
    if raw.is_symlink():raise ValueError('Work root cannot be a symbolic link')
    work=raw.resolve()
    # Reject unowned/protected locations before creating even a lock file.
    data=_load(work)
    _paths(work,data['cache_dir'],data['results_dir'],data['project'])
    with _locked(work):
        plan=_plan(work)
        if not execute:return plan
        expected=work.stat();quarantine=work.with_name('.'+work.name+'.removing-'+uuid.uuid4().hex)
        os.rename(work,quarantine);observed=quarantine.stat()
        if (expected.st_dev,expected.st_ino)!=(observed.st_dev,observed.st_ino):
            if not work.exists():os.rename(quarantine,work)
            raise ValueError('Work identity changed during cleanup; nothing deleted')
        shutil.rmtree(quarantine)
        return dict(plan,status='removed')
