#!/usr/bin/env python3
"""Install the reviewed four-queue handoff in the existing NOX dispatcher.

The original queue remains the sole task store. Only this dispatcher's source,
private catalog and additive project manifests change. Model/trainer services,
weights, STOP flags, existing claims and historical receipts are not rewritten.
"""
from __future__ import annotations

import ast
import base64
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

# Filled with reviewed source digests by the local bundle builder before commit.
SPEC = {'assets': {'owner_autonomy_pool.py': '2c4735938dacd2a062ed2ee0b20477a6191d39b0fcf2b6c49686c10133047102', 'owner_subagent_dispatcher.py': '88af9c11d54e084ccb868c474d17c2a85511600a0ff6578bfe5490b437fe554e', 'owner_subagent_processes.py': 'c1d5adfcc83300d749b42f66d50f41d5c62c4df52215e43cfc0b891e7c91101b', 'owner_resource_policy.py': '3a7b02a269508472b2a950f28cb067045913842261f8e80bc0804c7cc7cab834', 'test_owner_four_queue.py': '4334ec2e2047c34ed7ee5d1f24152a1a2468b07f4bdfc8ebf592d13a64648ac9', 'test_owner_normal3_continuity.py': '409411abe7a828d2633cd9c2e4792629a00925b4a6a8dfcead27f80dd3f75641', 'work_tasks.json': '5347258ca08500d61173d9b36f69cc0632eff36d3ea1e10fcbbc420de69be000', 'work_ideas.json': 'e1c84397506c6e46fdc3ce71b63cc5eba2f5cc0cd290f8d1e32d4840e25972ae', 'work_receipts.json': 'b40c012a7280889722f446083c4cbe878db15fd6da34ac19855a99a0a099af71', 'NOX_FOUR_QUEUE_ROUTING_20261118.json': 'f98ab106e16116a88947f6be207f73ec2bf9215ae107d415077b79479e91c671'}, 'expected_native': {'scripts/nox_dispatcher_t855u.py': '9ae0c67523967756206a0da31d1a1cab65281dc2f4f28989f2156cd27da43a21', 'scripts/owner_subagent_dispatcher.py': '179e50b71377e007d32a39d0558ff77dbe02267f43045a4c14763b3d4abd6114', 'scripts/owner_subagent_processes.py': '117842bc8f0f9adf825213403ebcd2139f80db692d4589ac05b3359381551164', 'scripts/owner_autonomy_pool.py': '8e14f7f7909cefb38686420638621ebf0903e337070ad95d733d86632064ef95', 'scripts/owner_task_plans.py': '7eb207b361086d3c34299b44fb36d96758cf824a7bf68a05e7868408d646f773', 'scripts/owner_component_tasks.py': '190bf9948dbe821b5fe3512e3edbc0a7a9348b14aa2a154274e78f058d5d6d5d', 'config/owner_native_subagents.json': 'e988316fc3f6a7600fbce088c4aa7de72c44f2bfcce097def8942fa93b9b9da9', 'state/dispatcher/policies/NOX_WEB_WEIGHTS_V06.md': '84780aaf911a229a654995f38972cdad5d99c72ab38842f76f787ec280acb46f'}, 'install_paths': {'owner_autonomy_pool.py': 'scripts/owner_autonomy_pool.py', 'owner_subagent_dispatcher.py': 'scripts/owner_subagent_dispatcher.py', 'owner_subagent_processes.py': 'scripts/owner_subagent_processes.py', 'owner_resource_policy.py': 'scripts/owner_resource_policy.py', 'test_owner_four_queue.py': 'scripts/test_owner_four_queue.py', 'test_owner_normal3_continuity.py': 'scripts/test_owner_normal3_continuity.py', 'work_tasks.json': 'state/dispatcher/project_work_tasks.json', 'work_ideas.json': 'state/dispatcher/project_work_ideas.json', 'work_receipts.json': 'state/dispatcher/project_work_receipts_source.json', 'NOX_FOUR_QUEUE_ROUTING_20261118.json': 'state/dispatcher/project_routing_4q.json'}, 'leaf_catalog': [{'id': '1V14-01.native4q.chat_health.20261118', 'handler': 'owner_native_typed_leaf', 'deps': [], 'priority': 'P1', 'resource': 'CPU_LIGHT', 'source_sha256': '88af9c11d54e084ccb868c474d17c2a85511600a0ff6578bfe5490b437fe554e', 'params': {'operation': 'chat_health', 'parent_task_id': '1V14-01'}, 'title': 'Chat and current model health check', 'queue_id': 'Q1_RUNTIME_CHAT', 'estimated_cost': 1}, {'id': '3A02.native4q.memory_schema.20261118', 'handler': 'owner_native_typed_leaf', 'deps': [], 'priority': 'P1', 'resource': 'CPU_LIGHT', 'source_sha256': '88af9c11d54e084ccb868c474d17c2a85511600a0ff6578bfe5490b437fe554e', 'params': {'operation': 'memory_schema', 'parent_task_id': '3A02'}, 'title': 'S03 schema and service status check', 'queue_id': 'Q2_MEMORY_KNOWLEDGE', 'estimated_cost': 1}, {'id': '4A03.native4q.training_prerequisites.20261118', 'handler': 'owner_native_typed_leaf', 'deps': [], 'priority': 'P1', 'resource': 'CPU_LIGHT', 'source_sha256': '88af9c11d54e084ccb868c474d17c2a85511600a0ff6578bfe5490b437fe554e', 'params': {'operation': 'training_prerequisites', 'parent_task_id': '4A03'}, 'title': 'Training prerequisites read-only check', 'queue_id': 'Q3_TRAINING_WEIGHTS', 'estimated_cost': 1}, {'id': 'I-48.native4q.queue_regression.20261118', 'handler': 'owner_native_typed_leaf', 'deps': [], 'priority': 'P1', 'resource': 'CPU_LIGHT', 'source_sha256': '88af9c11d54e084ccb868c474d17c2a85511600a0ff6578bfe5490b437fe554e', 'params': {'operation': 'queue_regression', 'parent_task_id': 'I-48'}, 'title': 'Four-queue and persistent-process focused regression', 'queue_id': 'Q4_INTEGRATION_ACCEPTANCE', 'estimated_cost': 1}], 'leaf_source_pins': {'test_owner_four_queue.py': '4334ec2e2047c34ed7ee5d1f24152a1a2468b07f4bdfc8ebf592d13a64648ac9', 'test_owner_normal3_continuity.py': '409411abe7a828d2633cd9c2e4792629a00925b4a6a8dfcead27f80dd3f75641', 'owner_resource_policy.py': '3a7b02a269508472b2a950f28cb067045913842261f8e80bc0804c7cc7cab834', 'owner_component_tasks.py': '190bf9948dbe821b5fe3512e3edbc0a7a9348b14aa2a154274e78f058d5d6d5d', 'owner_task_plans.py': '7eb207b361086d3c34299b44fb36d96758cf824a7bf68a05e7868408d646f773'}, 'project_handoff': {'work_tasks_sha256': '5347258ca08500d61173d9b36f69cc0632eff36d3ea1e10fcbbc420de69be000', 'work_ideas_sha256': 'e1c84397506c6e46fdc3ce71b63cc5eba2f5cc0cd290f8d1e32d4840e25972ae', 'routing_sha256': 'f98ab106e16116a88947f6be207f73ec2bf9215ae107d415077b79479e91c671'}, 'protected_processes': {'chat': {'pid': 3266857, 'start_ticks': 172046662}, 'proxy': {'pid': 3648425, 'start_ticks': 175058217}, 'web': {'pid': 3505392, 'start_ticks': 173653097}}}
ROOT = Path('/root/nox')
SERVICE = 'nox-dispatcher-t855u'
CONFIG = 'config/owner_native_subagents.json'
STATE = 'state/dispatcher/state.json'
STATUS = 'status/agents_t856u.json'
QUEUE_IDS = ('Q1_RUNTIME_CHAT', 'Q2_MEMORY_KNOWLEDGE',
             'Q3_TRAINING_WEIGHTS', 'Q4_INTEGRATION_ACCEPTANCE')
