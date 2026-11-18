#!/usr/bin/env python3
"""Append one reviewed 1A02 plan to the existing native catalog, without restart.

The owner maintenance lease prevents admissions during the config CAS. Exact
1A03 queue/claim/S03/source evidence is required. The existing native dispatcher
owns admission and execution; this entry never writes its queue or source tree.
"""
from __future__ import annotations
import base64
import contextlib
import copy
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import time

ROOT=Path('/root/nox')
SCHEMA='NOX_PROJECT_CATALOG_APPEND_SPEC_V1'
CONFIG='config/owner_native_subagents.json'
STATE='state/dispatcher/state.json'
STATUS='status/agents_t856u.json'
HANDLER='owner_native_project_work'
SHA=re.compile(r'^[0-9a-f]{64}$')
ID=re.compile(r'^[A-Za-z0-9_.:-]{1,128}$')
SPEC={}
try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}

class Hold(RuntimeError):pass

def require(value,code):
    if not value:raise Hold('HOLD_PROJECT_CATALOG_APPEND_'+code)

def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def digest(raw):return hashlib.sha256(raw).hexdigest()

def plain(path):
    path=Path(path)
    require(path.is_absolute() and not any(p.is_symlink() for p in (path,*path.parents)),'PATH')
    return path

def identity(info):
    return tuple(getattr(info,key) for key in ('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns'))

def read(path,limit=2*1024*1024):
    path=plain(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size<=limit,'FILE_BOUND')
        raw=stream.read(limit+1);after=os.fstat(stream.fileno())
    require(len(raw)<=limit and identity(before)==identity(after),'FILE_CHANGED')
    return raw,after

def document(path,limit=2*1024*1024):
    raw,info=read(path,limit);value=json.loads(raw)
    require(isinstance(value,dict),'DOCUMENT')
    return value,raw,info

