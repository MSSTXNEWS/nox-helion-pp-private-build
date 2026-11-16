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


def _worker(role, inbox, outbox, local_model_url, timeout):
    # These are CPU/IPC subagent processes; the existing NOX model stays on GPU0.
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    outbox.put({'kind':'READY','role':role,'pid':os.getpid()})
    while True:
        item = inbox.get()
        if item is None:
            return
        started = time.monotonic()
        try:
            result = _model_reply(item,local_model_url,timeout)
            out = {'state':'CANDIDATE_NOT_APPLIED','answer':result}
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
        self.processes = {}

    def __enter__(self):
        try:
            for role in self.roles:
                p = self.ctx.Process(target=_worker,args=(role,self.inboxes[role],self.outbox,self.url,self.timeout),name='NOX_SUBAGENT_'+role)
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
                if msg.get('kind')!='READY' or msg.get('role') not in self.processes:
                    raise GateError('HOLD_SUBAGENT_READY_SCHEMA')
                role = msg['role']
                if role in confirmed or msg['pid'] != self.processes[role].pid:
                    raise GateError('HOLD_SUBAGENT_PID_MISMATCH')
                confirmed[role] = msg['pid']
            if len(set(confirmed.values())) != len(self.roles):
                raise GateError('HOLD_SUBAGENT_NONUNIQUE_PID')
            return self
        except BaseException:
            self.__exit__(None,None,None)
            raise

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
                tid = event.get('id')
                role = event.get('role')
                if (event.get('kind')!='RESULT' or tid not in active or role != active_roles.get(tid)
                    or role not in busy_roles or event.get('pid')!=self.processes[role].pid):
                    raise GateError('HOLD_SUBAGENT_RESULT_IDENTITY')
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

    def __exit__(self,*_):
        for box in self.inboxes.values():
            try: box.put_nowait(None)
            except Exception: pass
        for p in self.processes.values():
            p.join(timeout=2)
            if p.is_alive():
                p.terminate()
                p.join(timeout=2)
        for q in [*self.inboxes.values(),self.outbox]:
            q.close()


if __name__=='__main__':
    # Only an explicit owner-native binding should ever call Subagents.run.
    # No CLI route accepts arbitrary instructions or bypasses STOP/lease.
    print('NOX_SUBAGENTS_SOURCE_AVAILABLE_NOT_NATIVE_INSTALLED')
