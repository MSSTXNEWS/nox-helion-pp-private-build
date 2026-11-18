#!/usr/bin/env python3
"""Exact two-file chat repair: visible failures and the existing SLIM_RULES.

The source/identity specification is filled only from a current native probe.
No project claim, model worker, model process, credential or scheduler changes.
The existing proxy is reloaded only after the exact serving idle gate passes.
"""
from __future__ import annotations

import ast
import base64
from contextlib import ExitStack, contextmanager
import ctypes
import fcntl
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import shlex
import stat
import time
import types


ROOT = Path('/root/nox')
SCRIPTS = ROOT / 'scripts'
SITE = ROOT / 'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site'
TARGETS = {'slim': SCRIPTS / 'slim_chat_t885u.py', 'ui': SITE / 'pc/v24/nox-v24-chat.js'}
BACKUP = ROOT / 'backup/owner_chat_decomposition'
CONFIG = ROOT / 'config/owner_native_subagents.json'
PUBLIC_ASSET_PATH = '/nox-web-v29/pc/v24/nox-v24-chat.js'
HELPER_SHA = 'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0'
SPEC = {}
try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}


class Hold(RuntimeError):
    pass


def require(value, reason):
    if not value:
        raise Hold('HOLD_CHAT_DECOMPOSITION_' + reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def safe(error):
    text = str(error)
    return text if re.fullmatch(r'(?:HOLD|WAIT)_[A-Z0-9_]{1,150}', text) else type(error).__name__


def identity(info):
    return tuple(getattr(info, key) for key in ('st_dev', 'st_ino', 'st_uid', 'st_gid',
                 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns'))


def parent_fd(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'ABSOLUTE_PATH')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def read(path, expected=None, maximum=1024*1024, public_state=False):
    directory = parent_fd(path)
    fd = None
    try:
        fd = os.open(Path(path).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                     dir_fd=directory)
        before = os.fstat(fd)
        permitted_group_state = public_state and before.st_gid == os.getegid()
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                and before.st_nlink == 1 and not before.st_mode & (0o002 if permitted_group_state else 0o022)
                and 0 <= before.st_size <= maximum, 'SOURCE_SCOPE')
        chunks, consumed = [], 0
        while True:
            chunk = os.read(fd, min(65536, before.st_size - consumed + 1))
            consumed += len(chunk)
            require(consumed <= before.st_size, 'SOURCE_GROWTH')
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
        current = os.stat(Path(path).name, dir_fd=directory, follow_symlinks=False)
        fresh_directory = parent_fd(path)
        try:
            named = os.stat(Path(path).name, dir_fd=fresh_directory, follow_symlinks=False)
        finally:
            os.close(fresh_directory)
        require(consumed == before.st_size and identity(before) == identity(after)
                == identity(current) == identity(named)
                and before.st_ctime_ns == after.st_ctime_ns == current.st_ctime_ns == named.st_ctime_ns,
                'SOURCE_CHANGED')
        raw = b''.join(chunks)
        require(expected is None or sha(raw) == expected, 'SOURCE_PIN')
        return raw, identity(before)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)


def private_directory(path):
    parent = parent_fd(path)
    try:
        try:
            os.mkdir(Path(path).name, mode=0o700, dir_fd=parent)
            os.fsync(parent)
        except FileExistsError:
            pass
        fd = os.open(Path(path).name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            info = os.fstat(fd)
            require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700,
                    'PRIVATE_DIRECTORY')
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def create(path, raw, mode=0o600):
    directory = parent_fd(path)
    fd = None
    try:
        fd = os.open(Path(path).name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     mode, dir_fd=directory)
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb', buffering=0) as target:
            fd = None
            offset = 0
            while offset < len(raw):
                wrote = target.write(raw[offset:])
                require(isinstance(wrote, int) and wrote > 0, 'WRITE_PROGRESS')
                offset += wrote
            os.fsync(target.fileno())
        os.fsync(directory)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)
    return read(path, sha(raw), len(raw))[1]