def atomic(path,raw,mode=0o600):
    path=plain(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,name=tempfile.mkstemp(prefix='.nox-catalog-',dir=path.parent)
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'wb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
        os.replace(name,path)
        parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(parent)
        finally:os.close(parent)
    finally:
        if os.path.exists(name):os.unlink(name)

def config_cas(path,old,old_info,new):
    current,info=read(path)
    require(current==old and identity(info)==identity(old_info),'CONFIG_CAS_CHANGED')
    atomic(path,new)
    require(read(path)[0]==new,'CONFIG_READBACK')

def stop_clear(root):
    names=('STOP','STOP.flag','stop.flag','.stop','program/STOP','state/STOP',
           'state/STOP.flag','state/OWNER_MAINTENANCE.flag')
    return not any(path.exists() or path.is_symlink() for path in
        [*(Path(root)/name for name in names),Path('/workspace/NOX_STOP')])

def process(pid):
    if type(pid) is not int or pid<=1:return None
    try:
        fields=Path('/proc',str(pid),'stat').read_text().rsplit(') ',1)[1].split()
        if fields[0] not in ('R','S','D','I'):return None
        return {'pid':pid,'start_ticks':int(fields[19]),'ppid':int(fields[1])}
    except (OSError,ValueError,IndexError):return None

def process_guard(specification):
    director=specification['expected_director'];found=process(director['pid'])
    require(found and found['start_ticks']==director['start_ticks'],'DIRECTOR_CHANGED')
    expected=specification['expected_workers']
    require(isinstance(expected,list) and len(expected)==3 and len({x['pid'] for x in expected})==3,'WORKER_PINS')
    rows=[]
    for worker in expected:
        observed=process(worker['pid'])
        require(observed and observed['start_ticks']==worker['start_ticks']
                and observed['ppid']==found['pid'],'WORKER_CHANGED')
        rows.append(observed)
    return {'director':found,'workers':rows}

def idle_status(root,specification):
    deadline=time.monotonic()+4
    expected={(x['pid'],x['start_ticks']) for x in specification['expected_workers']}
    while True:
        data,_,_=document(Path(root)/STATUS)
        native=data.get('native_subexecutors') or {};director=native.get('director') or {}
        workers=native.get('workers') or []
        if (native.get('mode')=='NORMAL' and native.get('target')==3
                and director.get('pid')==specification['expected_director']['pid']
                and director.get('process_starttime')==specification['expected_director']['start_ticks']
                and type(native.get('observed_at')) in (int,float)
                and 0<=time.time()-native['observed_at']<=15
                and len(workers)==3 and {(x.get('pid'),x.get('process_starttime')) for x in workers}==expected
                and all(x.get('current_task') is None and type(x.get('heartbeat_at')) in (int,float)
                        and 0<=time.time()-x['heartbeat_at']<=20 for x in workers)):
            return {'observed_at':native['observed_at'],'workers':[{
                key:x.get(key) for key in ('pid','ppid','process_starttime','role','heartbeat_at','current_task')} for x in workers]}
        require(time.monotonic()<deadline,'IDLE_NATIVE_STATUS_NOT_VERIFIED')
        time.sleep(.2)

def decode_assets(bundle,specification):
    pins=specification.get('assets')
    require(isinstance(pins,dict) and 1<=len(pins)<=40 and set(bundle)==set(pins),'ASSET_SET')
    result={};total=0
    for name,pin in pins.items():
        require(isinstance(name,str) and '/' not in name and SHA.fullmatch(str(pin)),'ASSET_PIN')
        value=bundle[name];require(isinstance(value,str) and len(value)<=3*1024*1024,'ASSET_BOUND')
        raw=base64.b64decode(value,validate=True);total+=len(raw)
        require(len(raw)<=2*1024*1024 and total<=8*1024*1024 and digest(raw)==pin,'ASSET_DIGEST')
        result[name]=raw
    return result

def exact_s03(root,receipt):
    path=plain(Path(root)/'kb/knowledge.sqlite')
    require(stat.S_ISREG(path.stat().st_mode),'S03_PATH')
    sha=digest(encoded(receipt))
    text='NOX native job '+receipt['job_id']+' '+receipt['phase']+' receipt_sha256 '+sha
    with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.2)) as conn:
        conn.execute('PRAGMA query_only=ON');deadline=time.monotonic()+2
        conn.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
        rows=conn.execute("SELECT id,meta,sha256 FROM s03_items WHERE segment='M2' AND text=? AND provenance=? LIMIT 2",
                          (text,'owner_native_subagents')).fetchall()
    require(len(rows)==1 and rows[0][2]==digest(('M2|'+text).encode())
            and json.loads(rows[0][1]).get('receipt')==receipt,'S03_EXACT_RECEIPT')
    return {'verified':True,'s03_item_id':rows[0][0],'receipt_sha256':sha}

