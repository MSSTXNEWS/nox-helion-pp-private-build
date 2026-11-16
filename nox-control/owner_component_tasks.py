#!/usr/bin/env python3
"""Six bounded native reconciliation jobs for the existing NOX dispatcher.

Completion means the named check actually ran. Pending OAuth, model promotion
and GPU optimizer acceptance remain explicit blockers, never installation PASS.
"""
from __future__ import annotations
import ast
import hashlib
import json
import os
import re
import stat
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path('/root/nox')
TASKS = ('owner.training_stack', 'owner.dispatcher', 'owner.chat',
         'owner.memory', 'owner.storage', 'owner.downloads')
PACKAGES = ('torch','transformers','accelerate','datasets','safetensors','peft',
            'bitsandbytes','trl','deepspeed','psutil','nvidia-ml-py')

def digest(path):
    with Path(path).open('rb') as stream:
        h=hashlib.sha256()
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def read_json(path, limit=1000000):
    p=Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size>limit:
        raise RuntimeError('UNREADABLE_BOUNDED_JSON')
    return json.loads(p.read_text())

def atomic(path, obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink() or path.parent.is_symlink():raise RuntimeError('RECEIPT_SYMLINK')
    fd, temporary=tempfile.mkstemp(prefix='.component-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(obj,stream,ensure_ascii=False,indent=2);stream.write('\n')
            stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)

def metadata():
    code="import importlib.metadata as m,json;d={};\nfor n in "+repr(PACKAGES)+":\n try:d[n]=m.version(n)\n except m.PackageNotFoundError:d[n]=None\nprint(json.dumps(d))"
    result=subprocess.run(['/root/venv_volta/bin/python','-c',code],capture_output=True,
                          text=True,timeout=25,check=True)
    return json.loads(result.stdout)

def health(port,path='/health'):
    start=time.monotonic()
    with urllib.request.urlopen('http://127.0.0.1:'+str(port)+path,timeout=8) as response:
        data=json.loads(response.read(100000))
        return response.status,data,round(time.monotonic()-start,4)

def training_stack():
    versions=metadata()
    missing=[name for name in PACKAGES if not versions.get(name)]
    entry=ROOT/'scripts/hybrid_training_entry.py'
    ast.parse(entry.read_text())
    return {'verified':not missing,'versions':versions,'missing':missing,
            'entry_sha256':digest(entry),'training_hold':(ROOT/'state/TRAIN_HOLD.flag').exists(),
            'scope':'INSTALLED_STACK_AND_SYNTAX_ONLY',
            'blockers':['REAL_OPTIMIZER_ACCEPTANCE_AND_HOLDOUT_REQUIRED']}

# V14-6-09: SOURCE-only observations from the ORIGINAL dispatcher state.
# A PID, worker configuration, mtime or heartbeat alone is never advancement.
# These samples are untrusted local telemetry, not a native writer lease,
# optimizer proof, verified S03 transaction or authorization to restart.
_HEX24 = re.compile(r'^[0-9a-f]{24}    config=read_json(ROOT/'config/dispatcher_agents_t868u.json')
    workers=int(config.get('workers',0))
    script=ROOT/'scripts/nox_dispatcher_t855u.py'
    ast.parse(script.read_text())
    progress=_dispatcher_progress_observation()
    return {'verified':workers==6,'workers':workers,'min_workers':config.get('min_workers'),
            'max_workers':config.get('max_workers'),'dispatcher_sha256':digest(script),
            'progress_observation':progress,
            'scope':'CONFIGURED_EXECUTORS_PLUS_UNATTESTED_PROGRESS_OBSERVATIONS',
            'live_progress_verified':False,
            'blockers':['CAPACITY_BENCHMARK_REQUIRED',
                        'NATIVE_PID_START_TICKS_OWNER_LEASE_AND_PROGRESS_READBACK_REQUIRED']}

def chat():
    measurements={}
    for port in (8080,8081,8082):
        code,_,seconds=health(port)
        measurements[str(port)]={'status':code,'seconds':seconds}
    _,slots,_=health(8081,'/slots')
    return {'verified':all(x['status']==200 for x in measurements.values()),
            'health':measurements,'model_slots':len(slots) if isinstance(slots,list) else None,
            'scope':'HEALTH_ONLY','blockers':['AUTHENTICATED_STREAM_AND_S03_E2E_REQUIRED']}

def memory():
    status,data,seconds=health(8080,'/nox/s03/status')
    counts=data.get('counts') if isinstance(data,dict) else None
    clean={k:v for k,v in counts.items() if isinstance(v,(int,float,bool))} if isinstance(counts,dict) else None
    return {'verified':status==200 and isinstance(counts,dict),'counts':clean,
            'seconds':seconds,'scope':'EXISTING_S03_READ_ONLY_STATUS',
            'blockers':['INDEPENDENT_BACKUP_RESTORE_REQUIRED']}

def storage():
    installed=shutil.which('rclone') is not None
    cfg=ROOT/'state/cold_drive.conf'
    private_config=cfg.is_file() and not cfg.is_symlink() and (cfg.stat().st_mode & 0o777)==0o600
    catalog=ROOT/'state/cold_drive_catalog.json'
    catalog_present=catalog.is_file() and not catalog.is_symlink()
    disk=shutil.disk_usage(ROOT)
    shm=shutil.disk_usage('/dev/shm')
    return {'verified':True,'rclone_installed':installed,'dedicated_config_present':private_config,
            'catalog_present':catalog_present,'disk_free_bytes':disk.free,'shm_free_bytes':shm.free,
            'scope':'STORAGE_INVENTORY_ONLY','bytes_evicted':0,
            'blockers':([] if installed and private_config and catalog_present else
                        ['OWNER_PC_OAUTH_AND_TWO_VERIFIED_COPIES_REQUIRED'])}

def downloads():
    manifest=read_json(ROOT/'config/owner_download_manifest.json')
    versions=metadata()
    components=[]
    for row in manifest.get('components',[]):
        package=row.get('package')
        components.append({'id':row.get('id',row.get('name')),'decision':row.get('decision',row.get('state')),
                           'package':package,'installed_version':versions.get(package) if package else None,
                           'owner_executor':row.get('owner_executor')})
    return {'verified':True,'manifest_sha256':digest(ROOT/'config/owner_download_manifest.json'),
            'components':components,'scope':'RECONCILIATION_ONLY','downloaded_bytes':0,
            'blockers':['LARGE_WEIGHTS_REQUIRE_VERIFIED_COLD_COPY_AND_SPACE_ADMISSION']}

HANDLERS=dict(zip(TASKS,(training_stack,dispatcher,chat,memory,storage,downloads)))

def run_component_task(task):
    task_id=task.get('id')
    if task_id not in HANDLERS:return False,{'verified':False,'error':'UNKNOWN_OWNER_COMPONENT'}
    started=time.time()
    try:
        evidence=HANDLERS[task_id]()
        success=evidence.get('verified') is True
        receipt={'schema':'NOX_OWNER_COMPONENT_V1','schema_version':1,'task_id':task_id,
                 'success':success,'verified':success,'started_at':started,'finished_at':time.time(),
                 'worker':task.get('claimed_by',task.get('executor')),'pid':os.getpid(),
                 'source_sha256':digest(__file__),'evidence':evidence}
    except Exception as exc:
        success=False
        receipt={'schema':'NOX_OWNER_COMPONENT_V1','schema_version':1,'task_id':task_id,
                 'success':False,'verified':False,'started_at':started,'finished_at':time.time(),
                 'error':type(exc).__name__}
    path=ROOT/'state/owner_components'/(task_id+'.json')
    atomic(path,receipt)
    return success,{'schema':'NOX_OWNER_COMPONENT_V1','schema_version':1,'task_id':task_id,
                    'verified':success,'success':success,'receipt_path':str(path),
                    'receipt_sha256':digest(path),'scope':receipt.get('evidence',{}).get('scope'),
                    'blockers':receipt.get('evidence',{}).get('blockers',[])}

def queue_tasks():
    titles=('Проверить оптимизированный стек обучения','Проверить шесть исполнителей',
            'Проверить здоровье действующего чата','Проверить действующую память S03',
            'Проверить перенос и ресурсы хранения','Актуализировать установленные зависимости')
    return [{'id':task_id,'class':'owner_order','priority':0,'deps':[],
             'handler':'owner_component','title':title,'status':'pending','lane':'owner_order',
             'locks':[],'retries':0,'max_retries':2,'timeout_sec':90,
             'source':'owner_60509551_task_boost_20261116'} for task_id,title in zip(TASKS,titles)]

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('task',choices=TASKS)
    args=parser.parse_args();ok,result=run_component_task({'id':args.task})
    print(json.dumps(result,ensure_ascii=False));raise SystemExit(0 if ok else 2)
)
_HEX64 = re.compile(r'^[0-9a-f]{64}    config=read_json(ROOT/'config/dispatcher_agents_t868u.json')
    workers=int(config.get('workers',0))
    script=ROOT/'scripts/nox_dispatcher_t855u.py'
    ast.parse(script.read_text())
    return {'verified':workers==6,'workers':workers,'min_workers':config.get('min_workers'),
            'max_workers':config.get('max_workers'),'dispatcher_sha256':digest(script),
            'scope':'CONFIGURED_EXECUTORS_NOT_MEASURED_CAPACITY',
            'blockers':['CAPACITY_BENCHMARK_REQUIRED']}

def chat():
    measurements={}
    for port in (8080,8081,8082):
        code,_,seconds=health(port)
        measurements[str(port)]={'status':code,'seconds':seconds}
    _,slots,_=health(8081,'/slots')
    return {'verified':all(x['status']==200 for x in measurements.values()),
            'health':measurements,'model_slots':len(slots) if isinstance(slots,list) else None,
            'scope':'HEALTH_ONLY','blockers':['AUTHENTICATED_STREAM_AND_S03_E2E_REQUIRED']}

def memory():
    status,data,seconds=health(8080,'/nox/s03/status')
    counts=data.get('counts') if isinstance(data,dict) else None
    clean={k:v for k,v in counts.items() if isinstance(v,(int,float,bool))} if isinstance(counts,dict) else None
    return {'verified':status==200 and isinstance(counts,dict),'counts':clean,
            'seconds':seconds,'scope':'EXISTING_S03_READ_ONLY_STATUS',
            'blockers':['INDEPENDENT_BACKUP_RESTORE_REQUIRED']}

def storage():
    installed=shutil.which('rclone') is not None
    cfg=ROOT/'state/cold_drive.conf'
    private_config=cfg.is_file() and not cfg.is_symlink() and (cfg.stat().st_mode & 0o777)==0o600
    catalog=ROOT/'state/cold_drive_catalog.json'
    catalog_present=catalog.is_file() and not catalog.is_symlink()
    disk=shutil.disk_usage(ROOT)
    shm=shutil.disk_usage('/dev/shm')
    return {'verified':True,'rclone_installed':installed,'dedicated_config_present':private_config,
            'catalog_present':catalog_present,'disk_free_bytes':disk.free,'shm_free_bytes':shm.free,
            'scope':'STORAGE_INVENTORY_ONLY','bytes_evicted':0,
            'blockers':([] if installed and private_config and catalog_present else
                        ['OWNER_PC_OAUTH_AND_TWO_VERIFIED_COPIES_REQUIRED'])}

def downloads():
    manifest=read_json(ROOT/'config/owner_download_manifest.json')
    versions=metadata()
    components=[]
    for row in manifest.get('components',[]):
        package=row.get('package')
        components.append({'id':row.get('id',row.get('name')),'decision':row.get('decision',row.get('state')),
                           'package':package,'installed_version':versions.get(package) if package else None,
                           'owner_executor':row.get('owner_executor')})
    return {'verified':True,'manifest_sha256':digest(ROOT/'config/owner_download_manifest.json'),
            'components':components,'scope':'RECONCILIATION_ONLY','downloaded_bytes':0,
            'blockers':['LARGE_WEIGHTS_REQUIRE_VERIFIED_COLD_COPY_AND_SPACE_ADMISSION']}

HANDLERS=dict(zip(TASKS,(training_stack,dispatcher,chat,memory,storage,downloads)))

def run_component_task(task):
    task_id=task.get('id')
    if task_id not in HANDLERS:return False,{'verified':False,'error':'UNKNOWN_OWNER_COMPONENT'}
    started=time.time()
    try:
        evidence=HANDLERS[task_id]()
        success=evidence.get('verified') is True
        receipt={'schema':'NOX_OWNER_COMPONENT_V1','schema_version':1,'task_id':task_id,
                 'success':success,'verified':success,'started_at':started,'finished_at':time.time(),
                 'worker':task.get('claimed_by',task.get('executor')),'pid':os.getpid(),
                 'source_sha256':digest(__file__),'evidence':evidence}
    except Exception as exc:
        success=False
        receipt={'schema':'NOX_OWNER_COMPONENT_V1','schema_version':1,'task_id':task_id,
                 'success':False,'verified':False,'started_at':started,'finished_at':time.time(),
                 'error':type(exc).__name__}
    path=ROOT/'state/owner_components'/(task_id+'.json')
    atomic(path,receipt)
    return success,{'schema':'NOX_OWNER_COMPONENT_V1','schema_version':1,'task_id':task_id,
                    'verified':success,'success':success,'receipt_path':str(path),
                    'receipt_sha256':digest(path),'scope':receipt.get('evidence',{}).get('scope'),
                    'blockers':receipt.get('evidence',{}).get('blockers',[])}

def queue_tasks():
    titles=('Проверить оптимизированный стек обучения','Проверить шесть исполнителей',
            'Проверить здоровье действующего чата','Проверить действующую память S03',
            'Проверить перенос и ресурсы хранения','Актуализировать установленные зависимости')
    return [{'id':task_id,'class':'owner_order','priority':0,'deps':[],
             'handler':'owner_component','title':title,'status':'pending','lane':'owner_order',
             'locks':[],'retries':0,'max_retries':2,'timeout_sec':90,
             'source':'owner_60509551_task_boost_20261116'} for task_id,title in zip(TASKS,titles)]

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('task',choices=TASKS)
    args=parser.parse_args();ok,result=run_component_task({'id':args.task})
    print(json.dumps(result,ensure_ascii=False));raise SystemExit(0 if ok else 2)
)
_PROGRESS_METRICS = frozenset(('optimizer_steps', 'global_step', 'completed_items',
                               'verified_bytes', 'completed_units'))


def _unique_object(pairs):
    row = {}
    for key, value in pairs:
        if key in row:
            raise ValueError('HOLD_DUPLICATE_JSON_PROPERTY')
        row[key] = value
    return row


def _strict_progress_json(path, limit=1024*1024):
    """Bound read and reject duplicates, nonfinite constants and symlinks."""
    path = Path(path)
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('HOLD_PROGRESS_NOT_BOUNDED_REGULAR')
        raw = stream.read(limit+1)
    if len(raw) > limit:
        raise ValueError('HOLD_PROGRESS_TOO_LARGE')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('HOLD_NONFINITE_PROGRESS')))


