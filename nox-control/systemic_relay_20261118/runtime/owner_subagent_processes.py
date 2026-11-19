#!/usr/bin/env python3
"""NOX's in-process owner-dispatcher extension: one OS process per subagent.

Accepts any *resource-admitted* number of typed, dependency-checked tasks in a
single batch. Children share the EXISTING local NOX model over loopback; none
loads a second model, starts a trainer, owns the authoritative queue or S03.
Results are untrusted candidate answers, never privileged commands or PASS.
This module is not auto-installed and does not bypass owner STOP/writer lease.
"""
from __future__ import annotations

import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import signal
import struct
import threading
import queue
import re
import time
import urllib.request
from collections import deque

SCHEMA = 'NOX_OWNER_SUBAGENTS_BATCH_V1'
TASK_ID = re.compile(r'^[A-Za-z0-9_.-]{1,128}$')
SAFE_ROLE = re.compile(r'^[A-Za-z][A-Za-z0-9_.-]{0,63}$')
MAX_TASK_TEXT_BYTES = 8192
MAX_OUTPUT_BYTES = 16384
HEARTBEAT_STALE_SEC = 45
MAX_IPC_BYTES = 4*1024*1024
HOSTS = {'127.0.0.1', 'localhost'}


class GateError(RuntimeError):
    pass


def _identity(pid):
    try:
        fields = Path('/proc', str(int(pid)), 'stat').read_text().split(') ', 1)[1].split()
        if fields[0] == 'Z':
            return None
        return {'pid': int(pid), 'ppid': int(fields[1]),
                'process_starttime': int(fields[19])}
    except (OSError, ValueError, IndexError):
        return None


class _WorkerOutbox:
    """One child writer; serialize its heartbeat and result threads."""
    def __init__(self, connection):
        self.connection = connection
        self.lock = None  # Initialized in the spawned child, never pickled.

    def put(self, value):
        if self.lock is None:
            self.lock = threading.Lock()
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False,
                         separators=(',',':')).encode()
        if len(raw) > MAX_IPC_BYTES:
            raise GateError('HOLD_SUBAGENT_IPC_SIZE')
        with self.lock:
            # Connection.send_bytes uses a signed network-order 32-bit length
            # for these bounded frames. Only the child may block on the pipe.
            self.connection.send_bytes(raw)


class _Cancellation:
    """Cooperative flag only; a dead child cannot leave a semaphore locked."""
    def __init__(self, context):
        self.value = context.RawValue('b', 0)

    def set(self):
        self.value.value = 1

    def clear(self):
        self.value.value = 0

    def is_set(self):
        return self.value.value != 0


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