def predecessor_proof(root,state,config,specification,executor):
    required=specification['required_task'];tid=required['id']
    require(isinstance(tid,str) and tid.startswith('1A03.') and ID.fullmatch(tid),'REQUIRED_TASK_SCOPE')
    row=state['tasks'].get(tid)
    require(isinstance(row,dict) and row.get('status')=='done' and row.get('handler')==HANDLER
            and row.get('parent_task_id')=='1A03','REQUIRED_TASK_NOT_DONE')
    result=row.get('result') or {};receipt=result.get('receipt') or {};claim=row.get('owner_claim') or {}
    pin=digest(encoded(receipt))
    require(SHA.fullmatch(str(required.get('receipt_sha256'))) and pin==required['receipt_sha256']
            and result.get('receipt_sha256')==pin and result.get('verified') is True
            and receipt.get('task_id')==tid and receipt.get('claim')==claim
            and claim.get('pid')==specification['expected_director']['pid']
            and re.fullmatch(r'[0-9a-f]{24}',str(claim.get('nonce','')))
            and receipt.get('source_sha256')==specification['expected_callback_sha256']
            and receipt.get('phase')=='PROJECT_WORK_INTEGRATED_ORIGINAL_NOT_ACCEPTED'
            and receipt.get('original_task_accepted') is False,'REQUIRED_TASK_RECEIPT')
    event=receipt.get('worker_result') or {};evidence=event.get('project_evidence') or {};tests=evidence.get('tests') or {}
    planner=event.get('planner_receipt') or {}
    require(evidence.get('state')=='INTEGRATED' and evidence.get('integration_verified') is True
            and evidence.get('task_id')==tid and evidence.get('claim')==claim['nonce']
            and digest(encoded(evidence))==event.get('project_evidence_sha256')
            and tests.get('passed') is True and tests.get('failures')==0 and tests.get('errors')==0 and tests.get('skipped')==0
            and evidence.get('trusted_tests_unchanged') is True
            and planner.get('model_called') is True and type(planner.get('model_turns')) is int
            and planner['model_turns']>=1,'REQUIRED_MODEL_INTEGRATION')
    reference=event.get('reference')
    require(isinstance(reference,dict) and reference.get('plan_sha256')==receipt.get('plan_sha256')
            and reference.get('contract_sha256')==required.get('contract_sha256'),'REQUIRED_GENERATED_PLAN')
    plan=executor.load_plan(reference,config['project_executor'])
    require(plan['task_id']==tid and plan.get('review_origin')=='MODEL_CANDIDATE'
            and plan['root_id']=='NOX_PROJECT_SOURCE','REQUIRED_GENERATED_PLAN_IDENTITY')
    with executor.tree(config['project_executor']['roots']['NOX_PROJECT_SOURCE']['path']) as handle:
        executor._check_source(handle,plan,integrated=True)
    proof=exact_s03(root,receipt)
    return {'task_id':tid,'receipt_sha256':pin,'s03':proof,'plan_sha256':reference['plan_sha256'],
            'source_postimages_verified':True,'model_turns':planner['model_turns']}

def load_executor(root,config,specification):
    pins=config.get('module_pins') or {}
    require(1<=len(pins)<=32 and pins.get('owner_subagent_dispatcher.py')==specification['expected_callback_sha256'],
            'CURRENT_CALLBACK_PIN')
    for name,pin in pins.items():
        require(re.fullmatch(r'owner_[a-z0-9_]+\.py',name) and SHA.fullmatch(str(pin)),'MODULE_PIN_SCOPE')
        require(digest(read(Path(root)/'scripts'/name)[0])==pin,'MODULE_SOURCE_CHANGED')
    require(digest(read(Path(root)/'scripts/owner_subagent_dispatcher.py')[0])==specification['expected_callback_sha256'],
            'CALLBACK_SOURCE_CHANGED')
    source=Path(root)/'scripts/owner_project_executor.py'
    spec=importlib.util.spec_from_file_location('_nox_approved_catalog_append_executor',source)
    require(spec is not None and spec.loader is not None,'EXECUTOR_LOADER')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.validate_config(config['project_executor'])
    require(config['project_executor']['package_root']==str(Path(root)/'state/dispatcher/project_executor/package')
            and config['project_executor']['roots']['NOX_PROJECT_SOURCE']['path']==str(Path(root)/'projects/owner_executor/source_workspace'),
            'PROJECT_PATH_SCOPE')
    return module

