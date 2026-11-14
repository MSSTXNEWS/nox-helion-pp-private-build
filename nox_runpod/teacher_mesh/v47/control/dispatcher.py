"""ONE NOX: 60 logical jobs through the EXISTING OneHost queue; no new worker daemon.

Only trusted native ports can enqueue or verify jobs. Every result distinguishes
SOURCE_PLANNED from NATIVE_QUEUE_ACCEPTED/READBACK and from real completion.
User/LLM text and external sources never authorize raw shell or self-deployment.
"""
from __future__ import annotations
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
import json, re

HERE=Path(__file__).resolve().parent
SHA=re.compile(r'^[0-9a-f]{64}$')
TASKID=re.compile(r'^NOX-V46-(0[1-9]|[1-5][0-9]|60)$')
LANES=frozenset({'CORE','MEMORY','FORGE','SKILLS','TEACHERS','WEB_QA'})


def canonical_hash(data:dict)->str:
    return sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def load_matrix(path:Path|None=None)->dict:
    matrix=json.loads((path or HERE/'TASKS_60_V46.json').read_text(encoding='utf-8'))
    if matrix.get('schema')!='NOX_V46_SIX_LANE_SIXTY_TASKS_V1':raise ValueError('HOLD_MATRIX_SCHEMA')
    tasks=matrix.get('tasks')
    if not isinstance(tasks,list) or len(tasks)!=60:raise ValueError('HOLD_MATRIX_COUNT')
    ids=set()
    for t in tasks:
        if not isinstance(t,dict) or not TASKID.fullmatch(str(t.get('task_id',''))):raise ValueError('HOLD_MATRIX_TASK_ID')
        if t['task_id'] in ids or t.get('lane') not in LANES or t.get('state')!='PLANNED_NOT_ENQUEUED':raise ValueError('HOLD_MATRIX_UNTRUSTED')
        ids.add(t['task_id'])
    for t in tasks:
        if not isinstance(t.get('depends_on'),list) or any(d not in ids or d==t['task_id'] for d in t['depends_on']):
            raise ValueError('HOLD_MATRIX_DEPENDENCY')
    return matrix


@dataclass(frozen=True)
class NativePorts:
    """Injected by authenticated OneHost ONLY; all functions must be genuine native callbacks."""
    authorize:Callable[[str],bool]
    stop:Callable[[],bool]
    state:Callable[[],Mapping]
    native_task_status:Callable[[str],Mapping]
    native_duplicate_check:Callable[[str],bool]
    approve:Callable[[str,str,Mapping],bool]
    queue_enqueue:Callable[[Mapping],Mapping]
    queue_readback:Callable[[str],Mapping]
    verify_queue_receipt:Callable[[Mapping,Mapping],bool]
    s03_audit:Callable[[Mapping],Mapping]
    s03_verify:Callable[[Mapping,Mapping],bool]


def _valid_completion(native:Mapping|None,tid:str)->bool:
    return (isinstance(native,Mapping) and native.get('task_id')==tid
      and native.get('state')=='COMPLETED' and native.get('native_verified') is True
      and isinstance(native.get('receipt_sha256'),str) and SHA.fullmatch(native['receipt_sha256']) is not None
      and native.get('independent_test_passed') is True)


def _priority(task:dict,progress:Mapping)->tuple:
    info=progress.get(task['task_id']) if isinstance(progress,Mapping) else None
    verified=(isinstance(info,Mapping) and info.get('native_verified') is True
              and isinstance(info.get('receipt_sha256'),str)
              and SHA.fullmatch(info['receipt_sha256']) is not None)
    p=info.get('percent') if verified else None
    advancing=type(p) in (int,float) and 50<=p<100
    rank={'P0':0,'P1':1,'P2':2,'P3':3}.get(task['priority'],4)
    return (0 if advancing else 1, -p if advancing else 0,rank,task['number'])


