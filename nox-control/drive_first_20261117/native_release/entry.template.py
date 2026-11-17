#!/usr/bin/env python3
"""Owner-approved code staging, Drive-first startup policy and one chat canary.

No provider credential export, service restart, model download or new scheduler.
Existing owner runner validates repository, actor, source SHA and native host.
"""
import ast,base64,gzip,hashlib,importlib.util,json,os,re,stat,sys,time,types
from pathlib import Path

ROOT=Path('/root/nox')
BUNDLE_SHA='BUNDLE_SHA256'
BUNDLE_DATA=gzip.decompress(base64.b64decode('BUNDLE_JSON_BASE64',validate=True))
if hashlib.sha256(BUNDLE_DATA).hexdigest()!=BUNDLE_SHA:raise RuntimeError('HOLD_BUNDLE_SHA')
BUNDLE=json.loads(BUNDLE_DATA)
DEST=ROOT/'extensions'/('drive_first_20261117_'+BUNDLE_SHA[:12])

def emit(kind,data):
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':data},ensure_ascii=False,separators=(',',':')),flush=True)

def directory(path):
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            except FileNotFoundError:
                os.mkdir(part,0o700,dir_fd=fd)
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child
        info=os.fstat(fd)
        if info.st_uid!=os.geteuid() or info.st_mode&0o022:raise RuntimeError('HOLD_DIRECTORY_OWNER')
        return fd
    except BaseException:os.close(fd);raise

def stage():
    total=0
    for rel,text in BUNDLE['files'].items():
        if not re.fullmatch(r'[A-Za-z0-9_./-]{1,150}',rel) or '..' in Path(rel).parts or rel.startswith('/'):
            raise RuntimeError('HOLD_BUNDLE_PATH')
        raw=text.encode();wanted=BUNDLE['sha256'][rel]
        if len(raw)>250000 or hashlib.sha256(raw).hexdigest()!=wanted:raise RuntimeError('HOLD_SOURCE_PIN')
        target=DEST/rel;parent=directory(target.parent)
        try:
            try:
                fd=os.open(target.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
            except FileExistsError:fd=None
            if fd is not None:
                with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
                os.fsync(parent)
            fd=os.open(target.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
            with os.fdopen(fd,'rb') as stream:
                info=os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size!=len(raw) or stream.read()!=raw:raise RuntimeError('HOLD_STAGE_COLLISION')
        finally:os.close(parent)
        total+=len(raw)
    return {'status':'SOURCE_INSTALLED_NOT_BOUND','directory':str(DEST),'files':len(BUNDLE['files']),'bytes':total,'bundle_sha256':BUNDLE_SHA,'new_services':0,'model_downloads':0}

def module(rel,name):
    path=DEST/rel;raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=BUNDLE['sha256'][rel]:raise RuntimeError('HOLD_INSTALLED_SOURCE_CHANGED')
    value=types.ModuleType(name);value.__file__=str(path)
    sys.modules[name]=value
    exec(compile(raw,str(path),'exec'),value.__dict__)
    return value

def bindings():
    rows=[]
    for name in ('nox_dispatcher_t855u.py','owner_subagent_dispatcher.py','owner_task_lifecycle.py','owner_event_outbox.py'):
        path=ROOT/'scripts'/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size>350000:
            rows.append({'path':str(path),'readable':False});continue
        raw=path.read_bytes();tree=ast.parse(raw)
        functions=[n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
        imports=[n.module for n in tree.body if isinstance(n,ast.ImportFrom) and n.module]
        maps={}
        for n in tree.body:
            if isinstance(n,ast.Assign) and isinstance(n.value,ast.Dict):
                for target in n.targets:
                    if isinstance(target,ast.Name) and re.search('HANDLER|REGISTRY|ACTION|TOOLS',target.id):
                        maps[target.id]=[k.value for k in n.value.keys if isinstance(k,ast.Constant) and isinstance(k.value,str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,100}',k.value)]
        rows.append({'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'functions':functions[:100],'imports':imports[:50],'registry_keys':maps})
    return rows

def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not request.isdigit() or not re.fullmatch('[0-9a-f]{40}',source):raise RuntimeError('HOLD_OWNER_REQUEST_CONTEXT')
    active=ROOT/'state/priority/CHAT_ACTIVE'
    if not active.is_file() or active.is_symlink() or active.read_text().strip()!='0':raise RuntimeError('HOLD_OWNER_CHAT_ACTIVE_OR_UNKNOWN')
    staged=stage();emit('drive_first_sources',staged)
    legacy=module('legacy/install.py','_nox_drive_first_legacy')
    result=legacy.install(apply=True,expected_source_sha='437739550dbdff28380a95302c1cc1e98ceab3f147de898b40dd8ec82ef80389')
    emit('legacy_drive_first_policy',result)
    sys.path.insert(0,str(DEST/'runtime'))
    from nox_integrations import Config,IntegrationBridge
    import nox_warm
    registry=IntegrationBridge(Config.load()).registry()
    emit('integrations_configuration_only',registry)
    readset=module('acceptance/native_integration_readset.py','_nox_onehost_binding_metadata')
    emit('onehost_binding_metadata',readset.run())
    probe=module('model/gguf_metadata_probe.py','_nox_bounded_gguf_metadata')
    try:emit('primary_gguf_metadata',probe.inspect_gguf())
    except Exception as exc:emit('primary_gguf_metadata',{'status':'HOLD','error_type':type(exc).__name__})
    acceptance=module('acceptance/native_acceptance.py','_nox_native_chat_acceptance')
    try:canary=acceptance.run(True,expected_source_sha=source)
    except Exception as exc:
        canary={'status':str(exc) if isinstance(exc,acceptance.Hold) else 'HOLD_READINESS_FAILURE','native_canary_pass':False,'credentials_exported':False}
        if isinstance(exc,acceptance.Hold) and hasattr(exc,'dependency_identifiers'):
            canary['dependency_identifiers']=exc.dependency_identifiers
    emit('native_resonance_acceptance',canary)
    return canary.get('native_canary_pass') is True and result.get('status') in ('PATCH_APPLIED_NOT_EXECUTED','ALREADY_APPLIED')

if __name__=='__main__':
    complete=False
    try:complete=main()
    except Exception as exc:emit('release_hold',{'status':'HOLD','error_type':type(exc).__name__,'reason':str(exc)[:180] if str(exc).startswith('HOLD') else 'BOUNDED_RELEASE_ERROR'})
    print('NOX_MAINT_REPAIR_COMPLETE='+str(complete).lower())
    if not complete:raise SystemExit(2)
