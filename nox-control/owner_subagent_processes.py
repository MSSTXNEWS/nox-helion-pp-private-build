#!/usr/bin/env python3
"""NOX's in-process owner-dispatcher extension: one OS process per subagent.

Accepts any *resource-admitted* number of typed, dependency-checked tasks in a
single batch. Children share the EXISTING local NOX model over loopback; none
loads a second model, starts a trainer, owns the authoritative queue or S03.
Results are untrusted candidate answers, never privileged commands or PASS.
This module is not auto-installed and does not bypass owner STOP/writer lease.
The separate dispatcher mode uses owner-claimed submit/poll events, child-side
policy preparation, bounded heartbeats and a no-replay rule for uncertain work.
"""
from __future__ import annotations

import json
import ctypes
import math
import multiprocessing as mp
import os
import queue
import re
import signal
import sys
import threading
import time
import urllib.request
from collections import deque

SCHEMA = 'NOX_OWNER_SUBAGENTS_BATCH_V1'
TASK_ID = re.compile(r'^[A-Za-z0-9_.-]{1,128}$')
SAFE_ROLE = re.compile(r'^[A-Za-z][A-Za-z0-9_.-]{0,63}$')
MAX_TASK_TEXT_BYTES = 8192
MAX_OUTPUT_BYTES = 16384
HOSTS = {'127.0.0.1', 'localhost'}
DISPATCHER_CONTEXT_KEYS = {'policy', 'operation', 'claim'}
POLICY_REFERENCE_KEYS = {'path', 'sha256'}
CLAIM_ID = re.compile(r'^[a-f0-9]{24}$')
SHA256 = re.compile(r'^[a-f0-9]{64}$')
# The original pool has one outbox. Never reuse it across batches: a failed
# long-running request may leave an old RESULT with a replayed TaskID.
_POOL_CLAIM_LOCK = threading.Lock()


class GateError(RuntimeError):
    pass


def validate(batch):
    """Validate an arbitrary-length DAG; no fixed 30/60 task limit."""
    if not isinstance(batch, dict) or batch.get('schema') != SCHEMA:
        raise GateError('HOLD_BATCH_SCHEMA')
    roles = batch.get('subagents')
    tasks = batch.get('tasks')
    if not isinstance(roles, list) or not roles or not isinstance(tasks, list):
        raise GateError('HOLD_BATCH_SHAPE')
    if any(not isinstance(x, str) or not SAFE_ROLE.fullmatch(x) for x in roles):
        raise GateError('HOLD_ROLE_ID')
    if len(set(roles)) != len(roles):
        raise GateError('HOLD_ROLE_DUPLICATE')
    indexed = {}
    for t in tasks:
        if not isinstance(t, dict) or set(t) != {'id', 'subagent', 'task', 'depends_on'}:
            raise GateError('HOLD_TASK_SCHEMA')
        tid, role, instruction, deps = (t[k] for k in ('id','subagent','task','depends_on'))
        if not isinstance(tid, str) or not TASK_ID.fullmatch(tid) or tid in indexed:
            raise GateError('HOLD_TASK_ID')
        if role not in roles or not isinstance(instruction,str) or not instruction.strip() or len(instruction.encode()) > MAX_TASK_TEXT_BYTES:
            raise GateError('HOLD_TASK_SCOPE')
        if not isinstance(deps,list) or len(set(map(str,deps))) != len(deps) or any(not isinstance(x,str) for x in deps):
            raise GateError('HOLD_TASK_DEPS')
        indexed[tid] = t
    indegree = {k: 0 for k in indexed}
    edges = {k: [] for k in indexed}
    for tid, t in indexed.items():
        for dep in t['depends_on']:
            if dep == tid or dep not in indexed:
                raise GateError('HOLD_TASK_DEPENDENCY')
            indegree[tid] += 1
            edges[dep].append(tid)
    ready = deque(k for k,v in indegree.items() if v == 0)
    seen = 0
    while ready:
        k = ready.popleft()
        seen += 1
        for v in edges[k]:
            indegree[v] -= 1
            if indegree[v] == 0:
                ready.append(v)
    if seen != len(tasks):
        raise GateError('HOLD_TASK_CYCLE')
    return indexed