def _pid_start_ticks(pid, proc_root=Path('/proc')):
    if type(pid) is not int or not 1 < pid <= 2**31-1:
        return None
    try:
        # The comm field may contain spaces and parentheses; split at LAST ') '.
        tail = (Path(proc_root)/str(pid)/'stat').read_text().rsplit(') ',1)[1].split()
        ticks = int(tail[19])
        return ticks if ticks > 0 else None
    except (OSError, ValueError, IndexError):
        return None


def _progress_snapshot(state, proc_root=Path('/proc'), observed_at=None):
    """Only same native task claim + stable process startticks can be compared."""
    now = time.time() if observed_at is None else observed_at
    if not isinstance(state, dict) or not isinstance(state.get('tasks'), dict):
        return {'observed_at':now, 'tasks':{}, 'status':'HOLD_DISPATCHER_STATE_SCHEMA'}
    tasks = state['tasks']
    if len(tasks) > 4096:
        return {'observed_at':now, 'tasks':{}, 'status':'HOLD_DISPATCHER_TASK_CAP'}
    result = {}
    for task_id, task in list(tasks.items())[:512]:
        if (not isinstance(task_id,str) or len(task_id)>128
                or not isinstance(task,dict) or task.get('status')!='running'):
            continue
        claim = task.get('owner_claim')
        if not isinstance(claim,dict):
            continue
        nonce, pid = claim.get('nonce'),claim.get('pid')
        if not isinstance(nonce,str) or not _HEX24.fullmatch(nonce):
            continue
        ticks = _pid_start_ticks(pid, proc_root)
        if ticks is None:
            continue
        info = task.get('progress')
        if not isinstance(info,dict):
            info = {}
        metric, value = info.get('metric'), info.get('current')
        receipt = info.get('source_receipt_sha256')
        eligible = (metric in _PROGRESS_METRICS and type(value) is int
                    and 0 <= value <= 10**12 and isinstance(receipt,str)
                    and _HEX64.fullmatch(receipt) is not None)
        result[task_id] = {'nonce':nonce, 'pid':pid,'start_ticks':ticks,
                           'metric':metric if eligible else None,
                           'current':value if eligible else None,
                           'source_receipt_sha256':receipt if eligible else None}
    return {'observed_at':now, 'tasks':result, 'status':'LOCAL_SNAPSHOT_NOT_NATIVE_ATTESTATION'}


