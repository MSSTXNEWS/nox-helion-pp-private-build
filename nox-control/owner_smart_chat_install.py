#!/usr/bin/env python3
"""Apply three reviewed transforms to exact native chat preimages.

Private source bytes and backups stay on the original host. The transaction
restarts only the exact existing proxy after a bounded model-idle observation.
It never kills a model, changes a training/STOP flag or claims chat acceptance.
"""
from __future__ import annotations

import ast
import base64
from contextlib import contextmanager
import ctypes
import errno
import fcntl
import hashlib
from http.client import HTTPConnection, HTTPException
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

# Freeze this to the reviewed, public metadata-only contract before deployment.
CONTRACT_SHA256 = '30f49ab7e9f2e18c176af4515979b5834203fcd0e728e75394dd5db1e6ae978f'
CONTRACT_NAME = 'owner_smart_chat_contract.json'
ROOT = Path('/root/nox')
STATE = ROOT / 'state'
SCRIPTS = ROOT / 'scripts'
SITE = ROOT / 'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site'
AREA = STATE / 'owner_smart_chat_backups'
TARGETS = {
    'stream': SCRIPTS / 'owner_chat_stream.py',
    'bridge': SCRIPTS / 'nox_v29_chat_bridge.py',
}
PREIMAGES = {
    'stream': '38f4dc2995dd2c31f1f4d6a816d485721267d7add1c789cc4693aca54233fe09',
    'bridge': '9d7475428ad8c553c756ca50280ac2363e7c03854abab285de560ae066d4586a',
}
PROTECTED = {
    'chat_proxy.py': 'cc1437ce8c3bfbbc4259ffdbe299bf3b8721d4b1bb09c88565ccb6cb9fdb95eb',
    'agent_loop.py': '0ecec93bcf3239b7decc768862d27fbdc60fe2b613103f201406761bb4850aaa',
    'nox_tools.py': '2c17b7684275b532d4cc710322588ce178c9b23866630b11c778d1863bc448aa',
    'owner_chat_evidence.py': 'ea66e05f30472b066444058ac18d0c7af74def410bde760396d1e2431161e8b2',
}
SERVICES = ('nox-proxy', 'nox-ds41-8098', 'nox-web29-18775')
PRESERVED_UI_SHA256 = '55e4445443cd0d4cfa4d2a8775dcd8c7689890daad492b58e01c298691ac7e20'
DISPATCHER = 'nox-dispatcher-t855u'
DISPATCHER_IDENTITY = {'pid': 106058, 'pgrp': 106058, 'start_ticks': 181620214}
FLAGS = tuple(ROOT / name for name in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP',
    'state/STOP', 'state/STOP.flag', 'state/OWNER_MAINTENANCE.flag')) + (Path('/workspace/NOX_STOP'),)
PRESERVE_FLAGS = (STATE / 'TRAIN_HOLD.flag', STATE / 'TRAIN_PAUSE_REQUEST.flag')
MAX_SOURCE = 1024 * 1024
SCHEMA = 'NOX_OWNER_SMART_CHAT_INSTALL_V1'
SAFE_ENV = {'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1'}


class Hold(RuntimeError):
    pass


class Deadline(BaseException):
    pass


def require(ok, code):
    if not ok:
        raise Hold('HOLD_SMART_CHAT_' + code)


def safe(exc):
    value = str(exc)
    return value if re.fullmatch(r'(?:HOLD|WAIT)_[A-Z0-9_]{1,120}', value) else type(exc).__name__


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def identity(info):
    # renameat2 exchanges inode names and changes ctime; the remaining identity
    # plus complete bytes is required on both sides before every exchange.
    return tuple(getattr(info, 'st_' + key) for key in
                 ('dev', 'ino', 'uid', 'gid', 'mode', 'nlink', 'size', 'mtime_ns'))


