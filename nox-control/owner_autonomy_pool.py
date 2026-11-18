"""NOX autonomous process-pool admission for the EXISTING owner dispatcher.

One user-facing NOX; NORMAL activates three dedicated *OS processes* and
FORSAZH activates six. A task batch may contain any number of typed tasks;
only a bounded ready window is admitted on each tick. Existing owner-native
callbacks do actual process lifecycle, task claiming and S03 persistence.
No second scheduler, untrusted shell, speculative GPU trainer or new database.
"""
from __future__ import annotations

from hashlib import sha256
import heapq
import json
import math
import re
import time
from collections import deque
from collections.abc import Mapping

SCHEMA = 'NOX_AUTONOMY_PROCESS_POOL_V1'
MODES = {'NORMAL': 3, 'FORSAZH': 6}
PRIORITIES = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3}
ID = re.compile(r'^[A-Za-z0-9._:-]{1,128}$')
SHA = re.compile(r'^[a-f0-9]{64}$')
MAX_PAGE = 256
MAX_PAGE_BYTES = 256 * 1024
RESOURCE_ADMISSION_MAX_AGE_SECONDS = 5.0
RESOURCE_ADMISSION_FUTURE_SKEW_SECONDS = 1.0


class AutoHold(ValueError):
    """Fail closed without changing existing work."""


def fingerprint(obj):
    return sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                             separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def verify_resource_admission(snapshot, *, now=None):
    """Verify the native gate decision is fresh and bound to this exact snapshot."""
    if not isinstance(snapshot, Mapping) or snapshot.get('resource_admission_allowed') is not True:
        raise AutoHold('HOLD_RESOURCE_ADMISSION')
    if (snapshot.get('native_verified') is not True
            or snapshot.get('instance_id') != 60509551
            or snapshot.get('stop_active') is not False
            or snapshot.get('source_sha_verified') is not True
            or snapshot.get('owner_scope_verified') is not True):
        raise AutoHold('HOLD_RESOURCE_ADMISSION_IDENTITY')
    observed_at = snapshot.get('resource_admission_observed_at')
    if type(observed_at) not in (int, float) or not math.isfinite(observed_at):
        raise AutoHold('HOLD_RESOURCE_ADMISSION_TIMESTAMP')
    current_time = time.time() if now is None else now
    if type(current_time) not in (int, float) or not math.isfinite(current_time):
        raise AutoHold('HOLD_RESOURCE_ADMISSION_CLOCK')
    age = current_time - observed_at
    if (age > RESOURCE_ADMISSION_MAX_AGE_SECONDS
            or age < -RESOURCE_ADMISSION_FUTURE_SKEW_SECONDS):
        raise AutoHold('HOLD_RESOURCE_ADMISSION_STALE')
    expected = snapshot.get('resource_admission_snapshot_sha256')
    if not isinstance(expected, str) or SHA.fullmatch(expected) is None:
        raise AutoHold('HOLD_RESOURCE_ADMISSION_SNAPSHOT')
    payload = dict(snapshot)
    payload.pop('resource_admission_snapshot_sha256', None)
    try:
        actual = fingerprint(payload)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AutoHold('HOLD_RESOURCE_ADMISSION_SNAPSHOT') from exc
    if actual != expected:
        raise AutoHold('HOLD_RESOURCE_ADMISSION_SNAPSHOT')
    return expected