def plan(matrix:dict, observations:Mapping, *, max_new:int=8)->dict:
    """Pure read-only plan; fails closed without LIVE signed OneHost/S03 inventory."""
    source_hash=canonical_hash(matrix)
    if not isinstance(observations,Mapping):return {'state':'HOLD_NATIVE_INVENTORY','planned':[],'source_sha256':source_hash}
    if observations.get('native_verified') is not True or observations.get('s03_native_verified') is not True:
        return {'state':'HOLD_NATIVE_INVENTORY','planned':[],'source_sha256':source_hash}
    if observations.get('stop_active') is not False:
        return {'state':'HOLD_STOP','planned':[],'source_sha256':source_hash}
    if observations.get('student_serving') is not True:
        return {'state':'HOLD_MAIN_CHAT','planned':[],'source_sha256':source_hash}
    if type(max_new) is not int or not 1<=max_new<=8:
        return {'state':'HOLD_LIMIT','planned':[],'source_sha256':source_hash}
    completed=observations.get('completed') or {}
    existing=observations.get('existing_tasks') or []
    progress=observations.get('progress') or {}
    resources=observations.get('resources') or {}
    if not isinstance(completed,Mapping) or not isinstance(existing,(list,set,tuple)) or not isinstance(resources,Mapping):
        return {'state':'HOLD_INVENTORY_TYPES','planned':[],'source_sha256':source_hash}
    budget_cpu=resources.get('available_cpu_slots')
    budget_gpu=resources.get('available_gpu1_slots')
    if type(budget_cpu) is not int or not 0<=budget_cpu<=8 or type(budget_gpu) is not int or not 0<=budget_gpu<=1:
        return {'state':'HOLD_UNKNOWN_RESOURCE_BUDGET','planned':[],'source_sha256':source_hash}
    disk=resources.get('disk_free_bytes')
    reserve=resources.get('checkpoint_disk_reserve_bytes',20_000_000_000)
    if type(disk) is not int or type(reserve) is not int or disk<0 or reserve<20_000_000_000:
        return {'state':'HOLD_DISK_TELEMETRY','planned':[],'source_sha256':source_hash}
    selected=[];blocked=[]
    gpu_slots=min(1,budget_gpu);cpu_slots=min(8,budget_cpu)
    for t in sorted(matrix['tasks'],key=lambda t:_priority(t,progress)):
        id=t['task_id']; reasons=[]
        if id in existing or _valid_completion(completed.get(id),id):continue
        for dep in t['depends_on']:
            if not _valid_completion(completed.get(dep),dep):reasons.append('PENDING_DEPENDENCY:'+dep)
        if t['requires_backup_restore'] and observations.get('offsite_restore_verified') is not True:reasons.append('BACKUP_RESTORE_GATE')
        if t['requires_license_and_privacy'] and observations.get('license_privacy_verified') is not True:reasons.append('DATA_RIGHTS_GATE')
        # No large model downloads and no optimizer without 20GB free reserve.
        if t['resource']=='GPU1_EXCLUSIVE' and disk<reserve:reasons.append('DISK_BELOW_CHECKPOINT_RESERVE')
        if t['resource']=='GPU1_EXCLUSIVE' and observations.get('gpu1_trainer_active') is True:
            reasons.append('GPU1_HAS_ACTIVE_TRAINER')
        if t['modifies_live_system'] and observations.get('native_writes_available') is not True:
            reasons.append('NATIVE_WRITES_UNAVAILABLE')
        if t['resource']=='GPU1_EXCLUSIVE':
            if gpu_slots<1:reasons.append('GPU1_BUSY_OR_NOT_ADMITTED')
        elif cpu_slots<1:reasons.append('CPU_QUOTA_EXHAUSTED')
        if reasons:
            blocked.append({'task_id':id,'reasons':reasons})
            continue
        if len(selected)>=max_new:continue
        selected.append({'task_id':id,'lane':t['lane'],'priority':t['priority'],'title':t['title'],
          'job_sha256':canonical_hash(t),'requires_native_owner':True,
          'requires_native_worker':True,'proposed_not_queued':True})
        if t['resource']=='GPU1_EXCLUSIVE':gpu_slots-=1
        else:cpu_slots-=1
    return {'state':'SOURCE_PLAN_ONLY','source_sha256':source_hash,'planned':selected,
       'blocked_count':len(blocked),'sample_blocked':blocked[:12],
       'jobs_enqueued':0,'native_receipts':[],'main_student_preserved':True}


