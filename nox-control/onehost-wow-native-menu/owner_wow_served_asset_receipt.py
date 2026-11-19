#!/usr/bin/env python3
"""Observe exact authenticated WOW static bytes without installing or opening chat."""

import base64
from contextlib import contextmanager
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
SITE = ROOT / 'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site'
PROXY_SOURCE = ROOT / 'scripts/chat_proxy.py'
LEASE = ROOT / 'state/owner_maintenance.lock'
PREFIX = '/nox-web-v29/'
AUTH = 'owner_media_acceptance_entry.py'
AUTH_SHA = '73107aed7d1eaa72d92fe15d4f91c8c5878e560e9efcffaf4dbf583f500fbf60'
LIMIT = 262144
REQUIRED = (
    'pc/resonance.html',
    'pc/v24/nox-v24-chat.js',
    'nox-v135-resonance-owner-bridge.js',
    'nox-v137-owner-self-status.js',
)
OPTIONAL = (
    'index.html', 'pc/index.html', 'pc/v24/nox-v24-menu.js',
    'nox-select-tiles-v5.js', 'nox-select-tiles-v5.css',
    'nox-connection-v13.js', 'nox-cinematic-worlds.js',
    'nox-world-controls-v13.css', 'nox-eclipse-backdrop.mjs',
    'nox-shared-chrome-v10.js', 'nox-shared-scene-v10.mjs',
    'pc/pages/cinema/index.html', 'pc/pages/games/index.html',
    'pc/pages/graph/index.html', 'pc/pages/music/index.html',
    'pc/pages/voice/index.html',
)
STOPS = tuple(ROOT / name for name in (
    'STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP',
    'state/STOP.flag', 'state/OWNER_MAINTENANCE.flag',
)) + (Path('/workspace/NOX_STOP'),)


def require(ok, reason):
    if not ok:
        raise RuntimeError('HOLD_WOW_SERVED_' + reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_auth():
    require(isinstance(BUNDLE, dict) and set(BUNDLE) == {AUTH}, 'AUTH_BUNDLE')
    source = BUNDLE[AUTH]
    require(isinstance(source, str) and 0 < len(source) <= 131072, 'AUTH_BOUND')
    raw = base64.b64decode(source, validate=True)
    require(sha(raw) == AUTH_SHA, 'AUTH_PIN')
    module = types.ModuleType('nox_wow_auth')
    exec(compile(raw, AUTH, 'exec'), module.__dict__)
    return module


def gate():
    require(not any(os.path.lexists(path) for path in STOPS), 'OWNER_STOP')


def bounded(path, limit):
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'LOCAL_READ_BOUND')
    return raw


def proxy_identity():
    result = subprocess.run(('supervisorctl', 'status', 'nox-proxy'),
                            capture_output=True, text=True, timeout=5, check=False)
    match = re.fullmatch(r'nox-proxy\s+RUNNING\s+pid\s+([1-9]\d*),[^\n]*\n?', result.stdout)
    require(result.returncode == 0 and match is not None, 'PROXY_NOT_RUNNING')
    pid = int(match[1])
    proc = Path('/proc') / str(pid)
    data = bounded(proc / 'stat', 8192)
    fields = data[data.rfind(b')') + 2:].split()
    argv = bounded(proc / 'cmdline', 65536).split(b'\0')
    require(len(fields) > 19 and fields[0] not in (b'Z', b'X')
            and fields[19].isdigit() and os.fsencode(PROXY_SOURCE) in argv, 'PROXY_IDENTITY')
    return pid, int(fields[19])


def bind_listener(expected):
    require(proxy_identity() == expected, 'PROXY_LIFETIME')
    sockets = set()
    for index, fd in enumerate((Path('/proc') / str(expected[0]) / 'fd').iterdir()):
        require(index < 4096, 'PROXY_FD_BOUND')
        try:
            target = os.readlink(fd)
        except FileNotFoundError:
            continue
        match = re.fullmatch(r'socket:\[(\d+)\]', target)
        if match:
            sockets.add(match[1])
    listen = set()
    for protocol in ('tcp', 'tcp6'):
        data = bounded(Path('/proc/net') / protocol, 2 * 1024 * 1024)
        for row in data.decode('ascii').splitlines()[1:]:
            fields = row.split()
            if len(fields) >= 10 and fields[3] == '0A' and fields[1].endswith(':1F90'):
                listen.add(fields[9])
    require(listen and listen <= sockets and proxy_identity() == expected, 'LISTENER_8080')
    return tuple(sorted(listen))


