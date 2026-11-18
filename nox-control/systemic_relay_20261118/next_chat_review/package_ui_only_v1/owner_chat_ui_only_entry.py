#!/usr/bin/env python3
"""Atomic replacement of the existing public chat JS without a service restart.

Only the exact reviewed static asset is exchanged. The running proxy, live chat
counter, policy modules, model, workers, queues and existing claims are untouched.
Official owner-authenticated GETs verify the canonical mounted asset on the same
proxy lifetime before and after the exchange. The native maintenance lease only
serializes this short file transaction; there is no foreground-idle requirement.
"""
from __future__ import annotations

import base64
from contextlib import ExitStack, contextmanager
import ctypes
import fcntl
import hashlib
import http.client
import json
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
TARGET = SITE / 'pc/v24/nox-v24-chat.js'
BACKUP = ROOT / 'backup/owner_chat_ui_only'
CONFIG = ROOT / 'config/owner_native_subagents.json'
PUBLIC_ASSET_PATH = '/nox-web-v29/pc/v24/nox-v24-chat.js'
HELPER_SHA = 'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0'
AUTH_HELPER_SHA = '73107aed7d1eaa72d92fe15d4f91c8c5878e560e9efcffaf4dbf583f500fbf60'
UI_BEFORE_SHA = '92b952b6c7ee31f22ed74912d9444a88989c014694424083336660dce21a8a5b'
UI_AFTER_SHA = '646fe556bb446aa0a7b30abd44f1ed41865877553ceef2bb703c85f6b112d5a2'
SPEC = {'schema': 'NOX_CHAT_UI_ONLY_INSTALL_SPEC_V1', 'before_ui_sha256': '92b952b6c7ee31f22ed74912d9444a88989c014694424083336660dce21a8a5b', 'after_ui_sha256': '646fe556bb446aa0a7b30abd44f1ed41865877553ceef2bb703c85f6b112d5a2', 'asset_bytes': {'after': 33602, 'before': 31906}, 'assets': {'native_helpers.py': 'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0', 'public_chat.js': '646fe556bb446aa0a7b30abd44f1ed41865877553ceef2bb703c85f6b112d5a2', 'official_auth.py': '73107aed7d1eaa72d92fe15d4f91c8c5878e560e9efcffaf4dbf583f500fbf60'}, 'guarded_sources': {'agent_loop.py': '0ecec93bcf3239b7decc768862d27fbdc60fe2b613103f201406761bb4850aaa', 'chat_proxy.py': '1b468ebda8cdae0dce3fd1b9df4f7def64c56d708796b05e5bd7f88fbc76af62', 'common.py': '618b2b24ffdf780e64a5d09955438dec5a9b6b8b04b3346b29c57fc750403167', 'nox_v29_chat_bridge.py': '9d7475428ad8c553c756ca50280ac2363e7c03854abab285de560ae066d4586a', 'owner_chat_evidence.py': 'ea66e05f30472b066444058ac18d0c7af74def410bde760396d1e2431161e8b2', 'owner_chat_stream.py': '38f4dc2995dd2c31f1f4d6a816d485721267d7add1c789cc4693aca54233fe09', 'slim_chat_t885u.py': '8e1a83a68b336fc0c12f350d754ea47e5b5b72688584670aacc0de4079b1d37b'}, 'protected_processes': {'nox-dispatcher-t855u': {'pgrp': 106058, 'pid': 106058, 'ppid': 114, 'start_ticks': 181620214}, 'nox-ds41-8098': {'pgrp': 3266857, 'pid': 3266857, 'ppid': 114, 'start_ticks': 172046662}, 'nox-web29-18775': {'pgrp': 3505392, 'pid': 3505392, 'ppid': 114, 'start_ticks': 173653097}, 'worker_0': {'pgrp': 106058, 'pid': 106174, 'ppid': 106058, 'start_ticks': 181621423}, 'worker_1': {'pgrp': 106058, 'pid': 106175, 'ppid': 106058, 'start_ticks': 181621423}, 'worker_2': {'pgrp': 106058, 'pid': 106176, 'ppid': 106058, 'start_ticks': 181621423}}, 'expected_proxy': {'pgrp': 3703386, 'pid': 3703386, 'ppid': 114, 'start_ticks': 175609570}, 'provenance': {'v5_spec_sha256': '0b3db4a0912660fae50db76b0239b77e73885f788cb8d113b0ce4797816cbd6c', 'unchanged_chat_hold_readback_sha256': '7bdc8f5c58aa57dba86238b08533f1a92ea9c267a57a4f2fb98932f8a373b135', 'unchanged_chat_hold_receipt_sha256': '4f854c83232358d6f928558f7a41816a08213bbcecb04895e61c17a436207b7b', 'current_process_readback_sha256': 'af4e38655364e37a740469db86058b03f48abfcd5539f29119dd9b836a963e09', 'current_process_request': [6989803150]}, 'foreground_idle_required': False, 'policy_write_or_reload': False, 'acceptance_scope': 'STATIC_ASSET_HTTP_ONLY_BEHAVIOR_PENDING', 'original_task_accepted': False}
try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