def replace_private(path, raw, previous):
    if previous is not None:
        read(path, sha(previous), len(previous))
    temporary = Path(path).with_name(Path(path).name + '.next')
    create(temporary, raw)
    directory = parent_fd(path)
    try:
        if previous is None:
            require(not os.path.lexists(path), 'RECEIPT_EXISTS')
        else:
            read(path, sha(previous), len(previous))
        os.replace(temporary.name, Path(path).name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        os.close(directory)


def exchange(first, second):
    one, two = parent_fd(first), None
    try:
        two = parent_fd(second)
        require(os.fstat(one).st_dev == os.fstat(two).st_dev, 'EXCHANGE_FILESYSTEM')
        libc = ctypes.CDLL(None, use_errno=True)
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(one, os.fsencode(Path(first).name), two, os.fsencode(Path(second).name), 2):
            raise OSError(ctypes.get_errno(), 'renameat2')
        os.fsync(one)
        os.fsync(two)
    finally:
        os.close(one)
        if two is not None:
            os.close(two)


def pair(row):
    target_raw, target_id = read(row['target'])
    staged_raw, staged_id = read(row['staged'])
    if (sha(target_raw), target_id, sha(staged_raw), staged_id) == (
            row['before_sha256'], row['before_identity'], row['after_sha256'], row['after_identity']):
        return 'ORIGINAL'
    if (sha(target_raw), target_id, sha(staged_raw), staged_id) == (
            row['after_sha256'], row['after_identity'], row['before_sha256'], row['before_identity']):
        return 'INSTALLED'
    raise Hold('HOLD_CHAT_DECOMPOSITION_EXCHANGE_IDENTITY')


@contextmanager
def lease(path, wait_seconds=8, create_new=False):
    parent = parent_fd(path)
    fd = None
    flags = os.O_RDWR if create_new else os.O_RDONLY
    flags |= os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    if create_new:
        flags |= os.O_CREAT
    try:
        fd = os.open(Path(path).name, flags, 0o600, dir_fd=parent)
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and info.st_nlink == 1 and not info.st_mode & 0o077, 'LEASE_SCOPE')
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                require(time.monotonic() < deadline, 'MAINTENANCE_BUSY')
                time.sleep(.05)
        named = os.stat(Path(path).name, dir_fd=parent, follow_symlinks=False)
        require((info.st_dev, info.st_ino) == (named.st_dev, named.st_ino), 'LEASE_CHANGED')
        yield
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def module(name, raw):
    result = types.ModuleType(name)
    result.__file__ = '<reviewed-chat-repair>/' + name + '.py'
    exec(compile(raw, result.__file__, 'exec'), result.__dict__)
    return result


def stop_clear():
    paths = [ROOT / name for name in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP',
             'state/STOP', 'state/STOP.flag', 'state/OWNER_MAINTENANCE.flag')]
    require(not any(os.path.lexists(path) for path in [*paths, Path('/workspace/NOX_STOP')]), 'OWNER_STOP')


def source_guards(spec):
    result = {name: sha(read(SCRIPTS / name, pin)[0]) for name, pin in spec['guarded_sources'].items()}
    result['owner_native_subagents.json'] = sha(read(CONFIG, maximum=2 * 1024 * 1024)[0])
    return result


def proc_identity(pid):
    require(type(pid) is int and 0 < pid < 2**31, 'PID_BOUND')
    try:
        with open('/proc/%d/stat' % pid, 'rb', buffering=0) as stream:
            raw = stream.read(8193)
        require(len(raw) <= 8192, 'PROC_STAT_BOUND')
        values = raw.rsplit(b') ', 1)[1].split()
        return {'pid': pid, 'starttime': values[19].decode('ascii'),
                'ppid': int(values[1]), 'pgrp': int(values[2]), 'state': values[0].decode('ascii')}
    except FileNotFoundError:
        return None


def same_pid(expected):
    current = proc_identity(expected['pid'])
    return bool(current and current['starttime'] == str(expected['starttime']))


def protected(helper, spec):
    result = {}
    for name, expected in spec['protected_processes'].items():
        observed = proc_identity(expected['pid'])
        require(observed and observed.get('state') not in ('Z', 'X')
                and str(observed.get('starttime')) == str(expected['start_ticks']), 'PROTECTED_PROCESS')
        result[name] = {key: observed[key] for key in ('pid', 'starttime', 'ppid', 'pgrp')}
    return result