def _compare_progress(previous, current, now=None):
    """No liveness claim without two separate samples of the SAME identity."""
    now = time.time() if now is None else now
    rows = current.get('tasks') if isinstance(current,dict) else None
    old = previous.get('tasks') if isinstance(previous,dict) else None
    ts = previous.get('observed_at') if isinstance(previous,dict) else None
    if not isinstance(rows,dict):
        return {'state':'HOLD_NO_CURRENT_TASK_SNAPSHOT','advancing':0,'possible_stalled':0}
    if type(ts) not in (int,float) or isinstance(ts,bool) or not isinstance(old,dict) or not 0 < now-ts <= 86400:
        return {'state':'HOLD_NO_COMPARABLE_PRIOR_SAMPLE','advancing':0,'possible_stalled':0}
    advancing,stalled,new_claim,unknown=0,0,0,0
    for tid,cur in rows.items():
        oldrow=old.get(tid)
        if not isinstance(oldrow,dict):
            unknown+=1;continue
        if (any(cur.get(k)!=oldrow.get(k) for k in ('nonce','pid','start_ticks','metric'))
                or cur.get('start_ticks') is None):
            new_claim+=1;continue
        oldn,newn=oldrow.get('current'),cur.get('current')
        if type(oldn) is not int or type(newn) is not int or oldn<0 or newn<0:
            unknown+=1;continue
        if newn > oldn:
            advancing+=1
        elif newn == oldn and now-ts >= 180:
            stalled+=1
        else:
            unknown+=1
    state=('OBSERVED_LOCAL_COUNTER_ADVANCE_UNATTESTED' if advancing else
           'POSSIBLE_STALL_NO_RESTART_AUTHORITY' if stalled else
           'HOLD_NO_MEANINGFUL_PROGRESS_DELTA')
    return {'state':state,'advancing':advancing,'possible_stalled':stalled,
            'new_claim_or_process':new_claim,'insufficient_evidence':unknown,
            'scope':'SELF_REPORTED_COUNTER_NOT_VERIFIED_NATIVE_OR_OPTIMIZER'}