def _task(row, allowed_handlers):
    if not isinstance(row, Mapping) or set(row) - {'id','handler','deps','priority','resource','source_sha256','params','title','estimated_cost'}:
        raise AutoHold('HOLD_TASK_FIELDS')
    tid, handler = row.get('id'), row.get('handler')
    if not isinstance(tid, str) or ID.fullmatch(tid) is None:
        raise AutoHold('HOLD_TASK_ID')
    if handler not in allowed_handlers:
        raise AutoHold('HOLD_UNREVIEWED_NATIVE_HANDLER')
    deps = row.get('deps', [])
    if not isinstance(deps, list) or any(not isinstance(x, str) or ID.fullmatch(x) is None for x in deps):
        raise AutoHold('HOLD_DEPENDENCY_FORMAT')
    if tid in deps or len(deps) != len(set(deps)):
        raise AutoHold('HOLD_SELF_OR_DUPLICATE_DEPENDENCY')
    priority = row.get('priority', 'P2')
    if priority not in PRIORITIES:
        raise AutoHold('HOLD_TASK_PRIORITY')
    resource = row.get('resource','CPU_LIGHT')
    if resource not in ('CPU_LIGHT','CPU_IO','GPU_EXCLUSIVE'):
        raise AutoHold('HOLD_RESOURCE_KIND')
    source = row.get('source_sha256')
    if not isinstance(source, str) or SHA.fullmatch(source) is None:
        raise AutoHold('HOLD_TASK_SOURCE_SHA')
    params = row.get('params', {})
    if not isinstance(params, dict) or len(json.dumps(params)) > 16*1024:
        raise AutoHold('HOLD_TASK_TYPED_PARAMS')
    cost = row.get('estimated_cost', 1)
    if type(cost) not in (int, float) or not math.isfinite(cost) or not 0 < cost <= 100000:
        raise AutoHold('HOLD_TASK_COST')
    title = row.get('title', tid)
    if not isinstance(title, str) or not 1 <= len(title) <= 180:
        raise AutoHold('HOLD_TITLE')
    return {'id':tid,'handler':handler,'deps':deps,'priority':priority,
            'resource':resource,'source_sha256':source,'params':params,
            'title':title,'estimated_cost':cost}


def validate_page(page, *, allowed_handlers, known_ids=frozenset()):
    """Validate ONE bounded page; no fixed limit on total queued task count.

    All cross-page dependencies are resolved against durable known IDs.
    Orchestration stores pages itself; this function never creates a job.
    """
    if not isinstance(page, dict) or set(page) != {'schema','tasks'} or page['schema'] != SCHEMA:
        raise AutoHold('HOLD_BATCH_SCHEMA')
    rows = page['tasks']
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_PAGE:
        raise AutoHold('HOLD_BATCH_PAGE_SIZE')
    try:
        raw = json.dumps(page, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError) as e:
        raise AutoHold('HOLD_UNSERIALIZABLE_BATCH') from e
    if len(raw.encode()) > MAX_PAGE_BYTES:
        raise AutoHold('HOLD_BATCH_BYTES')
    tasks = [_task(row, allowed_handlers) for row in rows]
    ids = [t['id'] for t in tasks]
    if len(ids) != len(set(ids)) or set(ids) & set(known_ids):
        raise AutoHold('HOLD_DUPLICATE_TASK_ID')
    available = set(ids) | set(known_ids)
    for row in tasks:
        if any(d not in available for d in row['deps']):
            raise AutoHold('HOLD_UNKNOWN_DEPENDENCY')
    # Cycles inside the page must be rejected, not indefinitely queued.
    dependencies = {r['id']: set(d for d in r['deps'] if d in ids) for r in tasks}
    children = {r['id']: [] for r in tasks}
    for tid, ds in dependencies.items():
        for dep in ds: children[dep].append(tid)
    ready = deque(t for t in ids if not dependencies[t]); seen = 0
    while ready:
        tid=ready.popleft();seen+=1
        for child in children[tid]:
            dependencies[child].discard(tid)
            if not dependencies[child]:ready.append(child)
    if seen!=len(tasks):raise AutoHold('HOLD_DEPENDENCY_CYCLE')
    return tasks



def validate_submission(submission, *, allowed_handlers, known_ids=frozenset()):
    """Accept one command with any number of tasks; paginate internally.

    Total count follows available storage/memory, not a literal 30/60 cap.
    Each emitted page is bounded, and the whole DAG is checked before enqueue.
    """
    if (not isinstance(submission, Mapping) or set(submission) != {'schema','tasks'}
        or submission.get('schema') != SCHEMA or not isinstance(submission.get('tasks'),list)):
        raise AutoHold('HOLD_SUBMISSION_SCHEMA')
    rows=submission['tasks']
    if not rows:
        raise AutoHold('HOLD_EMPTY_SUBMISSION')
    items=[_task(row,allowed_handlers) for row in rows]
    ids=[item['id'] for item in items]
    if len(set(ids))!=len(ids) or set(ids)&set(known_ids):
        raise AutoHold('HOLD_DUPLICATE_TASK_ID')
    known=set(ids)|set(known_ids)
    lookup={item['id']:item for item in items}
    children={tid:[] for tid in ids}
    indegree={tid:0 for tid in ids}
    for row in items:
        if any(dep not in known for dep in row['deps']):
            raise AutoHold('HOLD_UNKNOWN_DEPENDENCY')
        for dep in row['deps']:
            if dep in lookup:
                children[dep].append(row['id']);indegree[row['id']]+=1
    heap=[]
    for tid in ids:
        if not indegree[tid]:
            row=lookup[tid];heapq.heappush(heap,(PRIORITIES[row['priority']],row['estimated_cost'],tid))
    ordered=[]
    while heap:
        _,_,tid=heapq.heappop(heap)
        ordered.append(lookup[tid])
        for child in children[tid]:
            indegree[child]-=1
            if not indegree[child]:
                r=lookup[child];heapq.heappush(heap,(PRIORITIES[r['priority']],r['estimated_cost'],child))
    if len(ordered)!=len(items):
        raise AutoHold('HOLD_DEPENDENCY_CYCLE')
    pages=[];current=[]
    for row in ordered:
        trial={'schema':SCHEMA,'tasks':current+[row]}
        if len(current)>=MAX_PAGE or len(json.dumps(trial,ensure_ascii=False,allow_nan=False).encode())>MAX_PAGE_BYTES:
            if not current: raise AutoHold('HOLD_SINGLE_TASK_EXCEEDS_PAGE')
            pages.append({'schema':SCHEMA,'tasks':current});current=[]
        current.append(row)
    if current: pages.append({'schema':SCHEMA,'tasks':current})
    return {'schema':SCHEMA,'task_count':len(ordered),'page_count':len(pages),
            'request_sha256':fingerprint(submission),'pages':pages,'ordered':ordered}


