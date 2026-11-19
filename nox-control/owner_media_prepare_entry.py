#!/usr/bin/env python3
"""Pinned native admission/poll for one resumable background media installer.

Downloads run without the shared owner-maintenance lock. The short engine start
reacquires it and rechecks the original training HOLD; the existing installer
then acquires the same GPU1 lease used by training/media. No dispatcher binding,
chat restart, model promotion, or source deletion is performed here.
"""
from __future__ import annotations
import base64
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
STATE = ROOT/'state/owner_media'
SCRIPTS = ROOT/'scripts'
INSTALLER_SHA = 'e66a5b743deb0dfaa7e1e846e11b2d06190962d9ba0ba4abb67abeca54c02ca5'
LEGACY_INSTALLER_SHA = '504cd1c69d51c7aebfeb7b2c935904c4becb1e296f0d04beeb493c8775a13ee6'
LEGACY_WORKER_SHA = '80f44bc88266dddf46c4c40d9597d75be6b272d5fce1eab79a1e28f12cc4bc8e'
LEGACY_SOURCE_SHA = 'e88dc6f974f33552336143e553c0a0d0cd1ce7ce'
LEGACY_FAILED_REQUESTS = {'6903919663'}
RUNTIME_SHA = 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5'
PINS = {'owner_media_install.py':INSTALLER_SHA, 'owner_media_runtime.py':RUNTIME_SHA}
HOLD_TEXT = ('OWNER_REQUESTED_TRAINING_HALT request=6902883046 '
             'source=df3a6005ca711ce44b606b864db154c396cbeb92')
CONFIG = ROOT/'config/owner_media_runtime.json'
JOB = STATE/'prepare_job.json'
WORKER = SCRIPTS/'owner_media_prepare_worker.py'


def fail(code):
    raise RuntimeError(code)


def plain(path):
    path = Path(path)
    for parent in (*reversed(path.parents), path):
        if parent.is_symlink(): fail('HOLD_MEDIA_PREPARE_SYMLINK')
    return path


def digest(path):
    value = hashlib.sha256()
    with plain(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024), b''): value.update(block)
    return value.hexdigest()


def atomic(path, data):
    path = plain(path); path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.media-prepare-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def write_json(path, value):
    atomic(path, json.dumps(value, indent=2).encode())


def read_json(path, maximum=2*1024*1024):
    path = plain(path)
    if not path.is_file() or path.stat().st_size > maximum: fail('HOLD_MEDIA_PREPARE_STATE_SIZE')
    value = json.loads(path.read_text())
    if not isinstance(value, dict): fail('HOLD_MEDIA_PREPARE_STATE_SCHEMA')
    return value


def identity(pid):
    try:
        folder = Path('/proc')/str(pid)
        fields = (folder/'stat').read_text().split(') ', 1)[1].split()
        argv = [part.decode(errors='replace') for part in (folder/'cmdline').read_bytes().split(b'\0') if part]
        return {'pid':int(pid), 'start_ticks':fields[19], 'state':fields[0], 'argv':argv,
                'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except (OSError, ValueError, IndexError):
        return None


def same_job(record, observed):
    return bool(observed and observed.get('state') != 'Z' and all(
        record.get(key) == observed.get(key) for key in ('pid','start_ticks','boot_id','argv')))


def acquire(path):
    path = plain(path); path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd); return None
    return fd


def trainer_status():
    result = subprocess.run(['supervisorctl','status','nox-train-volta-t866u'],
                            capture_output=True, text=True, timeout=15)
    match = re.match(r'^nox-train-volta-t866u\s+(\w+)', result.stdout.strip())
    return match[1] if match else 'UNKNOWN'


def original_hold():
    path = plain(ROOT/'state/TRAIN_HOLD.flag')
    if not path.is_file() or path.stat().st_size > 4096 or not path.read_text().startswith(HOLD_TEXT):
        fail('HOLD_MEDIA_ORIGINAL_TRAINING_PAUSE_REQUIRED')
    for path in (ROOT/'STOP', ROOT/'STOP.flag', ROOT/'stop.flag', ROOT/'.stop', ROOT/'program/STOP',
                 ROOT/'state/STOP', ROOT/'state/MEDIA_STOP.flag', Path('/workspace/NOX_STOP')):
        if path.exists() or path.is_symlink(): fail('HOLD_MEDIA_NEW_OWNER_STOP')
    if trainer_status() not in ('STOPPED','EXITED','FATAL'): fail('HOLD_MEDIA_TRAINER_NOT_STOPPED')