def compose(config,row,plan,plan_pin):
    require(config.get('schema')=='NOX_NATIVE_SUBAGENT_BINDING_V1' and config.get('instance_id')==60509551
            and config.get('execution_mode')=='NATIVE_PROJECT_V1' and config.get('owner_authorized') is True
            and config.get('mode')=='NORMAL' and config.get('target')==3,'CONFIG_SCOPE')
    old=config.get('catalog')
    require(isinstance(old,dict) and old.get('schema')=='NOX_AUTONOMY_PROCESS_POOL_V1'
            and digest(encoded(old))==config.get('catalog_sha256') and isinstance(old.get('tasks'),list),'CATALOG_HASH')
    required={'id','handler','deps','resource','source_sha256','params','queue_id'}
    require(isinstance(row,dict) and required<=set(row)
            and not set(row)-(required|{'priority','estimated_cost','title'}),'NEW_CATALOG_FIELDS')
    require(isinstance(row.get('id'),str) and ID.fullmatch(row['id'])
            and row['id'].startswith('1A02.') and SHA.fullmatch(str(plan_pin)),'NEW_CATALOG_IDENTITY')
    cost=row.get('estimated_cost',1);title=row.get('title',row['id'])
    require(isinstance(row.get('priority','P2'),str) and row.get('priority','P2') in ('P0','P1','P2','P3')
            and type(cost) in (int,float) and math.isfinite(cost) and 0<cost<=100000
            and isinstance(title,str) and 1<=len(title)<=180,'NEW_CATALOG_PRESENTATION')
    require(isinstance(row['deps'],list) and all(isinstance(x,str) and ID.fullmatch(x) for x in row['deps'])
            and len(set(row['deps']))==len(row['deps']) and row['id'] not in row['deps'],'NEW_CATALOG_DEPENDENCIES')
    known={x['id'] for x in old['tasks']}
    require(len(known)==len(old['tasks']) and row['id'] not in known,'TASK_ALREADY_CATALOGED')
    require(plan.get('parent_task_id')=='1A02' and plan.get('root_id')=='NOX_PROJECT_SOURCE'
            and plan.get('review_origin')=='OWNER_REVIEWED' and plan.get('original_task_accepted') is False,
            'NEW_PLAN_SCOPE')
    require(row.get('id')==plan['task_id'] and row.get('handler')==HANDLER
            and row.get('queue_id')==plan['queue_id']=='Q1_RUNTIME_CHAT' and row.get('resource')=='CPU_LIGHT'
            and row.get('source_sha256')==config['module_pins']['owner_subagent_dispatcher.py']
            and row.get('params')=={'parent_task_id':'1A02','plan_sha256':plan_pin}
            and isinstance(row.get('deps'),list) and all(x in known for x in row['deps']), 'NEW_CATALOG_SCOPE')
    result=copy.deepcopy(config);result['catalog']['tasks'].append(copy.deepcopy(row))
    result['catalog_sha256']=digest(encoded(result['catalog']))
    require({k:v for k,v in result.items() if k not in ('catalog','catalog_sha256')}==
            {k:v for k,v in config.items() if k not in ('catalog','catalog_sha256')}
            and result['catalog']['tasks'][:-1]==old['tasks'],'UNRELATED_CONFIG_CHANGE')
    return result