MAX_BYTES = 32 * 1024 * 1024
SHA = re.compile(r'^[a-f0-9]{64}$')


class Hold(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise Hold('HOLD_FOUR_QUEUE_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def read_regular(path, maximum=MAX_BYTES):
    path = Path(path)
    require(path.is_absolute() and not any(p.is_symlink() for p in
            (path, *path.parents)), 'PATH_SCOPE')
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum,
                'FILE_BOUND')
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    require(len(raw) <= maximum and (before.st_dev, before.st_ino,
            before.st_size, before.st_mtime_ns) == (after.st_dev, after.st_ino,
            after.st_size, after.st_mtime_ns), 'FILE_CHANGED')
    return raw


def atomic(path, raw, mode=0o600):
    path = Path(path)
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'PATH_SCOPE')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix='.nox-four-queue-', dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def preimages(root, expected):
    result = {}
    for relative, pin in expected.items():
        require(SHA.fullmatch(pin) is not None, 'EXPECTED_SOURCE_PIN')
        raw = read_regular(Path(root) / relative)
        require(digest(raw) == pin, 'PREIMAGE_' + Path(relative).name)
        result[relative] = raw
    return result


def decode_assets(bundle, specification):
    result = {}
    require(set(bundle) == set(specification['assets']), 'BUNDLE_FILESET')
    for name, pin in specification['assets'].items():
        value = bundle[name]
        require(isinstance(value, str) and len(value) < 4 * 1024 * 1024,
                'BUNDLE_SIZE')
        raw = base64.b64decode(value, validate=True)
        require(digest(raw) == pin, 'BUNDLE_PIN_' + name)
        if name.endswith('.py'):
            compile(raw, name, 'exec')
        elif name.endswith('.json'):
            json.loads(raw)
        result[name] = raw
    return result