def proxy_identity(helper):
    service = helper.service_state('nox-proxy')
    before = proc_identity(service['pid']) if service.get('pid') else None
    observed = helper.process(service.get('pid')) if service.get('pid') else None
    after = proc_identity(service['pid']) if service.get('pid') else None
    config = helper.program_config('nox-proxy')
    command = shlex.split(config.get('command', ''))
    require(service.get('state') == 'RUNNING' and before and after and observed
            and all(before[key] == after[key] == observed[key] for key in ('pid', 'starttime', 'ppid', 'pgrp'))
            and observed.get('service') == 'nox-proxy'
            and str(SCRIPTS / 'chat_proxy.py') in observed.get('argv', [])
            and observed.get('state') not in ('Z', 'X')
            and command in (['/opt/supervisor-scripts/nox-proxy.sh'],
                            ['/bin/bash', '/opt/supervisor-scripts/nox-proxy.sh']),
            'PROXY_IDENTITY')
    if config.get('stopasgroup') == 'true' or config.get('killasgroup') == 'true':
        require(all(row.get('service') == 'nox-proxy' for row in helper.process_table().values()
                    if row.get('pgrp') == observed['pgrp'] and row.get('state') not in ('Z', 'X')),
                'PROXY_FOREIGN_GROUP')
    return {key: observed[key] for key in ('pid', 'starttime', 'pgrp')}


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'JSON_DUPLICATE')
            result[key] = value
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                      parse_constant=lambda value: require(False, 'JSON_NONFINITE'))


def activity_path(spec):
    # Inspect only the pinned AST. Do not import common.py or execute its code.
    raw, _ = read(SCRIPTS / 'common.py', spec['guarded_sources']['common.py'])
    text = raw.decode('utf-8')
    tree = ast.parse(text)
    assignments = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            assignments.setdefault(name, []).append(node.value)
    def resolve(node, seen=()):
        require(len(seen) <= 6, 'COMMON_PATH_DEPTH')
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            require(node.id not in seen and len(assignments.get(node.id, [])) == 1,
                    'COMMON_PATH_NAME')
            return resolve(assignments[node.id][0], (*seen, node.id))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'Path':
            require(len(node.args) == 1 and not node.keywords, 'COMMON_PATH_CALL')
            return Path(resolve(node.args[0], seen))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return Path(resolve(node.left, seen)) / resolve(node.right, seen)
        raise Hold('HOLD_CHAT_DECOMPOSITION_COMMON_PATH_EXPRESSION')
    require(len(assignments.get('CHAT_STATE', [])) == 1, 'COMMON_CHAT_STATE')
    path = Path(resolve(assignments['CHAT_STATE'][0], ('CHAT_STATE',)))
    require(path == ROOT / 'status/chat_state.json', 'COMMON_CHAT_PATH')
    for name, expected in spec['idle_gate']['symbols'].items():
        source_name, symbol = name.split(':', 1)
        source, _ = read(SCRIPTS / source_name, spec['guarded_sources'][source_name])
        decoded = source.decode('utf-8')
        nodes = [node for node in ast.parse(decoded).body
                 if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == symbol]
        require(len(nodes) == 1, 'IDLE_SYMBOL')
        segment = ast.get_source_segment(decoded, nodes[0])
        require(segment is not None and sha((segment + '\n').encode()) == expected, 'IDLE_SYMBOL_PIN')
    return path


def proxy_idle(spec):
    # The existing counter is separate from the legacy chat_active mtime marker.
    # A zero snapshot is an observed pre-stop condition, not an atomic drain lock.
    path = activity_path(spec)
    snapshots = []
    for sample in range(2):
        raw, ident = read(path, maximum=8192, public_state=True)
        value = strict_json(raw)
        require(isinstance(value, dict) and type(value.get('inflight')) is int
                and 0 <= value['inflight'] <= 1000000, 'CHAT_COUNTER_SCHEMA')
        require(value['inflight'] == 0, 'CHAT_REQUEST_ACTIVE')
        for name in ('last_start', 'last_end', 'last_ts'):
            number = value.get(name)
            require(type(number) in (int, float) and 0 <= number <= time.time() + 5
                    and math.isfinite(number), 'CHAT_COUNTER_TIMESTAMP')
        require(value['last_end'] >= value['last_start'], 'CHAT_COUNTER_ORDER')
        snapshots.append((sha(raw), ident))
        if not sample:
            time.sleep(.15)
    require(snapshots[0] == snapshots[1], 'CHAT_COUNTER_CHANGED')
    return {'path': str(path), 'inflight': 0, 'samples': 2,
            'sha256': snapshots[-1][0], 'atomic_admission_fence': False}


