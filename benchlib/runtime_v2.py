"""Inspect pinned runtimes without installing; provision only on explicit request."""
import fnmatch
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid
import copy

from .io import digest
from .preparation import PreparationError, item_lock


def _oci_reference(source):
    """Canonical repository@digest identity, independent of descriptor/transport."""
    value=source.get('url') if isinstance(source,dict) else source
    if not isinstance(value,str):raise ValueError('Container source must be a digest-pinned OCI URI')
    for prefix in ('docker://','oras://'):
        if value.startswith(prefix):value=value[len(prefix):];break
    if '://' in value or not re.fullmatch(r'[^\s@]+@sha256:[a-f0-9]{64}',value):
        raise ValueError('Container source must use an OCI digest')
    return value


def runtime_plan(plan, project, runtime='pixi', container_runtime=None, image=None):
    """Shared runtime declarations for standalone preparation and Nextflow."""
    from .catalogue import canonical_digest
    result=copy.deepcopy(plan)
    result['dependencies']=[r for r in result['dependencies'] if r['id']!='container-runtime']
    for item in result['dependencies']:
        if item['kind'] in ('software','software_environment'):
            item['manager']='native' if runtime=='native' else 'pixi'
            manifest=Path(project)/item.get('manifest','environments/pixi.toml')
            # Runtime selection must not silently rebind an existing frozen pin.
            # Missing sources remain inventory items rather than aborting dry-run.
            for field,path in [('manifest_sha256',manifest),('lock_sha256',manifest.with_name('pixi.lock'))]:
                if field not in item and path.is_file():item[field]=digest(path)
    if container_runtime and result.get('slots'):
        if not re.fullmatch(r'.+@sha256:[a-f0-9]{64}',image or ''):
            raise PreparationError('Container runtimes require a digest-pinned OCI image')
        suffix='.json' if container_runtime=='docker' else '.sif'
        result['dependencies'].append({'id':'container-runtime','kind':'container_image','runtime':container_runtime,
            'source':{'url':image},'target':'images/'+image.rsplit(':',1)[-1]+suffix})
    result['runtime']={'manager':runtime,'container_runtime':container_runtime,'image':image if container_runtime else None}
    result['plan_sha256']=canonical_digest({k:v for k,v in result.items() if k!='plan_sha256'})
    return result


def _save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.partial-'+uuid.uuid4().hex)
    temporary.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    os.replace(temporary,path)


def _paths(item, project, cache):
    manifest = (Path(project)/item.get('manifest','environments/pixi.toml')).resolve()
    if not manifest.is_relative_to(Path(project).resolve()):
        raise ValueError('Runtime manifest escapes project')
    environment = item.get('environment','default')
    if not re.fullmatch(r'[a-z][a-z0-9-]*',environment):
        raise ValueError('Invalid environment name')
    prefix = manifest.parent/'.pixi/envs'/environment
    receipt = Path(cache)/item.get('target','software/'+environment+'.json')
    if not receipt.resolve().is_relative_to(Path(cache).resolve()):
        raise ValueError('Runtime receipt escapes cache')
    return manifest, prefix, receipt


def _binaries(item):
    return list(dict.fromkeys(['python','minimap2']+list(item.get('executables',[]))))


def inspect_dependency(item, project, cache):
    """Filesystem inventory only: safe before scientific dependencies exist."""
    if item.get('kind')=='container_image':
        return _inspect_image(item,cache)
    if item.get('manager')=='native':return _inspect_native(item)
    manifest,prefix,receipt_path = _paths(item,project,cache)
    lock=manifest.with_name('pixi.lock')
    if not manifest.is_file() or not lock.is_file():
        return {'status':'missing','reason':'Pinned manifest or lock file missing','target_path':str(receipt_path)}
    hashes={'manifest_sha256':digest(manifest),'lock_sha256':digest(lock)}
    for field,actual in hashes.items():
        if item.get(field) is not None and item[field]!=actual:
            return {'status':'invalid','reason':'Declared runtime '+field+' differs from source'}
    if not prefix.is_dir() or not receipt_path.is_file():
        return {'status':'missing','reason':'Environment or preparation receipt missing','target_path':str(receipt_path)}
    try:
        receipt=json.loads(receipt_path.read_text())
        if (receipt['manifest_sha256']!=digest(manifest) or receipt['lock_sha256']!=digest(lock)
                or receipt['environment']!=item.get('environment','default')):
            return {'status':'invalid','reason':'Installed runtime belongs to a different manifest/lock'}
        for name in _binaries(item):
            binary=prefix/'bin'/name
            if not binary.is_file() or not os.access(binary,os.X_OK) or receipt['executables'].get(name)!=digest(binary):
                return {'status':'invalid','reason':'Missing or changed runtime executable: '+name}
        packages={p['name']:p['version'] for p in (json.loads(f.read_text()) for f in (prefix/'conda-meta').glob('*.json'))}
        for name,version in item.get('packages',{}).items():
            if not fnmatch.fnmatch(packages.get(name,''),str(version).removeprefix('==')):
                return {'status':'invalid','reason':'Installed package version differs: '+name}
    except (OSError,ValueError,KeyError) as error:
        return {'status':'invalid','reason':'Invalid runtime receipt: '+str(error)}
    return {'status':'cached','target_path':str(receipt_path),'prefix':str(prefix),
            'manifest_sha256':receipt['manifest_sha256'],'lock_sha256':receipt['lock_sha256']}


