#!/usr/bin/env python3
"""Read-only Drive streaming preflight. Never transfers bytes or changes queues."""
from __future__ import annotations

import ast
from collections import Counter
import glob
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time

ROOT = Path('/root/nox')
SAFE_PATH = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
REMOTE = 'nox_drive:'  # Existing nox_pc_export.validate_receipt contract; no remote guessing.
FOLDER = '1f6d8mwMtR6Be8xMMiA5EpLZI7B47IS2l'
SENTINEL = 'deepseek_iq2_xxs_manifest.json'
SENTINEL_ID = '1DF1I9UQeDxxeYlRT1_FhvepmHXB7bsrr'
REQUIRED_BYTES_ESTIMATE = 273_000_000_000


def read_regular(path, limit):
    path = Path(path)
    if any(p.is_symlink() for p in (*path.parents, path)):
        raise ValueError('SYMLINK_SOURCE')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError('BOUNDED_REGULAR_SOURCE_REQUIRED')
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > limit or (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError('SOURCE_CHANGED')
    return raw


def error_class(stderr, code):
    text = stderr.lower()
    if any(x in text for x in (b'invalid_grant', b'invalid credentials', b'failed to get token', b'unauthorized', b'401')):
        return 'HOLD_RCLONE_AUTH'
    if any(x in text for x in (b'insufficient permission', b'permission denied', b'accessnotconfigured', b'403')):
        return 'HOLD_RCLONE_PERMISSION'
    if b'quota' in text:
        return 'HOLD_RCLONE_QUOTA'
    return 'HOLD_RCLONE_EXIT_' + str(code)


def command(argv, timeout=20, limit=512 * 1024):
    """Only constant read-only argv reach here; suppress all provider stderr."""
    try:
        p = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {'returncode': None, 'state': 'HOLD_READ_ONLY_TIMEOUT'}, b''
    except OSError:
        return {'returncode': None, 'state': 'HOLD_EXECUTABLE_UNAVAILABLE'}, b''
    if len(p.stdout) > limit or len(p.stderr) > limit:
        return {'returncode': p.returncode, 'state': 'HOLD_READ_ONLY_OUTPUT_LIMIT'}, b''
    meta = {'returncode': p.returncode, 'state': 'OK' if p.returncode == 0 else error_class(p.stderr, p.returncode)}
    return meta, p.stdout if p.returncode == 0 else b''


def documented_profile():
    path = ROOT / 'state/cold_drive.conf'  # nox_pc_export.finalize uses this exact installed profile.
    result = {'path': str(path), 'contents_inspected': False}
    try:
        if any(p.is_symlink() for p in (*path.parents, path)):
            return dict(result, state='HOLD_DOCUMENTED_PROFILE_SYMLINK')
        info = path.lstat()
    except OSError:
        return dict(result, state='HOLD_DOCUMENTED_PROFILE_MISSING')
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
        return dict(result, state='HOLD_DOCUMENTED_PROFILE_OWNER_OR_MODE')
    return dict(result, state='VERIFIED_PRIVATE_PROFILE_METADATA', mode='0600', owner_uid=info.st_uid)


def drive_probe():
    executable = shutil.which('rclone', path=SAFE_PATH)
    result = {'remote_selection': 'ONLY_EXISTING_NOX_DRIVE_ALIAS', 'selected_remote': None,
              'folder_id': FOLDER, 'expected_manifest_id': SENTINEL_ID, 'maximum_objects': 10,
              'write_permission': 'NOT_EXERCISED_READ_ONLY', 'required_bytes_estimate': REQUIRED_BYTES_ESTIMATE,
              'required_bytes_is_final_manifest_total': False, 'rclone_path': executable}
    if not executable:
        return dict(result, state='HOLD_RCLONE_MISSING')
    meta, raw = command([executable, 'version'], timeout=8)
    result['version'] = dict(meta, first_line=raw.decode('utf-8', 'replace').splitlines()[:1])
    profile = documented_profile()
    result['documented_profile'] = profile
    if profile['state'] != 'VERIFIED_PRIVATE_PROFILE_METADATA':
        return dict(result, state=profile['state'])
    config_args = ['--config', profile['path']]
    meta, raw = command([executable, 'listremotes', *config_args], timeout=12, limit=16384)
    names = [x for x in raw.decode('utf-8', 'replace').splitlines() if re.fullmatch(r'[A-Za-z0-9_.-]{1,64}:', x)]
    result['listremotes'] = dict(meta, names=names[:64])
    capabilities = {}
    for name, args in (('rcat', ['rcat', '--help']), ('size', ['size', '--help']),
                       ('lsjson', ['lsjson', '--help']), ('drive_backend', ['help', 'backend', 'drive'])):
        status, help_text = command([executable, *args], timeout=8)
        capabilities[name] = dict(status, help_sha256=hashlib.sha256(help_text).hexdigest(),
                                 available=status['state'] == 'OK')
        if name == 'rcat':
            capabilities[name]['explicit_stream_size'] = b'--size' in help_text
        elif name == 'size':
            capabilities[name]['json_output'] = b'--json' in help_text
        elif name == 'lsjson':
            capabilities[name]['single_object_stat'] = b'--stat' in help_text
        else:
            capabilities[name]['root_folder_override'] = b'--drive-root-folder-id' in help_text
            capabilities[name]['chunk_size_option'] = b'--drive-chunk-size' in help_text
    result['capabilities'] = capabilities
    if meta['state'] != 'OK':
        return dict(result, state=meta['state'])
    if REMOTE not in names:
        return dict(result, state='HOLD_KNOWN_DRIVE_REMOTE_MISSING')
    result['selected_remote'] = REMOTE
    if not capabilities['drive_backend'].get('root_folder_override'):
        return dict(result, state='HOLD_BOUNDED_FOLDER_PROBE_UNSUPPORTED')
    common = [*config_args, '--drive-root-folder-id', FOLDER, '--retries', '1', '--low-level-retries', '1',
              '--contimeout', '10s', '--timeout', '20s']
    # rclone v1.53.3 NewFsSrc adds an exact-file filter for remote:file even without --stat.
    stat_args = ['--stat'] if capabilities['lsjson'].get('single_object_stat') else []
    status, raw = command([executable, 'lsjson', REMOTE + SENTINEL, *stat_args, *common], timeout=35, limit=65536)
    listing = dict(status, objects=[])
    if status['state'] == 'OK':
        try:
            values = json.loads(raw)
            values = [values] if isinstance(values, dict) else values
            if not isinstance(values, list) or len(values) > 10:
                raise ValueError('LIST_SCOPE')
            listing['objects'] = [{key: item[key] for key in ('Name', 'Path', 'ID', 'Size', 'MimeType', 'ModTime', 'IsDir')
                                   if key in item} for item in values if isinstance(item, dict)]
            listing['sentinel_id_verified'] = any(item.get('ID') == SENTINEL_ID and item.get('Name') == SENTINEL
                                                   and item.get('IsDir') is False for item in values)
        except (ValueError, TypeError, AttributeError):
            listing['state'] = 'HOLD_INVALID_FOLDER_METADATA'
    result['folder_listing'] = listing
    status, raw = command([executable, 'about', REMOTE, '--json', *common], timeout=35, limit=65536)
    quota = dict(status)
    if status['state'] == 'OK':
        try:
            value = json.loads(raw)
            quota.update({key: value[key] for key in ('total', 'used', 'free', 'trashed', 'other') if type(value.get(key)) is int})
        except (ValueError, TypeError, AttributeError):
            quota['state'] = 'HOLD_INVALID_QUOTA_METADATA'
    result['quota'] = quota
    if listing['state'] != 'OK':
        return dict(result, state=listing['state'])
    if not listing.get('sentinel_id_verified'):
        return dict(result, state='HOLD_EXPECTED_FOLDER_SENTINEL_NOT_VERIFIED')
    if quota['state'] != 'OK':
        return dict(result, state=quota['state'])
    if type(quota.get('free')) is not int:
        return dict(result, state='HOLD_DRIVE_FREE_QUOTA_UNKNOWN')
    if quota['free'] < REQUIRED_BYTES_ESTIMATE:
        return dict(result, state='HOLD_DRIVE_QUOTA_BELOW_ESTIMATE')
    if not capabilities['rcat'].get('explicit_stream_size') or not capabilities['size'].get('json_output'):
        return dict(result, state='HOLD_RCLONE_STREAM_SIZE_CAPABILITY')
    return dict(result, state='READY_READ_ONLY_DRIVE_STREAM_PREFLIGHT')


def system_probe():
    usage = shutil.disk_usage(ROOT)
    result = {'disk_free_bytes': usage.free, 'disk_total_bytes': usage.total, 'dev_fuse_exists': Path('/dev/fuse').exists()}
    for name in ('memory.max', 'memory.current'):
        try:
            result[name] = read_regular(Path('/sys/fs/cgroup') / name, 128).decode().strip()
        except (OSError, ValueError):
            result[name] = None
    result['commands'] = {}
    for name in ('cmake', 'g++', 'ninja', 'nvcc'):
        path = shutil.which(name, path=SAFE_PATH)
        row = {'path': path, 'available': bool(path)}
        if path:
            meta, raw = command([path, '--version'], timeout=8, limit=65536)
            row.update(meta, version_lines=raw.decode('utf-8', 'replace').splitlines()[:4])
        result['commands'][name] = row
    known_nvcc = Path('/usr/local/cuda-12.4/bin/nvcc')
    row = {'path': str(known_nvcc)}
    try:
        info = known_nvcc.stat()
        row['available'] = stat.S_ISREG(info.st_mode) and os.access(known_nvcc, os.X_OK)
        if row['available']:
            meta, raw = command([str(known_nvcc), '--version'], timeout=8, limit=65536)
            row.update(meta, version_lines=raw.decode('utf-8', 'replace').splitlines()[:5])
    except OSError:
        row['available'] = False
    result['known_cuda_12_4_nvcc'] = row
    patterns = ('/usr/local/cuda*/lib64/libcublas*', '/usr/local/cuda*/targets/x86_64-linux/lib/libcublas*',
                '/usr/lib/x86_64-linux-gnu/libcublas*', '/usr/local/cuda*/include/cublas*.h',
                '/usr/local/cuda*/targets/x86_64-linux/include/cublas*.h', '/usr/include/cublas*.h',
                '/root/venv_volta/lib/python3.*/site-packages/nvidia/cublas/lib/libcublas*',
                '/root/venv_volta/lib/python3.*/site-packages/nvidia/cublas/include/cublas*.h')
    paths = sorted({p for pattern in patterns for p in glob.glob(pattern)})[:40]
    result['cublas_paths'] = [{'path': p, 'bytes': Path(p).stat().st_size} for p in paths if Path(p).is_file()]
    return result


def dispatcher_probe():
    result = {'state_path': str(ROOT / 'state/dispatcher/state.json'), 'queue_mutated': False,
              'new_worker_started': False, 'long_download_handler': 'UNVERIFIED', 'sources': []}
    for name in ('nox_dispatcher_t855u.py', 'owner_task_plans.py', 'nox_cold_drive.py', 'nox_pc_export.py'):
        path = ROOT / 'scripts' / name
        try:
            raw = read_regular(path, 2 * 1024 ** 2)
            source = raw.decode('utf-8')
            tree = ast.parse(source)
            functions = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
            result['sources'].append({'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                                      'persistence_functions': sorted(functions & {'load_state', 'save_state', 'atomic_write', 'worker_loop'})})
            if name == 'owner_task_plans.py' and 'WAIT_DOWNLOAD_ADMISSION' in source:
                result['long_download_handler'] = 'HOLD_DOWNLOAD_ADMISSION_NOT_BOUND'
        except (OSError, ValueError, SyntaxError, UnicodeError) as exc:
            result['sources'].append({'path': str(path), 'state': type(exc).__name__})
    try:
        value = json.loads(read_regular(Path(result['state_path']), 16 * 1024 ** 2))
        tasks = value.get('tasks', {})
        if not isinstance(tasks, dict):
            raise ValueError('QUEUE_SHAPE')
        rows = [x for x in tasks.values() if isinstance(x, dict)]
        result.update(queue_readable=True, tasks=len(rows),
                      statuses=dict(Counter(x.get('status') for x in rows if x.get('status') in
                                            ('pending', 'wait', 'retry', 'running', 'done', 'failed', 'blocked', 'cancelled'))),
                      handlers=sorted({x['handler'] for x in rows if isinstance(x.get('handler'), str)
                                       and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', x['handler'])}),
                      maximum_declared_timeout_sec=max((x['timeout_sec'] for x in rows
                                                       if type(x.get('timeout_sec')) is int and 0 <= x['timeout_sec'] <= 864000), default=None))
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        result.update(queue_readable=False, queue_error=type(exc).__name__)
    return result


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch(r'[0-9]{1,20}', request) or not re.fullmatch(r'[0-9a-f]{40}', source):
        raise ValueError('OWNER_CONTEXT_REQUIRED')
    receipt = {'schema': 'NOX_DRIVE_STREAM_PREFLIGHT_V1', 'request': request, 'source_sha': source,
               'observed_at': time.time(), 'read_only': True, 'downloaded_bytes': 0, 'uploaded_bytes': 0,
               'deleted_objects': 0, 'services_changed': False, 'credential_config_inspected_or_printed': False,
               'system': system_probe(), 'dispatcher': dispatcher_probe(), 'drive': drive_probe()}
    receipt['state'] = receipt['drive']['state']
    receipt['persistent_download_task_ready'] = False  # Presence of a queue does not prove a bound long-running transfer handler.
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'drive_stream_read_only_preflight', 'data': receipt}, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'drive_stream_preflight_hold', 'error_class': type(exc).__name__}), flush=True)
        raise SystemExit(2)
