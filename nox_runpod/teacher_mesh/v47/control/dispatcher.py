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
    if matrix.get('dispatch_policy',{}).get('performance_policy_version')=='NOX_V94_VOLTA_AI_ACCEL_FIRST':
        ranks=set()
        deps={t['task_id']:t['depends_on'] for t in tasks}
        seen={}
        def check(task_id):
            if seen.get(task_id)==2:return
            if seen.get(task_id)==1:raise ValueError('HOLD_V94_DEPENDENCY_CYCLE')
            seen[task_id]=1
            for d in deps[task_id]:check(d)
            seen[task_id]=2
        for t in tasks:
            w,o=t.get('performance_wave'),t.get('performance_order')
            if type(w) is not int or not 0<=w<=4 or type(o) is not int or o<1:
                raise ValueError('HOLD_V94_PERFORMANCE_PRIORITY_METADATA')
            if (w,o) in ranks:raise ValueError('HOLD_V94_DUPLICATE_ORDER')
            ranks.add((w,o))
            check(t['task_id'])
    return matrix


def _working_source_matrix(matrix:dict)->dict:
    """One queue, two source-ID families: canonical R60 or legacy V46.

    Source schemas are metadata, not native signed approvals. Preserve R60 job
    IDs when canonical source is selected, and require exact correspondence
    with the single known-good local legacy V46 task matrix.
    """
    if not isinstance(matrix,dict):
        raise ValueError('HOLD_SOURCE_MATRIX_INVALID')
    if matrix.get('schema')=='NOX_V46_SIX_LANE_SIXTY_TASKS_V1':
        return matrix
    if matrix.get('schema')!='NOX_R60_SOURCE_PLAN_V1':
        raise ValueError('HOLD_SOURCE_MATRIX_SCHEMA')
    rows=matrix.get('tasks')
    if not isinstance(rows,list) or len(rows)!=60:
        raise ValueError('HOLD_R60_SOURCE_COUNT')
    by_id={}
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError('HOLD_R60_ROW')
        tid=row.get('task_id')
        if (not isinstance(tid,str)
                or not re.fullmatch(r'R60-(00[1-9]|0[1-5][0-9]|060)',tid)
                or tid in by_id):
            raise ValueError('HOLD_R60_DUPLICATE_OR_ID')
        by_id[tid]=row
    adapted=[]
    for old in load_matrix()['tasks']:
        n=old['number']
        rid=f'R60-{n:03d}'
        row=by_id.get(rid)
        if not isinstance(row,dict) or row.get('legacy_task_id')!=old['task_id']:
            raise ValueError('HOLD_R60_LEGACY_ALIAS')
        expected={f'R60-{int(x[-2:]):03d}' for x in old['depends_on']}
        deps=row.get('depends_on')
        if not isinstance(deps,list) or len(set(deps))!=len(deps) or set(deps)!=expected:
            raise ValueError('HOLD_R60_DEPENDENCY_DRIFT')
        for k in ('priority','performance_wave','performance_order',
                  'training_wave','training_order'):
            if row.get(k)!=old.get(k):
                raise ValueError('HOLD_R60_SOURCE_PRIORITY_DRIFT')
        for canonical,legacy in (('resource_class','resource'),
                                 ('backup_restore_required','requires_backup_restore'),
                                 ('license_privacy_required','requires_license_and_privacy'),
                                 ('modifies_live_system','modifies_live_system')):
            if row.get(canonical)!=old.get(legacy):
                raise ValueError('HOLD_R60_RESOURCE_SECURITY_DRIFT')
        adapted.append({**old,'task_id':rid,'legacy_task_id':old['task_id'],
                        'depends_on':deps})
    return {'schema':'NOX_R60_SINGLE_QUEUE_NORMALIZED_V46','tasks':adapted,
            'dispatch_policy':load_matrix()['dispatch_policy']}

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
    wave=task.get('training_wave',task.get('performance_wave'))
    if type(wave) is not int or not 0<=wave<=4:wave=rank
    order=task.get('training_order',task.get('performance_order'))
    if type(order) is not int or order<1:order=task['number']
    # Owner V99: real model/optimizer preparation and base-weight training come
    # before optional cognitive/media work. A verified 99% media job cannot
    # preempt the weight pipeline, and no background job preempts the P0 chat.
    return (wave, 0 if advancing else 1, -p if advancing else 0,
            rank,order,task['number'])


