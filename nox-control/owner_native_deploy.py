#!/usr/bin/env python3
"""Owner-gated, file-scoped installer for PR #444 idle-pool recovery.

The installer accepts only the two reviewed runtime modules and the generated
instruction-truth callback. It restarts only the fixed dispatcher PID using
SIGTERM; it has no terminate/kill/process-group fallback.
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
import signal
import stat
import subprocess
import tempfile
import time

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
SERVICE = 'nox-dispatcher-t855u'
SERVICE_CONFIG = Path('/etc/supervisor/conf.d/nox-dispatcher-t855u.conf')
CONFIG = ROOT / 'config/owner_native_subagents.json'
STATE = ROOT / 'state/dispatcher/state.json'
STATUS = ROOT / 'status/agents_t856u.json'
LOCK = ROOT / 'state/owner_maintenance.lock'
TARGETS = {
    'owner_subagent_dispatcher.py': ROOT / 'scripts/owner_subagent_dispatcher.py',
    'owner_subagent_processes.py': ROOT / 'scripts/owner_subagent_processes.py',
    'owner_subagent_instruction_truth.py': ROOT / 'scripts/owner_subagent_instruction_truth.py',
}
ASSET_SHA256 = {
    'owner_subagent_dispatcher.py': '9071db188cee194dcaa8e26d0a6599288d2cf397ebe5bee5357848fd6cc54ede',
    'owner_subagent_processes.py': 'b6a8980a96fddeb433bd87179aab1817e3e2d1f3315a0c737c738050c7087a9d',
    'owner_subagent_instruction_truth.py': '3ee5ff3c66d11d19fbd24423bd147411d7ec0b4afac14268f86d0baa0f7a1f20',
}
STOP_PATHS = ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP',
              'state/STOP', 'state/STOP.flag', 'state/OWNER_MAINTENANCE.flag')
SHA = re.compile(r'^[a-f0-9]{64}$')


class Hold(RuntimeError):
    pass


def require(ok, code):
    if not ok:
        raise Hold('HOLD_PR444_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def decode_bundle(bundle):
    require(isinstance(bundle, dict) and set(bundle) == set(ASSET_SHA256), 'BUNDLE_FILE_SET')
    result = {}
    for name, pin in ASSET_SHA256.items():
        item = bundle[name]
        require(isinstance(item, dict) and set(item) == {'content', 'sha256'}, 'BUNDLE_ITEM_SCHEMA')
        require(item['sha256'] == pin, 'BUNDLE_DECLARED_PIN')
        try:
            raw = base64.b64decode(item['content'], validate=True)
        except (ValueError, TypeError):
            raise Hold('HOLD_PR444_BUNDLE_BASE64')
        require(digest(raw) == pin, 'BUNDLE_CONTENT_PIN')
        compile(raw, name, 'exec')
        result[name] = raw
    return result


def read_regular(path, limit=8 * 1024 * 1024):
    path = Path(path)
    require(not path.is_symlink(), 'SYMLINK')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
        require(os.path.isfile(path) and st.st_nlink == 1 and st.st_size <= limit, 'REGULAR_FILE')
        raw = b''
        while len(raw) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        require(len(raw) <= limit, 'FILE_LIMIT')
        return raw
    finally:
        os.close(fd)


def atomic_write(path, raw, mode):
    path = Path(path)
    require(path.parent.is_dir() and not path.parent.is_symlink(), 'WRITE_PARENT')
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb', closefd=True) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def identity(pid):
    if type(pid) is not int or pid <= 1:
        return None
    try:
        tail = Path('/proc', str(pid), 'stat').read_text().rsplit(') ', 1)[1].split()
        if tail[0] not in ('R', 'S', 'D', 'I'):
            return None
        return {'pid': pid, 'ppid': int(tail[1]), 'pgrp': int(tail[2]),
                'start_ticks': int(tail[19])}
    except (OSError, ValueError, IndexError):
        return None


def descendants(pid):
    seen, pending = set(), [pid]
    while pending:
        parent = pending.pop(0)
        if parent in seen:
            continue
        seen.add(parent)
        require(len(seen) <= 64, 'PROCESS_BOUND')
        for task in (Path('/proc') / str(parent) / 'task').glob('*/children'):
            try:
                children = task.read_text().split()
            except OSError:
                continue
            require(len(children) <= 256 and all(x.isdigit() for x in children), 'CHILD_SCHEMA')
            for child in map(int, children):
                actual = identity(child)
                if actual and actual['ppid'] == parent and child not in seen:
                    pending.append(child)
    return [identity(pid) for pid in sorted(seen - {pid}) if identity(pid)]


def pgrp_members(pgrp):
    members = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        row = identity(int(entry.name))
        if row and row['pgrp'] == pgrp:
            members.append(row['pid'])
    return sorted(members)


def supervisor(action):
    require(action in ('status', 'start'), 'SUPERVISOR_ACTION')
    result = subprocess.run(['supervisorctl', action, SERVICE], capture_output=True,
                            text=True, timeout=25)
    if action == 'status':
        match = re.fullmatch(re.escape(SERVICE) +
            r'\s+(RUNNING|STOPPED|STARTING|STOPPING|BACKOFF|FATAL|EXITED)\b(?:\s+pid\s+(\d+))?.*',
            result.stdout.strip())
        require(match is not None, 'SUPERVISOR_STATUS')
        return {'state': match[1], 'pid': int(match[2]) if match[2] else None}
    require(result.returncode == 0, 'SUPERVISOR_START')
    return {'state': 'START_REQUESTED'}


def stop_flags_clear():
    return not any((ROOT / name).exists() or (ROOT / name).is_symlink()
                   for name in STOP_PATHS) and not Path('/workspace/NOX_STOP').exists()


def config_doc():
    raw = read_regular(CONFIG, 1024 * 1024)
    doc = json.loads(raw)
    require(isinstance(doc, dict) and doc.get('owner_authorized') is True
            and doc.get('instance_id') == 60509551, 'CONFIG_SCOPE')
    pins = doc.get('module_pins')
    require(isinstance(pins, dict), 'CONFIG_PINS')
    for name, path in TARGETS.items():
        require(pins.get(name) == digest(read_regular(path)), 'CONFIG_PREIMAGE_PIN')
    return raw, doc


def queue_is_idle():
    state = json.loads(read_regular(STATE, 16 * 1024 * 1024))
    tasks = state.get('tasks')
    require(isinstance(tasks, dict), 'QUEUE_SCHEMA')
    for row in tasks.values():
        if not isinstance(row, dict):
            continue
        require(row.get('status') != 'running', 'ACTIVE_QUEUE_TASK')
        if row.get('status') not in ('done', 'completed', 'blocked', 'failed'):
            require(row.get('owner_claim') is None, 'ACTIVE_QUEUE_CLAIM')
        lease = row.get('native_worker_lease')
        require(lease is None or (isinstance(lease, dict) and lease.get('phase') == 'SETTLED'),
                'ACTIVE_WORKER_LEASE')
        require(row.get('native_pool_recovery') is None, 'POOL_RECOVERY_ACTIVE')
    return digest(json.dumps(state, sort_keys=True, separators=(',', ':')).encode())


def supervisor_config():
    raw = read_regular(SERVICE_CONFIG, 65536)
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.read_string(raw.decode('utf-8'))
    require(parser.has_section('program:' + SERVICE), 'SERVICE_CONFIG_SECTION')
    section = parser['program:' + SERVICE]
    command = section.get('command', '').strip()
    require(command.startswith('/usr/bin/python') and
            '/root/nox/scripts/nox_dispatcher_t855u.py' in command, 'SERVICE_COMMAND')
    require(section.get('stopsignal', 'TERM').upper() == 'TERM', 'SERVICE_STOPSIGNAL')
    require(section.get('stopasgroup', 'false').lower() == 'false'
            and section.get('killasgroup', 'false').lower() == 'false', 'SERVICE_GROUP_SIGNAL')
    require(section.get('autorestart', 'unexpected').lower() == 'false', 'SERVICE_AUTORESTART')
    return digest(raw)


def validate_gate(gate, now=None):
    now = time.time() if now is None else now
    require(isinstance(gate, dict), 'GATE_SCHEMA')
    require(gate.get('owner_authenticated') is True and
            re.fullmatch(r'[0-9]{1,24}', str(gate.get('request_id', ''))) is not None and
            re.fullmatch(r'[a-f0-9]{40}', str(gate.get('source_sha', ''))) is not None,
            'OWNER_AUTH')
    observed = gate.get('observed_at')
    require(type(observed) in (float, int) and 0 <= now - observed <= 30, 'GATE_STALE')
    require(gate.get('owner_lock_held') is True and gate.get('stop_flags_clear') is True,
            'OWNER_LOCK_OR_STOP')
    require(gate.get('queue_claims_clear') is True and gate.get('pool_idle') is True,
            'QUEUE_OR_POOL_BUSY')
    require(gate.get('service') == SERVICE and gate.get('pid', 0) > 1 and
            gate.get('start_ticks', 0) > 0 and gate.get('pgrp', 0) > 1,
            'SERVICE_IDENTITY')
    require(SHA.fullmatch(str(gate.get('service_config_sha256', ''))) is not None
            and gate.get('pgid_members_exact') is True, 'SERVICE_SCOPE')
    require(gate.get('signal_mode') == 'SINGLE_PID_SIGTERM_NO_FALLBACK', 'SIGNAL_POLICY')
    return gate


def collect_gate(request_id, source_sha, lock_held):
    require(os.geteuid() == 0, 'OWNER_RUNTIME')
    require(stop_flags_clear(), 'STOP_FLAG')
    raw_config, config = config_doc()
    config_sha = supervisor_config()
    queue_sha = queue_is_idle()
    status_doc = json.loads(read_regular(STATUS, 2 * 1024 * 1024))
    native = status_doc.get('native_subexecutors')
    require(isinstance(native, dict) and native.get('state') != 'HOLD_NATIVE_STATUS_PROJECTION',
            'NATIVE_STATUS')
    observed = native.get('observed_at')
    require(type(observed) in (int, float) and 0 <= time.time() - observed <= 15, 'NATIVE_STATUS_STALE')
    director = native.get('director')
    require(isinstance(director, dict), 'DIRECTOR_STATUS')
    current = identity(director.get('pid'))
    require(current and current['start_ticks'] == director.get('start_ticks')
            and current['pgrp'] > 1, 'DIRECTOR_IDENTITY')
    workers = native.get('workers')
    require(isinstance(workers, list) and len(workers) == 3, 'WORKER_COUNT')
    expected = {current['pid']}
    for worker in workers:
        require(isinstance(worker, dict) and worker.get('native_pid_verified') is True
                and worker.get('state') == 'RUNNING' and worker.get('current_task') is None,
                'WORKER_NOT_IDLE')
        actual = identity(worker.get('pid'))
        require(actual and actual['ppid'] == current['pid']
                and actual['start_ticks'] == worker.get('start_ticks'), 'WORKER_IDENTITY')
        expected.add(actual['pid'])
    child_rows = descendants(current['pid'])
    child_ids = {row['pid'] for row in child_rows}
    require(expected - {current['pid']} <= child_ids, 'WORKER_CENSUS')
    group = pgrp_members(current['pgrp'])
    require(set(group) <= expected | child_ids and current['pid'] in group, 'UNRELATED_PGID_MEMBER')
    return validate_gate({
        'owner_authenticated': True, 'request_id': request_id, 'source_sha': source_sha,
        'observed_at': time.time(), 'owner_lock_held': lock_held,
        'stop_flags_clear': stop_flags_clear(), 'queue_claims_clear': True,
        'pool_idle': True, 'service': SERVICE, 'pid': current['pid'],
        'start_ticks': current['start_ticks'], 'pgrp': current['pgrp'],
        'service_config_sha256': config_sha, 'pgid_members_exact': True,
        'pgid_members': group, 'pgid_processes': group_rows,\n        'children': child_rows, 'queue_state_sha256': queue_sha,
        'config_sha256': digest(raw_config), 'signal_mode': 'SINGLE_PID_SIGTERM_NO_FALLBACK',
        'workers': sorted(expected - {current['pid']}),
    })


def write_receipt(receipt):
    path = ROOT / ('state/dispatcher/pr444_idle_install_' + receipt['request_id'] + '.json')
    atomic_write(path, json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode(), 0o600)
    print('NOX_PR444_IDLE_INSTALL=' + json.dumps(receipt, sort_keys=True), flush=True)


def run(bundle=BUNDLE, root=ROOT):
    require(Path(root) == ROOT, 'INSTANCE_ROOT')
    assets = decode_bundle(bundle)
    request_id = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source_sha = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch(r'[0-9]{1,24}', request_id) is not None
            and re.fullmatch(r'[a-f0-9]{40}', source_sha) is not None, 'OWNER_CONTEXT')
    lock_fd = os.open(LOCK, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    receipt = {'schema':'NOX_PR444_IDLE_INSTALL_RECEIPT_V1', 'request_id':request_id,
               'source_sha':source_sha, 'started_at':time.time(), 'state':'PREFLIGHT',
               'files_changed':0, 'kill_fallbacks':0}
    before, changes, applied = {}, {}, []
    old_identity = None
    stopped = False
    try:
        st = os.fstat(lock_fd)
        require(st.st_uid == 0 and st.st_nlink == 1 and not st.st_mode & 0o022,
                'OWNER_LOCK_METADATA')
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Hold('HOLD_PR444_OWNER_LOCK_BUSY') from exc
        gate = collect_gate(request_id, source_sha, True)
        receipt['pre_gate'] = gate
        old_identity = {'pid':gate['pid'], 'start_ticks':gate['start_ticks'], 'pgrp':gate['pgrp']}
        config_raw, config = config_doc()
        for name, path in TARGETS.items():
            before[str(path)] = read_regular(path)
            changes[str(path)] = assets[name]
        new_config = json.loads(config_raw)
        for name, raw in assets.items():
            new_config['module_pins'][name] = digest(raw)
        changes[str(CONFIG)] = (json.dumps(new_config, sort_keys=True, indent=2) + '\n').encode()
        require(digest(config_raw) == gate['config_sha256'], 'CONFIG_CAS')
        backup = ROOT / 'state/dispatcher/pr444_idle_install_backup' / request_id
        require(not backup.exists() and not backup.is_symlink(), 'BACKUP_EXISTS')
        backup.mkdir(parents=True, mode=0o700)
        for path, raw in before.items():
            atomic_write(backup / Path(path).name, raw, 0o600)
        atomic_write(backup / 'gate_before.json',
                     json.dumps(gate, sort_keys=True, separators=(',', ':')).encode(), 0o600)
        receipt['backup_path'] = str(backup)
        require(identity(old_identity['pid']) == {
            'pid':old_identity['pid'], 'start_ticks':old_identity['start_ticks'],
            'pgrp':old_identity['pgrp'], 'ppid':identity(old_identity['pid'])['ppid']},
            'DIRECTOR_CAS')
        # Re-capture immediately before the one allowed signal.
        gate = collect_gate(request_id, source_sha, True)
        require((gate['pid'], gate['start_ticks'], gate['pgrp']) ==
                (old_identity['pid'], old_identity['start_ticks'], old_identity['pgrp']),
                'SERVICE_CHANGED_BEFORE_TERM')
        os.kill(old_identity['pid'], signal.SIGTERM)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            current = identity(old_identity['pid'])
            status = supervisor('status')
            if (not current or current['start_ticks'] != old_identity['start_ticks']) and status['state'] == 'STOPPED':
                stopped = True
                break
            time.sleep(.25)
        require(stopped, 'GRACEFUL_TERM_TIMEOUT')
        require(not descendants(old_identity['pid']), 'OLD_CHILDREN_REMAIN')
        require(stop_flags_clear() and queue_is_idle() == gate['queue_state_sha256'],
                'QUEUE_OR_STOP_CHANGED')
        for path, raw in changes.items():
            current = read_regular(path) if Path(path).exists() else None
            require(current == before.get(path), 'FILE_CAS')
            applied.append(path)
            atomic_write(path, raw, 0o644 if path.endswith('.py') else 0o600)
            require(read_regular(path) == raw, 'WRITE_READBACK')
        supervisor('start')
        deadline = time.monotonic() + 25
        started = None
        while time.monotonic() < deadline:
            status = supervisor('status')
            if status['state'] == 'RUNNING' and status.get('pid'):
                started = identity(status['pid'])
                if started and started['pid'] != old_identity['pid']:
                    break
            time.sleep(.5)
        require(started and started['pid'] != old_identity['pid'], 'NEW_SERVICE_START')
        config_doc()
        status_doc = json.loads(read_regular(STATUS, 2 * 1024 * 1024))
        native = status_doc.get('native_subexecutors') or {}
        require(native.get('director', {}).get('pid') == started['pid']
                and native.get('director', {}).get('start_ticks') == started['start_ticks']
                and len(native.get('workers', [])) == 3
                and all(row.get('current_task') is None for row in native['workers']),
                'POSTSTART_READBACK')
        receipt.update(state='INSTALLED_ACTIVE', new_director=started,
                       post_pins={name:digest(raw) for name, raw in assets.items()},
                       files_changed=len(applied))
    except BaseException as exc:
        receipt['state'] = str(exc) if isinstance(exc, Hold) else 'HOLD_PR444_' + type(exc).__name__
        if applied:
            try:
                status = supervisor('status')
                current = identity(status.get('pid'))
                if status['state'] == 'RUNNING':
                    require(current and current['pid'] != old_identity['pid'], 'ROLLBACK_FOREIGN_PROCESS')
                    os.kill(current['pid'], signal.SIGTERM)
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline:
                        check = identity(current['pid'])
                        if not check or check['start_ticks'] != current['start_ticks']:
                            break
                        time.sleep(.25)
                    else:
                        raise Hold('HOLD_PR444_ROLLBACK_TERM_TIMEOUT')
                for path in reversed(applied):
                    current_raw = read_regular(path)
                    require(current_raw == changes[path], 'ROLLBACK_OWNERSHIP_CHANGED')
                    atomic_write(path, before[path], 0o644 if path.endswith('.py') else 0o600)
                    require(read_regular(path) == before[path], 'ROLLBACK_READBACK')
                if stopped:
                    supervisor('start')
                    receipt['rollback'] = 'PREIMAGE_RESTORED_AND_SERVICE_START_REQUESTED'
            except Exception as rollback_error:
                receipt['rollback'] = 'HOLD_' + type(rollback_error).__name__
        raise
    finally:
        receipt['finished_at'] = time.time()
        try:
            write_receipt(receipt)
        finally:
            os.close(lock_fd)


if __name__ == '__main__':
    run()