def tick_existing_dispatcher(namespace, state, *, mode):
    """Auto-invoked by existing owner planner on every queue-ingest cycle.

    Native callbacks, not a repo file/model prompt, own worker launch, queue
    claims, STOP and S03. Missing callbacks yield an honest HOLD, never a fake
    worker process or a second scheduler.
    """
    native=namespace.get('_nox_owner_autonomy_native')
    if native is None:
        return {'state':'HOLD_NATIVE_POOL_CALLBACKS','jobs_started':0}
    if not all(callable(getattr(native,key,None)) for key in
               ('read_reviewed_catalog','read_resource_snapshot','allowed_handlers')):
        return {'state':'HOLD_AUTONOMY_SOURCE_CALLBACKS','jobs_started':0}
    try:
        catalog=native.read_reviewed_catalog()
        runtime=native.read_resource_snapshot()
        if (not isinstance(runtime,Mapping) or runtime.get('native_verified') is not True
            or runtime.get('instance_id')!=60509551 or runtime.get('stop_active') is not False
            or runtime.get('source_sha_verified') is not True
            or runtime.get('owner_scope_verified') is not True):
            return {'state':'HOLD_AUTONOMY_NATIVE_SNAPSHOT','jobs_started':0}
        try:
            verify_resource_admission(runtime)
        except AutoHold as exc:
            return {'state':str(exc),'jobs_started':0}
        tasks=([] if isinstance(catalog,Mapping) and catalog.get('schema')==SCHEMA
               and catalog.get('tasks')==[] else
               validate_submission(catalog,allowed_handlers=native.allowed_handlers())['ordered'])
        status=runtime.get('task_status')
        return admit_native_tick(native,tasks=tasks,status=status,
            mode=mode,memory_ratio=runtime.get('cgroup_memory_ratio'),
            cpu_pressure=runtime.get('cpu_pressure',0),
            gpu_available=runtime.get('gpu_available') is True)
    except (AutoHold,TypeError,ValueError,OverflowError) as exc:
        return {'state':str(exc) if isinstance(exc,AutoHold) else 'HOLD_AUTONOMY_INPUT',
                'jobs_started':0}
    except Exception:
        return {'state':'HOLD_NATIVE_AUTONOMY_CALLBACK_EXCEPTION','jobs_started':0}


