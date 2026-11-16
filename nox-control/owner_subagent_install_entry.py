#!/usr/bin/env python3
"""Pinned owner maintenance: attach real workers to the original dispatcher.

Only the known dispatcher service is briefly restarted after draining claims.
The model, trainer, priority scheduler, owner STOP and existing S03 are retained.
Success requires three real review jobs and durable S03 receipts, not code PASS.
"""
from __future__ import annotations

import base64
import configparser
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
import urllib.request

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
SCRIPTS = ROOT/'scripts'
STATE = ROOT/'state'
DISPATCHER = SCRIPTS/'nox_dispatcher_t855u.py'
SERVICE = 'nox-dispatcher-t855u'
SUPERVISOR_CONFIG = Path('/etc/supervisor/conf.d/nox-t855u.conf')
SUPERVISOR_SHA = 'f9ec50e6feb5b39307666b109623234624c30e5c3dd8ec496d7f5d51a69f41b5'
BASE_DISPATCHER = 'a4097dae395f4289a7c67faa0047c0027dc128a9607f3f8189b4270bc5f7426b'
DEPENDENCY_PINS = {
    'owner_task_plans.py': '7eb207b361086d3c34299b44fb36d96758cf824a7bf68a05e7868408d646f773',
    'owner_task_lifecycle.py': '909502a75799096e094a622639fe959ecfa835cc70db705a4062541940cea27e',
    'owner_dispatcher_mentor.py': '12211a29f77de8e5181d4dd78c35d5da2ed5de0dc6ea529149d32f0896809292',
    'owner_event_outbox.py': 'e15d458f9d1f03b23fcbf0267206621769ff92f2bfe00d3baf79217e2ab74a02',
    's03_memory.py': '3ebdc3585f32bafbd0e1210ceee286b174a657c37696e16fce9fcafb57c43e10',
}
POLICY_NAME = 'NOX_PRIME_SIX_RELAY_20261115.md'
POLICY_SHA = '84780aaf911a229a654995f38972cdad5d99c72ab38842f76f787ec280acb46f'
MODULE_NAMES = ('owner_subagent_processes.py', 'owner_autonomy_pool.py', 'owner_subagent_dispatcher.py')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def emit(kind, value):
    print('NOX_MAINT_REPAIR='+json.dumps({'kind': kind, 'data': value}, separators=(',', ':')), flush=True)


def hold(code):
    raise RuntimeError(code)


def read(path, maximum=1024*1024):
    path = Path(path)
    if any(p.is_symlink() for p in (*path.parents, path)):
        hold('HOLD_NATIVE_INSTALL_SYMLINK')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            hold('HOLD_NATIVE_INSTALL_FILE_SCOPE')
        raw = stream.read(maximum+1)
    if len(raw) > maximum:
        hold('HOLD_NATIVE_INSTALL_FILE_SCOPE')
    return raw


def atomic(path, raw):
    path = Path(path)
    if any(p.is_symlink() for p in (*path.parents, path)):
        hold('HOLD_NATIVE_INSTALL_SYMLINK')
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.native-subagent-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def command(args, timeout=10):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout


def service():
    rc, output = command(['supervisorctl', 'status', SERVICE])
    match = re.match('^'+re.escape(SERVICE)+r'\s+(RUNNING|STOPPED|STARTING|STOPPING|BACKOFF|FATAL|EXITED|UNKNOWN)\b(?:\s+pid\s+(\d+))?', output.strip())
    return {'rc': rc, 'state': match[1] if match else 'UNKNOWN',
            'pid': int(match[2]) if match and match[2] else None}


def process(pid):
    try:
        folder = Path('/proc', str(int(pid)))
        fields = (folder/'stat').read_text().split(') ', 1)[1].split()
        argv = [x.decode() for x in (folder/'cmdline').read_bytes().split(b'\0') if x]
        return {'pid': int(pid), 'ppid': int(fields[1]), 'pgrp': int(fields[2]),
                'state': fields[0], 'starttime': int(fields[19]), 'argv': argv}
    except (OSError, ValueError, IndexError):
        return None