def prepare_config(raw, assets, specification, request, source):
    config = json.loads(raw)
    require(config.get('schema') == 'NOX_NATIVE_SUBAGENT_BINDING_V1'
            and config.get('instance_id') == 60509551
            and config.get('owner_authorized') is True
            and config.get('mode') == 'NORMAL' and config.get('target') == 3,
            'EXISTING_OWNER_CONFIG')
    old_catalog = copy.deepcopy(config.get('catalog'))
    require(isinstance(old_catalog, dict) and
            old_catalog.get('schema') == 'NOX_AUTONOMY_PROCESS_POOL_V1',
            'EXISTING_CATALOG')
    require(digest(encoded(old_catalog)) == config.get('catalog_sha256'),
            'EXISTING_CATALOG_HASH')
    old_rows = old_catalog.get('tasks')
    require(isinstance(old_rows, list) and len(old_rows) == 3,
            'EXISTING_REVIEW_COUNT')
    role_queues = dict(zip(('runtime', 'memory', 'weights'), QUEUE_IDS))
    for task in old_rows:
        require(task.get('handler') == 'owner_native_subagent_review'
                and task.get('params', {}).get('role') in role_queues,
                'EXISTING_REVIEW_SCOPE')
        task['queue_id'] = role_queues[task['params']['role']]
    rows = copy.deepcopy(specification['leaf_catalog'])
    require(len(rows) == 4 and {row.get('queue_id') for row in rows} == set(QUEUE_IDS),
            'FOUR_LEAF_QUEUES')
    require(len({row['id'] for row in [*old_rows, *rows]}) == 7,
            'LEAF_ID_COLLISION')
    for row in rows:
        require(row.get('handler') == 'owner_native_typed_leaf'
                and row.get('resource') == 'CPU_LIGHT'
                and row.get('source_sha256') == digest(assets['owner_subagent_dispatcher.py']),
                'LEAF_SCOPE')
    old_catalog['tasks'].extend(rows)
    config.update(execution_mode='NATIVE_LEAF_V1', catalog=old_catalog,
                  catalog_sha256=digest(encoded(old_catalog)),
                  owner_request=request, owner_source_sha=source)
    for name in ('owner_autonomy_pool.py', 'owner_subagent_processes.py',
                 'owner_subagent_dispatcher.py'):
        config['module_pins'][name] = digest(assets[name])
    config['leaf_source_pins'] = copy.deepcopy(specification['leaf_source_pins'])
    config['project_handoff'] = copy.deepcopy(specification['project_handoff'])
    config['global_worker_cap'] = 3
    return encoded(config)