def _choose_ready_with_diagnostics(tasks, *, status, mode, memory_ratio, cpu_pressure=0.0,
                                     gpu_available=False, verified_native=True):
    """Select with an explanation snapshot; diagnostics never alter selection."""
    if mode not in MODES:
        raise AutoHold('HOLD_MODE')
    if verified_native is not True:
        raise AutoHold('HOLD_NATIVE_RESOURCE_ADMISSION')
    if not isinstance(status, Mapping):
        raise AutoHold('HOLD_QUEUE_STATE')
    if type(memory_ratio) not in (float, int) or not math.isfinite(memory_ratio) or memory_ratio < 0:
        raise AutoHold('HOLD_CGROUP_MEMORY')
    if type(cpu_pressure) not in (float, int) or not math.isfinite(cpu_pressure) or cpu_pressure < 0:
        raise AutoHold('HOLD_CPU_PRESSURE')
    budget = MODES[mode]
    if memory_ratio >= .95: budget = 0
    elif memory_ratio >= .85: budget = min(budget,3)
    if cpu_pressure >= 50: budget = min(budget,1)
    elif cpu_pressure >= 20:budget = min(budget,3)
    pressure_limited_budget = budget
    # Reservation is native queue state, not only a lowercase "running".
    # A lost ACK can leave an admitted/queued/unknown job consuming a slot.
    # Fail closed for unknown/null/structured statuses; release capacity only
    # for explicit terminal states from the verified native snapshot.
    terminal = frozenset(('done','completed','failed','cancelled','canceled'))
    existing_claims = sum(
        1 for state in status.values()
        if not (isinstance(state, str) and state.casefold() in terminal))
    budget = max(0, budget-existing_claims)
    ranked=[]
    known_task_count=0
    dependency_blocked_count=0
    gpu_blocked_count=0
    for task in tasks:
        tid=task['id']
        # Presence is authoritative even when an uncertain native claim has
        # status None. Distinguish absent from unresolved before any replay.
        if tid in status:
            known_task_count+=1
            continue   # never reenqueue known/unknown/running/done jobs
        # Only explicit successful terminals release DAG dependents; failures,
        # cancellations and unresolved claims must never unlock new work.
        if any(not (isinstance(status.get(d), str) and status[d].casefold() in ('done', 'completed')) for d in task['deps']):
            dependency_blocked_count+=1
            continue
        if task['resource']=='GPU_EXCLUSIVE' and not gpu_available:
            gpu_blocked_count+=1
            continue
        heapq.heappush(ranked,(PRIORITIES[task['priority']],task['estimated_cost'],tid,task))
    eligible_candidate_count=len(ranked)
    selected=[];gpu_used=False
    while ranked and len(selected)<budget:
        *_, row=heapq.heappop(ranked)
        if row['resource']=='GPU_EXCLUSIVE':
            if gpu_used:continue
            gpu_used=True
        selected.append(row)
    if selected:
        reason_codes=[]
    elif not tasks:
        reason_codes=['EMPTY_CATALOG']
    else:
        reason_codes=[]
        if known_task_count==len(tasks):
            reason_codes.append('ALL_CATALOG_TASKS_ALREADY_KNOWN')
        elif known_task_count:
            reason_codes.append('KNOWN_TASKS_NOT_REPLAYED')
        if dependency_blocked_count:
            reason_codes.append('DEPENDENCIES_UNSATISFIED')
        if gpu_blocked_count:
            reason_codes.append('GPU_UNAVAILABLE')
        if eligible_candidate_count and budget==0:
            reason_codes.append('NO_DISPATCH_BUDGET')
        if not reason_codes:
            reason_codes=['NO_ELIGIBLE_TASK']
    diagnostics={
        'schema':'NOX_POOL_IDLE_DIAGNOSTICS_V1',
        'reason_codes':reason_codes,
        'catalog_task_count':len(tasks),
        'known_task_count':known_task_count,
        'dependency_blocked_count':dependency_blocked_count,
        'gpu_blocked_count':gpu_blocked_count,
        'eligible_candidate_count':eligible_candidate_count,
        'configured_budget':MODES[mode],
        'pressure_limited_budget':pressure_limited_budget,
        'reserved_claim_count':existing_claims,
        'remaining_budget':budget,
        'selected_task_count':len(selected),
    }
    return selected,diagnostics


def choose_ready(tasks, *, status, mode, memory_ratio, cpu_pressure=0.0,
                 gpu_available=False, verified_native=True):
    """Default three process claims, boost six; independent from queue length."""
    return _choose_ready_with_diagnostics(
        tasks,status=status,mode=mode,memory_ratio=memory_ratio,
        cpu_pressure=cpu_pressure,gpu_available=gpu_available,
        verified_native=verified_native)[0]


def classify_native_job_proof(proof):
    """Do not confuse an S03 admission receipt with execution of the task.

    Exact native terminal proof is additive to, not a replacement for, the
    existing signed task/job/S03 SHA validation. Missing fields mean UNKNOWN.
    """
    if proof.get('task_note') == 'ADMITTED_NOT_EXECUTED':
        return 'ADMITTED_NOT_EXECUTED'
    result_sha = proof.get('result_sha256')
    if (proof.get('terminal_state') == 'COMPLETED'
        and proof.get('execution_verified') is True
        and isinstance(result_sha, str) and SHA.fullmatch(result_sha)):
        return 'DONE_NATIVE'
    return 'EXECUTION_UNVERIFIED'