def _dispatcher_progress_observation(root=ROOT, proc_root=Path('/proc'), now=None):
    now = time.time() if now is None else now
    stop_candidates=(root/'STOP',root/'STOP.flag',root/'state/STOP',
                     root/'state/STOP.flag',root/'state/stop.flag',
                     Path('/workspace/NOX_STOP'))
    stop_present=any(p.exists() or p.is_symlink() for p in stop_candidates)
    path=root/'state/dispatcher/state.json'
    try:
        current=_progress_snapshot(_strict_progress_json(path),proc_root,now)
    except (OSError,ValueError,UnicodeError,TypeError):
        current={'observed_at':now,'tasks':{},'status':'HOLD_NATIVE_DISPATCHER_STATE_UNREADABLE'}
    previous=None
    try:
        last=_strict_progress_json(root/'state/owner_components/owner.dispatcher.json', 262144)
        if isinstance(last,dict) and last.get('schema')=='NOX_OWNER_COMPONENT_V1':
            evidence=last.get('evidence')
            if isinstance(evidence,dict):
                observation=evidence.get('progress_observation')
                if isinstance(observation,dict):
                    previous=observation.get('snapshot')
    except (OSError,ValueError,UnicodeError,TypeError):
        pass
    evaluated=_compare_progress(previous,current,now)
    if current['status'] != 'LOCAL_SNAPSHOT_NOT_NATIVE_ATTESTATION':
        evaluated['state']=current['status']
    if stop_present:
        evaluated['state']='HOLD_OWNER_STOP_PRESERVE'
    # Never treat an unauthenticated source snapshot as an owner writer lease.
    return {'state':evaluated['state'],'assessment':evaluated,
            'snapshot':current,'owner_stop_observed':stop_present,
            'writer_lease':'UNKNOWN_NOT_OBTAINED',
            'live_progress_verified':False,'restart_authorized':False}