def validate_handoff(assets):
    work = json.loads(assets['work_tasks.json'])['tasks']
    ideas = json.loads(assets['work_ideas.json'])['ideas']
    route = json.loads(assets['NOX_FOUR_QUEUE_ROUTING_20261118.json'])
    ids = [row['id'] for row in [*work, *ideas]]
    routed = [row['task_id'] for row in route['tasks']]
    require(len(ids) == len(set(ids)) == len(routed) == len(set(routed)) == 295,
            'PROJECT_ID_COVERAGE')
    require(set(ids) == set(routed) and
            {row['queue_id'] for row in route['tasks']} == set(QUEUE_IDS)
            and route['max_concurrent_workers'] == 3, 'PROJECT_ROUTING')
    return {'original_task_ids': 295, 'queue_counts': {
        q: sum(row['queue_id'] == q for row in route['tasks']) for q in QUEUE_IDS},
        'original_tasks_accepted': 0,
        'scope': 'FULL_PROJECT_SPECIFICATION_HANDOFF_WITH_SCOPED_EXECUTION_LEAVES'}


def apply_transaction(root, changes, before):
    """Compare immediately before each write; roll back only our own bytes."""
    applied = []
    try:
        for relative, raw in changes.items():
            path = Path(root) / relative
            previous = before.get(relative)
            try:
                current = read_regular(path)
            except FileNotFoundError:
                current = None
            require(current == previous, 'CONCURRENT_FILE_CHANGE_' + Path(relative).name)
            applied.append(relative)
            atomic(path, raw, 0o644 if relative.endswith('.py') else 0o600)
            require(read_regular(path) == raw, 'WRITE_READBACK_' + Path(relative).name)
        return applied
    except BaseException:
        rollback_transaction(root, changes, before, applied)
        raise


def rollback_transaction(root, changes, before, applied):
    outcomes = {}
    for relative in reversed(applied):
        path = Path(root) / relative
        try:
            if read_regular(path) != changes[relative]:
                outcomes[relative] = 'FOREIGN_CHANGE_PRESERVED'
            elif before.get(relative) is None:
                # Unreferenced additive files are retained. No existing data is deleted.
                outcomes[relative] = 'ADDITIVE_FILE_RETAINED_UNREFERENCED'
            else:
                atomic(path, before[relative], 0o644 if relative.endswith('.py') else 0o600)
                outcomes[relative] = 'PREIMAGE_RESTORED'
        except OSError:
            outcomes[relative] = 'ROLLBACK_IO_FAILED'
    return outcomes


def supervisor(action, name=SERVICE):
    require(name == SERVICE and action in ('status', 'stop', 'start'), 'SUPERVISOR_SCOPE')
    result = subprocess.run(['supervisorctl', action, name], capture_output=True,
                            text=True, timeout=25)
    if action == 'status':
        match = re.fullmatch(re.escape(name) + r'\s+(RUNNING|STOPPED|STARTING|STOPPING|BACKOFF|FATAL|EXITED)\b(?:\s+pid\s+(\d+))?.*',
                             result.stdout.strip())
        require(match is not None, 'SERVICE_STATUS')
        return {'state': match[1], 'pid': int(match[2]) if match[2] else None}
    require(result.returncode == 0, 'SERVICE_' + action.upper())
    return {'action': action, 'rc': result.returncode}


def process_identity(pid):
    if type(pid) is not int or pid <= 1:
        return None
    try:
        tail = Path('/proc', str(pid), 'stat').read_text().rsplit(') ', 1)[1].split()
        if tail[0] not in ('R', 'S', 'D', 'I'):
            return None
        return {'pid': pid, 'start_ticks': int(tail[19]),
                'ppid': int(tail[1]), 'pgrp': int(tail[2])}
    except (OSError, ValueError, IndexError):
        return None