def verify_distinct_native_processes(rows, *, requested, instance_id=60509551):
    """An agent ID/thread ID is NOT proof of an OS subexecutor process."""
    if type(requested) is not int or not 1 <= requested <= 6:
        raise AutoHold('HOLD_OS_PROCESS_TARGET')
    if not isinstance(rows, list) or len(rows)<requested:
        raise AutoHold('HOLD_OS_PROCESSES_NOT_LAUNCHED')
    live=[];seen=set();seen_pids=set()
    for row in rows:
        if not isinstance(row, Mapping): continue
        pid=row.get('pid');start=row.get('process_starttime')
        if (row.get('instance_id')!=instance_id or row.get('origin')!='existing_onehost'
            or row.get('native_pid_verified') is not True or row.get('state')!='RUNNING'
            or type(pid) is not int or pid<=1 or type(start) is not int or start<=0
            # A live PID/starttime is not enough: reject stale or unverified heartbeat.
            or row.get('native_heartbeat_verified') is not True
            or type(row.get('heartbeat_age_seconds')) not in (int,float)
            or not math.isfinite(row['heartbeat_age_seconds'])
            or not 0 <= row['heartbeat_age_seconds'] <= 600):continue
        identity=(pid,start)
        if identity in seen or pid in seen_pids:raise AutoHold('HOLD_DUPLICATE_NATIVE_PROCESS')
        seen.add(identity);seen_pids.add(pid);live.append(row)
    if len(live)!=requested:
        raise AutoHold('HOLD_UNVERIFIED_OS_PROCESS_COUNT')
    return live