def parent(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'ABSOLUTE_PATH')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd); fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def read(path, maximum=MAX_SOURCE):
    path = Path(path); directory = parent(path); fd = None
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid() and before.st_nlink == 1
                and not before.st_mode & 0o022 and 0 <= before.st_size <= maximum, 'FILE_SCOPE')
        pieces = []; size = 0
        while size <= maximum:
            raw = os.read(fd, min(65536, maximum + 1 - size))
            if not raw:
                break
            pieces.append(raw); size += len(raw)
        after = os.fstat(fd); named = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        require(size == before.st_size and identity(before) == identity(after) == identity(named)
                and before.st_ctime_ns == after.st_ctime_ns == named.st_ctime_ns, 'FILE_CHANGED')
        return b''.join(pieces), identity(before)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_directory(path):
    path = Path(path); directory = parent(path)
    try:
        try:
            os.mkdir(path.name, 0o700, dir_fd=directory); os.fsync(directory)
        except FileExistsError:
            pass
        info = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o700, 'PRIVATE_DIRECTORY')
    finally:
        os.close(directory)


def create(path, raw, mode=0o600):
    path = Path(path); directory = parent(path); fd = None
    try:
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     mode, dir_fd=directory)
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb') as stream:
            fd = None; stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.fsync(directory)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)
    current, meta = read(path, max(MAX_SOURCE, len(raw)))
    require(current == raw, 'PRIVATE_WRITE_READBACK')
    return meta


def exchange(first, second):
    one, two = parent(first), parent(second)
    try:
        require(os.fstat(one).st_dev == os.fstat(two).st_dev, 'EXCHANGE_FILESYSTEM')
        function = getattr(ctypes.CDLL(None, use_errno=True), 'renameat2', None)
        require(function is not None, 'EXCHANGE_UNAVAILABLE')
        function.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        function.restype = ctypes.c_int
        if function(one, os.fsencode(Path(first).name), two, os.fsencode(Path(second).name), 2):
            raise OSError(ctypes.get_errno(), 'atomic exchange failed')
        os.fsync(one); os.fsync(two)
    finally:
        os.close(two); os.close(one)


@contextmanager
def maintenance_lock(expected, wait_seconds=45):
    require(type(wait_seconds) is int and 0 <= wait_seconds <= 45, 'MAINTENANCE_WAIT_BOUND')
    path = STATE / 'owner_maintenance.lock'; directory = parent(path)
    fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
    os.close(directory)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and info.st_nlink == 1 and not info.st_mode & 0o022, 'MAINTENANCE_LOCK_SCOPE')
        gate(); assert_services(expected)
        started = time.monotonic(); deadline = started + wait_seconds; attempts = 0
        guarded = dict(expected, **{DISPATCHER: DISPATCHER_IDENTITY})
        while True:
            gate()
            named = os.stat(path, follow_symlinks=False)
            require((named.st_dev, named.st_ino, named.st_mode, named.st_uid, named.st_nlink) ==
                    (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink),
                    'MAINTENANCE_LOCK_CHANGED')
            for name, previous in guarded.items():
                current = process(previous['pid'])
                require({key: current[key] for key in ('pid', 'pgrp', 'start_ticks')} == previous,
                        'LEASE_WAIT_PROCESS_CHANGED_' + name.replace('-', '_').upper())
            attempts += 1
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Hold('WAIT_SMART_CHAT_EXISTING_MAINTENANCE_LEASE') from None
                time.sleep(min(0.5, remaining))
        acquired_at = time.monotonic()
        gate(); assert_services(expected)
        yield {'attempts': attempts, 'waited_ms': round((acquired_at - started) * 1000),
               'maximum_acquisition_wait_seconds': wait_seconds, 'inode': info.st_ino,
               'dispatcher_identity': dict(DISPATCHER_IDENTITY), 'existing_lock_reused': True,
               'lock_removed_or_holder_signaled': False}
    finally:
        os.close(fd)


def gate():
    require(not any(os.path.lexists(path) for path in FLAGS), 'OWNER_STOP_OR_MAINTENANCE')