def listener_owned(pid, port):
    before = proc_identity(pid)
    require(before is not None, 'HTTP_LISTENER_PID')
    owners = set()
    paths = list(Path('/proc/%d/fd' % pid).iterdir())
    require(len(paths) <= 4096, 'HTTP_LISTENER_FDS')
    for path in paths:
        try:
            target = os.readlink(path)
        except FileNotFoundError:
            continue
        match = re.fullmatch(r'socket:\[(\d+)\]', target)
        if match:
            owners.add(match[1])
    listeners = set()
    for name in ('tcp', 'tcp6'):
        with open('/proc/net/' + name, 'rb', buffering=0) as stream:
            chunks, total = [], 0
            while True:
                chunk = stream.read(min(65536, 2 * 1024 * 1024 - total + 1))
                total += len(chunk)
                require(total <= 2 * 1024 * 1024, 'HTTP_LISTENER_TABLE')
                if not chunk:
                    break
                chunks.append(chunk)
            data = b''.join(chunks)
        require(len(data) <= 2 * 1024 * 1024, 'HTTP_LISTENER_TABLE')
        for line in data.decode('ascii').splitlines()[1:]:
            fields = line.split()
            if len(fields) >= 10 and fields[3] == '0A' and int(fields[1].rsplit(':', 1)[1], 16) == port:
                listeners.add(fields[9])
    after = proc_identity(pid)
    require(after and before['starttime'] == after['starttime']
            and listeners and listeners <= owners, 'HTTP_LISTENER_OWNERSHIP')


def public_asset(expected, web_pid):
    listener_owned(web_pid, 18775)
    conn = http.client.HTTPConnection('127.0.0.1', 18775, timeout=3)
    try:
        conn.request('GET', PUBLIC_ASSET_PATH, headers={'Connection': 'close',
                     'Cache-Control': 'no-cache', 'Accept-Encoding': 'identity'})
        response = conn.getresponse()
        require(response.status == 200 and response.getheader('Content-Encoding', 'identity') == 'identity',
                'PUBLIC_ASSET_HTTP')
        raw = response.read(65537)
        require(len(raw) <= 65536 and sha(raw) == expected, 'PUBLIC_ASSET_SHA')
    finally:
        conn.close()
    listener_owned(web_pid, 18775)
    return {'port': 18775, 'path': PUBLIC_ASSET_PATH, 'status': 200, 'sha256': sha(raw),
            'credentials_used': False}


def stop_proxy(helper, expected, spec):
    require(proxy_identity(helper) == expected, 'PROXY_PRESTOP_IDENTITY')
    # Recheck immediately before every supervisor stop, including rollback of
    # a newly started proxy. A new active request leaves the source intact.
    proxy_idle(spec)
    require(proxy_identity(helper) == expected, 'PROXY_FINAL_PRESTOP_IDENTITY')
    helper.command(['supervisorctl', 'stop', 'nox-proxy'], 12)
    require(helper.service_state('nox-proxy').get('state') in ('STOPPED', 'EXITED'), 'PROXY_STOP')
    require(not same_pid(expected), 'PROXY_OLD_PROCESS_ALIVE')


def start_proxy(helper, record, save):
    stop_clear()
    require(helper.service_state('nox-proxy').get('state') in ('STOPPED', 'EXITED'), 'PROXY_START_STATE')
    helper.command(['supervisorctl', 'start', 'nox-proxy'], 12)
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if helper.service_state('nox-proxy').get('state') == 'RUNNING':
            current = proxy_identity(helper)
            if record.get('proxy_after') is None:
                record['proxy_after'] = current
                save()
            require(record['proxy_after'] == current, 'PROXY_RESTART_IDENTITY')
            conn = http.client.HTTPConnection('127.0.0.1', 8080, timeout=2)
            try:
                conn.request('GET', '/health', headers={'Connection': 'close'})
                response = conn.getresponse()
                response.read(4097)
                if response.status == 200:
                    listener_owned(current['pid'], 8080)
                    return current
            except OSError:
                pass
            finally:
                conn.close()
        time.sleep(.2)
    raise Hold('HOLD_CHAT_DECOMPOSITION_PROXY_HEALTH')