def dispatcher():
    config=read_json(ROOT/'config/dispatcher_agents_t868u.json')
    workers=int(config.get('workers',0))
    script=ROOT/'scripts/nox_dispatcher_t855u.py'
    ast.parse(script.read_text())
    return {'verified':workers==6,'workers':workers,'min_workers':config.get('min_workers'),
            'max_workers':config.get('max_workers'),'dispatcher_sha256':digest(script),
            'scope':'CONFIGURED_EXECUTORS_NOT_MEASURED_CAPACITY',
            'blockers':['CAPACITY_BENCHMARK_REQUIRED']}

def chat():
    measurements={}
    for port in (8080,8081,8082):
        code,_,seconds=health(port)
        measurements[str(port)]={'status':code,'seconds':seconds}
    _,slots,_=health(8081,'/slots')
    return {'verified':all(x['status']==200 for x in measurements.values()),
            'health':measurements,'model_slots':len(slots) if isinstance(slots,list) else None,
            'scope':'HEALTH_ONLY','blockers':['AUTHENTICATED_STREAM_AND_S03_E2E_REQUIRED']}

def memory():
    status,data,seconds=health(8080,'/nox/s03/status')
    counts=data.get('counts') if isinstance(data,dict) else None
    clean={k:v for k,v in counts.items() if isinstance(v,(int,float,bool))} if isinstance(counts,dict) else None
    return {'verified':status==200 and isinstance(counts,dict),'counts':clean,
            'seconds':seconds,'scope':'EXISTING_S03_READ_ONLY_STATUS',
            'blockers':['INDEPENDENT_BACKUP_RESTORE_REQUIRED']}