def active_model():
    rows = []
    for folder in Path('/proc').iterdir():
        if not folder.name.isdigit():
            continue
        try:
            if (folder/'comm').read_text().strip() != 'llama-server':
                continue
        except OSError:
            continue
        row = process(int(folder.name))
        if row and '--port' in row['argv']:
            index = row['argv'].index('--port')
            if row['argv'][index+1:index+2] == ['8081']:
                rows.append({'pid': row['pid'], 'starttime': row['starttime']})
    if len(rows) != 1:
        hold('HOLD_NATIVE_CHAT_MODEL_IDENTITY')
    return rows[0]


def health():
    result = {}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for port in (8080, 8081, 8082):
        try:
            with opener.open('http://127.0.0.1:%d/health' % port, timeout=2) as response:
                result[str(port)] = response.status
        except OSError:
            result[str(port)] = None
    return result


def global_stop():
    return any(path.exists() or path.is_symlink() for path in (
        ROOT/'STOP', ROOT/'STOP.flag', ROOT/'stop.flag', ROOT/'.stop', ROOT/'program/STOP',
        STATE/'STOP', Path('/workspace/NOX_STOP')))


def training_hold_observation():
    """Metadata of the one documented flag; never export arbitrary contents."""
    path = STATE/'TRAIN_HOLD.flag'
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {'path': str(path), 'present': False}
    result = {'path': str(path), 'present': True, 'bytes': info.st_size,
              'mtime_ns': info.st_mtime_ns, 'sha256': None}
    if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
        return {**result, 'classification': 'UNVERIFIED_TYPE_OR_SIZE'}
    try:
        raw = read(path, 4096)
        after = path.lstat()
        if (info.st_ino, info.st_size, info.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            return {**result, 'classification': 'UNVERIFIED_CHANGED'}
    except (OSError, RuntimeError):
        return {**result, 'classification': 'UNVERIFIED_UNREADABLE'}
    result['sha256'] = digest(raw)
    match = re.fullmatch(rb'OWNER_HYBRID_FAILED request=([0-9]{1,24})\n', raw)
    if match:
        result.update(classification='OWNER_HYBRID_FAILED', request=match[1].decode('ascii'))
    else:
        result['classification'] = 'OTHER_HOLD_CONTENT_NOT_EXPORTED'
    return result


def queue_state():
    value = json.loads(read(STATE/'dispatcher/state.json', 16*1024*1024))
    if not isinstance(value, dict) or not isinstance(value.get('tasks'), dict):
        hold('HOLD_NATIVE_QUEUE_SCHEMA')
    return value


def owner_events(expected):
    folder = STATE/'owner_events'
    try:
        cursor = json.loads(read(folder/'cursor.json', 24000))['last_sequence']
        events = []
        for sequence in range(max(1, cursor-49), cursor+1):
            row = json.loads(read(folder/'events'/('%016d.json' % sequence), 24000))
            task_id = (row.get('task') or {}).get('id')
            if (task_id in expected and row.get('kind') == 'task_verified'
                    and (row.get('verification') or {}).get('scope') == 'NATIVE_REVIEW_AND_S03_RECEIPT'):
                events.append({key: row.get(key) for key in ('event_id', 'sequence', 'task', 'verification', 'kind')})
        return events
    except (OSError, ValueError, KeyError, TypeError):
        return []


def sources():
    if digest(read(DISPATCHER)) != BASE_DISPATCHER:
        hold('HOLD_NATIVE_DISPATCHER_SOURCE_CHANGED')
    for name, pin in DEPENDENCY_PINS.items():
        if digest(read(SCRIPTS/name)) != pin:
            hold('HOLD_NATIVE_DISPATCHER_DEPENDENCY_CHANGED')
    if digest(read(SUPERVISOR_CONFIG, 32768)) != SUPERVISOR_SHA:
        hold('HOLD_NATIVE_DISPATCHER_SUPERVISOR_CHANGED')
    config = configparser.ConfigParser(interpolation=None)
    config.read_string(read(SUPERVISOR_CONFIG).decode())
    settings = config['program:'+SERVICE]
    if settings.get('stopasgroup') != 'true' or settings.get('killasgroup') != 'true':
        hold('HOLD_NATIVE_DISPATCHER_GROUP_POLICY')


def reviewed_modules():
    assets = {}
    for name in (*MODULE_NAMES, POLICY_NAME):
        raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
        if not raw or len(raw) > 262144:
            hold('HOLD_NATIVE_SUBAGENT_BUNDLE_MISSING')
        if name.endswith('.py'):
            compile(raw, name, 'exec')
        elif digest(raw) != POLICY_SHA:
            hold('HOLD_NATIVE_SUBAGENT_POLICY_BUNDLE')
        assets[name] = raw
    for name in MODULE_NAMES:
        module_name = name[:-3]
        module = types.ModuleType(module_name)
        module.__file__ = str(SCRIPTS/name)
        sys.modules[module_name] = module
        exec(compile(assets[name], str(SCRIPTS/name), 'exec'), module.__dict__)
    return assets, sys.modules['owner_subagent_dispatcher']


def catalog(module, policy_sha):
    titles = {'runtime': 'Проверить текущие ресурсы и dispatcher',
              'memory': 'Проверить исходную S03 и подтверждения задач',
              'weights': 'Отделить факты старого обучения от новых весов'}
    return {'schema': module.autonomy.SCHEMA,
            'tasks': [{'id': 'owner.native.v06.'+role+'.'+policy_sha[:12],
                       'handler': module.HANDLER, 'deps': [], 'priority': 'P1',
                       'resource': 'CPU_LIGHT', 'source_sha256': policy_sha,
                       'params': {'role': role}, 'title': titles[role]}
                      for role in module.ROLES]}


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}', source):
        hold('HOLD_NATIVE_OWNER_CONTEXT')
    receipt_path = STATE/('owner_native_subagents_install_'+request+'.json')
    if receipt_path.exists() or receipt_path.is_symlink():
        hold('HOLD_NATIVE_REQUEST_ALREADY_STARTED_READ_RECEIPT')
    assets, module = reviewed_modules()
    sources()
    if global_stop():
        hold('HOLD_OWNER_STOP')
    original = read(DISPATCHER)
    patched = module.patch_dispatcher(original.decode(), BASE_DISPATCHER).encode()
    config = {'schema': module.SCHEMA, 'policy_id': module.POLICY_ID, 'instance_id': 60509551,
              'mode': 'NORMAL', 'target': 3, 'owner_authorized': True,
              'owner_request': request, 'owner_source_sha': source,
              'policy': {'path': str(module.POLICY), 'sha256': POLICY_SHA},
              'module_pins': {name: digest(assets[name]) for name in MODULE_NAMES}}
    config['catalog'] = catalog(module, POLICY_SHA)
    config['catalog_sha256'] = digest(module.encoded(config['catalog']))
    targets = {SCRIPTS/name: assets[name] for name in MODULE_NAMES}
    targets.update({module.POLICY: assets[POLICY_NAME], module.CONFIG: module.encoded(config)})
    for target in targets:
        if target.exists() or target.is_symlink():
            hold('HOLD_NATIVE_SUBAGENT_TARGET_ALREADY_EXISTS')
    model_before = active_model()
    before_health = health()
    if any(before_health.get(str(port)) != 200 for port in (8080, 8081, 8082)):
        hold('HOLD_NATIVE_CORE_HEALTH')
    current = int(Path('/sys/fs/cgroup/memory.current').read_text())
    maximum = int(Path('/sys/fs/cgroup/memory.max').read_text())
    disk = os.statvfs(str(ROOT))
    if maximum-current < 4*1024**3 or disk.f_bavail*disk.f_frsize < 1024**3:
        hold('HOLD_NATIVE_SUBAGENT_RESOURCE_HEADROOM')
    fd = os.open(STATE/'owner_maintenance.lock', os.O_RDWR | os.O_NOFOLLOW)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    flag = STATE/'OWNER_MAINTENANCE.flag'
    if flag.exists() or flag.is_symlink():
        os.close(fd)
        hold('HOLD_EXISTING_OWNER_MAINTENANCE')
    note = ('NOX_NATIVE_SUBAGENT_INSTALL '+request+' '+source+'\n').encode()
    result = {'schema': 'NOX_NATIVE_SUBAGENT_INSTALL_RECEIPT_V1', 'request': request,
              'source_sha': source, 'started_at': time.time(), 'state': 'PREFLIGHT',
              'policy_sha256': POLICY_SHA, 'policy_bytes': len(assets[POLICY_NAME]),
              'source_pins': config['module_pins'], 'dispatcher_before_sha256': BASE_DISPATCHER,
              'dispatcher_after_sha256': digest(patched), 'active_model_before': model_before,
              'chat_health_before': before_health, 'training_started': False,
              'legacy_training_hold_before': training_hold_observation(),
              'weights_changed': False, 'global_stop_cleared': False, 'new_daemon': False,
              'original_dispatcher_thread_runners': 6, 'native_subexecutor_target': 3}
    backup = ROOT/'backup/owner_native_subagents'/request
    installed = []
    dispatcher_stopped = False
    released = False
    success = False
    def save():
        atomic(receipt_path, module.encoded(result))
    try:
        atomic(flag, note)
        save()
        deadline = time.monotonic()+25
        while any(t.get('status') == 'running' for t in queue_state()['tasks'].values()):
            if time.monotonic() >= deadline:
                hold('HOLD_NATIVE_DISPATCHER_ACTIVE_CLAIMS')
            time.sleep(.5)
        if global_stop():
            hold('HOLD_OWNER_STOP')
        sources()
        observed = service()
        owner = process(observed['pid']) if observed['pid'] else None
        if observed['state'] != 'RUNNING' or not owner or str(DISPATCHER) not in owner['argv']:
            hold('HOLD_NATIVE_DISPATCHER_IDENTITY')
        group = [row for folder in Path('/proc').iterdir() if folder.name.isdigit()
                 and (row := process(int(folder.name))) and row['pgrp'] == owner['pgrp'] and row['state'] != 'Z']
        if any(row['pid'] != owner['pid'] for row in group):
            hold('HOLD_NATIVE_DISPATCHER_OTHER_PROCESS_IN_GROUP')
        atomic(backup/'nox_dispatcher_t855u.py', original)
        stop_rc = command(['supervisorctl', 'stop', SERVICE], 25)[0]
        dispatcher_stopped = service()['state'] == 'STOPPED'
        if stop_rc != 0 or not dispatcher_stopped:
            hold('HOLD_NATIVE_DISPATCHER_STOP_UNVERIFIED')
        if any(t.get('status') == 'running' for t in queue_state()['tasks'].values()):
            hold('HOLD_NATIVE_QUEUE_CHANGED_DURING_DRAIN')
        for target, raw in targets.items():
            if target.exists() or target.is_symlink():
                hold('HOLD_NATIVE_SUBAGENT_TARGET_CHANGED')
            atomic(target, raw)
            installed.append(target)
            if digest(read(target)) != digest(raw):
                hold('HOLD_NATIVE_SUBAGENT_INSTALL_READBACK')
        atomic(DISPATCHER, patched)
        if digest(read(DISPATCHER)) != digest(patched):
            hold('HOLD_NATIVE_SUBAGENT_DISPATCHER_READBACK')
        result['state'] = 'INSTALLED_AWAITING_NATIVE_JOBS'
        save()
        if command(['supervisorctl', 'start', SERVICE], 30)[0] != 0 or service()['state'] != 'RUNNING':
            hold('HOLD_NATIVE_DISPATCHER_START_UNVERIFIED')
        dispatcher_stopped = False
        if active_model() != model_before or health() != before_health:
            hold('HOLD_NATIVE_CORE_IDENTITY_CHANGED')
        if read(flag, 4096) != note:
            hold('HOLD_NATIVE_MAINTENANCE_OWNER_CHANGED')
        flag.unlink()
        os.close(fd)
        fd = None
        released = True
        deadline = time.monotonic()+180
        expected = {task['id'] for task in config['catalog']['tasks']}
        while time.monotonic() < deadline:
            state = queue_state()
            tasks = [state['tasks'].get(tid, {}) for tid in sorted(expected)]
            if global_stop():
                hold('HOLD_OWNER_STOP')
            if all(task.get('status') == 'done' for task in tasks):
                proofs = []
                for task in tasks:
                    evidence = task.get('result') or {}
                    receipt = evidence.get('receipt')
                    if not isinstance(receipt, dict) or receipt.get('phase') != 'NATIVE_REVIEW_COMPLETED_CANDIDATE_NOT_APPLIED':
                        hold('HOLD_NATIVE_REVIEW_RESULT_SCHEMA')
                    proof = module.s03_readback(receipt)
                    if not proof or proof['receipt_sha256'] != evidence.get('receipt_sha256'):
                        hold('HOLD_NATIVE_REVIEW_S03_READBACK')
                    proofs.append({'task_id': task['id'], 'job_id': receipt['job_id'],
                        'claim': task.get('owner_claim'), 's03': proof,
                        'worker': receipt['worker_result']['native_observation']['worker'],
                        'policy_ack': receipt['worker_result']['native_observation']['policy_ack'],
                        'model_response': receipt['worker_result'].get('model_response'),
                        'scope': 'NATIVE_TECHNICAL_REVIEW_CANDIDATE_NOT_APPLIED'})
                agent_status = json.loads(read(ROOT/'status/agents_t856u.json', 750000))
                native = agent_status.get('native_subexecutors', {})
                workers = native.get('workers', [])
                checked = module.autonomy.verify_distinct_native_processes(workers, requested=3)
                if any(module.process_identity(row['pid']) != {
                        key: row[key] for key in ('pid', 'ppid', 'process_starttime')} for row in checked):
                    hold('HOLD_NATIVE_SUBAGENT_PROCESS_READBACK')
                if (not isinstance(native.get('observed_at'), (int, float))
                        or not 0 <= time.time()-native['observed_at'] <= 15
                        or any(not isinstance(row.get('heartbeat_at'), (int, float))
                               or not 0 <= time.time()-row['heartbeat_at'] <= 15 for row in checked)):
                    time.sleep(1)
                    continue
                if len({proof['worker']['pid'] for proof in proofs}) != 3:
                    hold('HOLD_NATIVE_SUBAGENT_JOB_PID_DISTINCTNESS')
                events = owner_events(expected)
                if {row['task']['id'] for row in events} != expected:
                    time.sleep(1)
                    continue
                if any(not any(event['task'].get('claim') == proof['claim']['nonce']
                               and event['verification'].get('receipt_sha256') == proof['s03']['receipt_sha256']
                               for event in events if event['task']['id'] == proof['task_id']) for proof in proofs):
                    hold('HOLD_NATIVE_TASK_CALLBACK_IDENTITY')
                result.update(state='LIVE_NATIVE_REVIEWS_AND_S03_VERIFIED', jobs=proofs,
                              native_pool=native, active_model_after=active_model(),
                              chat_health_after=health(), owner_task_events=events, finished_at=time.time())
                if result['active_model_after'] != model_before or result['chat_health_after'] != before_health:
                    hold('HOLD_NATIVE_CORE_IDENTITY_CHANGED')
                success = True
                break
            failed = [task for task in tasks if task.get('status') in ('blocked', 'failed')
                      and task.get('note') != 'WAIT_S03_ADMISSION_READBACK']
            if failed:
                result['task_holds'] = [{'id': t.get('id'), 'status': t.get('status'), 'note': t.get('note')}
                                        for t in failed]
                hold('HOLD_NATIVE_REVIEW_TASK_BLOCKED')
            time.sleep(2)
        if not success:
            hold('HOLD_NATIVE_REVIEW_ACCEPTANCE_TIMEOUT')
    except Exception as exc:
        message = str(exc)
        result.update(state='HOLD', error=message if re.fullmatch('HOLD_[A-Z0-9_]+', message) else type(exc).__name__)
        if not released:
            # No jobs were admitted under the maintenance flag. Restore only
            # this exact source and the newly installed, SHA-matched assets.
            try:
                if service()['state'] == 'RUNNING' and installed:
                    command(['supervisorctl', 'stop', SERVICE], 25)
                    dispatcher_stopped = True
                if digest(read(DISPATCHER)) == digest(patched):
                    atomic(DISPATCHER, original)
                for target in reversed(installed):
                    if target.exists() and digest(read(target)) == digest(targets[target]):
                        target.unlink()
                if dispatcher_stopped:
                    command(['supervisorctl', 'start', SERVICE], 30)
                result['rollback_service'] = service()
            except Exception as rollback_error:
                result['rollback_error'] = type(rollback_error).__name__
    finally:
        if fd is not None:
            try:
                if flag.exists() and read(flag, 4096) == note:
                    flag.unlink()
            finally:
                os.close(fd)
        result['source_installed'] = released
        result['legacy_training_hold_after'] = training_hold_observation()
        result['receipt_path'] = str(receipt_path)
        save()
        emit('native_subagent_install', result)
    print('NOX_MAINT_REPAIR_COMPLETE='+str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    try:
        code = main()
    except Exception as exc:
        reason = str(exc)
        emit('native_subagent_preflight', {'state': 'HOLD',
             'reason': reason if re.fullmatch('HOLD_[A-Z0-9_]+', reason) else type(exc).__name__})
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        code = 2
    raise SystemExit(code)