def prepare(bundle, spec):
    require(spec.get('schema') == 'NOX_CHAT_DECOMPOSITION_INSTALL_SPEC_V1', 'SPEC')
    require(set(spec.get('guarded_sources', {})) == {'common.py', 'owner_chat_stream.py', 'agent_loop.py',
            'chat_proxy.py', 'nox_v29_chat_bridge.py', 'owner_chat_evidence.py'}, 'GUARD_SET')
    require(set(spec.get('protected_processes', {})) == {'nox-ds41-8098', 'nox-web29-18775',
            'nox-dispatcher-t855u', 'worker_0', 'worker_1', 'worker_2'}, 'PROTECTED_SET')
    require(spec.get('idle_gate', {}).get('schema') == 'NOX_COMMON_INFLIGHT_IDLE_V1'
            and set(spec['idle_gate']['symbols']) == {'common.py:mark_chat', 'chat_proxy.py:_ChatActivityStream'},
            'IDLE_GATE_SPEC')
    require(set(spec.get('before', {})) == {'slim', 'ui'}, 'BEFORE_SET')
    require(set(bundle) == set(spec['assets']) == {'native_helpers.py', 'policy_patch.py', 'public_chat.js'},
            'BUNDLE_SET')
    assets = {}
    for name, expected in spec['assets'].items():
        require(isinstance(bundle[name], str) and len(bundle[name]) <= 262144
                and isinstance(expected, str) and re.fullmatch('[a-f0-9]{64}', expected), 'BUNDLE_BOUND')
        raw = base64.b64decode(bundle[name], validate=True)
        require(sha(raw) == expected and len(raw) <= 131072, 'BUNDLE_PIN')
        assets[name] = raw
    require(sha(assets['native_helpers.py']) == HELPER_SHA, 'HELPER_PIN')
    helper = module('_nox_current_chat_native_helpers', assets['native_helpers.py'])
    patcher = module('_nox_current_chat_policy_patch', assets['policy_patch.py'])
    source = {}
    old_slim, _ = read(TARGETS['slim'], spec['before']['slim'])
    source['slim'] = patcher.patch_slim(old_slim, spec['before']['slim'])
    tree = ast.parse(source['slim'])
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == 'SLIM_RULES' for target in node.targets))
    require(sha(ast.get_source_segment(source['slim'].decode(), assignment).encode())
            == spec['new_rules_assignment_sha256'], 'NEW_RULES_ASSIGNMENT')
    compile(source['slim'], str(TARGETS['slim']), 'exec')
    source['ui'] = assets['public_chat.js']
    require(sha(source['ui']) == spec['after_ui_sha256'] and 0 < len(source['ui']) <= 65536, 'UI_PIN')
    return helper, source