def stop_clear(root):
    names = ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP',
             'state/STOP', 'state/STOP.flag', 'state/OWNER_MAINTENANCE.flag')
    return not any(path.exists() or path.is_symlink() for path in
                   [*(Path(root) / name for name in names), Path('/workspace/NOX_STOP')])


def queue_idle(root):
    value = json.loads(read_regular(Path(root) / STATE))
    require(isinstance(value.get('tasks'), dict), 'QUEUE_SCHEMA')
    active = [key for key, row in value['tasks'].items()
              if isinstance(row, dict) and row.get('status') == 'running']
    return value, active


def protected_snapshot(specification):
    result = {}
    for label, expected in specification['protected_processes'].items():
        identity = process_identity(expected['pid'])
        require(identity and identity['start_ticks'] == expected['start_ticks'],
                'PROTECTED_PROCESS_' + label)
        result[label] = identity
    return result


def stop_checked():
    observed = supervisor('status')
    previous = process_identity(observed.get('pid'))
    if observed['state'] not in ('STOPPED', 'FATAL', 'EXITED'):
        try:
            supervisor('stop')
        except (OSError, subprocess.SubprocessError, Hold):
            pass  # The control response is not authoritative; reconcile the actual service.
    deadline = time.monotonic() + 15
    while True:
        current = supervisor('status')
        old_alive = process_identity(previous['pid']) if previous else None
        if (current['state'] in ('STOPPED', 'FATAL', 'EXITED')
                and (old_alive is None or old_alive != previous)):
            return current
        require(time.monotonic() < deadline, 'STOP_NOT_VERIFIED_NO_FILE_ROLLBACK')
        time.sleep(.5)


def start_checked(root, require_native_status=True):
    try:
        supervisor('start')
    except (OSError, subprocess.SubprocessError, Hold):
        pass
    deadline = time.monotonic() + 20
    stable = None
    stable_since = None
    while time.monotonic() < deadline:
        observed = supervisor('status')
        identity = process_identity(observed.get('pid'))
        if observed['state'] == 'RUNNING' and identity:
            loaded = not require_native_status
            try:
                status_doc = json.loads(read_regular(Path(root) / STATUS, 2 * 1024 * 1024))
                native = status_doc.get('native_subexecutors') or {}
                director = native.get('director') or {}
                loaded = (director.get('pid') == identity['pid']
                    and director.get('process_starttime') == identity['start_ticks']
                    and 0 <= time.time() - native.get('observed_at', 0) <= 15)
            except (OSError, ValueError, TypeError, Hold):
                pass
            if loaded:
                if identity != stable:
                    stable, stable_since = identity, time.monotonic()
                elif time.monotonic() - stable_since >= 2:
                    return identity
        elif observed['state'] in ('FATAL', 'EXITED'):
            break
        time.sleep(.5)
    raise Hold('HOLD_FOUR_QUEUE_STARTUP_NOT_VERIFIED')


def load_receipt_reader(root, expected_sha):
    path = Path(root) / 'scripts/owner_subagent_dispatcher.py'
    raw = read_regular(path)
    require(digest(raw) == expected_sha, 'RECEIPT_READER_PIN')
    sys.path.insert(0, str(Path(root) / 'scripts'))
    module = types.ModuleType('nox_four_queue_receipt_reader')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module.s03_readback