def _model_reply(task, url, timeout):
    """Fixed request to one owner-approved local existing model; NO tool calls."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme != 'http' or parsed.hostname not in HOSTS or parsed.path != '/v1/chat/completions' or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise GateError('HOLD_NONLOCAL_OR_UNREVIEWED_MODEL_URL')
    if not parsed.port or parsed.port < 1 or parsed.port > 65535:
        raise GateError('HOLD_MODEL_PORT')
    payload = {'model': 'nox', 'stream': False, 'temperature': 0.2, 'max_tokens': 512,
               'messages': [
                   {'role': 'system', 'content': 'You are an isolated NOX technical subagent. You may only analyze this task and return evidence-based suggestions. Do not claim to have run tools or changed code. No shell, credentials, network or privileged actions. Respond concisely in Russian.'},
                   {'role': 'user', 'content': task['task']}]}
    data = json.dumps(payload,ensure_ascii=False).encode()
    req = urllib.request.Request(url,data=data,method='POST',headers={'Content-Type':'application/json'})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):
            raise GateError('HOLD_MODEL_REDIRECT')
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(req,timeout=timeout) as response:
            if response.status != 200:
                raise GateError('HOLD_MODEL_HTTP')
            body = response.read(MAX_OUTPUT_BYTES+1)
    except (OSError, ValueError) as exc:
        raise GateError('HOLD_MODEL_UNAVAILABLE') from exc
    if len(body)>MAX_OUTPUT_BYTES:
        raise GateError('HOLD_MODEL_RESPONSE_SIZE')
    try:
        answer = json.loads(body)['choices'][0]['message']['content']
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        raise GateError('HOLD_MODEL_RESPONSE_SCHEMA') from exc
    if not isinstance(answer,str) or not answer.strip():
        raise GateError('HOLD_EMPTY_CANDIDATE')
    return answer


def _arm_parent_death_signal(expected_parent_pid):
    """Arrange prompt child exit when the dispatcher parent disappears."""
    if os.getppid() != expected_parent_pid:
        os._exit(70)
    if sys.platform == 'linux':
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        # Close the race where the parent exits between getppid() and prctl().
        if os.getppid() != expected_parent_pid:
            os._exit(70)


def _watch_parent(role, pid, expected_parent_pid, outbox, stopped):
    """Emit epoch heartbeats and bound non-Linux parent-death detection."""
    while not stopped.wait(1.0):
        if os.getppid() != expected_parent_pid:
            os._exit(70)
        try:
            outbox.put({'kind': 'HEARTBEAT', 'role': role, 'pid': pid,
                        'at': time.time()})
        except (OSError, ValueError):
            return


def _worker(role, inbox, outbox, local_model_url, timeout,
            worker_prepare=None, expected_parent_pid=None):
    # These are CPU/IPC subagent processes; the existing NOX model stays on GPU0.
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    if expected_parent_pid is not None:
        try:
            _arm_parent_death_signal(expected_parent_pid)
        except OSError:
            return
    outbox.put({'kind':'READY','role':role,'pid':os.getpid(),
                'heartbeat_at':time.time()})
    heartbeat_stop = None
    if worker_prepare is not None:
        heartbeat_stop = threading.Event()
        threading.Thread(target=_watch_parent,
                         args=(role, os.getpid(), expected_parent_pid, outbox, heartbeat_stop),
                         name='NOX_SUBAGENT_HEARTBEAT_'+role, daemon=True).start()
    while True:
        try:
            item = inbox.get(timeout=1 if worker_prepare is not None else None)
        except queue.Empty:
            continue
        if item is None:
            if heartbeat_stop is not None:
                heartbeat_stop.set()
            return
        started = time.monotonic()
        try:
            native_observation = None
            if worker_prepare is not None:
                prepared, native_observation = worker_prepare(item)
                context = item.get('_native_context')
                ack = (native_observation.get('policy_ack')
                       if isinstance(native_observation, dict) else None)
                worker = (native_observation.get('worker')
                          if isinstance(native_observation, dict) else None)
                if (not isinstance(prepared, dict)
                        or prepared.get('id') != item.get('id')
                        or prepared.get('subagent') != item.get('subagent')
                        or prepared.get('depends_on') != item.get('depends_on')
                        or prepared.get('_native_context') != context
                        or not isinstance(prepared.get('task'), str)
                        or len(prepared['task'].encode('utf-8')) > MAX_TASK_TEXT_BYTES
                        or not isinstance(context, dict)
                        or not isinstance(ack, dict)
                        or ack.get('sha256') != context.get('policy', {}).get('sha256')
                        or ack.get('full_file_read') is not True
                        or not isinstance(worker, dict)
                        or worker.get('pid') != os.getpid()
                        or native_observation.get('claim') != context.get('claim')
                        or len(json.dumps(native_observation, ensure_ascii=False,
                                          allow_nan=False).encode('utf-8')) > 65536):
                    raise GateError('HOLD_SUBAGENT_WORKER_PROOF')
                item = prepared
            result = _model_reply(item,local_model_url,timeout)
            out = {'state':'CANDIDATE_NOT_APPLIED','answer':result}
            if worker_prepare is not None:
                out['native_observation'] = native_observation
        except Exception as exc:
            out = {'state':str(exc) if isinstance(exc,GateError) else 'HOLD_SUBAGENT_EXCEPTION'}
        outbox.put({'kind':'RESULT','role':role,'pid':os.getpid(),
                    'id':item['id'],'elapsed_ms':round((time.monotonic()-started)*1000),**out})


class Subagents:
    def __init__(self, roles, *, model_url='http://127.0.0.1:8081/v1/chat/completions',
                 timeout=60, worker_prepare=None):
        if not isinstance(roles,list) or not roles or any(not isinstance(x,str) or not SAFE_ROLE.fullmatch(x) for x in roles) or len(set(roles)) != len(roles):
            raise GateError('HOLD_ROLE_ID')
        if not isinstance(timeout,(int,float)) or not 1 <= timeout <= 300:
            raise GateError('HOLD_TIMEOUT')
        if worker_prepare is not None and (
                not callable(worker_prepare)
                or getattr(worker_prepare, '__module__', None) != 'owner_subagent_dispatcher'
                or getattr(worker_prepare, '__name__', None) != 'worker_input'):
            raise GateError('HOLD_SUBAGENT_WORKER_PREPARE')
        self.roles = roles
        self.url = model_url
        self.timeout = timeout
        self.worker_prepare = worker_prepare
        self._persistent = worker_prepare is not None
        self.ctx = mp.get_context('spawn')
        self._abi_lock = threading.RLock()
        self.active = {}
        self.heartbeats = {}
        self._active_started = {}
        self._active_context = {}
        self._submitted_ids = set()
        self._terminal_ids = set()
        self._pending_events = deque()
        self._new_channels()

    def _new_channels(self):
        self.outbox = self.ctx.Queue()
        self.inboxes = {r:self.ctx.Queue() for r in self.roles}
        self.processes = {}
        self.heartbeats = {}
        self._shutdown_complete = False

    def __enter__(self):
        try:
            self._start_workers()
            return self
        except BaseException:
            self.__exit__(None,None,None)
            raise

    def _accept_heartbeat(self, msg):
        if not isinstance(msg, dict) or msg.get('kind') != 'HEARTBEAT':
            return False
        role, pid, at = msg.get('role'), msg.get('pid'), msg.get('at')
        process = self.processes.get(role)
        if (process is None or pid != process.pid or type(at) not in (int, float)
                or not math.isfinite(at) or at <= 0 or at > time.time()+5):
            return True  # Consume malformed/stale heartbeat without treating it as work.
        self.heartbeats[role] = max(float(at), self.heartbeats.get(role, 0.0))
        return True

    def _start_workers(self):
        for role in self.roles:
            p = self.ctx.Process(target=_worker,
                args=(role,self.inboxes[role],self.outbox,self.url,self.timeout,
                      self.worker_prepare,os.getpid()),
                name='NOX_SUBAGENT_'+role)
            p.start()
            self.processes[role] = p
        confirmed = {}
        deadline = time.monotonic()+15
        while len(confirmed) < len(self.roles):
            left = deadline-time.monotonic()
            if left <= 0:
                raise GateError('HOLD_SUBAGENT_PROCESS_START')
            try:
                msg = self.outbox.get(timeout=min(left,1))
            except queue.Empty:
                if not all(p.is_alive() for p in self.processes.values()):
                    raise GateError('HOLD_SUBAGENT_PROCESS_EXIT')
                continue
            if self._accept_heartbeat(msg):
                continue
            if not isinstance(msg, dict) or msg.get('kind')!='READY' or msg.get('role') not in self.processes:
                raise GateError('HOLD_SUBAGENT_READY_SCHEMA')
            role = msg['role']
            if role in confirmed or msg.get('pid') != self.processes[role].pid:
                raise GateError('HOLD_SUBAGENT_PID_MISMATCH')
            heartbeat_at = msg.get('heartbeat_at')
            if (type(heartbeat_at) not in (int, float)
                    or not math.isfinite(heartbeat_at) or heartbeat_at <= 0
                    or heartbeat_at > time.time()+5):
                raise GateError('HOLD_SUBAGENT_HEARTBEAT_START')
            confirmed[role] = msg['pid']
            self.heartbeats[role] = float(heartbeat_at)
        if len(set(confirmed.values())) != len(self.roles):
            raise GateError('HOLD_SUBAGENT_NONUNIQUE_PID')

    def _persistent_task(self, task):
        if not self._persistent:
            raise GateError('HOLD_SUBAGENT_DISPATCHER_MODE')
        if (not isinstance(task, dict)
                or set(task) != {'id', 'subagent', 'task', 'depends_on', '_native_context'}):
            raise GateError('HOLD_SUBAGENT_TASK_SCHEMA')
        tid, role, instruction = task['id'], task['subagent'], task['task']
        context = task['_native_context']
        if (not isinstance(tid, str) or not TASK_ID.fullmatch(tid)
                or role not in self.roles or not isinstance(instruction, str)
                or not instruction.strip() or len(instruction.encode('utf-8')) > MAX_TASK_TEXT_BYTES
                or type(task['depends_on']) is not list or task['depends_on']):
            raise GateError('HOLD_SUBAGENT_TASK_SCOPE')
        if (not isinstance(context, dict) or set(context) != DISPATCHER_CONTEXT_KEYS
                or context.get('operation') != role
                or not isinstance(context.get('claim'), str)
                or not CLAIM_ID.fullmatch(context['claim'])):
            raise GateError('HOLD_SUBAGENT_NATIVE_CONTEXT')
        policy = context.get('policy')
        if (not isinstance(policy, dict) or set(policy) != POLICY_REFERENCE_KEYS
                or not isinstance(policy.get('path'), str) or not policy['path'].startswith('/')
                or not isinstance(policy.get('sha256'), str)
                or not SHA256.fullmatch(policy['sha256'])):
            raise GateError('HOLD_SUBAGENT_POLICY_REFERENCE')

    def _failure(self, role, state):
        tid = self.active.pop(role, None)
        if tid is None or tid in self._terminal_ids:
            return False
        self._terminal_ids.add(tid)
        started = self._active_started.pop(role, time.monotonic())
        self._active_context.pop(role, None)
        process = self.processes.get(role)
        event = {'kind': 'RESULT', 'role': role,
                 'pid': getattr(process, 'pid', None), 'id': tid,
                 'elapsed_ms': max(0, round((time.monotonic()-started)*1000)),
                 'state': state}
        self._pending_events.append(event)
        return True

    def _notice_dead_workers(self):
        for role, process in list(self.processes.items()):
            try:
                alive = process.is_alive()
            except Exception:
                alive = False
            if not alive and role in self.active:
                # A dead child may have completed the model call but failed
                # before a complete IPC result was synchronized. Never accept
                # a late queue fragment or replay this task.
                self._failure(role, 'HOLD_SUBAGENT_PROCESS_EXIT')

    def _replace_idle_dead_pool(self):
        """Replace only proved-dead idle roles; retain every live peer and its IPC."""
        self._notice_dead_workers()
        dead = [role for role, process in self.processes.items()
                if not process.is_alive()]
        if not dead:
            return
        # An in-flight or just-fenced result must first be read by the owner.
        # Never restart a worker to replay an uncertain submitted TaskID.
        if self.active or self._pending_events:
            raise GateError('HOLD_SUBAGENT_POOL_NOT_READY')
        for role in dead:
            previous = self.processes[role]
            if previous.is_alive():
                continue
            try:
                previous.join(timeout=0)
            except (AssertionError, OSError, ValueError) as exc:
                raise GateError('HOLD_SUBAGENT_PROCESS_REAP') from exc
            inbound = self.ctx.Queue()
            replacement = None
            try:
                replacement = self.ctx.Process(
                    target=_worker,
                    args=(role, inbound, self.outbox, self.url, self.timeout,
                          self.worker_prepare, os.getpid()),
                    name='NOX_SUBAGENT_'+role)
                replacement.start()
                deadline = time.monotonic() + 15
                while True:
                    left = deadline - time.monotonic()
                    if left <= 0 or not replacement.is_alive():
                        raise GateError('HOLD_SUBAGENT_PROCESS_START')
                    try:
                        msg = self.outbox.get(timeout=min(left, 1))
                    except queue.Empty:
                        continue
                    if self._accept_heartbeat(msg):
                        continue
                    if (not isinstance(msg, dict) or msg.get('kind') != 'READY'
                            or msg.get('role') != role
                            or msg.get('pid') != replacement.pid):
                        raise GateError('HOLD_SUBAGENT_READY_SCHEMA')
                    at = msg.get('heartbeat_at')
                    if (type(at) not in (int, float) or not math.isfinite(at)
                            or at <= 0 or at > time.time()+5):
                        raise GateError('HOLD_SUBAGENT_HEARTBEAT_START')
                    if (replacement.pid == previous.pid
                            or replacement.pid in {p.pid for name, p in self.processes.items()
                                                   if name != role}):
                        raise GateError('HOLD_SUBAGENT_PID_REUSE')
                    break
            except BaseException:
                # Kill only this unadmitted replacement; never tear down peers.
                if replacement is not None and replacement.pid is not None:
                    if replacement.is_alive():
                        replacement.terminate()
                        replacement.join(timeout=2)
                    if replacement.is_alive() and hasattr(replacement, 'kill'):
                        replacement.kill()
                        replacement.join(timeout=2)
                inbound.close()
                raise
            old_inbound = self.inboxes[role]
            self.processes[role] = replacement
            self.inboxes[role] = inbound
            self.heartbeats[role] = float(at)
            old_inbound.close()

    def submit(self, task):
        """Submit one owner-claimed job; uncertain IDs stay fenced for pool life."""
        self._persistent_task(task)
        # Queue.put serializes asynchronously. Snapshot the exact admitted
        # claim/policy before enqueue so a caller cannot mutate it afterward.
        try:
            task = json.loads(json.dumps(task, ensure_ascii=False, allow_nan=False))
        except (TypeError, ValueError) as exc:
            raise GateError('HOLD_SUBAGENT_TASK_SCHEMA') from exc
        tid, role = task['id'], task['subagent']
        with self._abi_lock:
            if tid in self._submitted_ids or tid in self._terminal_ids:
                raise GateError('HOLD_SUBAGENT_TASK_REUSE')
            self._notice_dead_workers()
            if self._pending_events:
                raise GateError('HOLD_SUBAGENT_POOL_NOT_READY')
            self._replace_idle_dead_pool()
            if role in self.active:
                raise GateError('HOLD_SUBAGENT_WORKER_BUSY')
            process = self.processes.get(role)
            if process is None or not process.is_alive():
                raise GateError('HOLD_SUBAGENT_PROCESS_EXIT')
            self._submitted_ids.add(tid)
            self.active[role] = tid
            self._active_started[role] = time.monotonic()
            self._active_context[role] = task['_native_context']
            try:
                self.inboxes[role].put(task)
            except Exception as exc:
                self._failure(role, 'HOLD_SUBAGENT_SUBMIT_UNCERTAIN')
                raise GateError('HOLD_SUBAGENT_SUBMIT_UNCERTAIN') from exc
        return True

    def _accept_result(self, event, *, allow_exited=False):
        if not isinstance(event, dict):
            if len(self.active) == 1:
                self._failure(next(iter(self.active)), 'HOLD_SUBAGENT_RESULT_IDENTITY')
                return self._pending_events.popleft()
            for role in list(self.active):
                self._failure(role, 'HOLD_SUBAGENT_RESULT_IDENTITY')
            return self._pending_events.popleft() if self._pending_events else None
        role = event.get('role')
        if role not in self.active:
            return None  # Stale RESULT from an already-fenced task.
        assigned_id = self.active[role]
        process = self.processes.get(role)
        if (not process or (not process.is_alive() and not allow_exited)
                or event.get('kind') != 'RESULT'
                or event.get('pid') != process.pid
                or event.get('id') != assigned_id):
            self._failure(role, 'HOLD_SUBAGENT_RESULT_IDENTITY')
            return self._pending_events.popleft()
        common = {'kind', 'role', 'pid', 'id', 'elapsed_ms', 'state'}
        elapsed, state = event.get('elapsed_ms'), event.get('state')
        valid = type(elapsed) is int and elapsed >= 0
        if state == 'CANDIDATE_NOT_APPLIED':
            answer = event.get('answer')
            observation = event.get('native_observation')
            task_context = getattr(self, '_active_context', {}).get(role)
            ack = observation.get('policy_ack') if isinstance(observation, dict) else None
            worker = observation.get('worker') if isinstance(observation, dict) else None
            valid = (valid and set(event) == common | {'answer', 'native_observation'}
                     and isinstance(answer, str) and bool(answer.strip())
                     and len(answer.encode('utf-8')) <= MAX_OUTPUT_BYTES
                     and isinstance(observation, dict)
                     and isinstance(task_context, dict)
                     and observation.get('claim') == task_context.get('claim')
                     and isinstance(ack, dict)
                     and ack.get('sha256') == task_context.get('policy', {}).get('sha256')
                     and ack.get('full_file_read') is True
                     and isinstance(worker, dict) and worker.get('pid') == process.pid)
        elif isinstance(state, str) and state.startswith('HOLD_') and len(state) <= 128:
            valid = valid and set(event) == common
        else:
            valid = False
        if not valid:
            self._failure(role, 'HOLD_SUBAGENT_RESULT_SCHEMA')
            return self._pending_events.popleft()
        self.active.pop(role, None)
        self._active_started.pop(role, None)
        self._active_context.pop(role, None)
        self._terminal_ids.add(assigned_id)
        return event

    def poll(self, timeout=0):
        """Return one task-bound event; heartbeat messages stay internal."""
        if not self._persistent:
            raise GateError('HOLD_SUBAGENT_DISPATCHER_MODE')
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 <= timeout <= 300:
            raise GateError('HOLD_SUBAGENT_POLL_TIMEOUT')
        deadline = time.monotonic()+timeout
        with self._abi_lock:
            while True:
                self._notice_dead_workers()
                if self._pending_events:
                    return self._pending_events.popleft()
                left = deadline-time.monotonic()
                if left <= 0 and timeout > 0:
                    return None
                try:
                    event = (self.outbox.get_nowait() if timeout == 0
                             else self.outbox.get(timeout=min(left, 0.25)))
                except queue.Empty:
                    if timeout == 0:
                        return None
                    continue
                if self._accept_heartbeat(event):
                    continue
                accepted = self._accept_result(event)
                if accepted is not None:
                    return accepted

    def run(self,batch, *, stop_active, authorize, lease_current):
        """One request, any task count; only candidates, not queue/S03 commits."""
        if getattr(self, '_persistent', False):
            raise GateError('HOLD_SUBAGENT_DISPATCHER_MODE')
        tasks = validate(batch)
        if batch['subagents'] != self.roles:
            raise GateError('HOLD_BATCH_ROLE_DRIFT')
        if not all(callable(f) for f in (stop_active, authorize, lease_current)):
            raise GateError('HOLD_OWNER_GATE_CALLBACKS')
        def admitted():
            try:
                return stop_active() is False and authorize() is True and lease_current() is True
            except Exception:
                return False
        if not admitted():
            raise GateError('HOLD_OWNER_STOP_OR_LEASE')
        # One execution batch per OS pool. After timeout, owner STOP or a
        # revoked lease, an in-flight worker can still enqueue an old RESULT.
        # Its PID, role and TaskID would otherwise match a subsequent replay.
        # Atomically refuse reuse; a new explicit pool gets fresh IPC queues.
        with _POOL_CLAIM_LOCK:
            if getattr(self, '_batch_used', False):
                raise GateError('HOLD_SUBAGENT_POOL_REUSE')
            self._batch_used = True
        remaining = dict(tasks)
        outcomes = {}
        active = set()
        active_roles = {}  # Job ID must remain bound to its assigned OS worker role.
        active_started = {}  # Preserve original deadline for each in-flight job.
        busy_roles = set()
        while remaining or active:
            # Re-check gates before *each* dispatch, not only at batch start.
            if not admitted():
                raise GateError('HOLD_OWNER_GATE_CHANGED')
            progressed = False
            for tid,t in list(remaining.items()):
                if t['subagent'] in busy_roles or any(dep not in outcomes for dep in t['depends_on']):
                    continue
                if any(outcomes[d]['state']!='CANDIDATE_NOT_APPLIED' for d in t['depends_on']):
                    outcomes[tid]={'id':tid,'state':'HOLD_DEPENDENCY'}
                    del remaining[tid]
                    progressed = True
                    continue
                self.inboxes[t['subagent']].put(t)
                active_started[tid] = time.monotonic()
                busy_roles.add(t['subagent'])
                active.add(tid)
                active_roles[tid] = t['subagent']
                del remaining[tid]
                progressed = True
            if active:
                # A blocking result read must not mask a manual owner STOP or
                # a revoked writer lease for up to the model timeout (300s).
                # Poll only the existing IPC outbox; never add another daemon.
                # Unrelated fast responses may never extend a stalled job.
                deadline = min(active_started[job] + self.timeout + 5 for job in active)
                while True:
                    if not admitted():
                        raise GateError('HOLD_OWNER_GATE_CHANGED')
                    remaining_wait = deadline - time.monotonic()
                    if remaining_wait <= 0:
                        raise GateError('HOLD_SUBAGENT_TIMEOUT')
                    try:
                        event = self.outbox.get(timeout=min(remaining_wait, 0.25))
                        if time.monotonic() >= deadline:
                            raise GateError('HOLD_SUBAGENT_TIMEOUT')
                        break
                    except queue.Empty:
                        continue
                # The lease/STOP may change while an outbox event is in flight.
                # Do not return even a candidate as accepted after revocation.
                if not admitted():
                    raise GateError('HOLD_OWNER_GATE_CHANGED')
                if not isinstance(event, dict):
                    raise GateError('HOLD_SUBAGENT_RESULT_IDENTITY')
                tid = event.get('id')
                role = event.get('role')
                if (event.get('kind')!='RESULT' or tid not in active or role != active_roles.get(tid)
                    or role not in busy_roles or event.get('pid')!=self.processes[role].pid):
                    raise GateError('HOLD_SUBAGENT_RESULT_IDENTITY')
                # An in-process worker result is untrusted candidate evidence, not
                # permission to claim DONE/LIVE/INSTALLED or unlock dependents.
                common = {'kind', 'role', 'pid', 'id', 'elapsed_ms', 'state'}
                elapsed = event.get('elapsed_ms')
                state = event.get('state')
                if type(elapsed) is not int or elapsed < 0:
                    raise GateError('HOLD_SUBAGENT_RESULT_SCHEMA')
                if state == 'CANDIDATE_NOT_APPLIED':
                    answer = event.get('answer')
                    if (set(event) != common | {'answer'} or not isinstance(answer, str)
                        or not answer.strip() or len(answer.encode('utf-8')) > MAX_OUTPUT_BYTES):
                        raise GateError('HOLD_SUBAGENT_RESULT_SCHEMA')
                elif (not isinstance(state, str) or not state.startswith('HOLD_')
                      or len(state) > 128 or set(event) != common):
                    raise GateError('HOLD_SUBAGENT_RESULT_SCHEMA')
                outcomes[tid] = event
                active.remove(tid)
                del active_started[tid]
                del active_roles[tid]
                busy_roles.remove(role)
            elif not progressed and remaining:
                raise GateError('HOLD_SUBAGENT_DISPATCH_DEADLOCK')
        return {'schema': 'NOX_SUBAGENT_SOURCE_CANDIDATES_V1', 'processes': {r:p.pid for r,p in self.processes.items()},
                'task_count': len(tasks), 'results': outcomes, 'live_onehost_deployed': False,
                'queue_committed': False, 'model_weights_changed': False}

    def shutdown_and_drain(self):
        """Stop workers, then validate every queued task result before closing IPC."""
        with self._abi_lock:
            if getattr(self, '_shutdown_complete', False):
                return []
            for box in self.inboxes.values():
                try: box.put_nowait(None)
                except Exception: pass
            for process in self.processes.values():
                process.join(timeout=2)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=2)
                if process.is_alive() and hasattr(process, 'kill'):
                    process.kill()
                    process.join(timeout=2)

            events = []
            while True:
                try:
                    event = self.outbox.get_nowait()
                except queue.Empty:
                    break
                except (EOFError, OSError, ValueError):
                    break
                if self._accept_heartbeat(event):
                    continue
                accepted = self._accept_result(event, allow_exited=True)
                if accepted is not None:
                    events.append(accepted)
                while self._pending_events:
                    events.append(self._pending_events.popleft())

            # Anything still active has no complete, validated result. Fence it
            # as HOLD so the owner cannot retry the same submitted task.
            for role in list(self.active):
                process = self.processes.get(role)
                reason = ('HOLD_SUBAGENT_PROCESS_EXIT'
                          if process is None or not process.is_alive()
                          else 'HOLD_SUBAGENT_SHUTDOWN_UNRESOLVED')
                self._failure(role, reason)
            while self._pending_events:
                events.append(self._pending_events.popleft())
            for channel in [*self.inboxes.values(), self.outbox]:
                try: channel.close()
                except Exception: pass
            self._shutdown_complete = True
            return events

    def __exit__(self,*_):
        self.shutdown_and_drain()


if __name__=='__main__':
    # Only an explicit owner-native binding should ever call Subagents.run.
    # No CLI route accepts arbitrary instructions or bypasses STOP/lease.
    print('NOX_SUBAGENTS_SOURCE_AVAILABLE_NOT_NATIVE_INSTALLED')