def storage():
    installed=shutil.which('rclone') is not None
    cfg=ROOT/'state/cold_drive.conf'
    private_config=cfg.is_file() and not cfg.is_symlink() and (cfg.stat().st_mode & 0o777)==0o600
    catalog=ROOT/'state/cold_drive_catalog.json'
    catalog_present=catalog.is_file() and not catalog.is_symlink()
    disk=shutil.disk_usage(ROOT)
    shm=shutil.disk_usage('/dev/shm')
    return {'verified':True,'rclone_installed':installed,'dedicated_config_present':private_config,
            'catalog_present':catalog_present,'disk_free_bytes':disk.free,'shm_free_bytes':shm.free,
            'scope':'STORAGE_INVENTORY_ONLY','bytes_evicted':0,
            'blockers':([] if installed and private_config and catalog_present else
                        ['OWNER_PC_OAUTH_AND_TWO_VERIFIED_COPIES_REQUIRED'])}

def downloads():
    manifest=read_json(ROOT/'config/owner_download_manifest.json')
    versions=metadata()
    components=[]
    for row in manifest.get('components',[]):
        package=row.get('package')
        components.append({'id':row.get('id',row.get('name')),'decision':row.get('decision',row.get('state')),
                           'package':package,'installed_version':versions.get(package) if package else None,
                           'owner_executor':row.get('owner_executor')})
    return {'verified':True,'manifest_sha256':digest(ROOT/'config/owner_download_manifest.json'),
            'components':components,'scope':'RECONCILIATION_ONLY','downloaded_bytes':0,
            'blockers':['LARGE_WEIGHTS_REQUIRE_VERIFIED_COLD_COPY_AND_SPACE_ADMISSION']}

