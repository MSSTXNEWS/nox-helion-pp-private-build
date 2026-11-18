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