def execution_snapshot(root, leaf_specs, receipt_reader):
    agent = json.loads(read_regular(Path(root) / STATUS, 2 * 1024 * 1024))
    native = agent.get('native_subexecutors') or {}
    state, _ = queue_idle(root)
    rows = []
    for definition in leaf_specs:
        task_id = definition['id']
        task = state['tasks'].get(task_id)
        if not isinstance(task, dict):
            rows.append({'task_id': task_id, 'state': 'NOT_ADMITTED'})
            continue
        result = task.get('result') if isinstance(task.get('result'), dict) else {}
        receipt = result.get('receipt') if isinstance(result.get('receipt'), dict) else {}
        event = receipt.get('worker_result') if isinstance(receipt.get('worker_result'), dict) else {}
        leaf = event.get('leaf_evidence') if isinstance(event.get('leaf_evidence'), dict) else {}
        worker = leaf.get('worker') if isinstance(leaf.get('worker'), dict) else {}
        proof = None
        valid_receipt = (receipt.get('phase') == 'NATIVE_LEAF_COMPLETED_ORIGINAL_NOT_ACCEPTED'
            and receipt.get('task_id') == task_id
            and receipt.get('source_sha256') == definition['source_sha256']
            and receipt.get('claim') == task.get('owner_claim')
            and event.get('state') == 'NATIVE_LEAF_COMPLETED'
            and leaf.get('check_completed') is True
            and type(leaf.get('check_passed')) is bool
            and leaf.get('original_task_accepted') is False
            and leaf.get('model_called') is False
            and leaf.get('parent_task_id') == definition['params']['parent_task_id']
            and leaf.get('operation') == definition['params']['operation']
            and leaf.get('queue_id') == definition['queue_id']
            and leaf.get('claim') == (task.get('owner_claim') or {}).get('nonce')
            and worker.get('pid') == event.get('pid')
            and event.get('leaf_evidence_sha256') == digest(encoded(leaf))
            and result.get('receipt_sha256') == digest(encoded(receipt)))
        if valid_receipt:
            try:
                proof = receipt_reader(receipt)
            except Exception:
                proof = None
        verified = (isinstance(proof, dict) and proof.get('native_verified') is True
            and proof.get('task_id') == task_id
            and proof.get('receipt_sha256') == result.get('receipt_sha256'))
        rows.append({'task_id': task_id, 'state': task.get('status'),
                     'note': task.get('note'), 'claim': task.get('owner_claim'),
                     'receipt_sha256': result.get('receipt_sha256'),
                     'phase': receipt.get('phase'), 'worker_pid': event.get('pid'),
                     'worker_start_ticks': worker.get('process_starttime'),
                     'scope': result.get('scope'), 'parent_task_accepted': False,
                     'check_passed': leaf.get('check_passed'),
                     'blockers': leaf.get('blockers'),
                     'exact_s03_readback_verified': verified,
                     's03_item_id': proof.get('s03_item_id') if verified else None})
    return {'native_subexecutors': native, 'leaf_tasks': rows,
            'observed_at': time.time()}