def enqueue_approved(native:NativePorts,matrix:dict,owner_scope:str,*,limit:int=8)->dict:
    """Mutations only through native OneHost, with exact approval and readback.

    Native controls permissions, STOP, immutable receipts, concurrency, idempotency.
    If a step fails after enqueue, report UNKNOWN instead of issuing duplicate.
    """
    if not isinstance(owner_scope,str) or not re.fullmatch(r'[A-Za-z0-9._:@/-]{4,128}',owner_scope):
        return {'state':'HOLD_OWNER_SCOPE','jobs_enqueued':0}
    req=['authorize','stop','state','native_task_status','native_duplicate_check','approve','queue_enqueue',
         'queue_readback','verify_queue_receipt','s03_audit','s03_verify']
    if any(not callable(getattr(native,k,None)) for k in req):return {'state':'HOLD_NATIVE_CALLBACKS','jobs_enqueued':0}
    def gate():
        try:return native.stop() is False and native.authorize(owner_scope) is True
        except Exception:return False
    if not gate():return {'state':'HOLD_OWNER_OR_STOP','jobs_enqueued':0}
    try:inv=native.state();p=plan(matrix,inv,max_new=limit)
    except Exception:return {'state':'HOLD_NATIVE_STATE','jobs_enqueued':0}
    if p['state']!='SOURCE_PLAN_ONLY':return {'state':p['state'],'jobs_enqueued':0}
    receipts=[]
    for proposal in p['planned']:
        try:
            if not gate():return {'state':'HOLD_STOP_DURING_QUEUE','jobs_enqueued':len(receipts),'receipts':receipts}
            tid=proposal['task_id']
            if native.native_duplicate_check(tid) is not False:continue
            payload={'task_id':tid,'lane':proposal['lane'],'priority':proposal['priority'],
                     'job_sha256':proposal['job_sha256'],'matrix_sha256':p['source_sha256'],
                     'scope':owner_scope,'native_worker_required':True}
            digest=canonical_hash(payload)
            if native.approve(owner_scope,digest,dict(inv)) is not True:
                return {'state':'HOLD_NATIVE_OWNER_APPROVAL','jobs_enqueued':len(receipts),'receipts':receipts}
            if not gate():return {'state':'HOLD_STOP_DURING_QUEUE','jobs_enqueued':len(receipts),'receipts':receipts}
            ticket=native.queue_enqueue(payload)
            if not isinstance(ticket,Mapping) or ticket.get('accepted') is not True or not ticket.get('job_id'):
                return {'state':'HOLD_QUEUE_NOT_ACCEPTED','jobs_enqueued':len(receipts),'receipts':receipts}
            if native.verify_queue_receipt(ticket,payload) is not True:
                return {'state':'HOLD_QUEUE_RECEIPT_NOT_VERIFIED','enqueues_may_have_occurred':True,
                        'jobs_enqueued_verified':len(receipts),'receipts':receipts}
            readback=native.queue_readback(str(ticket['job_id']))
            if (not isinstance(readback,Mapping) or readback.get('job_id')!=ticket['job_id']
                or readback.get('task_id')!=tid or readback.get('state') not in ('pending','running')):
                return {'state':'HOLD_NATIVE_READBACK','enqueues_may_have_occurred':True,
                        'jobs_enqueued_verified':len(receipts),'receipts':receipts}
            event={'schema':'NOX_V46_QUEUED_RECEIPT','task_id':tid,'job_id':ticket['job_id'],
                   'job_sha256':payload['job_sha256'],'native_queue_receipt_sha256':canonical_hash(dict(ticket)),
                   'state':readback['state'],'source_matrix_sha256':p['source_sha256']}
            s03=native.s03_audit(event)
            if native.s03_verify(s03,event) is not True:
                return {'state':'HOLD_S03_DURABILITY_UNVERIFIED','enqueues_may_have_occurred':True,
                        'jobs_enqueued_verified':len(receipts),'receipts':receipts}
            receipts.append({'task_id':tid,'job_id':ticket['job_id'],'state':readback['state'],
                             'receipt_sha256':event['native_queue_receipt_sha256']})
        except Exception:
            return {'state':'HOLD_NATIVE_QUEUE_EXCEPTION','enqueues_may_have_occurred':True,
                    'jobs_enqueued_verified':len(receipts),'receipts':receipts}
    return {'state':'NATIVE_QUEUE_READBACK_AND_S03_VERIFIED','jobs_enqueued':len(receipts),'receipts':receipts,
            'training_completed':False,'weights_changed':False,'release_accepted':False}