HANDLERS=dict(zip(TASKS,(training_stack,dispatcher,chat,memory,storage,downloads)))

def run_component_task(task):
    task_id=task.get('id')
    if task_id not in HANDLERS:return False,{'verified':False,'error':'UNKNOWN_OWNER_COMPONENT'}
    started=time.time()
    try:
        evidence=HANDLERS[task_id]()
        success=evidence.get('verified') is True
        receipt={'schema':'NOX_OWNER_COMPONENT_V1','schema_version':1,'task_id':task_id,
                 'success':success,'verified':success,'started_at':started,'finished_at':time.time(),
                 'worker':task.get('claimed_by',task.get('executor')),'pid':os.getpid(),
                 'source_sha256':digest(__file__),'evidence':evidence}
    except Exception as exc:
        success=False
        receipt={'schema':'NOX_OWNER_COMPONENT_V1','schema_version':1,'task_id':task_id,
                 'success':False,'verified':False,'started_at':started,'finished_at':time.time(),
                 'error':type(exc).__name__}
    path=ROOT/'state/owner_components'/(task_id+'.json')
    atomic(path,receipt)
    return success,{'schema':'NOX_OWNER_COMPONENT_V1','schema_version':1,'task_id':task_id,
                    'verified':success,'success':success,'receipt_path':str(path),
                    'receipt_sha256':digest(path),'scope':receipt.get('evidence',{}).get('scope'),
                    'blockers':receipt.get('evidence',{}).get('blockers',[])}

def queue_tasks():
    titles=('Проверить оптимизированный стек обучения','Проверить шесть исполнителей',
            'Проверить здоровье действующего чата','Проверить действующую память S03',
            'Проверить перенос и ресурсы хранения','Актуализировать установленные зависимости')
    return [{'id':task_id,'class':'owner_order','priority':0,'deps':[],
             'handler':'owner_component','title':title,'status':'pending','lane':'owner_order',
             'locks':[],'retries':0,'max_retries':2,'timeout_sec':90,
             'source':'owner_60509551_task_boost_20261116'} for task_id,title in zip(TASKS,titles)]

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('task',choices=TASKS)
    args=parser.parse_args();ok,result=run_component_task({'id':args.task})
    print(json.dumps(result,ensure_ascii=False));raise SystemExit(0 if ok else 2)
