#!/usr/bin/env python3
"""Read-only metadata for the exact P0 install paths; existing repair runner."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

PATHS = (
    ('root', '/root/nox', 'directory'),
    ('scripts', '/root/nox/scripts', 'directory'),
    ('state', '/root/nox/state', 'directory'),
    ('chat_proxy.py', '/root/nox/scripts/chat_proxy.py', 'source'),
    ('nox_v29_chat_bridge.py', '/root/nox/scripts/nox_v29_chat_bridge.py', 'source'),
    ('owner_chat_stream.py', '/root/nox/scripts/owner_chat_stream.py', 'source'),
    ('maintenance_lock', '/root/nox/state/owner_maintenance.lock', 'lock'),
)
MAX_SOURCE = 250000


def metadata(info):
    kind = ('regular' if stat.S_ISREG(info.st_mode) else 'directory' if stat.S_ISDIR(info.st_mode)
            else 'symlink' if stat.S_ISLNK(info.st_mode) else 'other')
    return {'uid': info.st_uid, 'gid': info.st_gid, 'mode_octal': oct(stat.S_IMODE(info.st_mode)),
            'dev': info.st_dev, 'ino': info.st_ino, 'type': kind, 'size': info.st_size,
            'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}


def observe():
    rows = []
    for name, value, expected in PATHS:
        row = {'name': name, 'path': value, 'expected_type': expected}
        path = Path(value)
        try:
            info = path.lstat()
            row.update(state='OBSERVED', lstat=metadata(info), realpath=str(path.resolve(strict=True)))
            row['installer_checks'] = {
                'canonical_path': row['realpath'] == value,
                'owned_by_euid': info.st_uid == os.geteuid(),
                'no_group_or_other_write': not bool(info.st_mode & 0o022),
                'expected_type': stat.S_ISDIR(info.st_mode) if expected == 'directory' else stat.S_ISREG(info.st_mode),
            }
            if row['realpath'] != value or stat.S_ISLNK(info.st_mode):
                row['resolved_target_stat'] = metadata(path.stat())
            if expected == 'source' and stat.S_ISREG(info.st_mode):
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                try:
                    before = os.fstat(fd)
                    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_SOURCE:
                        row['source_hash_status'] = 'UNKNOWN_TYPE_OR_SIZE'
                    else:
                        raw = os.pread(fd, MAX_SOURCE + 1, 0)
                        after, named = os.fstat(fd), path.lstat()
                        keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_uid', 'st_gid', 'st_mode')
                        stable = len(raw) == before.st_size and all(getattr(before, k) == getattr(after, k) == getattr(named, k) == getattr(info, k) for k in keys)
                        row['source_hash_status'] = 'OBSERVED_STABLE' if stable else 'UNKNOWN_CHANGED_DURING_READ'
                        if stable:
                            row['sha256'] = hashlib.sha256(raw).hexdigest()
                            row['bytes'] = len(raw)
                finally:
                    os.close(fd)
        except OSError as exc:
            row.update(state='UNKNOWN_OS_ERROR', errno=exc.errno, error_type=type(exc).__name__)
        except RuntimeError:
            row.update(state='UNKNOWN_PATH_RESOLUTION')
        rows.append(row)
    return {'schema': 'NOX_NATIVE_CHAT_P0_PATH_DIAGNOSTIC_V1', 'euid': os.geteuid(), 'egid': os.getegid(),
            'paths': rows, 'diagnostic_complete': True, 'writes': 0, 'service_calls': 0,
            'network_calls': 0, 'model_calls': 0, 'installed': False, 'used': False, 'accepted': False,
            'install_guards_changed': False}


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch(r'[0-9]{1,24}', request) or not re.fullmatch(r'[0-9a-f]{40}', source):
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'native_chat_p0_path_diagnostic', 'data': {'status': 'HOLD_OWNER_REQUEST_CONTEXT', 'diagnostic_complete': False}}), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        return 2
    result = observe()
    result.update(owner_request_id=request, owner_source_sha=source)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'native_chat_p0_path_diagnostic', 'data': result}, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