def _model_reply(task, url, timeout, return_metadata=False):
    """Fixed request to one owner-approved local existing model; NO tool calls."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme != 'http' or parsed.hostname not in HOSTS or parsed.path != '/v1/chat/completions' or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise GateError('HOLD_NONLOCAL_OR_UNREVIEWED_MODEL_URL')
    if not parsed.port or parsed.port < 1 or parsed.port > 65535:
        raise GateError('HOLD_MODEL_PORT')
    payload = {'model': 'nox', 'stream': False, 'temperature': 0.2, 'max_tokens': 256,
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
        value = json.loads(body)
        answer = value['choices'][0]['message']['content']
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        raise GateError('HOLD_MODEL_RESPONSE_SCHEMA') from exc
    if not isinstance(answer,str) or not answer.strip():
        raise GateError('HOLD_EMPTY_CANDIDATE')
    if not return_metadata:
        return answer
    usage = value.get('usage') if isinstance(value.get('usage'), dict) else {}
    return answer, {'endpoint': url, 'model': value.get('model'),
                    'usage_counts': {key: usage[field] for key, field in (
                        ('input', 'prompt_tokens'), ('output', 'completion_tokens'), ('total', 'total_tokens'))
                        if type(usage.get(field)) is int and usage[field] >= 0},
                    'finish_reason': value['choices'][0].get('finish_reason'),
                    'weights_identity_verified': False}


def _worker(role, inbox, outbox, local_model_url, timeout, cancellation):
    # These are CPU/IPC subagent processes; the existing NOX model stays on GPU0.
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    parent = os.getppid()
    # Linux parent-death signal closes the HTTP client even while inference is
    # blocked; a crashed director cannot leave orphan workers using its slot.
    import ctypes
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        return
    if os.getppid() != parent:
        return
    outbox.put({'kind':'READY','role':role,'pid':os.getpid()})
    last_heartbeat = time.monotonic()
    while True:
        if cancellation.is_set():
            return  # Cooperative idle shutdown; no signal/kill fallback.
        if os.getppid() != parent:
            return  # Never leave orphan model clients after director death.
        try:
            item = inbox.get(timeout=1)
        except queue.Empty:
            if time.monotonic()-last_heartbeat >= 5:
                outbox.put({'kind':'HEARTBEAT','role':role,'pid':os.getpid(),
                            'at':time.time()})
                last_heartbeat = time.monotonic()
            continue
        if item is None:
            return
        started = time.monotonic()
        try:
            proof = None
            request = item
            if '_native_project_context' in item:
                from owner_project_executor import execute, ProjectHold
                def heartbeat():
                    outbox.put({'kind':'HEARTBEAT','role':role,'pid':os.getpid(), 'at':time.time()})
                heartbeat_stop = threading.Event()
                def keep_alive():
                    while not heartbeat_stop.wait(5):
                        heartbeat()
                heartbeat_thread = threading.Thread(target=keep_alive, name='project-heartbeat', daemon=True)
                heartbeat_thread.start()
                try:
                    if 'plan_sha256' not in item['_native_project_context']['reference']:
                        from owner_project_model_bridge import execute as plan_and_prepare
                        out = plan_and_prepare(item, cancelled=cancellation.is_set, heartbeat=heartbeat)
                    else:
                        out = execute(item, cancelled=cancellation.is_set, heartbeat=heartbeat)
                except ProjectHold as exc:
                    out = {'state':str(exc), 'passed':False, 'project_source_changed':False}
                finally:
                    heartbeat_stop.set()
                    heartbeat_thread.join(timeout=.2)
            elif '_native_leaf_context' in item:
                from owner_subagent_dispatcher import execute_native_leaf
                out = execute_native_leaf(item)
            else:
                if '_native_context' in item:
                    from owner_subagent_dispatcher import worker_input
                    request, proof = worker_input(item)
                result, model = _model_reply(request,local_model_url,timeout,return_metadata=True)
                out = {'state':'CANDIDATE_NOT_APPLIED','answer':result,'model_response':model}
                if proof is not None:
                    out['native_observation'] = proof
        except Exception as exc:
            out = {'state':str(exc) if isinstance(exc,GateError) else 'HOLD_SUBAGENT_EXCEPTION'}
        outbox.put({'kind':'RESULT','role':role,'pid':os.getpid(),
                    'id':item['id'],'elapsed_ms':round((time.monotonic()-started)*1000),**out})


class Subagents:
    def __init__(self, roles, *, model_url='http://127.0.0.1:8081/v1/chat/completions', timeout=60):
        if not isinstance(roles,list) or not roles or any(not isinstance(x,str) or not SAFE_ROLE.fullmatch(x) for x in roles) or len(set(roles)) != len(roles):
            raise GateError('HOLD_ROLE_ID')
        if not isinstance(timeout,(int,float)) or not 1 <= timeout <= 300:
            raise GateError('HOLD_TIMEOUT')
        self.roles = roles
        self.url = model_url
        self.timeout = timeout
        self.ctx = mp.get_context('spawn')
        # A feeder killed mid-frame must not block the director in Queue.get.
        # Each child owns a private pipe; parent reads are actually nonblocking.
        self.outboxes = {}
        self.senders = {}
        self.output_buffers = {}
        self.channel_faults = {}
        for role in roles:
            self._new_output(role)
        self.inboxes = {r:self.ctx.Queue() for r in roles}
        self.cancellations = {r:_Cancellation(self.ctx) for r in roles}
        self.processes = {}
        self.active = {}
        self.heartbeats = {}
        self.started = {}
        self.deadlines = {}
        self.identities = {}
        self.heartbeat_monotonic = {}
        self.heartbeat_expected = set()
        self.poll_cursor = 0

    def _new_output(self, role):
        receiver, sender = self.ctx.Pipe(duplex=False)
        os.set_blocking(receiver.fileno(), False)
        self.outboxes[role] = receiver
        self.senders[role] = _WorkerOutbox(sender)
        self.output_buffers[role] = bytearray()
        self.channel_faults.pop(role, None)

    def _receive(self, role):
        """At most 256 KiB read per call; incomplete frames never block."""
        if role in self.channel_faults:
            return None
        buffer = self.output_buffers[role]
        for _ in range(4):
            if len(buffer) >= 4:
                size = struct.unpack('!i', buffer[:4])[0]
                if not 0 < size <= MAX_IPC_BYTES:
                    self.channel_faults[role] = 'HOLD_SUBAGENT_IPC_FRAME_SIZE'
                    return None
                if len(buffer) >= size+4:
                    raw = bytes(buffer[4:size+4])
                    del buffer[:size+4]
                    try:
                        event = json.loads(raw)
                    except (ValueError, UnicodeError, RecursionError):
                        self.channel_faults[role] = 'HOLD_SUBAGENT_IPC_JSON'
                        return None
                    if not isinstance(event, dict):
                        self.channel_faults[role] = 'HOLD_SUBAGENT_IPC_SCHEMA'
                        return None
                    return event
            try:
                part = os.read(self.outboxes[role].fileno(), 65536)
            except BlockingIOError:
                return None
            except OSError:
                self.channel_faults[role] = 'HOLD_SUBAGENT_IPC_IO'
                return None
            if not part:
                self.channel_faults[role] = ('HOLD_SUBAGENT_IPC_TRUNCATED'
                    if buffer else 'HOLD_SUBAGENT_IPC_CLOSED')
                return None
            buffer.extend(part)
        return None

    def _start(self, role):
        p = self.ctx.Process(target=_worker,
            args=(role,self.inboxes[role],self.senders[role],self.url,
                  self.timeout,self.cancellations[role]),name='NOX_SUBAGENT_'+role)
        p.start()
        self.processes[role] = p
        self.senders[role].connection.close()
        identity = _identity(p.pid)
        if identity is not None and identity['ppid'] == os.getpid():
            self.identities[role] = identity

    def _ready(self, role, timeout=15):
        child = self.processes[role]
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            if not child.is_alive():
                raise GateError('HOLD_SUBAGENT_PROCESS_EXIT')
            msg = self._receive(role)
            if role in self.channel_faults:
                raise GateError(self.channel_faults[role])
            if msg is None:
                time.sleep(.02)
                continue
            identity = _identity(child.pid)
            if (msg.get('kind') != 'READY' or msg.get('role') != role
                    or msg.get('pid') != child.pid or identity is None
                    or identity['ppid'] != os.getpid()):
                raise GateError('HOLD_SUBAGENT_READY_IDENTITY')
            self.identities[role] = identity
            self.heartbeats[role] = time.time()
            self.heartbeat_monotonic[role] = time.monotonic()
            return identity
        raise GateError('HOLD_SUBAGENT_PROCESS_START')

    def __enter__(self):
        try:
            for role in self.roles:
                self._start(role)
            for role in self.roles:
                self._ready(role)
            if len({row['pid'] for row in self.identities.values()}) != len(self.roles):
                raise GateError('HOLD_SUBAGENT_NONUNIQUE_PID')
            return self
        except BaseException:
            self.__exit__(None,None,None)
            raise

    def submit(self, task):
        """Private director IPC. The authoritative claim remains in its queue."""
        role = task.get('subagent')
        if role not in self.processes or not self.processes[role].is_alive():
            raise GateError('HOLD_SUBAGENT_PROCESS_EXIT')
        if self.health_reason(role):
            raise GateError(self.health_reason(role))
        if role in self.active or not TASK_ID.fullmatch(str(task.get('id', ''))):
            raise GateError('HOLD_SUBAGENT_ROLE_BUSY_OR_TASK_ID')
        self.active[role] = task['id']
        self.started[role] = time.monotonic()
        project = task.get('_native_project_context')
        if isinstance(project, dict):
            self.heartbeat_expected.add(role)
        else:
            self.heartbeat_expected.discard(role)
        budget = 1800 if isinstance(project, dict) and 'plan_sha256' not in project.get('reference', {}) else self.timeout
        self.deadlines[role] = self.started[role] + budget + 10
        self.cancellations[role].clear()
        self.inboxes[role].put(task)

    def health_reason(self, role):
        if role in self.channel_faults:
            return self.channel_faults[role]
        child = self.processes.get(role)
        if child is None or not child.is_alive():
            return 'HOLD_SUBAGENT_PROCESS_EXIT'
        if _identity(child.pid) != self.identities.get(role):
            return 'HOLD_SUBAGENT_PROCESS_IDENTITY'
        if time.monotonic() > self.deadlines.get(role, float('inf')):
            return 'HOLD_SUBAGENT_TIMEOUT'
        # Idle children and project jobs heartbeat independently of inference.
        # Legacy review HTTP calls do not, so their existing hard deadline is
        # still authoritative while active.
        if ((role not in self.active or role in self.heartbeat_expected) and time.monotonic() -
                self.heartbeat_monotonic.get(role, time.monotonic()) > HEARTBEAT_STALE_SEC):
            return 'HOLD_SUBAGENT_HEARTBEAT_STALE'
        return None

    def retire(self, role, expected, *, gate):
        """Stop one owned lifetime; never clear its task reservation here."""
        child = self.processes.get(role)
        if (child is None or self.identities.get(role) != expected
                or child.pid != expected.get('pid') or gate() is not True):
            raise GateError('HOLD_SUBAGENT_RETIRE_IDENTITY')
        self.cancellations[role].set()
        if child.is_alive():
            if _identity(child.pid) != expected or gate() is not True:
                raise GateError('HOLD_SUBAGENT_RETIRE_IDENTITY')
            child.terminate()
            child.join(timeout=1)
        if child.is_alive():
            if _identity(child.pid) != expected or gate() is not True:
                raise GateError('HOLD_SUBAGENT_RETIRE_IDENTITY')
            child.kill()
            child.join(timeout=1)
        if child.is_alive() or child.exitcode is None or _identity(child.pid) == expected:
            raise GateError('HOLD_SUBAGENT_RETIRE_UNVERIFIED')
        return {'worker':dict(expected), 'exitcode':child.exitcode,
                'exit_verified':True, 'retired_at':time.time()}

    def acknowledge_retired(self, role, task_id):
        child = self.processes.get(role)
        if (child is None or child.is_alive() or child.exitcode is None
                or self.active.get(role) != task_id):
            raise GateError('HOLD_SUBAGENT_RETIRE_ACK')
        self.active.pop(role)
        self.started.pop(role, None)
        self.deadlines.pop(role, None)
        self.heartbeat_expected.discard(role)

    def restart_idle(self, role, expected, *, gate):
        """Replace only an idle failed lifetime; other roles retain their IPC."""
        if role in self.active or role in self.started or self.health_reason(role) is None:
            raise GateError('HOLD_SUBAGENT_RESTART_NOT_IDLE_FAILED')
        proof = self.retire(role, expected, gate=gate)
        if gate() is not True:
            raise GateError('HOLD_SUBAGENT_RESTART_GATE')
        self.inboxes[role].cancel_join_thread()
        self.inboxes[role].close()
        self.outboxes[role].close()
        self.senders[role].connection.close()
        self.inboxes[role] = self.ctx.Queue()
        self._new_output(role)
        self.cancellations[role] = _Cancellation(self.ctx)
        try:
            self._start(role)
            identity = self._ready(role)
        except BaseException:
            current = self.identities.get(role)
            if current and current.get('pid') == self.processes[role].pid:
                self.retire(role, current, gate=gate)
            raise
        return {**proof, 'replacement':identity, 'ready_at':time.time()}

    def cancel(self, task_id):
        """Cooperative cancellation lets a sandbox verifier terminate promptly."""
        for role, active in self.active.items():
            if active == task_id:
                self.cancellations[role].set()
                return True
        return False

    def poll(self, timeout=0.2):
        """Bounded receive lets the owner recheck STOP/lease every 200 ms."""
        deadline = time.monotonic()+max(0, timeout)
        event = None
        while event is None:
            for offset in range(len(self.roles)):
                role = self.roles[(self.poll_cursor+offset) % len(self.roles)]
                event = self._receive(role)
                if event is None:
                    continue
                # The private channel identifies the sender. Payload strings
                # cannot impersonate another role or a replacement lifetime.
                expected = self.identities.get(role)
                child = self.processes[role]
                live = _identity(child.pid)
                if (not isinstance(expected, dict) or expected.get('pid') != child.pid
                        or event.get('role') != role or event.get('pid') != child.pid
                        or live is not None and live != expected
                        or live is None and (child.is_alive() or child.exitcode is None)):
                    self.channel_faults[role] = 'HOLD_SUBAGENT_RESULT_IDENTITY'
                    event = None
                    continue
                self.poll_cursor = (self.roles.index(role)+1) % len(self.roles)
                break
            if event is not None or time.monotonic() >= deadline:
                break
            time.sleep(min(.02, max(0,deadline-time.monotonic())))
        if event is None:
            return None
        role = event.get('role')
        if event.get('kind') == 'HEARTBEAT':
            at = event.get('at')
            if type(at) not in (int,float) or not math.isfinite(at) or at < 0 or at > time.time()+1:
                self.channel_faults[role] = 'HOLD_SUBAGENT_HEARTBEAT_SCHEMA'
                return None
            self.heartbeats[role] = at
            self.heartbeat_monotonic[role] = time.monotonic()
            return None
        self.heartbeats[role] = time.time()
        self.heartbeat_monotonic[role] = time.monotonic()
        if event.get('kind') != 'RESULT' or event.get('id') != self.active.get(role):
            self.channel_faults[role] = 'HOLD_SUBAGENT_RESULT_IDENTITY'
            return None
        del self.active[role]
        self.started.pop(role, None)
        self.deadlines.pop(role, None)
        self.heartbeat_expected.discard(role)
        return event

    def run(self,batch, *, stop_active, authorize, lease_current):
        """One request, any task count; only candidates, not queue/S03 commits."""
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
        remaining = dict(tasks)
        outcomes = {}
        active = set()
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
                self.submit(t)
                busy_roles.add(t['subagent'])
                active.add(tid)
                del remaining[tid]
                progressed = True
            if active:
                for role in busy_roles:
                    reason = self.health_reason(role)
                    if reason:
                        raise GateError(reason)
                try:
                    event = self.poll(timeout=0.2)
                except queue.Empty:
                    event = None
                if event is None:
                    continue
                if not admitted():
                    raise GateError('HOLD_OWNER_GATE_CHANGED')
                tid = event.get('id')
                role = event.get('role')
                if event.get('kind')!='RESULT' or tid not in active or role not in busy_roles or event.get('pid')!=self.processes[role].pid:
                    raise GateError('HOLD_SUBAGENT_RESULT_IDENTITY')
                outcomes[tid] = event
                active.remove(tid)
                busy_roles.remove(role)
            elif not progressed and remaining:
                raise GateError('HOLD_SUBAGENT_DISPATCH_DEADLOCK')
        if not admitted():
            raise GateError('HOLD_OWNER_GATE_CHANGED')
        return {'schema': 'NOX_SUBAGENT_SOURCE_CANDIDATES_V1', 'processes': {r:p.pid for r,p in self.processes.items()},
                'task_count': len(tasks), 'results': outcomes, 'live_onehost_deployed': False,
                'queue_committed': False, 'model_weights_changed': False}

    def close_idle(self, *, timeout=2.0):
        """Cooperatively stop a verified idle generation; never terminate/kill."""
        if (self.active or self.started or type(timeout) not in (int, float)
                or not math.isfinite(timeout) or not 0.1 <= timeout <= 5):
            raise GateError('HOLD_SUBAGENT_IDLE_CLOSE_STATE')
        # A queued item without an active/started record is unknown work.
        # Queue.empty() is only a conservative veto, never proof of idleness.
        try:
            if any(not inbox.empty() for inbox in self.inboxes.values()):
                raise GateError('HOLD_SUBAGENT_IDLE_QUEUE_NOT_EMPTY')
        except (OSError, ValueError, AttributeError):
            raise GateError('HOLD_SUBAGENT_IDLE_QUEUE_UNKNOWN') from None
        for event in self.cancellations.values():
            event.set()
        deadline = time.monotonic()+timeout
        for process in self.processes.values():
            process.join(timeout=max(0, deadline-time.monotonic()))
        if any(process.is_alive() or process.exitcode is None
               for process in self.processes.values()):
            # Preserve every object/queue/reservation for owner recovery. No
            # terminate(), kill(), or channel close on an unknown lifetime.
            raise GateError('HOLD_SUBAGENT_GRACEFUL_SHUTDOWN_UNKNOWN')
        for inbox in self.inboxes.values():
            inbox.cancel_join_thread()
            inbox.close()
        for pipe in [*self.outboxes.values(),
                     *(item.connection for item in self.senders.values())]:
            pipe.close()
        self.active.clear()
        self.started.clear()
        self.deadlines.clear()
        return {'state':'IDLE_POOL_GRACEFULLY_STOPPED',
                'worker_pids':sorted(process.pid for process in self.processes.values()),
                'forced_signals':0}

    def __exit__(self,*_):
        for event in self.cancellations.values():
            event.set()
        for box in self.inboxes.values():
            try: box.put_nowait(None)
            except Exception: pass
        deadline = time.monotonic()+1
        for p in self.processes.values():
            p.join(timeout=max(0, deadline-time.monotonic()))
        for p in self.processes.values():
            if p.is_alive():
                p.terminate()
        deadline = time.monotonic()+2
        for p in self.processes.values():
            p.join(timeout=max(0, deadline-time.monotonic()))
        for p in self.processes.values():
            if p.is_alive():
                p.kill()
        deadline = time.monotonic()+1
        for p in self.processes.values():
            p.join(timeout=max(0, deadline-time.monotonic()))
        if any(p.is_alive() or p.exitcode is None for p in self.processes.values()):
            # The owner must retain this object and its reservations. Never
            # close/forget a generation whose process exit is still unknown.
            raise GateError('HOLD_SUBAGENT_PROCESS_SHUTDOWN')
        for q in self.inboxes.values():
            q.cancel_join_thread()
            q.close()
        for pipe in [*self.outboxes.values(),*(item.connection for item in self.senders.values())]:
            pipe.close()
        self.active.clear()
        self.started.clear()
        self.deadlines.clear()


if __name__=='__main__':
    # Only an explicit owner-native binding should ever call Subagents.run.
    # No CLI route accepts arbitrary instructions or bypasses STOP/lease.
    print('NOX_SUBAGENTS_SOURCE_AVAILABLE_NOT_NATIVE_INSTALLED')