def preserved():
    files = {}
    for name, expected in PROTECTED.items():
        raw, _ = read(SCRIPTS / name)
        require(sha(raw) == expected, 'PROTECTED_SOURCE_' + name.replace('.', '_').upper())
        files[name] = expected
    flags = {}
    for path in PRESERVE_FLAGS:
        flags[str(path)] = sha(read(path, 16384)[0]) if os.path.lexists(path) else None
    current_ui, _ = read(SITE / 'pc/v24/nox-v24-chat.js')
    require(sha(current_ui) == PRESERVED_UI_SHA256, 'FOREIGN_UI_CHANGED')
    files['nox-v24-chat.js'] = PRESERVED_UI_SHA256
    return {'source_pins': files, 'training_flags': flags}


def proc_raw(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'PROC_TYPE')
        raw = os.read(fd, limit + 1); require(len(raw) <= limit, 'PROC_SIZE')
        return raw
    finally:
        os.close(fd)


def process(pid):
    require(type(pid) is int and 0 < pid < 2**31, 'PID')
    base = '/proc/' + str(pid)
    def stat_row():
        raw = proc_raw(base + '/stat', 8192); parts = raw[raw.rindex(b')') + 2:].split()
        require(int(raw.split(b' ', 1)[0]) == pid and parts[0] not in (b'Z', b'X'), 'PROCESS_LIVE')
        return {'pid': pid, 'pgrp': int(parts[2]), 'start_ticks': int(parts[19])}
    before = stat_row(); argv = proc_raw(base + '/cmdline', 65536).rstrip(b'\0').split(b'\0')
    executable = os.readlink(base + '/exe')
    require(re.fullmatch(r'/[A-Za-z0-9/_.+\-]{1,260}', executable) is not None, 'PROCESS_EXE')
    require(before == stat_row(), 'PROCESS_CHANGED')
    return dict(before, executable=executable, argv=argv)


def command(args, timeout=8):
    result = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, timeout=timeout, env=SAFE_ENV)
    require(len(result.stdout) <= 65536, 'COMMAND_OUTPUT_BOUND')
    return result.returncode, result.stdout


def service(name):
    require(name in (*SERVICES, DISPATCHER), 'SERVICE_SCOPE')
    _, raw = command(['supervisorctl', 'status', name], timeout=5)
    rows = [line.split() for line in raw.decode('utf-8', 'replace').splitlines() if line.startswith(name + ' ')]
    require(len(rows) == 1 and len(rows[0]) >= 2, 'SERVICE_STATUS')
    status = rows[0][1]
    require(status in ('RUNNING', 'STOPPED', 'EXITED', 'FATAL', 'STARTING', 'STOPPING', 'BACKOFF'), 'SERVICE_STATE')
    result = {'service': name, 'state': status}
    if status == 'RUNNING':
        match = re.search(rb'\bpid ([0-9]{1,10}),', raw)
        require(match is not None, 'SERVICE_PID')
        proc = process(int(match[1])); result['identity'] = {k: proc[k] for k in ('pid', 'pgrp', 'start_ticks')}
        result['executable'] = proc['executable']
        if name == 'nox-proxy':
            require(os.fsencode(str(SCRIPTS / 'chat_proxy.py')) in proc['argv'], 'PROXY_ARGV')
    return result


def assert_services(expected, include_proxy=True):
    guarded = dict(expected, **{DISPATCHER: DISPATCHER_IDENTITY})
    for name in (*SERVICES, DISPATCHER):
        if name == 'nox-proxy' and not include_proxy:
            continue
        row = service(name)
        require(row.get('state') == 'RUNNING' and row.get('identity') == guarded[name],
                'SERVICE_PREDECESSOR_' + name.replace('-', '_').upper())


def proxy_group_alone(expected):
    _, raw = command(['ps', '-eo', 'pid=,pgid=,stat='], timeout=5)
    members = []
    for line in raw.splitlines():
        pieces = line.split()
        if len(pieces) == 3 and pieces[0].isdigit() and pieces[1].isdigit() and int(pieces[1]) == expected['pgrp']:
            if not pieces[2].startswith((b'Z', b'X')):
                members.append(int(pieces[0]))
    require(members == [expected['pid']], 'PROXY_GROUP_NOT_IDLE_AND_EXCLUSIVE')


