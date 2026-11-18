"""NOX autonomous process-pool admission for the EXISTING owner dispatcher.

One user-facing NOX; NORMAL supports three dedicated *OS processes* and
FORSAZH supports six, subject to the owner's current global worker cap (3).
A task batch may contain any number of typed tasks;
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
from collections import deque
from collections.abc import Mapping
import owner_resource_policy as resource_policy

SCHEMA = 'NOX_AUTONOMY_PROCESS_POOL_V1'
MODES = {'NORMAL': 3, 'FORSAZH': 6}
DEFAULT_WORKER_CAP = 3
QUEUE_IDS = ('Q1_RUNTIME_CHAT', 'Q2_MEMORY_KNOWLEDGE',
             'Q3_TRAINING_WEIGHTS', 'Q4_INTEGRATION_ACCEPTANCE')
TERMINAL = ('done', 'completed', 'failed', 'cancelled', 'canceled')
PRIORITIES = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3}
ID = re.compile(r'^[A-Za-z0-9._:-]{1,128}$')
SHA = re.compile(r'^[a-f0-9]{64}$')
MAX_PAGE = 256
MAX_PAGE_BYTES = 256 * 1024


class AutoHold(ValueError):
    """Fail closed without changing existing work."""


def fingerprint(obj):
    return sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                             separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _task(row, allowed_handlers):
    if not isinstance(row, Mapping) or set(row) - {'id','handler','deps','priority','resource','source_sha256','params','title','estimated_cost','utility','resource_demand','promotion_candidate_sha256','queue_id'}:
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
    optional = {key:row[key] for key in ('utility', 'resource_demand', 'promotion_candidate_sha256', 'queue_id') if key in row}
    if 'queue_id' in optional and optional['queue_id'] not in QUEUE_IDS:
        raise AutoHold('HOLD_TASK_QUEUE_ID')
    candidate = optional.get('promotion_candidate_sha256')
    if candidate is not None and not resource_policy.exact_sha(candidate):
        raise AutoHold('HOLD_PROMOTION_CANDIDATE_SHA')
    try: resource_policy.utility_score({**optional, 'estimated_cost':cost})
    except resource_policy.PolicyHold as exc: raise AutoHold(str(exc)) from exc
    return {'id':tid,'handler':handler,'deps':deps,'priority':priority,
            'resource':resource,'source_sha256':source,'params':params,
            'title':title,'estimated_cost':cost, **optional}


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
    # Preserve the owner's P0..P3 order. Within the same owner tier,
    # prioritize measured/declared utility per cost, just like choose_ready().
    # A cheap but nearly useless job must not monopolize the first page.
    # This is ordering only: it grants no owner lease or native admission.
    def _rank(task):
        return (PRIORITIES[task['priority']],
                -resource_policy.utility_score(task),
                task['estimated_cost'], task['id'])
    heap=[]
    for tid in ids:
        if not indegree[tid]:
            row=lookup[tid];heapq.heappush(heap,(*_rank(row),tid))
    ordered=[]
    while heap:
        *_,tid=heapq.heappop(heap)
        ordered.append(lookup[tid])
        for child in children[tid]:
            indegree[child]-=1
            if not indegree[child]:
                r=lookup[child];heapq.heappush(heap,(*_rank(r),child))
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


def tick_existing_dispatcher(namespace, state, *, mode, worker_cap=DEFAULT_WORKER_CAP):
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
        tasks=([] if isinstance(catalog,Mapping) and catalog.get('schema')==SCHEMA
               and catalog.get('tasks')==[] else
               validate_submission(catalog,allowed_handlers=native.allowed_handlers())['ordered'])
        status=runtime.get('task_status')
        return admit_native_tick(native,tasks=tasks,status=status,
            mode=mode,memory_ratio=runtime.get('cgroup_memory_ratio'),
            cpu_pressure=runtime.get('cpu_pressure',0),
            gpu_available=runtime.get('gpu_available') is True,
            policy_snapshot=runtime.get('resource_policy'),
            quality_receipts=runtime.get('quality_receipts'),
            quality_policies=runtime.get('quality_policies'), worker_cap=worker_cap,
            queue_cursor=runtime.get('queue_cursor'))
    except (AutoHold,TypeError,ValueError,OverflowError) as exc:
        return {'state':str(exc) if isinstance(exc,AutoHold) else 'HOLD_AUTONOMY_INPUT',
                'jobs_started':0}
    except Exception:
        return {'state':'HOLD_NATIVE_AUTONOMY_CALLBACK_EXCEPTION','jobs_started':0}


def _process_target(mode, memory_ratio, cpu_pressure, worker_cap):
    if mode not in MODES:
        raise AutoHold('HOLD_MODE')
    if type(worker_cap) is not int or not 1 <= worker_cap <= 6:
        raise AutoHold('HOLD_OWNER_WORKER_CAP')
    target = min(MODES[mode], worker_cap)
    if memory_ratio >= .95: target = 0
    elif memory_ratio >= .85: target = min(target, 3)
    if cpu_pressure >= 50: target = min(target, 1)
    elif cpu_pressure >= 20: target = min(target, 3)
    return target


def _in_flight(state):
    # Preserve the native branch's conservative reservation semantics. A lost
    # ACK may leave pending, blocked, null or unrecognized state with a claim.
    return not (isinstance(state, str) and state.casefold() in TERMINAL)


def choose_ready(tasks, *, status, mode, memory_ratio, cpu_pressure=0.0,
                 gpu_available=False, verified_native=True, policy_snapshot=None,
                 quality_receipts=None, quality_policies=None, decision_log=None,
                 worker_cap=DEFAULT_WORKER_CAP, queue_cursor=None):
    """One global cap; rotate four queues, priority/utility within each queue.

    The existing durable status census is the cursor: each previously absent
    TaskID consumes one turn when native_queue_claim records it. Pending,
    running, done and failed entries all retain that turn. Keep terminal rows
    in the reviewed catalog/status census; explicit resets start a new cycle.
    No independent cursor file, database, callback or scheduler is needed.
    """
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
    decisions = decision_log if decision_log is not None else {}
    quality_receipts = quality_receipts if isinstance(quality_receipts, Mapping) else {}
    quality_policies = quality_policies if isinstance(quality_policies, Mapping) else {}
    try:
        measured = resource_policy.Budget(policy_snapshot) if policy_snapshot is not None else None
    except resource_policy.PolicyHold as exc:
        raise AutoHold(str(exc)) from exc
    budget = _process_target(mode, memory_ratio, cpu_pressure, worker_cap)
    existing_claims = sum(_in_flight(row) for row in status.values())
    budget = max(0, budget-existing_claims)
    queued = any('queue_id' in task for task in tasks)
    if queued and any(task.get('queue_id') not in QUEUE_IDS and task['id'] not in status for task in tasks):
        raise AutoHold('HOLD_MIXED_OR_UNKNOWN_QUEUES')
    # Snapshot-derived ordering survives dispatcher restarts. Native claiming
    # already persists a distinct TaskID before S03 readback. Including pending
    # prevents the same first three queues winning every admission tick.
    if queue_cursor is not None and (type(queue_cursor) is not int
                                     or not 0 <= queue_cursor < len(QUEUE_IDS)):
        raise AutoHold('HOLD_NATIVE_QUEUE_CURSOR')
    cursor = (queue_cursor if queue_cursor is not None else
              sum(task['id'] in status for task in tasks) % len(QUEUE_IDS))
    queues = {qid: [] for qid in QUEUE_IDS} if queued else None
    ranked=[]
    for task in tasks:
        tid=task['id']
        if tid in status:continue   # presence includes unresolved/null claims
        if any(not (isinstance(status.get(d), str)
                    and status[d].casefold() in ('done', 'completed'))
               for d in task['deps']): continue
        if task['resource']=='GPU_EXCLUSIVE' and (measured is None or not gpu_available):
            decisions[tid] = 'HOLD_CHAT_BUDGET_ADMISSION' if measured is None else 'WAIT_GPU_AVAILABLE'
            continue
        # CPU_IO requires measured admission even if an old/malformed producer
        # omitted resource_demand entirely. An explicit resource contract (even
        # null) is never eligible for legacy pressure-only admission.
        # Only CPU_LIGHT with no demand key preserves the old fallback.
        if measured is None and (task['resource'] == 'CPU_IO' or 'resource_demand' in task):
            decisions[tid] = 'HOLD_MEASURED_RESOURCE_SNAPSHOT_REQUIRED'
            continue
        try: score = resource_policy.utility_score(task)
        except resource_policy.PolicyHold as exc:
            decisions[tid] = str(exc); continue
        heap = queues[task['queue_id']] if queues is not None else ranked
        heapq.heappush(heap,(PRIORITIES[task['priority']],-score,tid,task))
    selected=[];gpu_used=False
    while len(selected)<budget:
        if queues is None:
            if not ranked: break
            heap = ranked
        else:
            next_index = next((i % len(QUEUE_IDS)
                for i in range(cursor, cursor + len(QUEUE_IDS))
                if queues[QUEUE_IDS[i % len(QUEUE_IDS)]]), None)
            if next_index is None: break
            heap = queues[QUEUE_IDS[next_index]]
        *_, row=heapq.heappop(heap)
        if row['resource']=='GPU_EXCLUSIVE' and gpu_used: continue
        if row.get('promotion_candidate_sha256') is not None:
            gate = resource_policy.promotion_decision(quality_receipts.get(row['id']),
                candidate_sha=row['promotion_candidate_sha256'], criteria=quality_policies.get(row['id']))
            if not gate['eligible']:
                decisions[row['id']] = gate['reasons'][0]; continue
        if measured is not None:
            reason = measured.reserve(row, quality_receipts.get(row['id']), quality_policies.get(row['id']))
            if reason:
                decisions[row['id']] = reason; continue
        if row['resource']=='GPU_EXCLUSIVE': gpu_used=True
        decisions[row['id']] = 'ADMITTED_MEASURED' if measured is not None else 'ADMITTED_LEGACY_PRESSURE_ONLY'
        selected.append(row)
        # The native claim row persists its sequence + queue_id atomically;
        # queue_cursor is derived from that last claim after an empty-queue skip.
        if queues is not None: cursor = (next_index + 1) % len(QUEUE_IDS)
    return selected


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
            or type(pid) is not int or pid<=1 or type(start) is not int or start<=0):continue
        identity=(pid,start)
        if identity in seen:raise AutoHold('HOLD_DUPLICATE_NATIVE_PROCESS')
        # A reused PID with a different start_tick is a stale/mixed snapshot,
        # not another simultaneously live OS worker.
        if pid in seen_pids:raise AutoHold('HOLD_CONFLICTING_NATIVE_PID_STARTTIME')
        seen.add(identity);seen_pids.add(pid);live.append(row)
    if len(live)!=requested:
        raise AutoHold('HOLD_UNVERIFIED_OS_PROCESS_COUNT')
    return live


def admit_native_tick(native, *, tasks, status, mode, memory_ratio, cpu_pressure=0.0,
                      gpu_available=False, instance_id=60509551, policy_snapshot=None, quality_receipts=None, quality_policies=None,
                      worker_cap=DEFAULT_WORKER_CAP, queue_cursor=None):
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
    decisions = {}; yield_requests = []
    # Validate telemetry before requesting cooperative yield. The callback only
    # signals an existing trainer; it must never kill or suspend it mid-step.
    if policy_snapshot is not None:
        try: resource_policy.Budget(policy_snapshot)
        except resource_policy.PolicyHold as exc:
            return {'state':str(exc), 'jobs_started':0}
        request_yield = getattr(native, 'request_soft_yield', None)
        if callable(request_yield):
            for request in resource_policy.soft_yield_requests(policy_snapshot):
                # STOP/lease/scope may change after telemetry validation. A soft
                # yield is a native state mutation, so fence EACH request before
                # invoking its callback, not just subsequent worker launches.
                if (native.owner_allowed() is not True or native.stop_active() is not False
                    or native.writer_lease() is not True):
                    return {'state':'HOLD_OWNER_STOP_OR_WRITER_LEASE_CHANGED',
                            'jobs_started':0, 'soft_yield_requests':yield_requests}
                requested = request_yield(**request) is True
                yield_requests.append({**request, 'requested':requested, 'yield_completed':False})
    ready=choose_ready(tasks,status=status,mode=mode,memory_ratio=memory_ratio,
                       cpu_pressure=cpu_pressure,gpu_available=gpu_available,
                       policy_snapshot=policy_snapshot,quality_receipts=quality_receipts,quality_policies=quality_policies,decision_log=decisions,
                       worker_cap=worker_cap,queue_cursor=queue_cursor)
    # Compute the same physical-process target for both newly READY and
    # already-running work. In NORMAL the desired pool is exactly 3 processes.
    # Pressure and OWNER STOP may reduce it: they are never overridden.
    target=_process_target(mode,memory_ratio,cpu_pressure,worker_cap)
    if target==0:return {'state':'HOLD_RESOURCE_PRESSURE','jobs_started':0}
    if not ready:
        # No new jobs does NOT necessarily mean the pool is finished. All
        # original TaskIDs can be claimed already. Read real OS processes and
        # replenish only after the native owner resolves orphaned claims.
        rows=native.process_readback()
        if not isinstance(rows,list):
            return {'state':'HOLD_NATIVE_PROCESS_READBACK','jobs_started':0}
        running=any(_in_flight(value) for value in status.values())
        if running and len(rows)>target:
            # Measured pressure can lower admission 3 -> 1. Never shrink
            # active workers through a restart/reconciliation callback:
            # existing jobs must yield at verified safe boundaries.
            return {'state':'HOLD_POOL_ABOVE_ADMITTED_TARGET',
                    'jobs_started':0,
                    'active_subexecutor_processes':len(rows)}
        if not running:
            return {'state':'NATIVE_QUEUE_POLICY_WAIT' if decisions else 'NATIVE_QUEUE_IDLE',
                    'jobs_started':0,'policy_decisions':decisions,
                    'soft_yield_requests':yield_requests,
                    'active_subexecutor_processes':len(rows)}
        try:
            workers=verify_distinct_native_processes(
                rows,requested=target,instance_id=instance_id)
        except AutoHold as exc:
            # Never infer that a missing PID means its claimed task is dead.
            # Reconciliation is a native fenced operation, not a timer/TTL.
            if str(exc) not in ('HOLD_OS_PROCESSES_NOT_LAUNCHED',
                                'HOLD_UNVERIFIED_OS_PROCESS_COUNT'):
                return {'state':str(exc),'jobs_started':0}
            reconcile=getattr(native,'reconcile_worker_claims',None)
            if not callable(reconcile):
                return {'state':'HOLD_OWNER_WORKER_RECONCILIATION_REQUIRED',
                        'jobs_started':0,'active_subexecutor_processes':len(rows)}
            if (native.owner_allowed() is not True
                or native.stop_active() is not False
                or native.writer_lease() is not True):
                return {'state':'HOLD_OWNER_STOP_OR_WRITER_LEASE_CHANGED',
                        'jobs_started':0}
            try:
                # True must mean the OneHost writer proved completed/dead
                # ownership and fenced every orphaned claim, not just a TTL.
                reconciled=reconcile() is True
            except Exception:
                reconciled=False
            if not reconciled:
                return {'state':'HOLD_OWNER_WORKER_RECONCILIATION_REQUIRED',
                        'jobs_started':0}
            if (native.owner_allowed() is not True
                or native.stop_active() is not False
                or native.writer_lease() is not True):
                return {'state':'HOLD_OWNER_STOP_OR_WRITER_LEASE_CHANGED',
                        'jobs_started':0}
            if policy_snapshot is not None:
                try: resource_policy.Budget(policy_snapshot)
                except resource_policy.PolicyHold as e:
                    return {'state':str(e),'jobs_started':0}
            if native.ensure_processes(target) is not True:
                return {'state':'HOLD_NATIVE_PROCESS_START','jobs_started':0}
            try:
                workers=verify_distinct_native_processes(
                    native.process_readback(),requested=target,
                    instance_id=instance_id)
            except AutoHold as e:
                return {'state':str(e),'jobs_started':0}
        return {'state':'NATIVE_POOL_CONTINUING','jobs_started':0,
                'active_subexecutor_processes':len(workers),
                'policy_decisions':decisions,
                'soft_yield_requests':yield_requests}
    # Resource admission can take time. The owner may revoke STOP/lease while
    # policy and READY work are evaluated. Fence native worker launch itself;
    # never infer ongoing ownership from the earlier check or a TTL.
    if (native.owner_allowed() is not True or native.stop_active() is not False
        or native.writer_lease() is not True):
        return {'state':'HOLD_OWNER_STOP_OR_WRITER_LEASE_CHANGED','jobs_started':0}
    # FAST HOT PATH: existing verified OS workers execute the next READY task
    # in-place. Never call the supervisor just to process another task.
    # This does not weaken the owner STOP/writer lease/native queue claims.
    try:
        observed=native.process_readback()
    except Exception:
        return {'state':'HOLD_NATIVE_PROCESS_READBACK','jobs_started':0}
    if not isinstance(observed,list):
        return {'state':'HOLD_NATIVE_PROCESS_READBACK','jobs_started':0}
    if len(observed)>target:
        # Resource pressure may lower the admitted target. Do not shrink or
        # restart busy workers until their owner-controlled safe yield.
        return {'state':'HOLD_POOL_ABOVE_ADMITTED_TARGET','jobs_started':0,
                'active_subexecutor_processes':len(observed)}
    if len(observed)==target:
        try:
            workers=verify_distinct_native_processes(
                observed,requested=target,instance_id=instance_id)
        except AutoHold as exc:
            return {'state':str(exc),'jobs_started':0}
    else:
        # A missing PID may still own an in-flight TaskID. The native owner
        # must reconcile/fence that durable claim before any replenishment.
        if any(_in_flight(value) for value in status.values()):
            reconcile=getattr(native,'reconcile_worker_claims',None)
            if not callable(reconcile):
                return {'state':'HOLD_OWNER_WORKER_RECONCILIATION_REQUIRED',
                        'jobs_started':0}
            if (native.owner_allowed() is not True
                or native.stop_active() is not False
                or native.writer_lease() is not True):
                return {'state':'HOLD_OWNER_STOP_OR_WRITER_LEASE_CHANGED',
                        'jobs_started':0}
            try:
                reconciled=reconcile() is True
            except Exception:
                reconciled=False
            if not reconciled:
                return {'state':'HOLD_OWNER_WORKER_RECONCILIATION_REQUIRED',
                        'jobs_started':0}
        if (native.owner_allowed() is not True
            or native.stop_active() is not False
            or native.writer_lease() is not True):
            return {'state':'HOLD_OWNER_STOP_OR_WRITER_LEASE_CHANGED',
                    'jobs_started':0}
        if policy_snapshot is not None:
            try: resource_policy.Budget(policy_snapshot)
            except resource_policy.PolicyHold as exc:
                return {'state':str(exc),'jobs_started':0}
        # Only the existing native supervisor may create replacement OS PIDs.
        if native.ensure_processes(target) is not True:
            return {'state':'HOLD_NATIVE_PROCESS_START','jobs_started':0}
        try:
            workers=verify_distinct_native_processes(
                native.process_readback(),requested=target,
                instance_id=instance_id)
        except AutoHold as exc:
            return {'state':str(exc),'jobs_started':0}
    receipts=[]
    for task in ready:
        if policy_snapshot is not None:
            try: resource_policy.Budget(policy_snapshot)
            except resource_policy.PolicyHold as exc:
                return {'state':str(exc), 'jobs_started':len(receipts),'receipts':receipts}
        if (native.owner_allowed() is not True or native.stop_active() is not False
            or native.writer_lease() is not True):
            return {'state':'HOLD_STOP_OR_LEASE_CHANGED','jobs_started':len(receipts),'receipts':receipts}
        # A failed duplicate probe is NOT proof that no durable claim exists.
        # Keep it separate from a claim-write failure for the next owner.
        try:
            duplicate=native.native_duplicate_check(task['id'])
        except Exception:
            return {'state':'HOLD_DUPLICATE_CHECK_UNKNOWN','task_id':task['id'],
                    'jobs_started':len(receipts),'receipts':receipts}
        if duplicate is not False:
            return {'state':'HOLD_DUPLICATE_OR_UNKNOWN_TASK',
                    'jobs_started':len(receipts),'receipts':receipts}
        # A successful duplicate lookup is read-only. It may block on I/O
        # while OWNER STOP, owner scope or the writer lease changes. Recheck
        # all three immediately BEFORE requesting a potentially durable claim.
        # Native OneHost must also fence atomically inside queue_claim itself.
        if (native.owner_allowed() is not True or native.stop_active() is not False
            or native.writer_lease() is not True):
            return {'state':'HOLD_STOP_OR_LEASE_CHANGED_BEFORE_CLAIM',
                    'task_id':task['id'],'jobs_started':len(receipts),
                    'receipts':receipts}
        try:
            # The native writer can commit a claim before an RPC response is lost.
            result=native.native_queue_claim(task,owner_pids=[x['pid'] for x in workers])
        except Exception:
            return {'state':'UNKNOWN_NATIVE_CLAIM','possible_unverified_claim':task['id'],
                    'jobs_started':len(receipts),'receipts':receipts}
        # The native writer may have committed a claim before its RPC returned.
        # Reject truthy but malformed IDs (including bool/int) before S03: no
        # retry and no false native receipt when a producer changes its schema.
        job_id = result.get('job_id') if isinstance(result, Mapping) else None
        if (type(job_id) is not str or not 1 <= len(job_id) <= 256
            or job_id != job_id.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in job_id)):
            return {'state':'UNKNOWN_NATIVE_CLAIM','possible_unverified_claim':task['id'],
                    'jobs_started':len(receipts),'receipts':receipts}
        try:
            proof=native.s03_readback(task['id'],job_id)
        except Exception:
            # The queue claim may already be durable. Preserve its identity and
            # earlier receipts for recovery; do not retry or claim another task.
            proof=None
        if (not isinstance(proof,Mapping) or proof.get('native_verified') is not True
            or proof.get('task_id')!=task['id'] or proof.get('job_id')!=job_id
            or not isinstance(proof.get('receipt_sha256'),str)
            or SHA.fullmatch(proof['receipt_sha256']) is None):
            return {'state':'HOLD_S03_NATIVE_READBACK','jobs_started':len(receipts),'possible_unverified_claim':task['id'],'receipts':receipts}
        receipts.append({'task_id':task['id'],'job_id':job_id,'pid_count':len(workers),
                         's03_sha256':proof['receipt_sha256']})
    return {'state':'NATIVE_QUEUE_READBACK_VERIFIED' if receipts else 'NATIVE_POOL_READY_IDLE',
            'jobs_started':len(receipts),
            'active_subexecutor_processes':len(workers),'receipts':receipts,
            'policy_decisions':decisions,'soft_yield_requests':yield_requests}