class Hold(RuntimeError):
    pass


def require(value, reason):
    if not value:
        raise Hold('HOLD_CHAT_UI_ONLY_' + reason)


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
    raise Hold('HOLD_CHAT_UI_ONLY_EXCHANGE_IDENTITY')


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
                and str(observed.get('starttime')) == str(expected['start_ticks'])
                and observed['ppid'] == expected['ppid'] and observed['pgrp'] == expected['pgrp'],
                'PROTECTED_PROCESS')
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


def public_asset(expected, expected_bytes, proxy, auth, result):
    # Only an existing official owner session may fetch the protected mount.
    # Capture even a partially authenticated client so errors still close it.
    created = []
    class ScopedOwnerClient(auth.OwnerClient):
        def __init__(self, cookie=None):
            require(not created, 'OFFICIAL_SESSION_COUNT')
            super().__init__(cookie)
            created.append(self)
    result.update(port=8080, path=PUBLIC_ASSET_PATH, expected_sha256=expected,
                  expected_bytes=expected_bytes, status=None, content_encoding=None,
                  bytes_read=0, credentials_used=True, new_credentials_created=False,
                  session_created=False, session_closed=False,
                  raw_body_or_credentials_exported=False)
    conn = None
    failure = close_failure = None
    try:
        require(same_pid(proxy), 'ASSET_PROXY_LIFETIME')
        listener_owned(proxy['pid'], 8080)
        client = ScopedOwnerClient.authenticate()
        result['session_created'] = True
        require(same_pid(proxy), 'ASSET_AUTH_PROXY_LIFETIME')
        listener_owned(proxy['pid'], 8080)
        conn = http.client.HTTPConnection('127.0.0.1', 8080, timeout=3)
        conn.request('GET', PUBLIC_ASSET_PATH, headers={'Connection': 'close',
                     'Cache-Control': 'no-cache', 'Accept-Encoding': 'identity',
                     'Cookie': 'nox_chat=' + client.cookie})
        response = conn.getresponse()
        encoding = response.getheader('Content-Encoding', 'identity')
        result['status'] = response.status
        result['content_encoding'] = encoding if encoding in ('identity', 'gzip', 'br', 'deflate') else 'OTHER'
        raw = response.read(65537)
        result['bytes_read'] = len(raw)
        result['sha256' if len(raw) <= 65536 else 'read_prefix_sha256'] = sha(raw)
        result['body_within_limit'] = len(raw) <= 65536
        require(response.status == 200 and encoding == 'identity', 'PUBLIC_ASSET_HTTP')
        require(len(raw) <= 65536 and len(raw) == expected_bytes and sha(raw) == expected, 'PUBLIC_ASSET_SHA')
        require(same_pid(proxy), 'ASSET_FINAL_PROXY_LIFETIME')
        listener_owned(proxy['pid'], 8080)
    except BaseException as error:
        failure = error
    finally:
        if conn is not None:
            try:
                conn.close()
            except BaseException as error:
                close_failure = error
                result['transport_close_reason'] = safe(error)
        for client in created:
            result['session_created'] = True
            try:
                client.close()
                result['session_closed'] = True
            except BaseException as error:
                close_failure = error
                result['session_close_reason'] = safe(error)
            finally:
                client.cookie = None
    if failure is not None:
        raise failure
    require(close_failure is None and result['session_closed'], 'OFFICIAL_SESSION_CLOSE')
    return result


