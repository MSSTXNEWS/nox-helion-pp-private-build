#!/usr/bin/env python3
"""Reviewed, bounded DAGs inside the existing six-worker NOX dispatcher.

An accepted order is a pending plan, never completed work. This module creates
no workers, model instances, shell commands, trainers, or download services.
Training and download mutations require dedicated reviewed native handlers;
until those are registered their explicit prerequisites remain pending.
"""
from __future__ import annotations

import ast
import copy
from contextlib import contextmanager
import fcntl
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
import time

ROOT = Path('/root/nox')
CGROUP = Path('/sys/fs/cgroup')
MARKER = 'NOX_OWNER_TASK_PLANS_BIND_V1'
SCHEMA = 'NOX_OWNER_PLAN_V1'
RECEIPT = 'NOX_OWNER_PLAN_RECEIPT_V1'
REQUEST = 'NOX_OWNER_PLAN_REQUEST_V1'
SHA = re.compile(r'^[0-9a-f]{64}$')
IDENT = re.compile(r'^[A-Za-z0-9_.-]{1,128}$')
CODE = re.compile(r'^[A-Z][A-Z0-9_]{0,95}$')
PLAN_ID = re.compile(r'^[0-9a-f]{24}$')
NONCE = PLAN_ID
COMPONENTS = ('training_stack', 'dispatcher', 'chat', 'memory', 'storage', 'downloads')
PENDING = {'pending', 'wait', 'retry'}
TERMINAL_FAILURE = {'failed', 'blocked', 'cancelled'}
_LOCAL = threading.local()
_BOUND = None
_PRESSURE_LOCK = threading.Lock()
_PRESSURE_CACHE = {'at': 0.0, 'path': None, 'value': None}