def append(bundle,specification,root=ROOT):
    require(specification.get('schema')==SCHEMA,'SPEC_SCHEMA')
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    require(re.fullmatch(r'[0-9]{1,24}',request) and re.fullmatch(r'[0-9a-f]{40}',source),'OWNER_CONTEXT')
    assets=decode_assets(bundle,specification);root=plain(root);config_path=root/CONFIG
    require(stop_clear(root),'OWNER_STOP');process_guard(specification);idle_status(root,specification)
    lockpath=plain(root/'state/owner_maintenance.lock');fd=os.open(lockpath,os.O_RDONLY|os.O_NOFOLLOW)
    receipt={'schema':'NOX_PROJECT_CATALOG_APPEND_RECEIPT_V1','request':request,'source_sha':source,
             'state':'PREFLIGHT','native_queue_writes':0,'source_tree_writes':0,'supervisor_calls':0,
             'original_tasks_accepted':0,'started_at':time.time()}
    old=new=None;attempted=False
    def lease_guard():
        info=os.fstat(fd);named=lockpath.stat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and info.st_nlink==1
                and not info.st_mode&0o022 and (info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'LEASE_PATH_CHANGED')
    def guard():
        lease_guard();require(stop_clear(root),'OWNER_STOP_CHANGED');process_guard(specification)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise Hold('HOLD_PROJECT_CATALOG_APPEND_MAINTENANCE_BUSY') from exc
        guard();config,old,info=document(config_path)
        require(SHA.fullmatch(str(specification.get('expected_config_sha256')))
                and digest(old)==specification['expected_config_sha256'],'CONFIG_PREIMAGE')
        require(info.st_uid==os.geteuid() and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600,'CONFIG_OWNER_MODE')
        executor=load_executor(root,config,specification)
        state,_,_=document(root/STATE,16*1024*1024)
        require(isinstance(state.get('tasks'),dict),'QUEUE_SCHEMA')
        proof=predecessor_proof(root,state,config,specification,executor)
        plan_raw=assets[specification['plan_asset']];plan=json.loads(plan_raw)
        require(encoded(plan)==plan_raw,'PLAN_CANONICAL');plan_pin=digest(plan_raw)
        row=specification['catalog_row'];require(row.get('deps')==[proof['task_id']],'PREDECESSOR_DEPENDENCY')
        require(row.get('id') not in state['tasks'],'TASK_ALREADY_IN_QUEUE')
        proposed=compose(config,row,plan,plan_pin);new=encoded(proposed)
        executor.validate_plan(plan,config['project_executor'])
        payloads={pin:assets[name] for pin,name in specification['payload_assets'].items()}
        with executor.tree(config['project_executor']['roots']['NOX_PROJECT_SOURCE']['path']) as handle:
            executor._check_source(handle,plan)
            guard()
            reference=executor.materialize_plan(plan,payloads,config['project_executor'])
            require(reference=={'plan_sha256':plan_pin},'STAGED_PLAN_REFERENCE')
            executor._check_source(handle,plan)
            latest,_,_=document(root/STATE,16*1024*1024)
            require(latest['tasks'].get(proof['task_id'])==state['tasks'][proof['task_id']]
                    and row['id'] not in latest['tasks'],'QUEUE_PREDECESSOR_CHANGED')
            guard();idle_status(root,specification)
            attempted=True;config_cas(config_path,old,info,new)
            guard()
        receipt.update(state='CATALOG_APPENDED_ADMISSION_PENDING',task_id=row['id'],plan_sha256=plan_pin,
            predecessor=proof,old_config_sha256=digest(old),new_config_sha256=digest(new),
            old_catalog_rows=len(config['catalog']['tasks']),new_catalog_rows=len(proposed['catalog']['tasks']),
            preserved_old_catalog=True,unchanged_owner_metadata=True,processes=process_guard(specification))
    except BaseException as exc:
        text=str(exc)
        receipt['state']=text if re.fullmatch(r'HOLD_[A-Z0-9_]{1,200}',text) else 'HOLD_PROJECT_CATALOG_APPEND_'+type(exc).__name__
        if attempted and old is not None and new is not None:
            try:
                lease_guard();current,current_info=read(config_path)
                if current==new:config_cas(config_path,new,current_info,old);receipt['rollback']='OWN_CONFIG_RESTORED_BEFORE_LEASE_RELEASE'
                elif current==old:receipt['rollback']='PREIMAGE_ALREADY_PRESENT'
                else:receipt['rollback']='FOREIGN_CONFIG_PRESERVED'
            except Exception:receipt['rollback']='UNVERIFIED_NO_FOREIGN_OVERWRITE'
        raise
    finally:
        os.close(fd);receipt['finished_at']=time.time()
        destination=root/'state/dispatcher/project_catalog_append'/('append_'+request+'.json')
        atomic(destination,encoded(receipt))
        if receipt['state']!='CATALOG_APPENDED_ADMISSION_PENDING':
            print('NOX_MAINT_PROJECT_CATALOG_APPEND='+encoded(receipt).decode(),flush=True)
    receipt['same_processes_after_release']=process_guard(specification)==receipt['processes']
    atomic(root/'state/dispatcher/project_catalog_append'/('append_'+request+'.json'),encoded(receipt))
    require(receipt['same_processes_after_release'],'PROCESS_CHANGED_AFTER_RELEASE')
    print('NOX_MAINT_PROJECT_CATALOG_APPEND='+encoded(receipt).decode(),flush=True)
    return receipt

def main():
    append(BUNDLE,SPEC)
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)

if __name__=='__main__':main()