def expected_proxy(helper, spec):
    current = proxy_identity(helper)
    expected = spec['expected_proxy']
    observed = proc_identity(expected['pid'])
    require(current['pid'] == expected['pid']
            and current['starttime'] == str(expected['start_ticks'])
            and current['pgrp'] == expected['pgrp']
            and observed and observed['starttime'] == current['starttime']
            and observed['ppid'] == expected['ppid'], 'EXPECTED_PROXY')
    return current


def prepare(bundle, spec):
    require(spec.get('schema') == 'NOX_CHAT_UI_ONLY_INSTALL_SPEC_V1', 'SPEC')
    require(set(spec.get('guarded_sources', {})) == {
            'common.py', 'owner_chat_stream.py', 'agent_loop.py', 'chat_proxy.py',
            'nox_v29_chat_bridge.py', 'owner_chat_evidence.py', 'slim_chat_t885u.py'}, 'GUARD_SET')
    require(set(spec.get('protected_processes', {})) == {
            'nox-ds41-8098', 'nox-web29-18775', 'nox-dispatcher-t855u',
            'worker_0', 'worker_1', 'worker_2'}, 'PROTECTED_SET')
    require(spec.get('before_ui_sha256') == UI_BEFORE_SHA
            and spec.get('after_ui_sha256') == UI_AFTER_SHA
            and spec.get('asset_bytes') == {'before': 31906, 'after': 33602}, 'ASSET_SPEC')
    require(set(bundle) == set(spec.get('assets', {})) == {
            'native_helpers.py', 'public_chat.js', 'official_auth.py'}, 'BUNDLE_SET')
    assets = {}
    for name, pin in spec['assets'].items():
        require(isinstance(bundle[name], str) and len(bundle[name]) <= 262144
                and isinstance(pin, str) and re.fullmatch('[a-f0-9]{64}', pin), 'BUNDLE_BOUND')
        raw = base64.b64decode(bundle[name], validate=True)
        require(sha(raw) == pin and len(raw) <= 131072, 'BUNDLE_PIN')
        assets[name] = raw
    require(sha(assets['native_helpers.py']) == HELPER_SHA, 'HELPER_PIN')
    require(sha(assets['official_auth.py']) == AUTH_HELPER_SHA, 'AUTH_HELPER_PIN')
    candidate = assets['public_chat.js']
    require(sha(candidate) == UI_AFTER_SHA and len(candidate) == 33602, 'UI_PIN')
    helper = module('_nox_current_chat_ui_helpers', assets['native_helpers.py'])
    auth = module('_nox_current_chat_ui_official_auth', assets['official_auth.py'])
    return helper, candidate, auth