def install(bundle, specification, root=ROOT):
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch(r'[0-9]{1,24}', request) and
            re.fullmatch(r'[a-f0-9]{40}', source), 'OWNER_OPERATION_CONTEXT')
    root = Path(root)
    assets = decode_assets(bundle, specification)
    handoff = validate_handoff(assets)
    require(stop_clear(root), 'OWNER_STOP')
    before = preimages(root, specification['expected_native'])
    config = prepare_config(before[CONFIG], assets, specification, request, source)
    changes = {target: assets[name] for name, target in specification['install_paths'].items()}
    changes[CONFIG] = config
    for relative in changes:
        if relative not in before:
            try:
                previous = read_regular(root / relative)
            except FileNotFoundError:
                previous = None
            require(previous is None or previous == changes[relative],
                    'ADDITIVE_PATH_ALREADY_DIFFERENT_' + Path(relative).name)
            before[relative] = previous
    protected = protected_snapshot(specification)
    lock_path = root / 'state/owner_maintenance.lock'
    require(not lock_path.is_symlink(), 'MAINTENANCE_LOCK_PATH')
    lock = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW)
    stopped = False
    applied = []
    receipt = {'schema': 'NOX_FOUR_QUEUE_NATIVE_INSTALL_V1', 'request': request,
               'source_sha': source, 'handoff': handoff, 'state': 'PREFLIGHT',
               'original_tasks_accepted': 0, 'training_started': False,
               'model_restarted': False, 'started_at': time.time()}
    final_baseline = None
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Hold('HOLD_FOUR_QUEUE_MAINTENANCE_LEASE_BUSY') from exc
        # Read the pinned files again under the same owner lease that fences installation.
        preimages(root, specification['expected_native'])
        require(stop_clear(root), 'OWNER_STOP_CHANGED')
        deadline = time.monotonic() + 35
        while True:
            state, active = queue_idle(root)
            if not active:
                break
            require(time.monotonic() < deadline, 'ACTIVE_TASKS_NOT_DRAINED')
            time.sleep(1)
        observed = supervisor('status')
        require(observed['state'] == 'RUNNING' and process_identity(observed['pid']),
                'ORIGINAL_DISPATCHER_NOT_RUNNING')
        require(protected_snapshot(specification) == protected, 'PROTECTED_CHANGED')
        backup = root / 'state/dispatcher/four_queue_rollback' / request
        require(not backup.exists(), 'BACKUP_ALREADY_EXISTS')
        backup.mkdir(parents=True, mode=0o700)
        for relative, raw in before.items():
            if raw is not None and relative in changes:
                atomic(backup / relative, raw)
        atomic(backup / 'original_queue_snapshot.json', encoded(state))
        atomic(backup / 'source_manifest.json', encoded({key: digest(value)
            for key, value in before.items() if value is not None}))
        receipt.update(previous_director=process_identity(observed['pid']),
                       backup_path=str(backup), previous_queue_entries=len(state['tasks']))
        stop_checked()
        stopped = True
        require(process_identity(observed['pid']) is None, 'DISPATCHER_STILL_ALIVE')
        require(stop_clear(root), 'OWNER_STOP_AFTER_DRAIN')
        require(protected_snapshot(specification) == protected, 'PROTECTED_CHANGED')
        # A completed stop makes the original writer's last snapshot authoritative.
        final_baseline, active = queue_idle(root)
        require(not active, 'ACTIVE_CLAIM_AFTER_DRAIN')
        atomic(backup / 'final_stopped_queue_snapshot.json', encoded(final_baseline))
        receipt['final_stopped_queue_sha256'] = digest(encoded(final_baseline))
        applied = apply_transaction(root, changes, before)
        require(stop_clear(root), 'OWNER_STOP_BEFORE_START')
        start_checked(root)
        stopped = False
        receipt.update(state='INSTALLED_NATIVE_ACCEPTANCE_PENDING',
                       installed_files={key: digest(value) for key, value in changes.items()},
                       protected_processes=protected)
    except BaseException as exc:
        receipt['state'] = str(exc) if isinstance(exc, Hold) else 'HOLD_FOUR_QUEUE_INSTALL_EXCEPTION'
        try:
            observed_now = supervisor('status')
            stopped = observed_now['state'] in ('STOPPED', 'FATAL', 'EXITED')
            if applied:
                stop_checked()
                stopped = True
                receipt['rollback'] = rollback_transaction(root, changes, before, applied)
            if stopped and stop_clear(root):
                restored = all(value is None or read_regular(root / key) == value
                    for key, value in before.items() if key in changes)
                require(restored, 'ROLLBACK_NOT_VERIFIED')
                start_checked(root)
                stopped = False
                receipt['restart_original'] = 'RUNNING_VERIFIED'
        except Exception as recovery_exc:
            receipt['recovery'] = str(recovery_exc) if isinstance(recovery_exc, Hold) else 'HOLD_RECOVERY_UNVERIFIED'
        print('NOX_MAINT_FOUR_QUEUE_INSTALL=' + json.dumps(receipt, ensure_ascii=False), flush=True)
        raise
    finally:
        os.close(lock)
    # The maintenance lease has been handed back. Native admission owns every task.
    snapshots = []
    deadline = time.monotonic() + 115
    last = None
    acceptance_error = None
    try:
      receipt_reader = load_receipt_reader(root, digest(assets['owner_subagent_dispatcher.py']))
      while time.monotonic() < deadline:
        require(stop_clear(root), 'OWNER_STOP_DURING_ACCEPTANCE')
        require(protected_snapshot(specification) == protected, 'PROTECTED_CHANGED')
        try:
            last = execution_snapshot(root, specification['leaf_catalog'], receipt_reader)
            workers = last['native_subexecutors'].get('workers') or []
            director = supervisor('status')
            valid = []
            for row in workers:
                identity = process_identity(row.get('pid'))
                if (identity and identity['ppid'] == director['pid']
                        and identity['start_ticks'] == row.get('process_starttime')
                        and type(row.get('heartbeat_at')) in (int, float)
                        and 0 <= time.time() - row['heartbeat_at'] <= 20):
                    valid.append({**row, 'observed_ppid': identity['ppid']})
            if len(workers) == len(valid) == len({row['pid'] for row in valid}) == 3:
                snapshots.append({'at': time.time(), 'workers': valid})
                if len(snapshots) > 2:
                    snapshots = [snapshots[0], snapshots[-1]]
            terminal = all(row['state'] in ('blocked', 'failed') or
                row['state'] == 'done' and row.get('exact_s03_readback_verified') is True
                for row in last['leaf_tasks'])
            if terminal and len(snapshots) >= 2:
                break
        except (OSError, ValueError, TypeError, Hold):
            pass
        time.sleep(2)
    except Exception as exc:
        acceptance_error = str(exc) if isinstance(exc, Hold) else 'HOLD_FOUR_QUEUE_ACCEPTANCE_IO'
    try:
        director = supervisor('status')
    except Exception:
        director = {'state': 'UNKNOWN'}
    receipt.update(finished_at=time.time(), readback=last, process_snapshots=snapshots,
                   director=director)
    preserved = False
    try:
        latest_state, _ = queue_idle(root)
        original = final_baseline['tasks']
        missing = sorted(set(original) - set(latest_state['tasks']))
        historical = {key: value for key, value in original.items()
                      if value.get('status') in ('done', 'failed', 'blocked')}
        changed = [key for key, value in historical.items()
                   if any(value.get(field) != latest_state['tasks'].get(key, {}).get(field)
                          for field in ('owner_claim', 'result'))]
        receipt['queue_preservation'] = {'original_ids': len(original),
            'missing_original_ids': missing,
            'historical_claim_receipt_entries': len(historical),
            'changed_historical_claim_receipt_ids': changed,
            'new_ids': sorted(set(latest_state['tasks']) - set(original))}
        preserved = not missing and not changed
    except Exception:
        receipt['queue_preservation'] = {'state': 'UNKNOWN_READBACK'}
    stable_workers = (len(snapshots) >= 2 and
        {(row['pid'], row['process_starttime'], row['observed_ppid']) for row in snapshots[0]['workers']} ==
        {(row['pid'], row['process_starttime'], row['observed_ppid']) for row in snapshots[-1]['workers']})
    receipt['same_worker_identities'] = stable_workers
    completed = [row for row in (last or {}).get('leaf_tasks', [])
                 if row['state'] == 'done' and row.get('exact_s03_readback_verified') is True]
    seen = {}
    for row in completed:
        identity = (row['worker_pid'], row['worker_start_ticks'])
        if all(type(value) is int and value > 0 for value in identity):
            seen.setdefault(identity, []).append(row['task_id'])
    receipt['same_process_successive_task_ids'] = [
        {'pid': key[0], 'start_ticks': key[1], 'task_ids': value}
        for key, value in seen.items() if len(value) >= 2]
    if stable_workers and len(completed) == 4 and preserved:
        receipt['state'] = 'THREE_NATIVE_WORKERS_FOUR_SCOPED_LEAVES_COMPLETED'
    else:
        receipt['state'] = 'INSTALLED_NATIVE_EXECUTION_NOT_FULLY_VERIFIED'
    if acceptance_error:
        receipt['state'] = acceptance_error
    destination = root / 'state/dispatcher' / ('four_queue_install_' + request + '.json')
    atomic(destination, encoded(receipt))
    require(read_regular(destination) == encoded(receipt), 'FINAL_RECEIPT_READBACK')
    print('NOX_MAINT_FOUR_QUEUE_INSTALL=' + json.dumps(receipt, ensure_ascii=False), flush=True)
    return receipt


def main():
    try:
        install(BUNDLE, SPEC)
    except Exception as exc:
        error = str(exc) if isinstance(exc, Hold) else type(exc).__name__
        print('NOX_MAINT_FOUR_QUEUE_ERROR=' + json.dumps({'error': error[:240]}), flush=True)
        raise
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    main()