def http(port, path, json_body=False):
    client = HTTPConnection('127.0.0.1', port, timeout=3)
    try:
        client.request('GET', path, headers={'Connection': 'close', 'Accept': 'application/json'})
        response = client.getresponse(); require(response.status == 200, 'HTTP_' + str(port))
        if not json_body:
            return response.status
        raw = response.read(262145); require(len(raw) <= 262144, 'HTTP_RESPONSE_BOUND')
        return json.loads(raw)
    finally:
        client.close()


def slots_idle():
    rows = http(8098, '/slots', True)
    require(isinstance(rows, list) and len(rows) == 2, 'SLOT_SCHEMA')
    for row in rows:
        require(isinstance(row, dict), 'SLOT_SCHEMA')
        values = [row[k] for k in ('is_processing', 'processing') if k in row]
        require(values and all(type(v) is bool for v in values), 'SLOT_ACTIVITY_UNKNOWN')
        if any(values):
            return False
    return True


def bounded_idle(expected, preserved_before, seconds):
    deadline = time.monotonic() + seconds; stable = 0; samples = 0
    while time.monotonic() < deadline:
        gate(); assert_services(expected)
        require(preserved() == preserved_before, 'PRESERVED_STATE_CHANGED')
        samples += 1; stable = stable + 1 if slots_idle() else 0
        if stable >= 3:
            proxy_group_alone(expected['nox-proxy'])
            return {'model_port': 8098, 'consecutive_idle_samples': stable, 'samples': samples,
                    'proxy_group_exclusive': True, 'application_lease_introspection': 'NOT_AVAILABLE',
                    'no_model_or_training_process_signaled': True}
        time.sleep(1)
    raise Hold('WAIT_SMART_CHAT_MODEL_SLOTS_BUSY_NO_RESTART')


def stop_proxy(expected):
    row = service('nox-proxy')
    require(row.get('state') == 'RUNNING' and row.get('identity') == expected, 'PROXY_PRESTOP_IDENTITY')
    proxy_group_alone(expected); require(slots_idle(), 'CHAT_BECAME_BUSY')
    code, _ = command(['supervisorctl', 'stop', 'nox-proxy'], timeout=35)
    require(code == 0 and service('nox-proxy')['state'] in ('STOPPED', 'EXITED'), 'PROXY_STOP')
    try:
        remaining = process(expected['pid'])
    except (OSError, Hold):
        remaining = None
    require(remaining is None or remaining['start_ticks'] != expected['start_ticks'], 'OLD_PROXY_STILL_ALIVE')


def start_proxy(expected_executable, on_started=None):
    gate(); require(service('nox-proxy')['state'] in ('STOPPED', 'EXITED', 'FATAL'), 'PROXY_START_STATE')
    code, _ = command(['supervisorctl', 'start', 'nox-proxy'], timeout=35)
    require(code == 0, 'PROXY_START_COMMAND')
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        gate(); row = service('nox-proxy')
        if row.get('state') == 'RUNNING':
            require(row.get('executable') == expected_executable, 'PROXY_INTERPRETER_CHANGED')
            if on_started is not None:
                on_started(row['identity'])
            try:
                http(8080, '/health')
                return row['identity']
            except (OSError, Hold, HTTPException):
                pass
        time.sleep(.5)
    raise Hold('HOLD_SMART_CHAT_PROXY_START_HEALTH')


def bundle(name, expected, maximum=262144):
    require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', name), 'BUNDLE_NAME')
    require(isinstance(expected, str) and re.fullmatch(r'[a-f0-9]{64}', expected), 'BUNDLE_PIN_UNFROZEN')
    value = BUNDLE.get(name)
    require(isinstance(value, str) and 0 < len(value) <= maximum * 2, 'BUNDLE_MISSING')
    raw = base64.b64decode(value, validate=True)
    require(0 < len(raw) <= maximum and sha(raw) == expected, 'BUNDLE_SOURCE_SHA')
    return raw


