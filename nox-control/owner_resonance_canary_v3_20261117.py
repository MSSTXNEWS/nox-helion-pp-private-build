#!/usr/bin/env python3
"""Read-only prepare-path observation for request6957849667; existing repair runner."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

OBSERVED_REQUEST = '6957849667'
PATHS = (('root', '/root/nox', 'directory'), ('scripts', '/root/nox/scripts', 'directory'), ('state', '/root/nox/state', 'directory'), ('maintenance_lock', '/root/nox/state/owner_maintenance.lock', 'lock'), ('backup_parent', '/root/nox/backup', 'directory'), ('maintenance_backup_parent', '/root/nox/backup/owner_maintenance', 'directory'), ('request_backup', '/root/nox/backup/owner_maintenance/6957849667', 'directory'), ('native_backup', '/root/nox/backup/owner_maintenance/6957849667/native-chat-p0', 'directory'), ('stage', '/root/nox/scripts/.owner-chat-p0-6957849667', 'directory'), ('native:owner_chat_stream.py', '/root/nox/scripts/owner_chat_stream.py', 'source'), ('stage:owner_chat_stream.py', '/root/nox/scripts/.owner-chat-p0-6957849667/owner_chat_stream.py', 'source'), ('backup:owner_chat_stream.py', '/root/nox/backup/owner_maintenance/6957849667/native-chat-p0/owner_chat_stream.py', 'source'), ('native:nox_v29_chat_bridge.py', '/root/nox/scripts/nox_v29_chat_bridge.py', 'source'), ('stage:nox_v29_chat_bridge.py', '/root/nox/scripts/.owner-chat-p0-6957849667/nox_v29_chat_bridge.py', 'source'), ('backup:nox_v29_chat_bridge.py', '/root/nox/backup/owner_maintenance/6957849667/native-chat-p0/nox_v29_chat_bridge.py', 'source'), ('native:chat_proxy.py', '/root/nox/scripts/chat_proxy.py', 'source'), ('stage:chat_proxy.py', '/root/nox/scripts/.owner-chat-p0-6957849667/chat_proxy.py', 'source'), ('backup:chat_proxy.py', '/root/nox/backup/owner_maintenance/6957849667/native-chat-p0/chat_proxy.py', 'source'), ('operation_receipt', '/root/nox/state/owner_maintenance_6957849667.json', 'receipt'))

MAX_SOURCE = 250000
MAX_TOTAL_READ = 1048576


def metadata(info):
    kind = ('regular' if stat.S_ISREG(info.st_mode) else 'directory' if stat.S_ISDIR(info.st_mode)
            else 'symlink' if stat.S_ISLNK(info.st_mode) else 'other')
    return {'uid': info.st_uid, 'gid': info.st_gid, 'mode_octal': oct(stat.S_IMODE(info.st_mode)),
            'dev': info.st_dev, 'ino': info.st_ino, 'type': kind, 'size': info.st_size,
            'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}


def observe():
    rows = []
    bytes_read = 0
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
            if expected in ('source', 'receipt') and row['realpath'] != value:
                row['source_hash_status'] = 'UNKNOWN_NONCANONICAL_PATH'
            elif expected in ('source', 'receipt') and stat.S_ISREG(info.st_mode):
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                try:
                    before = os.fstat(fd)
                    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_SOURCE or bytes_read + before.st_size > MAX_TOTAL_READ:
                        row['source_hash_status'] = 'UNKNOWN_TYPE_OR_SIZE'
                    else:
                        raw = os.pread(fd, min(MAX_SOURCE + 1, MAX_TOTAL_READ - bytes_read), 0)
                        bytes_read += len(raw)
                        after, named = os.fstat(fd), path.lstat()
                        keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_uid', 'st_gid', 'st_mode')
                        stable = len(raw) == before.st_size and all(getattr(before, k) == getattr(after, k) == getattr(named, k) == getattr(info, k) for k in keys)
                        row['source_hash_status'] = 'OBSERVED_STABLE' if stable else 'UNKNOWN_CHANGED_DURING_READ'
                        if stable:
                            row['sha256'] = hashlib.sha256(raw).hexdigest()
                            row['bytes'] = len(raw)
                            if expected == 'receipt':
                                try:
                                    value = json.loads(raw)
                                    row['receipt_summary'] = {
                                        'request_matches': value.get('request') == OBSERVED_REQUEST,
                                        'status': value.get('status') if value.get('status') in ('HOLD', 'HOLD_METADATA_PREFLIGHT', 'APPLIED_RELOADED_USE_PENDING', 'ROLLED_BACK_RELOADED') else 'UNKNOWN',
                                        'error': value.get('error') if value.get('error') in ('HOLD_FILENOTFOUNDERROR', 'HOLD_PERMISSIONERROR') else 'UNKNOWN',
                                        'phases': [v.get('phase') for v in value.get('steps', [])[:100] if isinstance(v, dict) and v.get('phase') in ('permission_hardening_planned', 'permission_hardened', 'private_backup_directory_created', 'preflight', 'staged_verified_and_backed_up', 'proxy_stopped', 'files_replaced_verified', 'proxy_reloaded', 'originals_restored_and_reloaded')],
                                        'replaced_files': [v for v in value.get('replaced_files', []) if v in ('owner_chat_stream.py', 'nox_v29_chat_bridge.py', 'chat_proxy.py')],
                                    }
                                except (ValueError, TypeError, AttributeError):
                                    row['receipt_summary_status'] = 'UNKNOWN_INVALID_RECEIPT'
                finally:
                    os.close(fd)
        except OSError as exc:
            row.update(state='UNKNOWN_OS_ERROR', errno=exc.errno, error_type=type(exc).__name__)
        except RuntimeError:
            row.update(state='UNKNOWN_PATH_RESOLUTION')
        rows.append(row)
    return {'schema': 'NOX_NATIVE_CHAT_P0_PREPARE_DIAGNOSTIC_V1', 'euid': os.geteuid(), 'egid': os.getegid(),
            'observed_request': OBSERVED_REQUEST, 'paths': rows, 'bytes_read': bytes_read, 'read_budget': MAX_TOTAL_READ, 'diagnostic_complete': True, 'writes': 0, 'service_calls': 0,
            'network_calls': 0, 'model_calls': 0, 'installed': None, 'used': False, 'accepted': False,
            'install_guards_changed': False}


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch(r'[0-9]{1,24}', request) or not re.fullmatch(r'[0-9a-f]{40}', source):
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'native_chat_p0_prepare_diagnostic', 'data': {'status': 'HOLD_OWNER_REQUEST_CONTEXT', 'diagnostic_complete': False}}), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        return 2
    result = observe()
    result.update(owner_request_id=request, owner_source_sha=source)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'native_chat_p0_prepare_diagnostic', 'data': result}, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