def run(bundle, spec):
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    commit = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch(r'[0-9]{1,24}', request)
            and re.fullmatch(r'[a-f0-9]{40}', commit), 'OWNER_CONTEXT')
    record = {
        'schema': 'NOX_CHAT_UI_ONLY_INSTALL_V1', 'request': request, 'source_sha': commit,
        'state': 'PREFLIGHT', 'started_at': time.time(), 'changed': [],
        'asset_exchange_attempted': False, 'asset_install_verified': False,
        'proxy_stop_attempted': False, 'proxy_restarted': False,
        'model_restarted': False, 'worker_restarts': 0, 'queue_or_claims_written': False,
        'policy_source_written': False, 'policy_loaded': False,
        'chat_counter_read': False, 'chat_counter_written': False,
        'foreground_idle_required': False, 'new_permissions_or_credentials': False,
        'generation_calls': 0, 'tests_executed': False,
        'behavioral_acceptance_verified': False, 'original_task_accepted': False,
        'rollback_verified': False,
    }
    journal = previous = row = None
    success = False

    def save():
        nonlocal previous
        if journal is not None:
            raw = encode(record)
            replace_private(journal / 'result.json', raw, previous)
            previous = raw

    with ExitStack() as stack:
        try:
            helper, candidate, auth = prepare(bundle, spec)
            stack.enter_context(lease(ROOT / 'state/owner_chat_ui_only.lock', create_new=True))
            stop_clear()
            guards = source_guards(spec)
            protected_before = protected(helper, spec)
            original = expected_proxy(helper, spec)
            record['proxy_before'] = original
            record['protected_before'] = protected_before
            record['guarded_sources_before'] = guards
            record['public_asset_before'] = {}
            public_asset(UI_BEFORE_SHA, 31906, original, auth, record['public_asset_before'])
            private_directory(BACKUP)
            journal = BACKUP / request
            require(not os.path.lexists(journal), 'REQUEST_REUSED')
            private_directory(journal)
            old, old_id = read(TARGET, UI_BEFORE_SHA, 65536)
            create(journal / 'original_ui', old)
            stage = journal / 'exchanged_ui'
            new_id = create(stage, candidate, stat.S_IMODE(old_id[4]))
            require(new_id[2:5] == old_id[2:5], 'PRESERVED_ASSET_METADATA')
            row = {'name': 'ui', 'target': str(TARGET), 'staged': str(stage),
                   'before_sha256': UI_BEFORE_SHA, 'after_sha256': UI_AFTER_SHA,
                   'before_identity': old_id, 'after_identity': new_id}
            record['sources'] = [row]
            record['state'] = 'PREPARED'
            save()
            # The existing maintenance lease serializes source transactions.
            # An active chat continues on the same process; no drain is needed.
            stack.enter_context(lease(ROOT / 'state/owner_maintenance.lock'))
            stop_clear()
            require(source_guards(spec) == guards
                    and protected(helper, spec) == protected_before
                    and expected_proxy(helper, spec) == original, 'PRESERVED_BEFORE')
            require(pair(row) == 'ORIGINAL', 'PREEXCHANGE_PAIR')
            record['asset_exchange_attempted'] = True
            save()
            exchange(row['target'], row['staged'])
            require(pair(row) == 'INSTALLED', 'POSTEXCHANGE_PAIR')
            record['changed'].append('ui')
            save()
            record['public_asset_after'] = {}
            public_asset(UI_AFTER_SHA, 33602, original, auth, record['public_asset_after'])
            require(pair(row) == 'INSTALLED', 'FINAL_PAIR')
            protected_after = protected(helper, spec)
            guards_after = source_guards(spec)
            require(protected_after == protected_before and guards_after == guards
                    and expected_proxy(helper, spec) == original, 'PRESERVED_AFTER')
            record.update(state='STATIC_ASSET_HTTP_VERIFIED', asset_install_verified=True,
                          protected_processes_unchanged=True, proxy_after=original,
                          protected_after=protected_after, guarded_sources_after=guards_after,
                          ui_after_sha256=UI_AFTER_SHA, finished_at=time.time())
            save()
            success = True
        except BaseException as error:
            record.update(state='HOLD_CHAT_UI_ONLY_INSTALL', reason=safe(error),
                          asset_install_verified=False)
            if record['asset_exchange_attempted'] and row is not None:
                try:
                    # Revert only our exact exchange pair. Foreign modifications
                    # to this asset are never overwritten; other files are not touched.
                    if pair(row) == 'INSTALLED':
                        exchange(row['target'], row['staged'])
                    require(pair(row) == 'ORIGINAL', 'ROLLBACK_PAIR')
                    record['rollback_verified'] = True
                    record['ui_after_sha256'] = UI_BEFORE_SHA
                    try:
                        record['public_asset_rollback'] = {}
                        public_asset(UI_BEFORE_SHA, 31906, original, auth,
                                     record['public_asset_rollback'])
                        record['rollback_http_verified'] = True
                    except BaseException as failure:
                        record['rollback_http_verified'] = False
                        record['rollback_http_reason'] = safe(failure)
                except BaseException as failure:
                    record['rollback_reason'] = safe(failure)
            record['finished_at'] = time.time()
            try:
                save()
            except BaseException as failure:
                record['receipt_error'] = safe(failure)
    if previous is not None:
        record['receipt_sha256'] = sha(previous)
    print('NOX_MAINT_REPAIR=' + encode({'kind': 'chat_ui_only_install', 'data': record}).decode(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    raise SystemExit(run(BUNDLE, SPEC))

