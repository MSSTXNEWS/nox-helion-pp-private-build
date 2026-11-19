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
import multiprocessing as mp
import os
import signal
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
HOSTS = {'127.0.0.1', 'localhost'}


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
        self.outbox = self.ctx.Queue()
        self.inboxes = {r:self.ctx.Queue() for r in roles}
        self.cancellations = {r:self.ctx.Event() for r in roles}
        self.processes = {}
        self.active = {}
        self.heartbeats = {}
        self.started = {}
        self.deadlines = {}

    def __enter__(self):
        try:
            for role in self.roles:
                p = self.ctx.Process(target=_worker,args=(role,self.inboxes[role],self.outbox,self.url,self.timeout,self.cancellations[role]),name='NOX_SUBAGENT_'+role)
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
                if (msg.get('kind') == 'HEARTBEAT' and msg.get('role') in confirmed
                        and msg.get('pid') == confirmed[msg['role']]):
                    self.heartbeats[msg['role']] = time.time()
                    continue
                if msg.get('kind')!='READY' or msg.get('role') not in self.processes:
                    raise GateError('HOLD_SUBAGENT_READY_SCHEMA')
                role = msg['role']
                if role in confirmed or msg['pid'] != self.processes[role].pid:
                    raise GateError('HOLD_SUBAGENT_PID_MISMATCH')
                confirmed[role] = msg['pid']
                self.heartbeats[role] = time.time()
            if len(set(confirmed.values())) != len(self.roles):
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
        if role in self.active or not TASK_ID.fullmatch(str(task.get('id', ''))):
            raise GateError('HOLD_SUBAGENT_ROLE_BUSY_OR_TASK_ID')
        self.active[role] = task['id']
        self.started[role] = time.monotonic()
        project = task.get('_native_project_context')
        budget = 1800 if isinstance(project, dict) and 'plan_sha256' not in project.get('reference', {}) else self.timeout
        self.deadlines[role] = self.started[role] + budget + 10
        self.cancellations[role].clear()
        self.inboxes[role].put(task)

    def cancel(self, task_id):
        """Cooperative cancellation lets a sandbox verifier terminate promptly."""
        for role, active in self.active.items():
            if active == task_id:
                self.cancellations[role].set()
                return True
        return False

    def poll(self, timeout=0.2):
        """Bounded receive lets the owner recheck STOP/lease every 200 ms."""
        if not all(p.is_alive() for p in self.processes.values()):
            raise GateError('HOLD_SUBAGENT_PROCESS_EXIT')
        if any(time.monotonic() > deadline for deadline in self.deadlines.values()):
            raise GateError('HOLD_SUBAGENT_TIMEOUT')
        try:
            event = self.outbox.get(timeout=timeout)
        except queue.Empty:
            return None
        role = event.get('role')
        if role not in self.processes or event.get('pid') != self.processes[role].pid:
            raise GateError('HOLD_SUBAGENT_RESULT_IDENTITY')
        if event.get('kind') == 'HEARTBEAT':
            at = event.get('at')
            if not isinstance(at, (int, float)) or at > time.time()+1:
                raise GateError('HOLD_SUBAGENT_HEARTBEAT_SCHEMA')
            self.heartbeats[role] = at
            return None
        self.heartbeats[role] = time.time()
        if event.get('kind') != 'RESULT' or event.get('id') != self.active.get(role):
            raise GateError('HOLD_SUBAGENT_RESULT_IDENTITY')
        del self.active[role]
        self.started.pop(role, None)
        self.deadlines.pop(role, None)
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
        for q in [*self.inboxes.values(),self.outbox]:
            q.close()
        self.active.clear()
        self.started.clear()
        self.deadlines.clear()


if __name__=='__main__':
    # Only an explicit owner-native binding should ever call Subagents.run.
    # No CLI route accepts arbitrary instructions or bypasses STOP/lease.
    print('NOX_SUBAGENTS_SOURCE_AVAILABLE_NOT_NATIVE_INSTALLED')
