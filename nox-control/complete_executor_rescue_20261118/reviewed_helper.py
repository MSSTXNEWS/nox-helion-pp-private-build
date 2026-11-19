#!/usr/bin/env python3
"""Append one scoped owner-reviewed rescue or follow-up, without restart.

FAILED_MODEL_RESCUE requires the exact unintegrated failed 1A03 model receipt.
VERIFIED_REVIEWED_FOLLOWUP requires its owner-reviewed rescue to be integrated.
Both preserve the old catalog and worker generation. The native dispatcher owns
admission and execution; this entry never writes its queue or project source.
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
SCHEMA='NOX_REVIEWED_PROJECT_CATALOG_APPEND_SPEC_V1'
CONFIG='config/owner_native_subagents.json'
STATE='state/dispatcher/state.json'
STATUS='status/agents_t856u.json'
HANDLER='owner_native_project_work'
SHA=re.compile(r'^[0-9a-f]{64}$')
ID=re.compile(r'^[A-Za-z0-9_.:-]{1,128}$')
FAILED_MODEL_RESCUE='FAILED_MODEL_RESCUE'
VERIFIED_REVIEWED_FOLLOWUP='VERIFIED_REVIEWED_FOLLOWUP'
FAILED_TASK='1A03.project.cursor_admission.focus_retry.20261118'
FAILED_RECEIPT='284d6284b5d088b4dcaa16250f4151ba26cad0b9f20f73bd708e9a60a097b80d'
FAILED_CONTRACT='eece310e5608fa9c633d7c75ce280541d9bec6af8a0c35815465ae82679d4ce4'
RESCUE_TASK='1A03.project.cursor_admission.owner_rescue.20261118'
BASELINE_SOURCE={
    'owner_chat_request_ledger.py':'006fc038f43682fa36d2310f2343c83a42fd28897e7debfbe0d63536ee069729',
    'native_v29_full_bridge.py':'d9ec6a8250a167d774ba5090219cfaac3ad2995ddd88228d1abe5514fc9dd791'}
SPEC={}
try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}

class Hold(RuntimeError):pass

def require(value,code):
    if not value:raise Hold('HOLD_REVIEWED_PROJECT_CATALOG_APPEND_'+code)

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

def mode_scope(specification):
    mode=specification.get('mode');required=specification.get('required_task')
    require(mode in (FAILED_MODEL_RESCUE,VERIFIED_REVIEWED_FOLLOWUP)
            and isinstance(required,dict),'GUARD_MODE')
    source=specification.get('expected_source_pins')
    require(isinstance(source,dict) and set(source)==set(BASELINE_SOURCE)
            and all(SHA.fullmatch(str(pin)) for pin in source.values()),'EXPECTED_SOURCE_PINS')
    if mode==FAILED_MODEL_RESCUE:
        require(set(required)=={'id','receipt_sha256','contract_sha256'}
                and required['id']==FAILED_TASK and required['receipt_sha256']==FAILED_RECEIPT
                and required['contract_sha256']==FAILED_CONTRACT
                and source==BASELINE_SOURCE,'FAILED_MODEL_SCOPE')
        return '1A03',[]
    require(set(required)=={'id','receipt_sha256','plan_sha256'} and required['id']==RESCUE_TASK
            and SHA.fullmatch(str(required['receipt_sha256']))
            and SHA.fullmatch(str(required['plan_sha256'])),'REVIEWED_FOLLOWUP_SCOPE')
    return '1A02',[RESCUE_TASK]

def source_pair_proof(handle,specification):
    mode_scope(specification);proof={}
    for path,pin in specification['expected_source_pins'].items():
        raw,_=handle.get(path)
        require(isinstance(raw,bytes) and digest(raw)==pin,'SOURCE_PAIR_CHANGED')
        proof[path]=pin
    handle.assert_current()
    return proof

def failed_contract(config,executor):
    contract=executor.load_contract_metadata({'contract_sha256':FAILED_CONTRACT},config['project_executor'])
    require(contract.get('task_id')==FAILED_TASK and contract.get('parent_task_id')=='1A03'
            and contract.get('root_id')=='NOX_PROJECT_SOURCE' and contract.get('queue_id')=='Q1_RUNTIME_CHAT'
            and contract.get('acceptance_scope')=='SOURCE_PATCH_TESTED'
            and contract.get('verification',{}).get('min_tests')==30,'FAILED_CONTRACT_SCOPE')
    return contract

def reviewed_plan_scope(plan,config,specification,executor,*,predecessor=False):
    parent,_=mode_scope(specification)
    if predecessor:parent='1A03'
    changes={row['path'] for row in plan.get('files',[])}
    context={row['path']:row['sha256'] for row in plan.get('context',[])}
    require(plan.get('parent_task_id')==parent and plan.get('root_id')=='NOX_PROJECT_SOURCE'
            and plan.get('review_origin')=='OWNER_REVIEWED' and plan.get('original_task_accepted') is False
            and plan.get('acceptance_scope')=='SOURCE_PATCH_TESTED' and plan.get('queue_id')=='Q1_RUNTIME_CHAT'
            and 'contract_sha256' not in plan and bool(changes) and changes<=set(BASELINE_SOURCE),'REVIEWED_PLAN_SCOPE')
    if parent=='1A03':
        contract=failed_contract(config,executor)
        require(plan.get('task_id')==RESCUE_TASK and changes==set(BASELINE_SOURCE)
                and plan['context']==contract['context'] and plan['verification']==contract['verification'],
                'RESCUE_CONTRACT_CHANGED')
    else:
        require(all(context.get(path)==pin for path,pin in specification['expected_source_pins'].items()),
                'FOLLOWUP_CONTEXT_CHANGED')

def predecessor_proof(root,state,config,specification,executor):
    mode_scope(specification);mode=specification['mode'];required=specification['required_task'];tid=required['id']
    failed=mode==FAILED_MODEL_RESCUE
    row=state['tasks'].get(tid);wanted_status='blocked' if failed else 'done'
    require(isinstance(row,dict) and row.get('status')==wanted_status and row.get('handler')==HANDLER
            and row.get('parent_task_id')=='1A03' and row.get('queue_id')=='Q1_RUNTIME_CHAT','PREDECESSOR_STATUS')
    result=row.get('result') or {};receipt=result.get('receipt') or {};claim=row.get('owner_claim') or {}
    pin=digest(encoded(receipt));wanted_phase='PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED' if failed else 'PROJECT_WORK_INTEGRATED_ORIGINAL_NOT_ACCEPTED'
    require(SHA.fullmatch(str(required.get('receipt_sha256'))) and pin==required['receipt_sha256']
            and result.get('receipt_sha256')==pin and result.get('verified') is True
            and receipt.get('task_id')==tid and receipt.get('parent_task_id')=='1A03'
            and receipt.get('queue_id')=='Q1_RUNTIME_CHAT' and receipt.get('claim')==claim
            and claim.get('pid')==specification['expected_director']['pid']
            and re.fullmatch(r'[0-9a-f]{24}',str(claim.get('nonce','')))
            and receipt.get('execution_claim')==claim['nonce']
            and receipt.get('source_sha256')==specification['expected_callback_sha256']
            and (row.get('params') or {}).get('source_sha256')==specification['expected_callback_sha256']
            and receipt.get('phase')==wanted_phase and receipt.get('scope')=='SOURCE_PATCH_TESTED'
            and receipt.get('live_service_deployed') is False
            and receipt.get('original_task_accepted') is False,'PREDECESSOR_RECEIPT')
    event=receipt.get('worker_result') or {};evidence=event.get('project_evidence') or {}
    worker=evidence.get('worker') or {}
    expected={(x['pid'],x['start_ticks']) for x in specification['expected_workers']}
    require(evidence.get('schema')=='NOX_PROJECT_EXECUTION_EVIDENCE_V1'
            and evidence.get('task_id')==tid and evidence.get('parent_task_id')=='1A03'
            and evidence.get('queue_id')=='Q1_RUNTIME_CHAT' and evidence.get('root_id')=='NOX_PROJECT_SOURCE'
            and evidence.get('acceptance_scope')=='SOURCE_PATCH_TESTED' and evidence.get('original_task_accepted') is False
            and evidence.get('claim')==claim['nonce']
            and digest(encoded(evidence))==event.get('project_evidence_sha256')
            and (worker.get('pid'),worker.get('process_starttime')) in expected
            and worker.get('ppid')==specification['expected_director']['pid']
            and event.get('pid')==worker['pid'] and event.get('id')==tid and event.get('kind')=='RESULT',
            'PREDECESSOR_WORKER_EVIDENCE')
    proof=exact_s03(root,receipt)
    if failed:
        planner=event.get('planner_receipt') or {};params=row.get('params') or {}
        require(evidence.get('state')=='BLOCKED_PLANNER' and evidence.get('reason')=='PLANNER_TURN_BUDGET_EXHAUSTED'
                and evidence.get('project_source_changed') is False and evidence.get('model_commands_executed') is False
                and evidence.get('plan_sha256') is None and receipt.get('plan_sha256') is None
                and receipt.get('project_source_changed') is False and params.get('plan_sha256') is None
                and evidence.get('contract_sha256')==params.get('contract_sha256')==required['contract_sha256']
                and planner.get('contract_sha256')==required['contract_sha256']
                and planner.get('task_id')==tid and planner.get('state')=='PLANNER_TURN_BUDGET_EXHAUSTED'
                and planner.get('original_task_accepted') is False
                and event.get('reference')=={'contract_sha256':required['contract_sha256']},'FAILED_MODEL_NOT_UNINTEGRATED')
        contract=failed_contract(config,executor)
        with executor.tree(config['project_executor']['roots']['NOX_PROJECT_SOURCE']['path']) as handle:
            pair=source_pair_proof(handle,specification)
            executor._check_source(handle,{'context':contract['context'],'files':[]})
        return {'task_id':tid,'mode':mode,'receipt_sha256':pin,'s03':proof,
                'contract_sha256':required['contract_sha256'],'source_pins':pair,
                'failed_model_source_unchanged':True,'worker':worker}
    plan_pin=required['plan_sha256'];params=row.get('params') or {};tests=evidence.get('tests') or {}
    require(params.get('plan_sha256')==receipt.get('plan_sha256')==evidence.get('plan_sha256')==plan_pin
            and params.get('contract_sha256') is None,'PREDECESSOR_REVIEWED_PLAN_PIN')
    # Owner-reviewed events have no generated-model reference; use the durable plan pin.
    plan=executor.load_plan({'plan_sha256':plan_pin},config['project_executor'])
    reviewed_plan_scope(plan,config,specification,executor,predecessor=True)
    require(evidence.get('state')=='INTEGRATED' and evidence.get('integration_verified') is True
            and evidence.get('project_source_changed') is True and receipt.get('project_source_changed') is True
            and evidence.get('trusted_tests_unchanged') is True
            and evidence.get('postimages')=={row['path']:row['after_sha256'] for row in plan['files']}
            and evidence.get('tests_sha256')==digest(encoded(tests))
            and tests.get('completed') is True and tests.get('passed') is True
            and type(tests.get('tests_run')) is int and tests['tests_run']>=plan['verification']['min_tests']
            and tests.get('modules')==plan['verification']['modules']
            and tests.get('failures')==0 and tests.get('errors')==0 and tests.get('skipped')==0,
            'PREDECESSOR_REVIEWED_INTEGRATION')
    sandbox=tests.get('sandbox') or {}
    require(sandbox.get('uid')==65534 and sandbox.get('gid')==65534
            and all(sandbox.get(key) is True for key in
                    ('exec_denied','fork_denied','network_denied','host_path_hidden','no_new_privs','seccomp_filter')),
            'PREDECESSOR_SANDBOX_PROOF')
    with executor.tree(config['project_executor']['roots']['NOX_PROJECT_SOURCE']['path']) as handle:
        executor._check_source(handle,plan,integrated=True)
        pair=source_pair_proof(handle,specification)
    return {'task_id':tid,'mode':mode,'receipt_sha256':pin,'s03':proof,'plan_sha256':plan_pin,
            'source_postimages_verified':True,'source_pins':pair,'tests_run':tests['tests_run'],'worker':worker}

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
    spec=importlib.util.spec_from_file_location('_nox_approved_reviewed_catalog_append_executor',source)
    require(spec is not None and spec.loader is not None,'EXECUTOR_LOADER')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.validate_config(config['project_executor'])
    require(config['project_executor']['package_root']==str(Path(root)/'state/dispatcher/project_executor/package')
            and config['project_executor']['roots']['NOX_PROJECT_SOURCE']['path']==str(Path(root)/'projects/owner_executor/source_workspace'),
            'PROJECT_PATH_SCOPE')
    return module

def compose(config,row,plan,plan_pin,specification):
    parent,dependencies=mode_scope(specification)
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
            and row['id'].startswith(parent+'.') and SHA.fullmatch(str(plan_pin))
            and (parent!='1A03' or row['id']==RESCUE_TASK),'NEW_CATALOG_IDENTITY')
    cost=row.get('estimated_cost',1);title=row.get('title',row['id'])
    require(isinstance(row.get('priority','P2'),str) and row.get('priority','P2') in ('P0','P1','P2','P3')
            and type(cost) in (int,float) and math.isfinite(cost) and 0<cost<=100000
            and isinstance(title,str) and 1<=len(title)<=180,'NEW_CATALOG_PRESENTATION')
    require(isinstance(row['deps'],list) and all(isinstance(x,str) and ID.fullmatch(x) for x in row['deps'])
            and len(set(row['deps']))==len(row['deps']) and row['id'] not in row['deps'],'NEW_CATALOG_DEPENDENCIES')
    known={x['id'] for x in old['tasks']}
    require(len(known)==len(old['tasks']) and row['id'] not in known,'TASK_ALREADY_CATALOGED')
    require(plan.get('parent_task_id')==parent and plan.get('root_id')=='NOX_PROJECT_SOURCE'
            and plan.get('review_origin')=='OWNER_REVIEWED' and plan.get('original_task_accepted') is False,
            'NEW_PLAN_SCOPE')
    require(row.get('id')==plan['task_id'] and row.get('handler')==HANDLER
            and row.get('queue_id')==plan['queue_id']=='Q1_RUNTIME_CHAT' and row.get('resource')=='CPU_LIGHT'
            and row.get('source_sha256')==config['module_pins']['owner_subagent_dispatcher.py']
            and row.get('params')=={'parent_task_id':parent,'plan_sha256':plan_pin}
            and row.get('deps')==dependencies and all(x in known for x in row['deps']), 'NEW_CATALOG_SCOPE')
    result=copy.deepcopy(config);result['catalog']['tasks'].append(copy.deepcopy(row))
    result['catalog_sha256']=digest(encoded(result['catalog']))
    require({k:v for k,v in result.items() if k not in ('catalog','catalog_sha256')}==
            {k:v for k,v in config.items() if k not in ('catalog','catalog_sha256')}
            and result['catalog']['tasks'][:-1]==old['tasks'],'UNRELATED_CONFIG_CHANGE')
    return result

def append(bundle,specification,root=ROOT):
    require(specification.get('schema')==SCHEMA,'SPEC_SCHEMA')
    mode_scope(specification)
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    require(re.fullmatch(r'[0-9]{1,24}',request) and re.fullmatch(r'[0-9a-f]{40}',source),'OWNER_CONTEXT')
    assets=decode_assets(bundle,specification);root=plain(root);config_path=root/CONFIG
    require(stop_clear(root),'OWNER_STOP');process_guard(specification);idle_status(root,specification)
    lockpath=plain(root/'state/owner_maintenance.lock');fd=os.open(lockpath,os.O_RDONLY|os.O_NOFOLLOW)
    receipt={'schema':'NOX_REVIEWED_PROJECT_CATALOG_APPEND_RECEIPT_V1','request':request,'source_sha':source,
             'mode':specification['mode'],
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
        except BlockingIOError as exc:raise Hold('HOLD_REVIEWED_PROJECT_CATALOG_APPEND_MAINTENANCE_BUSY') from exc
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
        row=specification['catalog_row']
        require(row.get('deps')==mode_scope(specification)[1],'PREDECESSOR_DEPENDENCY')
        require(row.get('id') not in state['tasks'],'TASK_ALREADY_IN_QUEUE')
        executor.validate_plan(plan,config['project_executor'])
        reviewed_plan_scope(plan,config,specification,executor)
        proposed=compose(config,row,plan,plan_pin,specification);new=encoded(proposed)
        payloads={pin:assets[name] for pin,name in specification['payload_assets'].items()}
        with executor.tree(config['project_executor']['roots']['NOX_PROJECT_SOURCE']['path']) as handle:
            executor._check_source(handle,plan)
            source_pair_proof(handle,specification)
            guard()
            reference=executor.materialize_plan(plan,payloads,config['project_executor'])
            require(reference=={'plan_sha256':plan_pin},'STAGED_PLAN_REFERENCE')
            executor._check_source(handle,plan)
            source_pair_proof(handle,specification)
            latest,_,_=document(root/STATE,16*1024*1024)
            require(latest['tasks'].get(proof['task_id'])==state['tasks'][proof['task_id']]
                    and row['id'] not in latest['tasks'],'QUEUE_PREDECESSOR_CHANGED')
            exact_s03(root,latest['tasks'][proof['task_id']]['result']['receipt'])
            guard();idle_status(root,specification)
            attempted=True;config_cas(config_path,old,info,new)
            guard()
        receipt.update(state='CATALOG_APPENDED_ADMISSION_PENDING',task_id=row['id'],plan_sha256=plan_pin,
            predecessor=proof,old_config_sha256=digest(old),new_config_sha256=digest(new),
            old_catalog_rows=len(config['catalog']['tasks']),new_catalog_rows=len(proposed['catalog']['tasks']),
            preserved_old_catalog=True,unchanged_owner_metadata=True,processes=process_guard(specification))
    except BaseException as exc:
        text=str(exc)
        receipt['state']=text if re.fullmatch(r'HOLD_[A-Z0-9_]{1,200}',text) else 'HOLD_REVIEWED_PROJECT_CATALOG_APPEND_'+type(exc).__name__
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
        destination=root/'state/dispatcher/reviewed_project_catalog_append'/('append_'+request+'.json')
        atomic(destination,encoded(receipt))
        if receipt['state']!='CATALOG_APPENDED_ADMISSION_PENDING':
            print('NOX_MAINT_REVIEWED_PROJECT_CATALOG_APPEND='+encoded(receipt).decode(),flush=True)
    try:
        receipt['same_processes_after_release']=process_guard(specification)==receipt['processes']
        require(receipt['same_processes_after_release'],'PROCESS_CHANGED_AFTER_RELEASE')
    except BaseException:
        receipt.update(state='HOLD_REVIEWED_PROJECT_CATALOG_APPEND_PROCESS_CHANGED_AFTER_RELEASE',
                       same_processes_after_release=False,rollback='NO_ROLLBACK_AFTER_ADMISSION_RELEASE')
        atomic(root/'state/dispatcher/reviewed_project_catalog_append'/('append_'+request+'.json'),encoded(receipt))
        print('NOX_MAINT_REVIEWED_PROJECT_CATALOG_APPEND='+encoded(receipt).decode(),flush=True)
        raise
    atomic(root/'state/dispatcher/reviewed_project_catalog_append'/('append_'+request+'.json'),encoded(receipt))
    print('NOX_MAINT_REVIEWED_PROJECT_CATALOG_APPEND='+encoded(receipt).decode(),flush=True)
    return receipt

def main():
    append(BUNDLE,SPEC)
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)

if __name__=='__main__':main()