def contract():
    value = json.loads(bundle(CONTRACT_NAME, CONTRACT_SHA256, 32768))
    require(isinstance(value, dict) and value.get('schema') == 'NOX_SMART_CHAT_CONTRACT_V1', 'CONTRACT_SCHEMA')
    require(value.get('preimages') == PREIMAGES and set(value.get('transforms', {})) == set(TARGETS), 'CONTRACT_TARGETS')
    expected = value.get('services')
    require(isinstance(expected, dict) and set(expected) == set(SERVICES), 'CONTRACT_SERVICES')
    for row in expected.values():
        require(isinstance(row, dict) and set(row) == {'pid', 'pgrp', 'start_ticks'}
                and all(type(v) is int and v > 0 for v in row.values()), 'CONTRACT_PROCESS_IDENTITY')
    require(type(value.get('idle_wait_seconds')) is int and 3 <= value['idle_wait_seconds'] <= 60, 'CONTRACT_IDLE_BOUND')
    return value


def _cgroup_read(name, maximum=16384):
    path = '/sys/fs/cgroup/' + name
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        contents = os.read(descriptor, maximum + 1)
        require(len(contents) <= maximum, 'CGROUP_READ_BOUND')
        return contents.decode('ascii')
    finally:
        os.close(descriptor)


def _cgroup_numbers(name, keys):
    result = {}
    for line in _cgroup_read(name).splitlines():
        pair = line.split()
        if len(pair) == 2 and pair[0] in keys and pair[1].isdigit():
            result[pair[0]] = int(pair[1])
    require(all(key in result for key in keys), 'CGROUP_COUNTER_MISSING')
    return result


def _cgroup_snapshot():
    maximum, current = _cgroup_read('memory.max').strip(), _cgroup_read('memory.current').strip()
    require(maximum.isdigit() and current.isdigit(), 'CGROUP_MEMORY_UNMEASURED')
    stat = _cgroup_numbers('memory.stat', ('file', 'shmem', 'inactive_file', 'file_dirty', 'file_writeback'))
    events = _cgroup_numbers('memory.events', ('max', 'oom', 'oom_kill'))
    raw = _cgroup_read('memory.pressure', 4096)
    pressure = {}
    for line in raw.splitlines():
        fields = line.split()
        if fields and fields[0] in ('some', 'full'):
            for item in fields[1:]:
                if item.startswith('avg10='):
                    pressure[fields[0]] = float(item.split('=', 1)[1])
    require(set(pressure) == {'some', 'full'}, 'CGROUP_PSI_UNAVAILABLE')
    potential = max(0, min(stat['inactive_file'],
        stat['file'] - stat['shmem'] - stat['file_dirty'] - stat['file_writeback']))
    return {'max': int(maximum), 'current': int(current), 'raw_margin': int(maximum) - int(current),
        'potential_inactive_file': potential, 'oom': events['oom'], 'oom_kill': events['oom_kill'],
        'max_events': events['max'], 'psi_some_avg10': pressure['some'], 'psi_full_avg10': pressure['full']}


def reload_resource_admission(expected, protected_before, record):
    """Inspect actual working set; rely on kernel page eviction, not read-only memory.reclaim."""
    minimum_raw = 16 * 1024 * 1024
    minimum_inactive = 16 * 1024**3
    samples = []
    result = {'mode': 'KERNEL_AUTOMATIC_RECLAIM_ON_ALLOCATION',
        'cgroup_memory_reclaim_attempted': False, 'memory_max_changed': False,
        'model_or_training_restarted': False, 'service_changes': False,
        'requires_raw_margin_after_proxy_stop': 64 * 1024 * 1024,
        'samples': samples}
    record['resource_admission'] = result
    for index in range(3):
        gate(); assert_services(expected)
        require(preserved() == protected_before, 'RESOURCE_PRESERVED_CHANGED')
        sample = _cgroup_snapshot(); samples.append(sample)
        require(sample['raw_margin'] >= minimum_raw, 'CGROUP_RAW_MARGIN_BELOW_16MIB')
        require(sample['max'] > 1024**3 and
                sample['potential_inactive_file'] >= minimum_inactive,
                'CGROUP_INACTIVE_CACHE_INSUFFICIENT')
        require(sample['oom'] == 0 and sample['oom_kill'] == 0 and
                sample['psi_some_avg10'] < 1.0 and sample['psi_full_avg10'] < 0.2,
                'CGROUP_PRESSURE_OR_OOM')
        if index:
            require(sample['max'] == samples[0]['max'] and
                sample['max_events'] - samples[0]['max_events'] <= 5,
                'CGROUP_UNSTABLE_MEMORY_EVENTS')
        require(slots_idle(), 'RESOURCE_MODEL_ACTIVE')
        time.sleep(.5)
    http(8080, '/health'); http(8098, '/health')
    result.update(status='CACHE_BACKED_ADMITTED_FOR_SINGLE_PROXY_REPLACEMENT',
        raw_margin_first=samples[0]['raw_margin'],
        raw_margin_last=samples[-1]['raw_margin'],
        no_double_proxy=True)
    return result