def admit_native_tick(native, *, tasks, status, mode, memory_ratio, cpu_pressure=0.0,
                      gpu_available=False, instance_id=60509551):
    """Native owner callback must create/read back separate OS workers.

    Only this method may dispatch. The source module NEVER starts background
    processes or executes model-generated shell on its own; OneHost's existing
    process supervisor implements ensure_processes and queue admission.
    """
    if not all(callable(getattr(native,x,None)) for x in
               ('owner_allowed','stop_active','writer_lease','ensure_processes',
                'process_readback','native_duplicate_check','native_queue_claim','s03_readback')):
        return {'state':'HOLD_NATIVE_POOL_CALLBACKS','jobs_started':0}
    if (native.owner_allowed() is not True or native.stop_active() is not False
        or native.writer_lease() is not True):
        return {'state':'HOLD_OWNER_STOP_OR_WRITER_LEASE','jobs_started':0}
    ready,idle_diagnostics=_choose_ready_with_diagnostics(
        tasks,status=status,mode=mode,memory_ratio=memory_ratio,
        cpu_pressure=cpu_pressure,gpu_available=gpu_available)
    # Keep a fixed pool of actual OS workers ready even if the queue is idle.
    # Resource pressure can temporarily reduce the target; do not fake workers.
    target=MODES[mode]
    if memory_ratio>=.95:target=0
    elif memory_ratio>=.85:target=min(target,3)
    if cpu_pressure>=50:target=min(target,1)
    elif cpu_pressure>=20:target=min(target,3)
    if target==0:return {'state':'HOLD_RESOURCE_PRESSURE','jobs_started':0,
                            'idle_diagnostics':idle_diagnostics}
    # This MUST be a native process-supervisor operation, not a Python thread.
    if native.ensure_processes(target) is not True:
        return {'state':'HOLD_NATIVE_PROCESS_START','jobs_started':0}
    try:workers=verify_distinct_native_processes(native.process_readback(),requested=target,instance_id=instance_id)
    except AutoHold as e:return {'state':str(e),'jobs_started':0}
    # ensure_processes/process_readback may cross a STOP/lease transition.
    # In particular, an idle pool must not be reported ready after revocation.
    if (native.owner_allowed() is not True or native.stop_active() is not False
        or native.writer_lease() is not True):
        return {'state':'HOLD_STOP_OR_LEASE_CHANGED','jobs_started':0}
    receipts=[];seen_job_ids=set()
    for task in ready:
        if (native.owner_allowed() is not True or native.stop_active() is not False or native.writer_lease() is not True):
            return {'state':'HOLD_STOP_OR_LEASE_CHANGED','jobs_started':len(receipts),'receipts':receipts}
        # Keep duplicate lookup errors separate from a possibly committed claim.
        # Neither outcome authorizes a replay until exact native queue/S03 readback.
        try:
            duplicate=native.native_duplicate_check(task['id'])
        except Exception:
            return {'state':'HOLD_NATIVE_DUPLICATE_READBACK',
                    'jobs_started':len(receipts),'possible_unverified_claim':task['id'],
                    'receipts':receipts}
        if duplicate is not False:
            return {'state':'HOLD_DUPLICATE_OR_UNKNOWN_TASK',
                    'jobs_started':len(receipts),'possible_unverified_claim':task['id'],
                    'receipts':receipts}
        try:
            # Owner scope, STOP and lease can change during duplicate lookup.
            if (native.owner_allowed() is not True or native.stop_active() is not False
                or native.writer_lease() is not True):
                return {'state':'HOLD_STOP_OR_LEASE_CHANGED',
                        'jobs_started':len(receipts),'receipts':receipts}
        except Exception:
            return {'state':'HOLD_OWNER_GATE_READBACK',
                    'jobs_started':len(receipts),'receipts':receipts}
        try:
            result=native.native_queue_claim(task,owner_pids=[x['pid'] for x in workers])
        except Exception:
            # The queue may have committed the task before its acknowledgement
            # failed; preserve the exact ID for reconciliation, never retry.
            return {'state':'UNKNOWN_NATIVE_CLAIM',
                    'jobs_started':len(receipts),'possible_unverified_claim':task['id'],
                    'receipts':receipts}
        # Never retry a claim after ambiguous result; demand durable readback.
        job_id=result.get('job_id') if isinstance(result,Mapping) else None
        # A native claim may exist even if its returned ID is invalid or repeated.
        # Preserve the task ID for exact readback; never enqueue it again blindly.
        if type(job_id) not in (str,int) or ID.fullmatch(str(job_id)) is None:
            return {'state':'UNKNOWN_NATIVE_CLAIM','jobs_started':len(receipts),
                    'possible_unverified_claim':task['id'],'receipts':receipts}
        if str(job_id) in seen_job_ids:
            return {'state':'HOLD_NATIVE_JOB_ID_COLLISION','jobs_started':len(receipts),
                    'possible_unverified_claim':task['id'],'receipts':receipts}
        try:
            proof=native.s03_readback(task['id'],job_id)
        except Exception:
            return {'state':'HOLD_S03_NATIVE_READBACK','jobs_started':len(receipts),
                    'possible_unverified_claim':task['id'],'receipts':receipts}
        if (not isinstance(proof,Mapping) or proof.get('native_verified') is not True
            or proof.get('task_id')!=task['id'] or proof.get('job_id')!=result['job_id']
            or not isinstance(proof.get('receipt_sha256'),str)
            or SHA.fullmatch(proof['receipt_sha256']) is None):
            return {'state':'HOLD_S03_NATIVE_READBACK','jobs_started':len(receipts),'possible_unverified_claim':task['id'],'receipts':receipts}
        seen_job_ids.add(str(job_id))
        execution_evidence = classify_native_job_proof(proof)
        receipts.append({'task_id':task['id'],'job_id':job_id,'pid_count':len(workers),
                         's03_sha256':proof['receipt_sha256'],
                         'execution_evidence':execution_evidence})
        # S03 can block while the owner presses STOP or a native writer lease
        # expires. Preserve the already-confirmed claim/receipt, but never
        # report the pool ready or dispatch another task on a revoked fence.
        try:
            still_authorized = (native.owner_allowed() is True
                and native.stop_active() is False and native.writer_lease() is True)
        except Exception:
            return {'state':'HOLD_OWNER_GATE_READBACK',
                    'jobs_started':len(receipts),'receipts':receipts}
        if not still_authorized:
            return {'state':'HOLD_STOP_OR_LEASE_CHANGED',
                    'jobs_started':len(receipts),'receipts':receipts}
    result={'state':'NATIVE_QUEUE_READBACK_VERIFIED' if receipts else 'NATIVE_POOL_READY_IDLE',
            'jobs_started':len(receipts),  # legacy counter: CLAIMS, not executed jobs
            'jobs_completed_verified':sum(r['execution_evidence']=='DONE_NATIVE' for r in receipts),
            'active_subexecutor_processes':len(workers),'receipts':receipts}
    if not receipts:
        result['idle_diagnostics']=idle_diagnostics
    return result