def prepare_dependency(item, project, cache, offline=False):
    if item.get('kind')=='container_image':
        return _prepare_image(item,project,cache,offline)
    if item.get('manager')=='native':
        state=_inspect_native(item)
        if state['status']!='cached':raise PreparationError(state['reason']+'; native tools are never installed automatically')
        return state
    manifest,prefix,receipt_path=_paths(item,project,cache)
    with item_lock(Path(cache).resolve(),'runtime-install:'+str(manifest)):
        state=inspect_dependency(item,project,cache)
        if state['status']=='cached':return state
        if state['status']=='invalid':raise PreparationError(state['reason'])
        if offline:
            raise PreparationError(state['reason']+'; prepare this environment online before offline execution; no installation attempted')
        lock=manifest.with_name('pixi.lock')
        if not manifest.is_file() or not lock.is_file():raise PreparationError(state['reason'])
        before={'manifest_sha256':digest(manifest),'lock_sha256':digest(lock)}
        pixi=shutil.which('pixi')
        if not pixi:raise PreparationError('Pixi is required to prepare locked environments')
        command=[pixi,'install','--locked','--manifest-path',str(manifest),'--environment',item.get('environment','default')]
        try:subprocess.run(command,check=True,capture_output=True,text=True)
        except (OSError,subprocess.CalledProcessError) as error:
            raise PreparationError('Locked environment preparation failed: '+str(error)) from error
        if digest(manifest)!=before['manifest_sha256'] or digest(lock)!=before['lock_sha256']:
            raise PreparationError('Pinned manifest/lock changed during environment preparation; no receipt published')
        binaries={name:digest(prefix/'bin'/name) for name in _binaries(item)}
        _save(receipt_path,{'schema_version':2,'environment':item.get('environment','default'),
            'manifest_sha256':digest(manifest),'lock_sha256':digest(manifest.with_name('pixi.lock')),
            'executables':binaries,'preparation_network':'permitted'})
        state=inspect_dependency(item,project,cache)
        if state['status']!='cached':raise PreparationError(state.get('reason','Runtime verification failed'))
        return state


def _image_paths(item,cache):
    path=Path(cache)/item.get('target','images/runtime.sif')
    if not path.resolve().is_relative_to(Path(cache).resolve()):raise ValueError('Image escapes cache')
    return path,path.with_name(path.name+'.receipt.json')


def _inspect_image(item,cache):
    if item.get('runtime')=='docker':return _inspect_docker(item,cache)
    if item.get('runtime','apptainer') not in ('apptainer','singularity'):
        return {'status':'invalid','reason':'SIF preparation supports Apptainer/Singularity; Docker needs an OCI image handler'}
    image,receipt=_image_paths(item,cache)
    if image.is_file() and not receipt.is_file():
        return {'status':'invalid','reason':'Image exists without a verified preparation receipt','target_path':str(image)}
    if not image.is_file() or not receipt.is_file():
        return {'status':'missing','reason':'Prepared local image or receipt missing','target_path':str(image)}
    try:
        data=json.loads(receipt.read_text())
        if (_oci_reference(data['source'])!=_oci_reference(item['source']) or data['sha256']!=digest(image)
                or item.get('sha256') is not None and item['sha256']!=data['sha256']):
            return {'status':'invalid','reason':'Container image or source binding changed'}
    except (OSError,ValueError,KeyError):return {'status':'invalid','reason':'Invalid image receipt'}
    return {'status':'cached','target_path':str(image),'sha256':data['sha256']}