def post_stop_resource_admission(before, record):
    """Old proxy is already stopped: measure freed RAM before swapping any file."""
    gate()
    current = _cgroup_snapshot()
    record['post_stop_resource'] = current
    require(current['max'] == before['max'], 'CGROUP_LIMIT_CHANGED')
    require(current['oom'] == before['oom'] and current['oom_kill'] == before['oom_kill'],
            'CGROUP_POSTSTOP_OOM_EVENT')
    require(current['psi_some_avg10'] < 1.0 and current['psi_full_avg10'] < 0.2,
            'CGROUP_POSTSTOP_PRESSURE')
    require(current['raw_margin'] >= 64 * 1024 * 1024,
            'CGROUP_PROXY_RELEASE_INSUFFICIENT')
    require(current['potential_inactive_file'] >= 16 * 1024**3,
            'CGROUP_POSTSTOP_INACTIVE_CACHE_INSUFFICIENT')
    http(8098, '/health')
    require(slots_idle(), 'RESOURCE_MODEL_BECAME_ACTIVE')
    return current



def candidate(label, raw, spec, executable):
    transform_source = bundle(spec['module'], spec['sha256'])
    module = types.ModuleType('_reviewed_smart_chat_' + label)
    module.__file__ = '<reviewed-' + label + '-transform>'
    exec(compile(transform_source, module.__file__, 'exec'), module.__dict__)
    require(callable(getattr(module, 'transform', None)), 'TRANSFORM_INTERFACE')
    result = module.transform(raw)
    require(isinstance(result, bytes) and 0 < len(result) <= MAX_SOURCE and result != raw, 'TRANSFORM_RESULT')
    expected_postimage = spec.get('postimage_sha256')
    require(expected_postimage is None or sha(result) == expected_postimage, 'POSTIMAGE_PIN')
    if label != 'ui':
        ast.parse(result)
        p = subprocess.run([executable, '-I', '-S', '-B', '-c',
            "import sys; compile(sys.stdin.buffer.read(),'<reviewed-native-chat>','exec')"],
            input=result, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8, env=SAFE_ENV)
        require(p.returncode == 0 and not p.stdout, 'TARGET_INTERPRETER_COMPILE')
    else:
        require(isinstance(expected_postimage, str) and spec.get('node_syntax_verified') is True, 'UI_EXACT_SYNTAX_RECEIPT')
    return result


def pair(row):
    current, current_id = read(row['target']); saved, saved_id = read(row['staged'])
    if (sha(current), current_id, sha(saved), saved_id) == (row['old_sha'], row['old_id'], row['new_sha'], row['new_id']):
        return 'ORIGINAL'
    require((sha(current), current_id, sha(saved), saved_id) ==
            (row['new_sha'], row['new_id'], row['old_sha'], row['old_id']), 'FOREIGN_SOURCE_PAIR')
    return 'INSTALLED'