def run(bundle, spec):
    request, commit = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch(r'[0-9]{1,24}', request) and re.fullmatch(r'[a-f0-9]{40}', commit), 'OWNER_CONTEXT')
    record = {'schema': 'NOX_CHAT_DECOMPOSITION_INSTALL_V1', 'request': request, 'source_sha': commit,
              'state': 'PREFLIGHT', 'started_at': time.time(), 'changed': [], 'proxy_after': None,
              'proxy_stop_attempted': False, 'proxy_restart_verified': False,
              'model_restarted': False, 'worker_restarts': 0, 'queue_or_claims_written': False,
              'new_permissions_or_credentials': False, 'generation_calls': 0, 'tests_executed': False,
              'behavioral_acceptance_verified': False, 'rollback_verified': False}
    journal = previous = None
    rows = []
    success = False
    def save():
        nonlocal previous
        if journal is not None:
            raw = encode(record)
            replace_private(journal / 'result.json', raw, previous)
            previous = raw
    with ExitStack() as stack:
        try:
            helper, candidate = prepare(bundle, spec)
            stack.enter_context(lease(ROOT / 'state/owner_chat_decomposition.lock', create_new=True))
            stop_clear()
            guards = source_guards(spec)
            protected_before = protected(helper, spec)
            original = proxy_identity(helper)
            require(original['pid'] == spec['expected_proxy']['pid']
                    and str(original['starttime']) == str(spec['expected_proxy']['start_ticks']), 'EXPECTED_PROXY')
            record['proxy_before'] = original
            listener_owned(original['pid'], 8080)
            record['public_asset_before'] = public_asset(spec['before']['ui'],
                                              spec['protected_processes']['nox-web29-18775']['pid'])
            private_directory(BACKUP)
            journal = BACKUP / request
            require(not os.path.lexists(journal), 'REQUEST_REUSED')
            private_directory(journal)
            for name, target in TARGETS.items():
                old, old_id = read(target, spec['before'][name])
                create(journal / ('original_' + name), old)
                stage = journal / ('exchanged_' + name)
                new_id = create(stage, candidate[name], stat.S_IMODE(old_id[4]))
                row = {'name': name, 'target': str(target), 'staged': str(stage),
                       'before_sha256': sha(old), 'after_sha256': sha(candidate[name]),
                       'before_identity': old_id, 'after_identity': new_id}
                rows.append(row)
            record['sources'] = rows
            record['state'] = 'PREPARED'
            save()
            # No queue-idle or global-model-slot gate: these two serving files
            # are independent of source-workspace MODEL tasks.
            stack.enter_context(lease(ROOT / 'state/owner_maintenance.lock'))
            stop_clear()
            require(source_guards(spec) == guards and protected(helper, spec) == protected_before,
                    'PRESERVED_BEFORE')
            require(all(pair(row) == 'ORIGINAL' for row in rows), 'PRESTOP_PAIR')
            record['idle_before_stop'] = proxy_idle(spec)
            record['proxy_stop_attempted'] = True
            save()
            stop_proxy(helper, original, spec)
            stop_clear()
            for row in rows:
                require(pair(row) == 'ORIGINAL', 'PREEXCHANGE_PAIR')
                exchange(row['target'], row['staged'])
                require(pair(row) == 'INSTALLED', 'POSTEXCHANGE_PAIR')
                record['changed'].append(row['name'])
                save()
            start_proxy(helper, record, save)
            record['public_asset_after'] = public_asset(spec['after_ui_sha256'],
                                             spec['protected_processes']['nox-web29-18775']['pid'])
            require(all(pair(row) == 'INSTALLED' for row in rows), 'FINAL_PAIR')
            require(source_guards(spec) == guards and protected(helper, spec) == protected_before,
                    'PRESERVED_AFTER')
            record.update(state='SOURCE_AND_PROXY_HEALTH_VERIFIED', proxy_restart_verified=True,
                          source_install_verified=True, protected_processes_unchanged=True,
                          full_slim_after_sha256=rows[0]['after_sha256'],
                          ui_after_sha256=rows[1]['after_sha256'], finished_at=time.time())
            save()
            success = True
        except BaseException as error:
            record.update(state='HOLD_CHAT_DECOMPOSITION_INSTALL', reason=safe(error),
                          source_install_verified=False)
            if record['proxy_stop_attempted']:
                try:
                    require(source_guards(spec) == guards and protected(helper, spec) == protected_before,
                            'ROLLBACK_PRESERVED')
                    states = [pair(row) for row in rows]
                    service = helper.service_state('nox-proxy')
                    if service.get('state') == 'RUNNING':
                        current = proxy_identity(helper)
                        require(current in (original, record.get('proxy_after')), 'ROLLBACK_FOREIGN_PROXY')
                        if any(state == 'INSTALLED' for state in states):
                            stop_proxy(helper, current, spec)
                    elif service.get('state') not in ('STOPPED', 'EXITED'):
                        raise Hold('HOLD_CHAT_DECOMPOSITION_ROLLBACK_PROXY_UNSETTLED')
                    else:
                        require(not same_pid(original), 'ROLLBACK_OLD_PROXY_ALIVE')
                        require(record.get('proxy_after') is None or not same_pid(record['proxy_after']),
                                'ROLLBACK_REPLACEMENT_PROXY_ALIVE')
                    for row in reversed(rows):
                        if pair(row) == 'INSTALLED':
                            exchange(row['target'], row['staged'])
                        require(pair(row) == 'ORIGINAL', 'ROLLBACK_PAIR')
                    if helper.service_state('nox-proxy').get('state') in ('STOPPED', 'EXITED'):
                        require(not same_pid(original), 'ROLLBACK_OLD_PROXY_ALIVE')
                        require(record.get('proxy_after') is None or not same_pid(record['proxy_after']),
                                'ROLLBACK_REPLACEMENT_PROXY_ALIVE')
                        record['proxy_after'] = None
                        start_proxy(helper, record, save)
                    record['rollback_verified'] = True
                except BaseException as failure:
                    record['rollback_reason'] = safe(failure)
            record['finished_at'] = time.time()
            try:
                save()
            except BaseException as failure:
                record['receipt_error'] = safe(failure)
    if previous is not None:
        record['receipt_sha256'] = sha(previous)
    print('NOX_MAINT_REPAIR=' + encode({'kind': 'chat_decomposition_install', 'data': record}).decode(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    raise SystemExit(run(BUNDLE, SPEC))