def _prepare_image(item,project,cache,offline):
    if item.get('runtime')=='docker':return _prepare_docker(item,cache,offline)
    image,receipt=_image_paths(item,cache)
    with item_lock(Path(cache).resolve(),'image:'+str(image)):
        state=_inspect_image(item,cache)
        if state['status']=='cached':return state
        if state['status']=='invalid' or offline:raise PreparationError(state['reason']+'; no network attempted')
        source=item['source'];source=source.get('url') if isinstance(source,dict) else source
        if not isinstance(source,str) or not re.search(r'@sha256:[a-f0-9]{64}$',source):
            raise PreparationError('Container source must use an OCI digest')
        if '://' not in source:source='docker://'+source
        if not source.startswith(('docker://','oras://')):
            raise PreparationError('SIF preparation requires a Docker or ORAS OCI source')
        engine=shutil.which(item.get('runtime','apptainer'))
        if not engine:raise PreparationError('Container engine is unavailable')
        image.parent.mkdir(parents=True,exist_ok=True)
        temporary=image.with_name(image.stem+'.partial-'+uuid.uuid4().hex+'.sif')
        subprocess.run([engine,'pull',str(temporary),source],check=True,capture_output=True,text=True)
        subprocess.run([engine,'inspect',str(temporary)],check=True,capture_output=True,text=True)
        try:os.link(temporary,image)
        except FileExistsError:raise PreparationError('Image appeared outside its preparation lock; not overwritten')
        temporary.unlink()
        _save(receipt,{'schema_version':2,'source':item['source'],'sha256':digest(image)})
        return _inspect_image(item,cache)


def _inspect_native(item):
    executables={}
    for name in _binaries(item):
        path=shutil.which(name)
        if not path or not Path(path).is_file() or not os.access(path,os.X_OK):
            return {'status':'missing','reason':'Native executable unavailable: '+name}
        executables[name]={'path':path,'sha256':digest(path)}
    return {'status':'cached','manager':'native','executables':executables,
            'version_verification':'Exact scientific tool versions are checked at invocation; no install or version command during inventory.'}


def _docker_source(item):
    return _oci_reference(item.get('source'))


def _docker_receipt(item,cache):
    source=_docker_source(item)
    path=Path(cache)/item.get('target','images/docker-'+source.rsplit(':',1)[-1][:16]+'.json')
    if not path.resolve().is_relative_to(Path(cache).resolve()):raise ValueError('Docker receipt escapes cache')
    return path


def _inspect_docker(item,cache):
    """Inspect the local daemon only; image inspect never invokes docker pull."""
    try:source=_docker_source(item);receipt_path=_docker_receipt(item,cache)
    except ValueError as error:return {'status':'invalid','reason':str(error)}
    engine=shutil.which('docker')
    if not engine:return {'status':'missing','reason':'Docker executable unavailable'}
    try:
        result=subprocess.run([engine,'image','inspect','--format','{{json .}}',source],
                              capture_output=True,text=True,timeout=30)
    except (OSError,subprocess.TimeoutExpired) as error:
        return {'status':'missing','reason':'Local Docker daemon inventory unavailable: '+str(error)}
    if result.returncode!=0:
        return {'status':'missing','reason':'Pinned image is unavailable in the local Docker daemon','target_path':str(receipt_path)}
    try:
        image=json.loads(result.stdout)
        if isinstance(image,list):image=image[0]
        image_id=image['Id'];repo_digests=image.get('RepoDigests') or []
        if source not in repo_digests or not re.fullmatch(r'sha256:[a-f0-9]{64}',image_id):
            return {'status':'invalid','reason':'Local Docker image does not match the declared repository digest'}
        if item.get('image_id') is not None and item['image_id']!=image_id:
            return {'status':'invalid','reason':'Local Docker image ID differs from manifest'}
        if receipt_path.exists():
            receipt=json.loads(receipt_path.read_text())
            if _oci_reference(receipt.get('source'))!=source or receipt.get('image_id')!=image_id:
                return {'status':'invalid','reason':'Local Docker image/source differs from its preparation receipt'}
    except (OSError,ValueError,KeyError,IndexError,TypeError) as error:
        return {'status':'invalid','reason':'Invalid local Docker image inventory: '+str(error)}
    return {'status':'cached','runtime':'docker','image':source,'image_id':image_id,
            'target_path':str(receipt_path),'availability_scope':'local Docker daemon; shared receipts do not load another host daemon'}


def _prepare_docker(item,cache,offline):
    try:source=_docker_source(item);receipt=_docker_receipt(item,cache)
    except ValueError as error:raise PreparationError(str(error)) from error
    with item_lock(Path(cache).resolve(),'docker-image:'+source):
        state=_inspect_docker(item,cache)
        if state['status']=='invalid':raise PreparationError(state['reason'])
        if state['status']!='cached':
            if offline:raise PreparationError(state['reason']+'; no network attempted')
            engine=shutil.which('docker')
            if not engine:raise PreparationError('Docker executable unavailable')
            try:subprocess.run([engine,'pull',source],check=True,capture_output=True,text=True)
            except (OSError,subprocess.CalledProcessError) as error:
                raise PreparationError('Pinned Docker image preparation failed: '+str(error)) from error
            state=_inspect_docker(item,cache)
            if state['status']!='cached':raise PreparationError(state.get('reason','Docker image verification failed'))
        _save(receipt,{'schema_version':2,'source':item['source'],'image_id':state['image_id']})
        return state