def main():
    request, source_sha = (os.environ.get(k, '') for k in ('NOX_OWNER_REQUEST_ID', 'NOX_OWNER_SOURCE_SHA'))
    require(re.fullmatch(r'[0-9]{1,24}', request) and re.fullmatch(r'[a-f0-9]{40}', source_sha), 'OWNER_CONTEXT')
    spec = contract(); expected = spec['services']; rows = []; journal = None; previous = None; new_proxy = None
    before = None; original_executable = None
    record = {'schema': SCHEMA, 'request': request, 'source_sha': source_sha, 'contract_sha256': CONTRACT_SHA256,
        'state': 'PREFLIGHT', 'source_changed': [], 'proxy_stop_attempted': False, 'proxy_start_attempted': False,
        'proxy_restarted': False, 'model_or_training_restarted': False, 'stop_flags_changed': False,
        'private_source_exported': False, 'chat_behavior_acceptance_verified': False,
        'chat_behavior_acceptance_pending': True, 'started_at': time.time()}
    def save():
        nonlocal previous
        if journal is None:
            return
        raw = encoded(record); path = journal / 'result.json'
        if previous is None:
            create(path, raw)
        else:
            old, meta = read(path); require(old == previous, 'RECEIPT_PREIMAGE')
            stage = journal / 'result.next'; create(stage, raw)
            require(read(path) == (old, meta), 'RECEIPT_CHANGED')
            os.replace(stage, path); sync_dir(journal)
            require(read(path)[0] == raw, 'RECEIPT_READBACK')
        previous = raw
    def expired(*_):
        raise Deadline()
    def remember_proxy(value):
        nonlocal new_proxy
        if new_proxy is None:
            new_proxy = value
            record['proxy_after'] = value
            save()
        else:
            require(new_proxy == value, 'PROXY_REPLACED_DURING_HEALTH')
    old_handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGALRM, signal.SIGTERM)}
    success = False
    for sig in old_handlers:
        signal.signal(sig, expired)
    signal.setitimer(signal.ITIMER_REAL, 210)
    try:
        with maintenance_lock(expected) as lease:
            try:
                record['maintenance_lease'] = lease
                gate(); assert_services(expected); before = preserved()
                original_executable = service('nox-proxy')['executable']
                record['transform_preflight'] = []
                for label, target in TARGETS.items():
                    try:
                        raw, old_id = read(target); require(sha(raw) == PREIMAGES[label], 'PREIMAGE_' + label.upper())
                        new = candidate(label, raw, spec['transforms'][label], original_executable)
                        rows.append({'label': label, 'target': target, 'old': raw, 'old_id': old_id,
                            'old_sha': sha(raw), 'new': new, 'new_sha': sha(new)})
                        record['transform_preflight'].append({'label': label, 'state': 'COMPUTED_AND_SYNTAX_VERIFIED',
                            'old_sha256': sha(raw), 'new_sha256': sha(new), 'new_bytes': len(new)})
                    except Exception as transform_error:
                        record['transform_preflight'].append({'label': label, 'state': 'HELD', 'reason': safe(transform_error)})
                require(len(rows) == len(TARGETS), 'TRANSFORM_PREFLIGHT')
                record['reload_resource_admission'] = reload_resource_admission(expected, before, record)
                private_directory(AREA); journal = AREA / request
                require(not os.path.lexists(journal), 'REQUEST_REUSED'); private_directory(journal)
                for row in rows:
                    create(journal / (row['label'] + '.original'), row['old'])
                    row['staged'] = journal / (row['label'] + '.exchange')
                    row['new_id'] = create(row['staged'], row['new'], stat.S_IMODE(row['old_id'][4]))
                record['prepared_files'] = [{'label': r['label'], 'target': str(r['target']),
                    'old_sha256': r['old_sha'], 'new_sha256': r['new_sha'],
                    'old_identity': r['old_id'], 'new_identity': r['new_id'],
                    'new_bytes': len(r['new'])} for r in rows]
                record.update(state='PRIVATE_TRANSFORMS_STAGED', preserved_before=before,
                    service_predecessors=expected, proxy_executable=original_executable)
                save()
                record['idle_observation'] = bounded_idle(expected, before, spec['idle_wait_seconds'])
                require(all(pair(row) == 'ORIGINAL' for row in rows), 'PRESTOP_FILE_CHANGED')
                gate(); record['proxy_stop_attempted'] = True; save()
                stop_proxy(expected['nox-proxy'])
                record['post_stop_resource_admission'] = post_stop_resource_admission(record['resource_admission']['samples'][0], record)
                gate(); assert_services(expected, include_proxy=False)
                require(preserved() == before, 'POSTSTOP_PRESERVED_CHANGED')
                for row in rows:
                    gate(); require(pair(row) == 'ORIGINAL', 'SOURCE_PREIMAGE')
                    exchange(row['target'], row['staged'])
                    require(pair(row) == 'INSTALLED', 'SOURCE_POSTIMAGE')
                    record['source_changed'].append(row['label']); save()
                gate(); assert_services(expected, include_proxy=False)
                record['proxy_start_attempted'] = True; save()
                new_proxy = start_proxy(original_executable, remember_proxy)
                record.update(proxy_restarted=True, proxy_after=new_proxy); save()
                require(all(pair(row) == 'INSTALLED' for row in rows), 'FINAL_POSTIMAGES')
                require(preserved() == before, 'FINAL_PRESERVED_CHANGED')
                assert_services(expected, include_proxy=False)
                for port in (8080, 8082, 8098):
                    http(port, '/health')
                record['resource_after_restart'] = _cgroup_snapshot()
                require(record['resource_after_restart']['oom_kill'] == record['resource_admission']['samples'][0]['oom_kill'], 'CGROUP_POSTRESTART_OOM_KILL')
                record.update(state='TWO_SOURCE_TRANSFORMS_AND_PROXY_RELOAD_VERIFIED',
                    source_install_verified=True, preserved_state_verified=True, finished_at=time.time())
                save(); success = True
            except BaseException as exc:
                signal.setitimer(signal.ITIMER_REAL, 0)
                record.update(state='HOLD_SMART_CHAT_INSTALL', reason=safe(exc), source_install_verified=False)
                if record['proxy_stop_attempted']:
                    try:
                        signal.setitimer(signal.ITIMER_REAL, 95)
                        current = service('nox-proxy')
                        if current['state'] == 'RUNNING':
                            own = new_proxy or expected['nox-proxy']
                            require(current.get('identity') == own, 'ROLLBACK_FOREIGN_PROXY')
                            if any(pair(row) == 'INSTALLED' for row in rows):
                                stop_proxy(own)
                        require(service('nox-proxy')['state'] in ('STOPPED', 'EXITED', 'FATAL', 'RUNNING'), 'ROLLBACK_SERVICE_STATE')
                        for row in reversed(rows):
                            if pair(row) == 'INSTALLED':
                                require(service('nox-proxy')['state'] != 'RUNNING', 'ROLLBACK_PROXY_NOT_STOPPED')
                                exchange(row['target'], row['staged'])
                            require(pair(row) == 'ORIGINAL', 'ROLLBACK_SOURCE')
                        if service('nox-proxy')['state'] != 'RUNNING':
                            if any(os.path.lexists(path) for path in FLAGS):
                                record['rollback_restart_held_by_owner_stop'] = True
                            else:
                                record['rollback_proxy'] = start_proxy(original_executable)
                        record['rollback_sources_verified'] = True
                        record['rollback_preserved_verified'] = preserved() == before
                    except BaseException as rollback_error:
                        record.update(rollback_sources_verified=False, rollback_reason=safe(rollback_error))
                record['finished_at'] = time.time()
                try:
                    save()
                except BaseException as receipt_error:
                    record['receipt_error'] = safe(receipt_error)
    except BaseException as exc:
        record.update(state='HOLD_SMART_CHAT_INSTALL', reason=safe(exc), finished_at=time.time())
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
    if previous is not None:
        record['receipt_sha256'] = sha(previous)
    print('NOX_MAINT_REPAIR=' + encoded({'kind': 'smart_chat_install', 'data': record}).decode().strip(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('NOX_MAINT_REPAIR=' + encoded({'kind': 'smart_chat_install', 'data': {
            'schema': SCHEMA, 'state': 'HOLD_PREFLIGHT', 'reason': safe(exc), 'source_changed': []}}).decode().strip(), flush=True)
        raise SystemExit(2)