def legacy_migration_proof(old):
    """Only the observed, terminated closure failure may be upgraded."""
    if (not isinstance(old,dict) or old.get('schema')!='NOX_MEDIA_PREPARE_JOB_V1'
            or old.get('request') not in LEGACY_FAILED_REQUESTS
            or old.get('installer_sha256')!=LEGACY_INSTALLER_SHA
            or old.get('runtime_sha256')!=RUNTIME_SHA or old.get('worker_sha256')!=LEGACY_WORKER_SHA
            or old.get('source_sha')!=LEGACY_SOURCE_SHA
            or type(old.get('pid')) is not int or old['pid']<=0
            or same_job(old,identity(old['pid']))):
        fail('HOLD_MEDIA_LEGACY_JOB_IDENTITY')
    archived = read_json(STATE/'prepare_jobs'/(old['request']+'.json'),16000)
    result = read_json(STATE/('prepare_result_'+old['request']+'.json'),16000)
    times = (result.get('started'),result.get('finished'))
    if (archived!=old or result.get('schema')!='NOX_MEDIA_PREPARE_WORKER_V1'
            or result.get('request')!=old['request'] or result.get('source_sha')!=old['source_sha']
            or result.get('state')!='HOLD_MEDIA_PREPARE' or result.get('error')!='HOLD_MEDIA_DEPENDENCY_CLOSURE'
            or not all(type(value) in (int,float) and math.isfinite(value) for value in times)
            or not 0 < times[0] <= times[1]):
        fail('HOLD_MEDIA_LEGACY_FAILURE_RECEIPT')
    original_hold()
    return {'request':old['request'],'previous_installer_sha256':LEGACY_INSTALLER_SHA,
            'previous_worker_sha256':LEGACY_WORKER_SHA,'terminal_result_sha256':digest(STATE/('prepare_result_'+old['request']+'.json'))}


def install_component(path, data, expected, legacy=None, migration=None):
    path=plain(path)
    if hashlib.sha256(data).hexdigest()!=expected:fail('HOLD_MEDIA_BUNDLE_PIN')
    compile(data,str(path),'exec')
    if path.exists():
        old_sha=digest(path)
        if old_sha==expected:return
        if not migration or not legacy or old_sha!=legacy:
            fail('HOLD_MEDIA_INSTALLED_COMPONENT_CHANGED')
        backup=plain(STATE/'source_backups'/(path.name+'.'+old_sha))
        if backup.exists():
            if digest(backup)!=old_sha:fail('HOLD_MEDIA_SOURCE_BACKUP_CHANGED')
        else:atomic(backup,path.read_bytes())
        if digest(path)!=old_sha:fail('HOLD_MEDIA_COMPONENT_CHANGED_DURING_BACKUP')
    atomic(path,data)
    os.chmod(path,0o700 if path==WORKER else 0o755)
    if digest(path)!=expected:fail('HOLD_MEDIA_INSTALLED_COMPONENT_READBACK')