class PlanHold(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def read_bytes(path, maximum=262144):
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise PlanHold('HOLD_PLAN_FILE_SCOPE')
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > maximum or (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise PlanHold('HOLD_PLAN_FILE_CHANGED')
    return raw


def read_json(path, maximum=262144):
    return json.loads(read_bytes(path, maximum))


def file_sha(path):
    return hashlib.sha256(read_bytes(path, 2 * 1024 * 1024)).hexdigest()


def private_directory(path):
    path = Path(path)
    if not path.is_relative_to(ROOT / 'state/owner_plans'):
        raise PlanHold('HOLD_PLAN_DIRECTORY_SCOPE')
    for item in (ROOT, ROOT / 'state', ROOT / 'state/owner_plans', path):
        if item.is_symlink():
            raise PlanHold('HOLD_PLAN_DIRECTORY_SYMLINK')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def atomic_json(path, value):
    path = Path(path)
    if path.is_symlink():
        raise PlanHold('HOLD_PLAN_RECEIPT_SYMLINK')
    private_directory(path.parent)
    raw = (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode()
    if len(raw) > 262144:
        raise PlanHold('HOLD_PLAN_RECEIPT_SIZE')
    fd, temporary = tempfile.mkstemp(prefix='.plan-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def plan_directory(plan_id):
    if not isinstance(plan_id, str) or not PLAN_ID.fullmatch(plan_id):
        raise PlanHold('HOLD_PLAN_ID')
    return ROOT / 'state/owner_plans' / plan_id


@contextmanager
def maintenance_read_lock():
    path = ROOT / 'state/owner_maintenance.lock'
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise PlanHold('WAIT_NATIVE_MAINTENANCE')
        yield
    finally:
        os.close(fd)


def parallel_policy():
    try:
        mode = read_json(ROOT / 'state/task_boost_mode.json', 16000)
    except (OSError, ValueError, PlanHold):
        mode = {}
    boosted = mode.get('enabled') is True
    target = 6 if boosted else 3
    try:
        config = read_json(ROOT / 'config/owner_task_lifecycle.json', 16000)
        value = (config.get('parallelism') or {}).get('task_boost_target' if boosted else 'normal_target')
        if config.get('schema') == 'NOX_OWNER_TASK_LIFECYCLE_V1' and type(value) is int and 3 <= value <= 6:
            target = value
    except (OSError, ValueError, PlanHold):
        pass
    return ('TASK_BOOST' if boosted else 'NORMAL'), target


def pressure_snapshot():
    """Read cgroup pressure once per three seconds; no probe worker or sleep."""
    now = time.monotonic()
    with _PRESSURE_LOCK:
        if (_PRESSURE_CACHE['path'] == str(CGROUP) and _PRESSURE_CACHE['value'] is not None
                and 0 <= now - _PRESSURE_CACHE['at'] < 3):
            return dict(_PRESSURE_CACHE['value'])
        value = {'state': 'LOAD_UNKNOWN', 'memory_ratio': None, 'cpu_some_avg10': None}
        try:
            current = read_bytes(CGROUP / 'memory.current', 256).decode().strip()
            maximum = read_bytes(CGROUP / 'memory.max', 256).decode().strip()
            if current.isdigit() and maximum.isdigit() and int(maximum) > 0:
                value['memory_ratio'] = min(2.0, int(current) / int(maximum))
        except (OSError, ValueError, PlanHold):
            pass
        try:
            raw = read_bytes(CGROUP / 'cpu.pressure', 512).decode()
            match = re.search(r'^some\s+avg10=([0-9.]+)', raw, re.M)
            if match:
                pressure = float(match[1])
                if math.isfinite(pressure) and 0 <= pressure <= 100:
                    value['cpu_some_avg10'] = pressure
        except (OSError, ValueError, PlanHold):
            pass
        if value['memory_ratio'] is not None or value['cpu_some_avg10'] is not None:
            value['state'] = 'LOAD_OBSERVED'
        _PRESSURE_CACHE.update(at=now, path=str(CGROUP), value=value)
        return dict(value)


def admission_capacity():
    mode, target = parallel_policy()
    pressure = pressure_snapshot()
    ratio, cpu = pressure.get('memory_ratio'), pressure.get('cpu_some_avg10')
    reason = 'MODE_TARGET_WITH_OBSERVED_LOAD'
    if pressure.get('state') == 'LOAD_UNKNOWN':
        target, reason = min(target, 3), 'CONSERVATIVE_LOAD_UNKNOWN'
    if ratio is not None and ratio >= 0.95:
        target, reason = 0, 'NEW_BRANCHES_WAIT_MEMORY_PRESSURE'
    elif ratio is not None and ratio >= 0.85:
        target, reason = min(target, 3), 'NEW_BRANCHES_LIMITED_MEMORY_PRESSURE'
    if cpu is not None and cpu >= 50 and target > 1:
        target, reason = 1, 'NEW_BRANCHES_LIMITED_CPU_PRESSURE'
    elif cpu is not None and cpu >= 20 and target > 3:
        target, reason = 3, 'NEW_BRANCHES_LIMITED_CPU_PRESSURE'
    return mode, target, reason


def safe_codes(values):
    if not isinstance(values, list) or len(values) > 32 or any(not isinstance(x, str) or not CODE.fullmatch(x) for x in values):
        raise PlanHold('HOLD_PLAN_BLOCKER_SCHEMA')
    return sorted(set(values))


def requested_plan(task):
    """Only typed requests and exact, harmless status aliases are recognized."""
    if task.get('owner_parent_id'):
        raise PlanHold('NEEDS_PLAN_RECURSIVE_EXPANSION_FORBIDDEN')
    params = task.get('params') or {}
    request = params.get('plan')
    if request is None:
        orders = params.get('orders')
        if not isinstance(orders, list) or len(orders) != 1 or not isinstance(orders[0], dict):
            raise PlanHold('NEEDS_PLAN_TYPED_OWNER_REQUEST')
        order = orders[0]
        request = order.get('plan')
        if request is None and order.get('kind') in ('audit', 'status'):
            request = {'schema': REQUEST, 'intent': 'audit'}
        if request is None and str(order.get('name', '')).strip().casefold() in (
                'audit', 'status', 'nox status', 'аудит', 'статус', 'проверь состояние нокс'):
            request = {'schema': REQUEST, 'intent': 'audit'}
    if not isinstance(request, dict) or request.get('schema') != REQUEST:
        raise PlanHold('NEEDS_PLAN_TYPED_OWNER_REQUEST')
    intent = request.get('intent')
    if intent == 'status':
        intent = 'audit'
    if intent not in ('audit', 'optimize_workers', 'downloads', 'training_status', 'training_resume'):
        raise PlanHold('NEEDS_PLAN_UNREVIEWED_INTENT')
    allowed = {'schema', 'intent'} | ({'component_ids'} if intent == 'downloads' else set())
    if set(request) - allowed:
        raise PlanHold('NEEDS_PLAN_UNREVIEWED_PARAMETERS')
    result = {'schema': REQUEST, 'intent': intent}
    if intent == 'downloads':
        ids = request.get('component_ids', [])
        if not isinstance(ids, list) or not 1 <= len(ids) <= 6 or any(not isinstance(x, str) or not IDENT.fullmatch(x) for x in ids):
            raise PlanHold('NEEDS_PLAN_DOWNLOAD_COMPONENT_IDS')
        result['component_ids'] = sorted(set(ids))
    return result


def checkpoint_inventory():
    path = ROOT / 'lora/qlora_t866u/runs_owner_hybrid/owner_last_result.json'
    try:
        raw = read_bytes(path)
        value = json.loads(raw)
    except (OSError, ValueError, PlanHold):
        return {'verified': True, 'scope': 'TRAINING_PROGRESS_INVENTORY',
                'blockers': ['VERIFIED_OPTIMIZER_RECEIPT_REQUIRED'], 'verified_step': 0}
    step = value.get('global_step') if isinstance(value, dict) else None
    verified = (type(step) is int and step > 0 and value.get('adapter_delta_verified') is True
                and value.get('state') in ('VERIFIED_BOUNDED_ADAPTER_UPDATE', 'CHECKPOINTED_OWNER_STOP'))
    return {'verified': True, 'scope': 'TRAINING_PROGRESS_INVENTORY',
            'blockers': [] if verified else ['VERIFIED_OPTIMIZER_RECEIPT_REQUIRED'],
            'verified_step': step if verified else 0, 'receipt_sha256': hashlib.sha256(raw).hexdigest()}


def specifications(request):
    """Three to six real branches; dependencies determine useful parallelism."""
    intent = request['intent']
    if intent == 'audit':
        return [(name, 'component:' + name, []) for name in COMPONENTS]
    if intent == 'optimize_workers':
        return [('budget', 'resource_budget', []), ('apply', 'worker_config', ['budget']),
                ('verify', 'worker_verify', ['apply'])]
    if intent == 'downloads':
        return [('storage', 'component:storage', []), ('manifest', 'component:downloads', []),
                ('download', 'download_admission', ['storage', 'manifest'])]
    if intent == 'training_status':
        return [('stack', 'component:training_stack', []), ('budget', 'resource_budget', []),
                ('checkpoint', 'training_inventory', [])]
    if intent == 'training_resume':
        return [('stack', 'component:training_stack', []), ('budget', 'resource_budget', []),
                ('resume', 'training_admission', ['stack', 'budget']),
                ('checkpoint', 'training_progress', ['resume'])]
    if intent == 'media':
        return [('engine', 'media_readiness', []), ('budget', 'resource_budget', []),
                ('generation', 'media_native', ['engine', 'budget'])]
    raise PlanHold('NEEDS_PLAN_UNREVIEWED_INTENT')


def receipt_path(task):
    claim = task.get('owner_claim') or {}
    if not isinstance(claim.get('nonce'), str) or not NONCE.fullmatch(claim['nonce']):
        raise PlanHold('HOLD_PLAN_NATIVE_CLAIM_REQUIRED')
    return plan_directory(task.get('owner_plan_id')) / (digest(task.get('id'))[:24] + '.' + claim['nonce'] + '.json')


class Planner:
    def __init__(self, namespace):
        self.ns = namespace
        self.mentor = namespace['owner_mentor']
        self.components = importlib.import_module('owner_component_tasks')
        self.state = None

    def admitted(self, task):
        return not self.mentor.stop_active() and self.ns['_nox_owner_task_admitted'](task)

    def manifest(self, task):
        manifest = read_json(plan_directory(task.get('owner_plan_id')) / 'manifest.json')
        if (manifest.get('schema') != SCHEMA or manifest.get('plan_id') != task.get('owner_plan_id')
                or manifest.get('source_sha256') != file_sha(__file__)
                or not isinstance(manifest.get('nodes'), list) or not 3 <= len(manifest['nodes']) <= 6):
            raise PlanHold('HOLD_PLAN_MANIFEST_CHANGED')
        return manifest

    def install(self, state, parent, request, media_task=None):
        parent_id = parent['id']
        if not IDENT.fullmatch(parent_id) or parent.get('owner_parent_id'):
            raise PlanHold('NEEDS_PLAN_PARENT_ID')
        plan_id = digest({'parent': parent_id, 'request': request, 'version': MARKER})[:24]
        specs = specifications(request)
        names = {name: 'owner.branch.' + plan_id + '.' + name for name, _, _ in specs}
        if media_task is not None:
            names['generation'] = media_task['id']
        nodes = []
        for name, operation, dependencies in specs:
            nodes.append({'id': names[name], 'step': name, 'operation': operation,
                          'deps': [names[dep] for dep in dependencies],
                          'handler': 'owner_media' if operation == 'media_native' else 'owner_plan_step'})
        with self.ns['_qlock']:
            tasks = state.setdefault('tasks', {})
            active = {t.get('owner_plan_id') for t in tasks.values() if isinstance(t, dict) and t.get('status') in PENDING | {'running'} and t.get('owner_plan_id')}
            if plan_id not in active and len(active) >= 16:
                raise PlanHold('WAIT_PLAN_QUEUE_BUDGET')
            for node in nodes:
                old = tasks.get(node['id'])
                if old is not None and old is not media_task and old.get('owner_plan_id') != plan_id:
                    raise PlanHold('HOLD_PLAN_TASK_COLLISION')
            manifest = {'schema': SCHEMA, 'plan_id': plan_id, 'parent_id': parent_id,
                        'intent': request['intent'], 'request_sha256': digest(request),
                        'source_sha256': file_sha(__file__), 'nodes': nodes,
                        'created_at': time.time(), 'global_worker_cap': 6, 'recursive_expansion': False,
                        'parameters': {k: v for k, v in request.items() if k in ('component_ids', 'job_id')}}
            if request['intent'] == 'training_resume':
                manifest['baseline_step'] = checkpoint_inventory()['verified_step']
            path = plan_directory(plan_id) / 'manifest.json'
            if path.exists():
                previous = read_json(path)
                if any(previous.get(k) != manifest.get(k) for k in ('schema', 'plan_id', 'parent_id', 'intent', 'request_sha256', 'source_sha256', 'nodes', 'parameters')):
                    raise PlanHold('HOLD_PLAN_EXISTING_MANIFEST_CHANGED')
                manifest = previous
            else:
                atomic_json(path, manifest)
            for node in nodes:
                if node['id'] in tasks and tasks[node['id']] is not media_task:
                    continue  # Never reset a previous claim, failure or result.
                if node['operation'] == 'media_native':
                    child = media_task
                else:
                    child = {'id': node['id'], 'handler': 'owner_plan_step', 'class': 'owner_order',
                             'priority': 0, 'lane': 'owner_order', 'status': 'pending', 'locks': [],
                             'retries': 0, 'max_retries': 1, 'timeout_sec': 90,
                             'title': 'Reviewed NOX plan step ' + node['step'], 'source': MARKER,
                             'params': {'operation': node['operation']}}
                child.update(owner_parent_id=parent_id, owner_plan_id=plan_id, owner_plan_step=node['step'], deps=node['deps'])
                tasks[node['id']] = child
            parent.update(handler='owner_plan_join', owner_plan_id=plan_id,
                          owner_plan_children=[node['id'] for node in nodes],
                          owner_plan_intent=request['intent'], deps=[node['id'] for node in nodes],
                          owner_plan_state='PLANNED_WAITING_FOR_VERIFIED_BRANCHES')
            tasks[parent_id] = parent
            self.ns['save_state'](state)
        return {'state': 'PLAN_QUEUED_NOT_COMPLETED', 'plan_id': plan_id,
                'planned_branches': len(nodes), 'global_worker_cap': 6,
                'pending_task_ids': [node['id'] for node in nodes], 'verified': False}

    def owner_order(self, task):
        try:
            if not self.admitted(task):
                raise PlanHold('WAIT_NATIVE_ADMISSION')
            state = getattr(_LOCAL, 'state', None)
            if state is None:
                raise PlanHold('HOLD_PLAN_NATIVE_STATE_REQUIRED')
            return 'wait', self.install(state, task, requested_plan(task))
        except PlanHold as exc:
            reason = str(exc)
            return ('wait' if reason.startswith('WAIT_') else False), {'state': reason, 'verified': False,
                    'supported_intents': ['audit', 'optimize_workers', 'downloads', 'training_status', 'training_resume'],
                    'media_entry': 'EXISTING_AUTHENTICATED_MEDIA_JOB'}

    def write_receipt(self, task, started, native, **extra):
        scope = native.get('scope')
        if native.get('verified') is not True or not isinstance(scope, str) or not CODE.fullmatch(scope):
            raise PlanHold('HOLD_PLAN_NATIVE_VERIFICATION')
        blockers = safe_codes(native.get('blockers', []))
        record = {'schema': RECEIPT, 'plan_id': task['owner_plan_id'], 'task_id': task['id'],
                  'handler': task['handler'], 'claim': copy.deepcopy(task['owner_claim']),
                  'started_at': started, 'finished_at': time.time(), 'pid': os.getpid(),
                  'source_sha256': file_sha(__file__), 'manifest_sha256': file_sha(plan_directory(task['owner_plan_id']) / 'manifest.json'),
                  'verified': True, 'scope': scope, 'blockers': blockers,
                  'native_evidence_sha256': digest(native), **extra}
        path = receipt_path(task)
        if path.exists():
            raise PlanHold('HOLD_PLAN_CLAIM_RECEIPT_EXISTS')
        atomic_json(path, record)
        return {'schema': RECEIPT, 'verified': True, 'scope': scope, 'blockers': blockers,
                'receipt_path': str(path), 'receipt_sha256': file_sha(path)}

    def resource_check(self):
        result = self.mentor.component_validation({'params': {'component': 'resource_budget'}})
        proof = result.get('verification')
        if not isinstance(proof, dict) or proof.get('kind') != 'native_cgroup_budget':
            raise PlanHold('WAIT_RESOURCE_BUDGET')
        return {'verified': True, 'scope': 'OBSERVED_RESOURCE_BUDGET', 'blockers': [], 'evidence': proof}

    def worker_configuration(self, apply, task):
        with maintenance_read_lock():
            return self._worker_configuration_locked(apply, task)

    def _worker_configuration_locked(self, apply, task):
        path = ROOT / 'config/dispatcher_agents_t868u.json'
        before_raw = read_bytes(path)
        before = json.loads(before_raw)
        if not isinstance(before, dict):
            raise PlanHold('HOLD_WORKER_CONFIGURATION_SCHEMA')
        desired = self.mentor.worker_config(before)
        if apply and desired != before:
            # Only the already-active six-worker configuration is normalized;
            # this does not restart a service or claim model capacity.
            with self.ns['_qlock']:
                if not self.admitted(task) or read_bytes(path) != before_raw:
                    raise PlanHold('WAIT_WORKER_CONFIG_ADMISSION_CHANGED')
                self.mentor.atomic_json(path, desired)
        after = read_json(path)
        if any(after.get(k) != 6 for k in ('workers', 'min_workers', 'max_workers')) or after.get('tuner_may_adjust') is not False or self.ns.get('WORKERS') != 6:
            raise PlanHold('HOLD_SIX_EXECUTOR_CONFIGURATION')
        return {'verified': True, 'scope': 'SIX_EXECUTOR_CONFIGURATION_ONLY',
                'blockers': ['MEASURED_MODEL_CAPACITY_NOT_ESTABLISHED'],
                'before_sha256': hashlib.sha256(before_raw).hexdigest(), 'after_sha256': file_sha(path),
                'changed': before != after, 'workers': 6}

    def step(self, task):
        started = time.time()
        try:
            if not self.admitted(task):
                raise PlanHold('WAIT_NATIVE_ADMISSION')
            manifest = self.manifest(task)
            node = next((n for n in manifest['nodes'] if n['id'] == task['id']), None)
            operation = (task.get('params') or {}).get('operation')
            if node is None or node['handler'] != 'owner_plan_step' or node['operation'] != operation or node['step'] != task.get('owner_plan_step'):
                raise PlanHold('HOLD_PLAN_STEP_CHANGED')
            if operation.startswith('component:'):
                component = operation.split(':', 1)[1]
                if component not in COMPONENTS:
                    raise PlanHold('HOLD_UNKNOWN_COMPONENT')
                native = self.components.HANDLERS['owner.' + component]()
                if native.get('verified') is not True:
                    raise PlanHold('HOLD_COMPONENT_CHECK_FAILED')
            elif operation == 'resource_budget':
                native = self.resource_check()
            elif operation in ('worker_config', 'worker_verify'):
                native = self.worker_configuration(operation == 'worker_config', task)
            elif operation in ('training_inventory', 'training_progress'):
                native = checkpoint_inventory()
                if operation == 'training_progress' and native['verified_step'] <= manifest.get('baseline_step', 0):
                    raise PlanHold('WAIT_FRESH_VERIFIED_OPTIMIZER_PROGRESS')
            elif operation == 'media_readiness':
                media = self.ns.get('owner_media_runtime')
                if media is None:
                    raise PlanHold('WAIT_MEDIA_RUNTIME_ADMISSION')
                job = media.load_job(manifest['parameters']['job_id'])
                result = media.capabilities()
                if result.get(job['request']['kind']) is not True:
                    raise PlanHold('WAIT_MEDIA_ENGINE_OR_ASSETS')
                native = {'verified': True, 'scope': 'MEDIA_ENGINE_AND_ASSET_READINESS_ONLY',
                          'blockers': ['ACTUAL_MEDIA_OUTPUT_REQUIRED'], 'kind': job['request']['kind']}
            elif operation == 'training_admission':
                # owner_training_resume.py is a separately pinned maintenance
                # operation. Never invoke its old start_qlora/ensure_program
                # shortcuts, remove HOLD, or spawn a second trainer here.
                raise PlanHold('WAIT_TRAINING_ADMISSION')
            elif operation == 'download_admission':
                raise PlanHold('WAIT_DOWNLOAD_ADMISSION')
            else:
                raise PlanHold('HOLD_PLAN_OPERATION')
            return True, self.write_receipt(task, started, native)
        except PlanHold as exc:
            code = str(exc)
            with self.ns['_qlock']:
                task['owner_plan_wait'] = code
            return ('wait' if code.startswith('WAIT_') else False), {'state': code, 'verified': False,
                    'plan_id': task.get('owner_plan_id'), 'prerequisite': code.removeprefix('WAIT_')}
        except Exception as exc:
            return False, {'state': 'HOLD_PLAN_CHECK_' + type(exc).__name__.upper(), 'verified': False}

    def verified_children(self, task, state):
        manifest = self.manifest(task)
        rows, blockers = [], set()
        media_verified = False
        for node in manifest['nodes']:
            child = (state.get('tasks') or {}).get(node['id'])
            if not isinstance(child, dict) or child.get('owner_plan_id') != task['owner_plan_id'] or child.get('owner_parent_id') != task['id']:
                raise PlanHold('HOLD_PLAN_CHILD_IDENTITY')
            if child.get('status') in TERMINAL_FAILURE:
                raise PlanHold('HOLD_PLAN_CHILD_FAILED')
            if child.get('status') != 'done':
                raise PlanHold('WAIT_PLAN_CHILDREN')
            proof = self.mentor.verify_success(child, child.get('result'))
            if not isinstance(proof, dict):
                raise PlanHold('HOLD_PLAN_CHILD_RESULT_UNVERIFIED')
            if node['operation'] == 'media_native' and proof.get('kind') != 'native_media_output':
                raise PlanHold('HOLD_PLAN_MEDIA_OUTPUT_UNVERIFIED')
            media_verified |= node['operation'] == 'media_native'
            blockers.update(safe_codes(proof.get('blockers', [])))
            rows.append({'task_id': child['id'], 'claim_nonce': (child.get('owner_claim') or {}).get('nonce'),
                         'proof_sha256': digest(proof), 'result_sha256': digest(child.get('result'))})
        if media_verified:
            blockers.discard('ACTUAL_MEDIA_OUTPUT_REQUIRED')
        return rows, sorted(blockers)

    def join(self, task):
        started = time.time()
        try:
            if not self.admitted(task):
                raise PlanHold('WAIT_NATIVE_ADMISSION')
            state = getattr(_LOCAL, 'state', None)
            if state is None:
                raise PlanHold('HOLD_PLAN_NATIVE_STATE_REQUIRED')
            manifest = self.manifest(task)
            with self.ns['_qlock']:
                # Native tasks hold live threading locks in private fields.
                # Only the bounded plan's persisted public fields are copied.
                snapshot = {'tasks': {node['id']: copy.deepcopy({k: v for k, v in (state.get('tasks', {}).get(node['id']) or {}).items()
                                                               if not k.startswith('_')}) for node in manifest['nodes']}}
            children, blockers = self.verified_children(task, snapshot)
            intent = self.manifest(task)['intent']
            scope = {'audit': 'BOUNDED_COMPONENT_AUDIT', 'optimize_workers': 'SIX_EXECUTOR_CONFIGURATION_ONLY',
                     'training_status': 'TRAINING_STATUS_CHECKS_ONLY', 'training_resume': 'VERIFIED_TRAINING_PROGRESS',
                     'downloads': 'VERIFIED_REQUESTED_DOWNLOADS', 'media': 'VERIFIED_MEDIA_OUTPUT'}[intent]
            native = {'verified': True, 'scope': scope, 'blockers': blockers, 'verified_children': len(children)}
            return True, self.write_receipt(task, started, native, children=children)
        except PlanHold as exc:
            code = str(exc)
            return ('wait' if code.startswith('WAIT_') else False), {'state': code, 'verified': False,
                    'plan_id': task.get('owner_plan_id'), 'pending_task_ids': task.get('owner_plan_children', [])}

    def auto_media(self, state):
        for task in list((state.get('tasks') or {}).values()):
            if task.get('handler') != 'owner_media' or task.get('owner_plan_id') or task.get('status') not in PENDING:
                continue
            job_id = (task.get('params') or {}).get('job_id')
            if (not isinstance(job_id, str) or not re.fullmatch(r'[0-9a-f]{32}', job_id)
                    or task.get('id') != 'owner.media.' + job_id or task.get('locks') != ['gpu1']
                    or task.get('deps') or task.get('owner_claim')):
                continue
            parent_id = 'owner.plan.media.' + job_id
            if parent_id in state['tasks']:
                continue
            parent = {'id': parent_id, 'handler': 'owner_plan_join', 'class': 'owner_order', 'priority': 0,
                      'lane': 'owner_order', 'status': 'pending', 'locks': [], 'deps': [], 'retries': 0,
                      'max_retries': 1, 'timeout_sec': 90, 'source': MARKER,
                      'title': 'Verify completed owner media plan'}
            self.install(state, parent, {'schema': REQUEST, 'intent': 'media', 'job_id': job_id}, media_task=task)

    def verify(self, task, evidence):
        if task.get('handler') not in ('owner_plan_step', 'owner_plan_join') or not isinstance(evidence, dict):
            return None
        try:
            manifest = self.manifest(task)
            path = receipt_path(task)
            raw = read_bytes(path)
            record = json.loads(raw)
            claim = task.get('owner_claim') or {}
            if (evidence.get('schema') != RECEIPT or evidence.get('verified') is not True
                    or evidence.get('receipt_path') != str(path) or evidence.get('receipt_sha256') != hashlib.sha256(raw).hexdigest()
                    or record.get('schema') != RECEIPT or record.get('verified') is not True
                    or record.get('task_id') != task.get('id') or record.get('handler') != task['handler']
                    or record.get('plan_id') != manifest['plan_id'] or record.get('claim') != claim
                    or record.get('pid') != claim.get('pid') or record.get('started_at', 0) < task.get('owner_claim_epoch', float('inf'))
                    or record.get('finished_at', 0) < record.get('started_at', 0)
                    or record.get('source_sha256') != file_sha(__file__)
                    or record.get('manifest_sha256') != file_sha(plan_directory(manifest['plan_id']) / 'manifest.json')
                    or not CODE.fullmatch(str(record.get('scope', ''))) or record.get('scope') != evidence.get('scope')
                    or safe_codes(record.get('blockers', [])) != evidence.get('blockers')):
                return None
            proof = {'kind': 'bounded_native_plan_step', 'receipt_sha256': evidence['receipt_sha256'],
                     'source_sha256': record['source_sha256'], 'scope': record['scope'], 'blockers': record['blockers']}
            if task['handler'] == 'owner_plan_join':
                state = read_json(self.ns['STATE'], 16 * 1024 * 1024)
                children, blockers = self.verified_children(task, state)
                if record.get('children') != children or record['blockers'] != blockers:
                    return None
                proof.update(kind='bounded_native_plan_join', verified_children=len(children))
            return proof
        except (OSError, ValueError, TypeError, PlanHold):
            return None


def verify_success(task, evidence=None):
    return _BOUND.verify(task, evidence) if _BOUND is not None else None


def plan_metadata(task, state):
    tasks = state.get('tasks') or {}
    plan_id = task.get('owner_plan_id')
    siblings = [row for row in tasks.values() if isinstance(row, dict) and plan_id and row.get('owner_plan_id') == plan_id and row.get('owner_parent_id')]
    running = sum(row.get('status') == 'running' for row in tasks.values() if isinstance(row, dict))
    active = sum(row.get('status') == 'running' for row in siblings)
    ready = 0
    if _BOUND is not None:
        for row in siblings:
            if row.get('status') in PENDING and all((tasks.get(dep) or {}).get('status') == 'done' for dep in row.get('deps', [])) and _BOUND.admitted(row):
                ready += 1
    mode, target, load_reason = admission_capacity()
    width = active + min(ready, max(0, 6 - running), max(0, target - active))
    return {'plan_id': plan_id, 'parent_id': task.get('owner_parent_id') or task.get('id'),
            'mode': mode,
            'planned_branches': len(siblings) if siblings else 1, 'admitted_width': min(6, width),
            'new_admission_cap': target, 'load_reason': load_reason,
            'running': running, 'queued': sum(row.get('status') in PENDING for row in tasks.values() if isinstance(row, dict)),
            'reason': 'NATIVE_DEPENDENCIES_AND_RESOURCE_GATES' if plan_id else 'REVIEWED_PLAN_REQUIRED',
            'global_cap': 6, 'recursive_expansion': False}


def bind_dispatcher(namespace):
    global _BOUND
    if namespace.get('_owner_plans_bound'):
        return
    required = ('run_one', 'ingest_owner_orders', 'deps_ok', 'save_state', '_nox_owner_task_admitted')
    if (namespace.get('WORKERS') != 6 or not isinstance(namespace.get('HANDLERS'), dict)
            or '_qlock' not in namespace or 'STATE' not in namespace or 'owner_mentor' not in namespace
            or any(not callable(namespace.get(name)) for name in required)):
        raise PlanHold('HOLD_PLAN_NATIVE_CONTRACT')
    planner = Planner(namespace)
    old_run, old_ingest, old_deps, old_admission = (namespace[name] for name in ('run_one', 'ingest_owner_orders', 'deps_ok', '_nox_owner_task_admitted'))
    def run(state, task):
        previous = getattr(_LOCAL, 'state', None)
        _LOCAL.state = state
        planner.state = state
        try:
            return old_run(state, task)
        finally:
            _LOCAL.state = previous
    def ingest(state):
        with namespace['_qlock']:
            # Legacy owner ingestion reconstructs deps/handler on every tick.
            # Preserve only already-owned plan bindings; never replay results.
            saved = {key: {field: copy.deepcopy(value) for field, value in task.items()
                           if field.startswith('owner_plan') or field in ('handler', 'deps')}
                     for key, task in (state.get('tasks') or {}).items()
                     if task.get('owner_plan_id') and not task.get('owner_parent_id')}
            old_ingest(state)
            for key, value in saved.items():
                if key in state['tasks']:
                    state['tasks'][key].update(value)
            planner.state = state
            planner.auto_media(state)
        # NOX autonomously admits reviewed work on EVERY existing dispatcher tick.
        # This is outside _qlock: native process/queue calls enforce own fencing.
        # Separate OS process PID proofs are required; never count threads as agents.
        try:
            import owner_autonomy_pool
            mode_name = 'FORSAZH' if parallel_policy()[0] == 'TASK_BOOST' else 'NORMAL'
            namespace['_nox_autonomy_last'] = owner_autonomy_pool.tick_existing_dispatcher(
                namespace, state, mode=mode_name)
        except (ImportError, AttributeError):
            namespace['_nox_autonomy_last'] = {
                'state': 'HOLD_AUTONOMY_POOL_MODULE_NOT_INSTALLED', 'jobs_started': 0}
    def dependencies(state, task):
        if task.get('handler') == 'owner_plan_join' and task.get('owner_plan_id'):
            children = [state['tasks'].get(key) for key in task.get('owner_plan_children', [])]
            # Let the join report an explicit failed prerequisite; do not leave
            # a parent indefinitely queued behind a permanently blocked child.
            if children and any(isinstance(row, dict) and row.get('status') in TERMINAL_FAILURE for row in children):
                return True
        return old_deps(state, task)
    def admission(task):
        if not old_admission(task):
            return False
        if not task.get('owner_parent_id') or not task.get('owner_plan_id') or planner.state is None:
            return True
        claim = task.get('owner_claim') or {}
        if task.get('status') == 'running' and isinstance(claim.get('nonce'), str) and NONCE.fullmatch(claim['nonce']):
            return True  # A load change never interrupts an already-owned claim.
        _, target, _ = admission_capacity()
        with namespace['_qlock']:
            others = sum(row.get('status') == 'running' and row.get('id') != task.get('id')
                         and row.get('owner_plan_id') == task['owner_plan_id'] and bool(row.get('owner_parent_id'))
                         for row in planner.state.get('tasks', {}).values())
        return others < target
    namespace['HANDLERS'].update(owner_order=planner.owner_order, owner_plan_step=planner.step, owner_plan_join=planner.join)
    namespace['run_one'], namespace['ingest_owner_orders'], namespace['deps_ok'] = run, ingest, dependencies
    namespace['_nox_owner_task_admitted'] = admission
    namespace['_owner_plans_bound'] = True
    namespace['_owner_planner'] = planner
    _BOUND = planner


def patch_dispatcher(source, expected_sha256):
    if not isinstance(expected_sha256, str) or not SHA.fullmatch(expected_sha256) or hashlib.sha256(source.encode()).hexdigest() != expected_sha256:
        raise PlanHold('HOLD_PLAN_DISPATCHER_SOURCE_CHANGED')
    if MARKER in source:
        return source
    tree = ast.parse(source)
    names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    if not {'run_one', 'owner_claim_ready', 'ingest_owner_orders', 'deps_ok'} <= names:
        raise PlanHold('HOLD_PLAN_NATIVE_ANCHORS')
    anchor = 'if __name__ == "__main__":'
    if source.count(anchor) != 1 or 'NOX_OWNER_TASK_LIFECYCLE_BIND_V1' in source:
        raise PlanHold('HOLD_PLAN_BIND_BEFORE_LIFECYCLE')
    addition = '# ' + MARKER + '\nimport owner_task_plans\nowner_task_plans.bind_dispatcher(globals())\n\n'
    changed = source.replace(anchor, addition + anchor, 1)
    compile(changed, '<owner-task-plans>', 'exec')
    return changed