@contextmanager
def owner_lease():
    gate()
    path = LEASE
    require(not any(item.is_symlink() for item in path.parents), 'LEASE_PATH')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and info.st_nlink == 1 and not info.st_mode & 0o022, 'LEASE_INODE')
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            require(False, 'MAINTENANCE_LEASE_BUSY')
        yield
        current = path.lstat()
        require((info.st_dev, info.st_ino) == (current.st_dev, current.st_ino), 'LEASE_REPLACED')
        gate()
    finally:
        os.close(fd)


def served(relative, cookie=None):
    require(relative in REQUIRED or relative in OPTIONAL, 'ROUTE_SCOPE')
    headers = {'Connection': 'close', 'Accept-Encoding': 'identity', 'Cache-Control': 'no-cache'}
    if cookie is not None:
        headers['Cookie'] = 'nox_chat=' + cookie
    connection = http.client.HTTPConnection('127.0.0.1', 8080, timeout=3)
    try:
        connection.request('GET', PREFIX + relative, headers=headers)
        reply = connection.getresponse()
        if reply.status != 200:
            return reply.status, None
        length = reply.getheader('Content-Length')
        require(reply.getheader('Content-Encoding', 'identity') == 'identity'
                and isinstance(length, str) and length.isdigit()
                and 0 < int(length) <= LIMIT, 'HTTP_BODY_HEADER')
        raw = reply.read(LIMIT + 1)
        require(len(raw) == int(length), 'HTTP_BODY_LENGTH')
        return reply.status, (len(raw), sha(raw))
    finally:
        connection.close()


def disk(relative, auth):
    try:
        raw = auth.read(SITE / relative, LIMIT)
    except FileNotFoundError:
        return None
    require(bool(raw), 'EMPTY_DISK_ASSET')
    return len(raw), sha(raw)


def asset_row(relative, auth, cookie):
    gate()
    before = disk(relative, auth)
    status, wire = served(relative, cookie)
    after = disk(relative, auth)
    require(before == after, 'DISK_CHANGED')
    matched = status == 200 and wire is not None and wire == before
    absent = status == 404 and before is None and relative in OPTIONAL
    row = {'path': relative, 'http': status, 'disk_matches_http': matched}
    if wire is not None:
        row.update(served_bytes=wire[0], served_sha256=wire[1])
    if before is not None:
        row.update(disk_bytes=before[0], disk_sha256=before[1])
    return row, (matched or absent)


def main(record):
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch(r'[0-9]{1,24}', request) and re.fullmatch(r'[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    require(os.geteuid() == 0, 'ROOT_REQUIRED')
    record.update(request=request, source_sha=source)
    auth = load_auth()
    clients = []

    class ScopedClient(auth.OwnerClient):
        def __init__(self, cookie=None):
            require(not clients, 'AUTH_COUNT')
            super().__init__(cookie)
            clients.append(self)

    with owner_lease():
        process = proxy_identity()
        listeners = bind_listener(process)
        record['proxy'] = {'pid': process[0], 'start_ticks': process[1], 'port': 8080}
        record['anonymous_asset_status'], _ = served(REQUIRED[0])
        require(record['anonymous_asset_status'] == 401, 'AUTHENTICATED_MOUNT')
        accepted = True
        try:
            client = ScopedClient.authenticate()
            require(bind_listener(process) == listeners, 'LISTENER_CHANGED')
            record['owner_session_verified'] = True
            for relative in REQUIRED + OPTIONAL:
                row, okay = asset_row(relative, auth, client.cookie)
                record['assets'].append(row)
                accepted &= okay
        finally:
            if clients:
                require(bind_listener(process) == listeners, 'LISTENER_CHANGED_BEFORE_LOGOUT')
                clients[0].close()
                record['owner_session_closed'] = True
        require(bind_listener(process) == listeners, 'LISTENER_CHANGED_AFTER_LOGOUT')
        require(accepted, 'ASSET_MATRIX_MISMATCH')


def timeout(_sig, _frame):
    require(False, 'TIME_BUDGET')


if __name__ == '__main__':
    record = {'schema': 'NOX_WOW_SERVED_ASSET_MATRIX_V1', 'static_root': str(SITE),
              'http_prefix': PREFIX, 'assets': [], 'browser_execution_verified': False,
              'service_changes': 0, 'application_posts': 0, 'asset_bodies_exported': False}
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(100)
    try:
        main(record)
        record['state'] = 'AUTHENTICATED_CURRENT_STATIC_MATRIX'
        rc = 0
    except Exception as exc:
        record['state'] = 'HOLD'
        reason = str(exc)
        record['reason'] = reason if re.fullmatch(r'HOLD_[A-Z0-9_]{1,120}', reason) else type(exc).__name__
        rc = 2
    finally:
        signal.alarm(0)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'wow_served_asset_matrix', 'data': record},
          separators=(',', ':'), sort_keys=True), flush=True)
    if rc == 0:
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    raise SystemExit(rc)