def module_from_installer():
    path = SCRIPTS/'owner_media_install.py'
    if digest(path) != INSTALLER_SHA: fail('HOLD_MEDIA_INSTALLER_SOURCE_CHANGED')
    spec = importlib.util.spec_from_file_location('owner_pinned_media_install', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def readiness(installer):
    """READY is independently observed; generation acceptance remains separate."""
    if not CONFIG.is_file(): return {'state':'NOT_PREPARED'}
    config = read_json(CONFIG)
    rows = config.get('assets', [])
    known = {row['filename']:row for row in installer.ASSETS}
    if (not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
            or len(rows) != len(known) or {row.get('filename') for row in rows} != set(known)):
        fail('HOLD_MEDIA_CONFIG_ASSET_SET')
    missing = []
    for row in rows:
        expected = known[row['filename']]
        if any(row.get(key) != expected[key] for key in ('bytes','sha256','role','kind')):
            fail('HOLD_MEDIA_CONFIG_ASSET_IDENTITY')
        if not installer.validate_file(row['path'], expected): missing.append(row['filename'])
    if missing:
        return {'state':'FILES_INCOMPLETE_REHYDRATION_REQUIRED','missing':missing,
                'all_asset_sha256_verified':False,'generation_acceptance_verified':False}
    state = 'FILES_VERIFIED_ENGINE_NOT_READY'
    if config.get('enabled') is True:
        service = installer.service_status()
        if service['state'] != 'RUNNING': fail('HOLD_MEDIA_READY_SERVICE_NOT_RUNNING')
        process = installer.process_identity(service['pid'])
        if (process['cuda'] != '1' or process['service'] != installer.SERVICE
                or str(Path(config['engine_root'])/'main.py') not in process['argv']
                or str(process['start_ticks']) != str(config.get('start_ticks'))
                or process['pid'] != config.get('engine_pid')):
            fail('HOLD_MEDIA_READY_PROCESS_IDENTITY')
        if installer.sha256(Path(config['engine_root'])/'main.py') != config.get('engine_main_sha256'):
            fail('HOLD_MEDIA_READY_ENGINE_SOURCE')
        nodes = installer.get_json('http://127.0.0.1:8188/object_info', limit=8*1024*1024)
        if any(name not in nodes for name in installer.REQUIRED_NODES):
            fail('HOLD_MEDIA_READY_REQUIRED_NODES')
        options = {'checkpoint':('CheckpointLoaderSimple','ckpt_name'), 'unet':('UNETLoader','unet_name'),
                   'clip':('CLIPLoader','clip_name'), 'vae':('VAELoader','vae_name')}
        for row in rows:
            node, field = options[row['role']]
            if row['filename'] not in nodes.get(node, {}).get('input', {}).get('required', {}).get(field, [[]])[0]:
                fail('HOLD_MEDIA_READY_MODEL_OPTION')
        installer.health_chat()
        state = 'ENGINE_AND_FILES_READY_GENERATION_ACCEPTANCE_PENDING'
    return {'state':state, 'assets':len(rows), 'bytes':sum(row['bytes'] for row in rows),
            'all_asset_sha256_verified':True, 'generation_acceptance_verified':False,
            'config_sha256':digest(CONFIG), 'engine_service':config.get('engine_service')}


# One finite background job, not a new daemon or scheduler. Its inherited flock
# remains held through download, verification and the optional engine start.
WORKER_SOURCE = r'''#!/usr/bin/env python3
import argparse,fcntl,hashlib,importlib.util,json,os,re,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--source',required=True)
p.add_argument('--mode',choices=('install','start'),required=True);p.add_argument('--lock-fd',type=int,required=True);a=p.parse_args()
ROOT=Path('/root/nox');STATE=ROOT/'state/owner_media'
target=STATE/('prepare_result_'+a.request+'.json')
result={'schema':'NOX_MEDIA_PREPARE_WORKER_V1','request':a.request,'source_sha':a.source,'started':time.time(),'mode':a.mode}
def fail(code):raise RuntimeError(code)
def save():
 import tempfile
 fd,tmp=tempfile.mkstemp(prefix='.media-result-',dir=STATE)
 try:
  with os.fdopen(fd,'w') as f:json.dump(result,f);f.flush();os.fsync(f.fileno())
  os.replace(tmp,target)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
lock=None
try:
 if not a.request.isdigit() or not re.fullmatch('[a-f0-9]{40}',a.source):fail('HOLD_MEDIA_WORKER_CONTEXT')
 if os.fstat(a.lock_fd).st_ino!=(STATE/'prepare.lock').stat().st_ino:fail('HOLD_MEDIA_WORKER_LEASE')
 fcntl.flock(a.lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 source=ROOT/'scripts/owner_media_install.py'
 if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest()!='__INSTALLER_SHA__':fail('HOLD_MEDIA_WORKER_SOURCE')
 spec=importlib.util.spec_from_file_location('nox_media_installer_job',source)
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 if a.mode=='install':config=mod.install(False)
 else:
  config=json.loads(mod.plain(mod.CONFIG).read_text())
  for row in config['assets']:
   if not mod.validate_file(row['path'],row):fail('HOLD_MEDIA_START_ASSET_MISSING')
 result['state']='FILES_VERIFIED_ENGINE_START_PENDING';save()
 # Only engine startup takes the shared maintenance writer lease. Downloads
 # above do not block the six dispatcher executors or owner chat repair.
 lock=os.open(ROOT/'state/owner_maintenance.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
 deadline=time.monotonic()+3
 while True:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
  except BlockingIOError:
   if time.monotonic()>=deadline:
    result['state']='FILES_VERIFIED_ENGINE_START_DEFERRED';save();sys.exit(0)
   time.sleep(0.1)
 hold=mod.plain(ROOT/'state/TRAIN_HOLD.flag')
 if not hold.is_file() or hold.stat().st_size>4096 or not hold.read_text().startswith('__HOLD_TEXT__'):fail('HOLD_MEDIA_ORIGINAL_TRAINING_PAUSE_REQUIRED')
 for stop in (ROOT/'STOP',ROOT/'STOP.flag',ROOT/'stop.flag',ROOT/'.stop',ROOT/'program/STOP',ROOT/'state/STOP',ROOT/'state/MEDIA_STOP.flag',Path('/workspace/NOX_STOP')):
  if stop.exists() or stop.is_symlink():fail('HOLD_MEDIA_NEW_OWNER_STOP')
 state=subprocess.run(['supervisorctl','status','nox-train-volta-t866u'],capture_output=True,text=True,timeout=15).stdout
 if not re.match(r'^nox-train-volta-t866u\s+(STOPPED|EXITED|FATAL)\b',state.strip()):fail('HOLD_MEDIA_TRAINER_NOT_STOPPED')
 config=mod.start_engine(config)
 result['state']=config['readiness_scope'];result['config_sha256']=hashlib.sha256(mod.CONFIG.read_bytes()).hexdigest()
 result['generation_acceptance_verified']=False
except Exception as exc:
 result['state']='HOLD_MEDIA_PREPARE';code=str(exc)
 result['error']=code if re.fullmatch('HOLD_[A-Z0-9_]+',code) else type(exc).__name__
finally:
 result['finished']=time.time();save()
 if lock is not None:os.close(lock)
 os.close(a.lock_fd)
print('NOX_MEDIA_PREPARE_RESULT='+json.dumps(result),flush=True)
sys.exit(2 if result['state']=='HOLD_MEDIA_PREPARE' else 0)
'''.replace('__INSTALLER_SHA__', INSTALLER_SHA).replace('__HOLD_TEXT__', HOLD_TEXT)


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID',''); source = os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not request.isdigit() or not re.fullmatch('[0-9a-f]{40}', source): fail('HOLD_OWNER_REQUEST_CONTEXT')
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    result = {'schema':'NOX_OWNER_MEDIA_PREPARE_V1','request':request,'source_sha':source,
              'started':time.time(),'generation_acceptance_verified':False,'source_deleted':False,
              'training_started':False,'dispatcher_modified':False}
    maintenance = acquire(ROOT/'state/owner_maintenance.lock')
    if maintenance is None: fail('HOLD_OWNER_MAINTENANCE_BUSY')
    job_fd = None; success = False
    try:
        old = read_json(JOB) if JOB.exists() else None
        if old and same_job(old, identity(old.get('pid'))):
            if old.get('installer_sha256') != INSTALLER_SHA or old.get('runtime_sha256') != RUNTIME_SHA:
                fail('HOLD_MEDIA_RUNNING_JOB_SOURCE_CHANGED')
            result.update(state='INSTALL_RUNNING',job=old,worker_alive=True)
            success = True
        else:
            job_fd = acquire(STATE/'prepare.lock')
            if job_fd is None: fail('HOLD_MEDIA_UNTRACKED_PREPARATION_BUSY')
            migration = None
            installed_source = plain(SCRIPTS/'owner_media_install.py')
            old_installer = installed_source.exists() and digest(installed_source)==LEGACY_INSTALLER_SHA
            old_worker = WORKER.exists() and digest(WORKER)==LEGACY_WORKER_SHA
            if old_installer or old_worker:
                migration=legacy_migration_proof(old)
                result['additive_dependency_migration']=migration
            for name, sha in PINS.items():
                data = base64.b64decode(BUNDLE.get(name,''), validate=True)
                install_component(SCRIPTS/name,data,sha,
                                  LEGACY_INSTALLER_SHA if name=='owner_media_install.py' else None,migration)
            installer = module_from_installer()
            observed = readiness(installer)
            if observed['state'] == 'ENGINE_AND_FILES_READY_GENERATION_ACCEPTANCE_PENDING':
                result.update(state=observed['state'], readiness=observed, worker_alive=False)
                success = True
            else:
                original_hold()
                lease = acquire(ROOT/'state/forge_training.lock')
                if lease is None: fail('HOLD_MEDIA_GPU1_LEASE_BUSY')
                os.close(lease)
                free = installer.run(['nvidia-smi','-i','1','--query-gpu=memory.free','--format=csv,noheader,nounits']).strip()
                if not free.isdigit() or int(free) < 27000: fail('HOLD_MEDIA_GPU1_ADMISSION')
                installer.health_chat()
                worker_bytes = WORKER_SOURCE.encode(); compile(worker_bytes, str(WORKER), 'exec')
                install_component(WORKER,worker_bytes,hashlib.sha256(worker_bytes).hexdigest(),
                                  LEGACY_WORKER_SHA,migration)
                mode = 'start' if observed.get('all_asset_sha256_verified') else 'install'
                log = plain(ROOT/'logs'/('owner_media_prepare_'+request+'.log'))
                log.parent.mkdir(parents=True, exist_ok=True)
                log_fd = os.open(log, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                argv = [sys.executable,'-u',str(WORKER),'--request',request,'--source',source,
                        '--mode',mode,'--lock-fd',str(job_fd)]
                env = dict(os.environ, CUDA_VISIBLE_DEVICES='1', OMP_NUM_THREADS='4',
                           MKL_NUM_THREADS='4', OPENBLAS_NUM_THREADS='1', TOKENIZERS_PARALLELISM='false',
                           PYTHONDONTWRITEBYTECODE='1', NOX_MEDIA_PREPARE_SOURCE=source)
                try:
                    child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log_fd, stderr=subprocess.STDOUT,
                        env=env, start_new_session=True, close_fds=True, pass_fds=(job_fd,))
                finally: os.close(log_fd)
                # Native argv must match after exec; no guessed or host nvidia PID.
                observed_process = None
                for _ in range(20):
                    observed_process = identity(child.pid)
                    if observed_process and observed_process['argv'] == argv: break
                    time.sleep(0.05)
                if not observed_process or observed_process['argv'] != argv: fail('HOLD_MEDIA_WORKER_START_IDENTITY')
                job = {**observed_process, 'schema':'NOX_MEDIA_PREPARE_JOB_V1','request':request,
                       'source_sha':source,'mode':mode,'log':str(log),'installer_sha256':INSTALLER_SHA,
                       'runtime_sha256':RUNTIME_SHA,'worker_sha256':hashlib.sha256(worker_bytes).hexdigest(),
                       'created_at':time.time()}
                write_json(STATE/'prepare_jobs'/(request+'.json'), job); write_json(JOB, job)
                result.update(state='INSTALL_RUNNING',job=job,worker_alive=True,
                              gpu1_free_mib_before=int(free), readiness=observed)
                success = True
        if old:
            old_result = STATE/('prepare_result_'+str(old.get('request'))+'.json')
            if old_result.is_file(): result['previous_worker_result'] = read_json(old_result, 16000)
    except Exception as exc:
        code = str(exc); result['state'] = 'HOLD_MEDIA_PREPARE'
        result['error'] = code if re.fullmatch('HOLD_[A-Z0-9_]+', code) else type(exc).__name__
    finally:
        if job_fd is not None: os.close(job_fd)
        os.close(maintenance)
        result['finished'] = time.time()
        write_json(ROOT/'state'/('owner_maintenance_'+request+'.json'), result)
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'native_media_prepare_receipt','data':result}), flush=True)
    if success: print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        code = str(exc); reason = code if re.fullmatch('HOLD_[A-Z0-9_]+', code) else type(exc).__name__
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'failure','data':reason}), flush=True)
        raise SystemExit(2)
