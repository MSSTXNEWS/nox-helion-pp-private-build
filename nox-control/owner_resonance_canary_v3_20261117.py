#!/usr/bin/env python3
"""Bounded read-only identity observation of the existing maintenance lock."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat

LOCK = Path('/root/nox/state/owner_maintenance.lock')
KNOWN_SERVICES = {'nox-proxy', 'nox-dispatcher-t855u', 'nox-lifeline-guard', 'nox-priority-arbiter', 'nox-cores', 'nox-web29-18775', 'nox-selfheal'}

def bounded(path, limit):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('BOUND_EXCEEDED')
    return raw

def lifetime(pid):
    raw = bounded('/proc/' + str(pid) + '/stat', 8192)
    parts = raw.rsplit(b') ', 1)[1].split()
    if len(parts) < 20 or not parts[19].isdigit():
        raise ValueError('PROC_STAT_SHAPE')
    return {'pid': pid, 'state': parts[0].decode('ascii'), 'ppid': int(parts[1]), 'pgrp': int(parts[2]), 'start_ticks': int(parts[19])}

def holder(pid):
    try:
        row = lifetime(pid)
        argv = bounded('/proc/' + str(pid) + '/cmdline', 65536)
        row['argv_sha256'] = hashlib.sha256(argv).hexdigest()
        row['exe_basename'] = os.path.basename(os.readlink('/proc/' + str(pid) + '/exe'))
        env = dict(piece.split(b'=', 1) for piece in bounded('/proc/' + str(pid) + '/environ', 262144).split(b'\0') if b'=' in piece)
        svc = env.get(b'SUPERVISOR_PROCESS_NAME', env.get(b'PROC_NAME', b'')).decode('ascii', 'replace')
        row['known_service'] = svc if svc in KNOWN_SERVICES else None
        for key, pattern in (('NOX_OWNER_REQUEST_ID', r'[0-9]{1,24}'), ('NOX_OWNER_SOURCE_SHA', r'[a-f0-9]{40}')):
            value = env.get(key.encode(), b'').decode('ascii', 'replace')
            if re.fullmatch(pattern, value):
                row[key.lower()] = value
        after = lifetime(pid)
        if after['start_ticks'] != row['start_ticks']:
            return {'pid': pid, 'state': 'IDENTITY_CHANGED'}
        return row
    except (OSError, ValueError, IndexError) as exc:
        return {'pid': pid, 'state': 'UNKNOWN', 'error_type': type(exc).__name__}

def run():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if os.geteuid() != 0 or not re.fullmatch(r'[0-9]{1,24}', request) or not re.fullmatch(r'[a-f0-9]{40}', source):
        raise ValueError('OWNER_CONTEXT')
    before = LOCK.lstat()
    result = {'schema': 'NOX_MAINTENANCE_LOCK_DIAGNOSTIC_V1', 'owner_request_id': request, 'owner_source_sha': source,
              'lock': {'path': str(LOCK), 'dev': before.st_dev, 'ino': before.st_ino, 'uid': before.st_uid, 'gid': before.st_gid,
                       'mode_octal': oct(stat.S_IMODE(before.st_mode)), 'regular': stat.S_ISREG(before.st_mode)},
              'writes': 0, 'service_calls': 0, 'signals': 0, 'model_calls': 0, 'holders': []}
    if not stat.S_ISREG(before.st_mode) or LOCK.resolve() != LOCK:
        raise ValueError('LOCK_TYPE')
    key = (os.major(before.st_dev), os.minor(before.st_dev), before.st_ino)
    rows = []
    for line in bounded('/proc/locks', 2097152).decode('ascii').splitlines():
        fields = line.split()
        if len(fields) < 8 or '->' in fields:
            continue
        try:
            dev = fields[5].split(':')
            identity = (int(dev[0], 16), int(dev[1], 16), int(dev[2]))
            if identity != key:
                continue
            rows.append({'kind': fields[1], 'scope': fields[2], 'access': fields[3], 'pid': int(fields[4])})
        except (ValueError, IndexError):
            continue
    result['kernel_locks'] = rows[:16]
    result['kernel_rows_truncated'] = len(rows) > 16
    for pid in sorted({x['pid'] for x in rows if x['pid'] > 0})[:16]:
        result['holders'].append(holder(pid))
    fd = os.open(LOCK, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError('LOCK_IDENTITY_CHANGED')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result['nonblocking_probe'] = 'ACQUIRED_AND_IMMEDIATELY_RELEASED'
            fcntl.flock(fd, fcntl.LOCK_UN)
        except BlockingIOError:
            result['nonblocking_probe'] = 'BUSY'
    finally:
        os.close(fd)
    after = LOCK.lstat()
    result['stable_lock_identity'] = (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)
    result['status'] = 'OBSERVED_NOT_AUTHORIZATION_TO_MUTATE'
    return result

try:
    data = run()
    complete = True
except (OSError, ValueError, IndexError) as error:
    data = {'schema': 'NOX_MAINTENANCE_LOCK_DIAGNOSTIC_V1', 'status': 'HOLD_DIAGNOSTIC_' + type(error).__name__.upper(),
            'writes': 0, 'service_calls': 0, 'signals': 0, 'model_calls': 0}
    complete = False
print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'maintenance_lock_diagnostic', 'data': data}, separators=(',', ':')), flush=True)
print('NOX_MAINT_REPAIR_COMPLETE=' + str(complete).lower(), flush=True)
raise SystemExit(0 if complete else 2)