def plan(matrix:dict, observations:Mapping, *, max_new:int=8)->dict:
    """Pure read-only plan; fails closed without LIVE signed OneHost/S03 inventory."""
    source_hash=canonical_hash(matrix)
    try: working=_working_source_matrix(matrix)
    except (TypeError,ValueError,KeyError):
        return {'state':'HOLD_SOURCE_MATRIX_ALIAS_OR_SCHEMA','planned':[],
                'jobs_enqueued':0,'source_sha256':source_hash}
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
    reserve=resources.get('checkpoint_disk_reserve_bytes',10_000_000_000)
    if type(disk) is not int or type(reserve) is not int or disk<0 or reserve<10_000_000_000:
        return {'state':'HOLD_DISK_TELEMETRY','planned':[],'source_sha256':source_hash}
    # Reconcile real OneHost queue state before proposing any new work.
    # Never re-enqueue a running or unknown task on stale heartbeat alone.
    blocked_native=set()
    if 'task_status' in observations or 'native_queue_verified' in observations:
        from .worm_supervisor import audit_native_queue
        report=audit_native_queue(matrix,observations,now_unix=observations.get('now_unix'))
        if report['state']!='NATIVE_QUEUE_RECONCILED_PROPOSALS_ONLY':
            return {'state':report['state'],'planned':[],'jobs_enqueued':0,'source_sha256':source_hash}
        blocked_native=set(report['protected_task_ids'])
    selected=[];blocked=[]
    gpu_slots=min(1,budget_gpu);cpu_slots=min(8,budget_cpu)
    for t in sorted(working['tasks'],key=lambda t:_priority(t,progress)):
        id=t['task_id']; reasons=[]
        if id in blocked_native or id in existing or _valid_completion(completed.get(id),id):continue
        for dep in t['depends_on']:
            if not _valid_completion(completed.get(dep),dep):reasons.append('PENDING_DEPENDENCY:'+dep)
        if t['requires_backup_restore'] and observations.get('offsite_restore_verified') is not True:reasons.append('BACKUP_RESTORE_GATE')
        if t['requires_license_and_privacy'] and observations.get('license_privacy_verified') is not True:reasons.append('DATA_RIGHTS_GATE')
        # The 10GB floor applies to NEW disk writes, never healthy chat,
        # CPU-only diagnostics or RAM-backed read-only operations.
        if t['modifies_live_system'] and disk<reserve:
            reasons.append('HOLD_NEW_DISK_WRITE_BELOW_10GB_FLOOR')
        if t['resource']=='GPU1_EXCLUSIVE':
            if observations.get('gpu1_peak_verified') is not True:
                reasons.append('HOLD_GPU1_PEAK_VRAM_UNVERIFIED')
            if observations.get('gpu1_owner_lease') is not True:
                reasons.append('HOLD_ONEHOST_GPU1_LEASE')
            if observations.get('gpu1_teacher_active') is not False or observations.get('gpu1_trainer_active') is not False:
                reasons.append('HOLD_GPU1_ALREADY_USED')
            if observations.get('chat_state')!='idle' or observations.get('chat_recent') is not False:
                reasons.append('HOLD_CHAT_P0_FIRST')
            if t['modifies_live_system'] and observations.get('gpu1_write_budget_verified') is not True:
                reasons.append('HOLD_GPU1_CHECKPOINT_DISK_BUDGET')
        if t['modifies_live_system'] and observations.get('native_writes_available') is not True:
            reasons.append('NATIVE_WRITES_UNAVAILABLE')
        if t['resource']=='GPU1_EXCLUSIVE':
            if gpu_slots<1:reasons.append('GPU1_BUSY_OR_NOT_ADMITTED')
        elif cpu_slots<1:reasons.append('CPU_QUOTA_EXHAUSTED')
        if reasons:
            blocked.append({'task_id':id,'reasons':reasons})
            continue
        if len(selected)>=max_new:continue
        selected.append({'task_id':id,'lane':t['lane'],'priority':'P1',
          'source_priority':t['priority'],'performance_wave':t.get('performance_wave'),
          'performance_order':t.get('performance_order'),
          'training_wave':t.get('training_wave'),'training_order':t.get('training_order'),
          'training_target_compute_pct':85,'chat_priority':'P0',
          'ai_acceleration_tasks':t.get('ai_acceleration_tasks',[]),
          'title':t['title'],'job_sha256':canonical_hash(t),'requires_native_owner':True,
          'requires_native_worker':True,'proposed_not_queued':True})
        if t.get('legacy_task_id'):
            selected[-1]['legacy_task_id']=t['legacy_task_id']
        if t['resource']=='GPU1_EXCLUSIVE':gpu_slots-=1
        else:cpu_slots-=1
    return {'state':'SOURCE_PLAN_ONLY','source_sha256':source_hash,'planned':selected,
       'blocked_count':len(blocked),'sample_blocked':blocked[:12],
       'jobs_enqueued':0,'native_receipts':[],'main_student_preserved':True,
       'training_gpu1_compute_target_pct':85,
       'cpu_data_preparation_threads_max_fraction':0.85,
       'ram_cache_cgroup_fraction_max':0.85,
       'cpu_initial_worker_limit':8,
       'actual_training_started':False}


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
    try:
        inv=native.state()
        if (not isinstance(inv,Mapping) or inv.get('native_queue_verified') is not True
                or inv.get('native_writes_available') is not True
                or inv.get('owner_queue_writer_lease_verified') is not True
                or not isinstance(inv.get('task_status'),Mapping)
                or type(inv.get('now_unix')) is not int or inv['now_unix']<=0):
            return {'state':'HOLD_NATIVE_QUEUE_WRITER_LEASE_OR_STATUS','jobs_enqueued':0}
        from .worm_supervisor import audit_native_queue
        evidence=audit_native_queue(matrix,inv,now_unix=inv['now_unix'])
        if (evidence.get('state')!='NATIVE_QUEUE_RECONCILED_PROPOSALS_ONLY'
                or evidence.get('untrusted_count')!=0):
            return {'state':'HOLD_NATIVE_QUEUE_RECONCILE_OR_UNTRUSTED','jobs_enqueued':0}
        p=plan(matrix,inv,max_new=limit)
    except Exception:
        return {'state':'HOLD_NATIVE_STATE','jobs_enqueued':0}
    if p['state']!='SOURCE_PLAN_ONLY':return {'state':p['state'],'jobs_enqueued':0}
    receipts=[]
    for proposal in p['planned']:
        try:
            if not gate():return {'state':'HOLD_STOP_DURING_QUEUE','jobs_enqueued':len(receipts),'receipts':receipts}
            tid=proposal['task_id']
            identities=(tid,proposal['legacy_task_id']) if proposal.get('legacy_task_id') else (tid,)
            duplicate=[native.native_duplicate_check(name) for name in identities]
            if any(x is True for x in duplicate):continue
            if any(x is not False for x in duplicate):
                return {'state':'HOLD_NATIVE_DUPLICATE_STATE_UNKNOWN',
                        'jobs_enqueued_verified':len(receipts),'receipts':receipts}
            payload={'task_id':tid,'lane':proposal['lane'],'priority':'P1','chat_priority':'P0',
                     'source_priority':proposal.get('source_priority'),
                     'performance_wave':proposal.get('performance_wave'),
                     'training_wave':proposal.get('training_wave'),
                     'training_target_compute_pct':85,
                     'must_recheck_chat_before_work':True,
                     'job_sha256':proposal['job_sha256'],'matrix_sha256':p['source_sha256'],
                     'scope':owner_scope,'native_worker_required':True}
            if proposal.get('legacy_task_id'):
                payload['legacy_task_id']=proposal['legacy_task_id']
            digest=canonical_hash(payload)
            if native.approve(owner_scope,digest,dict(inv)) is not True:
                return {'state':'HOLD_NATIVE_OWNER_APPROVAL','jobs_enqueued':len(receipts),'receipts':receipts}
            if not gate():return {'state':'HOLD_STOP_DURING_QUEUE','jobs_enqueued':len(receipts),'receipts':receipts}
            ticket=native.queue_enqueue(payload)
            if (not isinstance(ticket,Mapping) or ticket.get('accepted') is not True
                    or not isinstance(ticket.get('job_id'),str)
                    or not re.fullmatch(r'[A-Za-z0-9._:@/-]{1,128}',ticket['job_id'])):
                return {'state':'HOLD_QUEUE_NOT_ACCEPTED','jobs_enqueued':len(receipts),'receipts':receipts}
            if native.verify_queue_receipt(ticket,payload) is not True:
                return {'state':'HOLD_QUEUE_RECEIPT_NOT_VERIFIED','enqueues_may_have_occurred':True,
                        'jobs_enqueued_verified':len(receipts),'receipts':receipts}
            readback=native.queue_readback(str(ticket['job_id']))
            if (not isinstance(readback,Mapping) or readback.get('job_id')!=ticket['job_id']
                or readback.get('task_id')!=tid or readback.get('state') not in ('pending','running')):
                return {'state':'HOLD_NATIVE_READBACK','enqueues_may_have_occurred':True,
                        'jobs_enqueued_verified':len(receipts),'receipts':receipts}
            # Native task registry must independently attest the exact job.
            status=native.native_task_status(tid)
            if (not isinstance(status,Mapping) or status.get('task_id')!=tid
                    or status.get('job_id')!=ticket['job_id']
                    or status.get('native_verified') is not True
                    or status.get('owner_scope')!=owner_scope
                    or status.get('state') not in ('PENDING','RUNNING','CLAIMED')
                    or not isinstance(status.get('receipt_sha256'),str)
                    or SHA.fullmatch(status['receipt_sha256']) is None):
                return {'state':'HOLD_NATIVE_TASK_REGISTRY_READBACK',
                        'enqueues_may_have_occurred':True,'jobs_enqueued_verified':len(receipts),
                        'receipts':receipts}
            event={'schema':'NOX_V46_QUEUED_RECEIPT','task_id':tid,'job_id':ticket['job_id'],
                   'job_sha256':payload['job_sha256'],
                   'native_queue_receipt_sha256':canonical_hash(dict(ticket)),
                   'native_task_status_receipt_sha256':status['receipt_sha256'],
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
    return {'state':'NATIVE_QUEUE_READBACK_AND_S03_VERIFIED' if receipts else 'NATIVE_QUEUE_NO_NEW_JOBS',
            'jobs_enqueued':len(receipts),'receipts':receipts,
            'training_completed':False,'weights_changed':False,'release_accepted':False}
