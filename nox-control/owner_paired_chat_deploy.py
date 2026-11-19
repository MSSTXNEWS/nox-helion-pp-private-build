#!/usr/bin/env python3
"""Owner-only, exact-pin paired V135/V112 install for the existing NOX chat.

The `inspect` phase is read-only and returns opaque preimage tokens for the
two fixed production paths. `apply` requires those exact tokens, freshly
re-reads both targets, saves scoped backups, exchanges both files atomically
while `nox-proxy` is stopped, starts that one service once, and verifies the
installed files and served/imported contracts. This script is transported as
stdin by the existing pinned owner SSH route; never run it locally as a deploy.
"""
from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

SOURCE_COMMIT = 'daf5077bf8f0573ca3a991e7ade9ab733e8195f5'
JS_BLOB = 'c4b3c870b9b2a8ee6c17c06bdb5866f4967a9ba7'
PY_BLOB = '4976fead0517e9d22ead636b2179f3d9436c0b50'
JS_SHA256 = '21a2a9eb1d61358021811ab98a8f03932be1c16a0967566cb1e4b5b6d05dc122'
PY_SHA256 = '28d3bece361499c9d04425f068833800094346204b9930192c3ad5ce6b2e8e3c'
ROOT = Path('/root/nox')
JS_PATH = ROOT / 'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/nox-v135-resonance-owner-bridge.js'
PY_PATH = ROOT / 'scripts/nox_v29_chat_bridge.py'
TARGETS = {'js': JS_PATH, 'python': PY_PATH}
SERVICE = 'nox-proxy'
LOCK_PATH = ROOT / 'state/owner_maintenance.lock'
BACKUP_ROOT = ROOT / 'backup/paired_chat_deploy'
MAX_TARGET = 2 * 1024 * 1024
MEMORY_MIN = 2 * 1024 ** 3


def require(ok: bool, code: str) -> None:
    if not ok:
        raise RuntimeError('HOLD_PAIRED_CHAT_' + code)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git_blob_id(raw: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def safe_emit(kind: str, data: dict) -> None:
    # Receipts contain metadata and digests only; never source bytes or stderr.
    print('NOX_MAINT_PAIRED_CHAT=' + json.dumps({'kind': kind, 'data': data},
          sort_keys=True, separators=(',', ':'), allow_nan=False), flush=True)


def identity(st: os.stat_result) -> list[int]:
    return [st.st_dev, st.st_ino, st.st_uid, st.st_gid,
            stat.S_IMODE(st.st_mode), st.st_nlink, st.st_size,
            st.st_mtime_ns, st.st_ctime_ns]


def moved_equal(observed: list[int], original: list[int]) -> bool:
    # rename/exchange updates ctime; all other identity fields remain pinned.
    return observed[:8] == original[:8]


def open_directory(path: Path) -> int:
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for name in path.parts[1:]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = child
        held = os.fstat(fd)
        require(stat.S_ISDIR(held.st_mode) and held.st_uid == 0 and not (held.st_mode & 0o002)
                and (not (held.st_mode & 0o020) or held.st_gid == 0), 'PARENT_IDENTITY')
        return fd
    except BaseException:
        os.close(fd)
        raise


def parent_token(fd: int) -> list[int]:
    held = os.fstat(fd)
    return [held.st_dev, held.st_ino, held.st_uid, held.st_gid, stat.S_IMODE(held.st_mode)]


def ensure_directory(path: Path) -> int:
    """Create only missing fixed backup directories, without following links."""
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    transferred = False
    try:
        for name in path.parts[1:]:
            try:
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            except FileNotFoundError:
                os.mkdir(name, 0o700, dir_fd=fd)
                os.fsync(fd)
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        require(info.st_uid == 0 and not (info.st_mode & 0o002)
                and (not (info.st_mode & 0o020) or info.st_gid == 0), 'BACKUP_DIRECTORY_IDENTITY')
        transferred = True
        return fd
    finally:
        if not transferred:
            os.close(fd)


def open_parent(path: Path) -> int:
    require(path in TARGETS.values() and path.is_absolute() and '..' not in path.parts, 'PATH_SCOPE')
    return open_directory(path.parent)


def stable_read(path: Path) -> tuple[bytes, dict]:
    parent = open_parent(path)
    fd = None
    try:
        before = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1
                and not (before.st_mode & 0o022) and 0 <= before.st_size <= MAX_TARGET, 'TARGET_FILE')
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
        require(identity(before) == identity(os.fstat(fd)), 'TARGET_CHANGED_BEFORE_READ')
        chunks = []
        remaining = before.st_size
        while remaining:
            block = os.read(fd, min(65536, remaining))
            require(bool(block), 'TARGET_TRUNCATED')
            chunks.append(block)
            remaining -= len(block)
        raw = b''.join(chunks)
        after = os.fstat(fd)
        named = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        require(identity(before) == identity(after) == identity(named), 'TARGET_CHANGED_DURING_READ')
        pinfo = os.fstat(parent)
        check_parent = open_parent(path)
        try:
            require((pinfo.st_dev, pinfo.st_ino) == (os.fstat(check_parent).st_dev, os.fstat(check_parent).st_ino), 'PARENT_REPLACED')
        finally:
            os.close(check_parent)
        token_data = {'sha256': digest(raw), 'file': identity(after), 'path': str(path),
                      'parent': [pinfo.st_dev, pinfo.st_ino, pinfo.st_uid, pinfo.st_gid, stat.S_IMODE(pinfo.st_mode)]}
        token = base64.urlsafe_b64encode(json.dumps(token_data, sort_keys=True, separators=(',', ':')).encode()).decode().rstrip('=')
        return raw, {'sha256': digest(raw), 'file_identity': identity(after),
                     'parent_identity': token_data['parent'], 'preimage_token': token}
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def decode_token(value: str) -> dict:
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{80,700}', value), 'PREIMAGE_TOKEN_FORMAT')
    try:
        parsed = json.loads(base64.urlsafe_b64decode(value + '=' * (-len(value) % 4)))
    except Exception as exc:
        raise RuntimeError('HOLD_PAIRED_CHAT_PREIMAGE_TOKEN_DECODE') from exc
    require(isinstance(parsed, dict) and set(parsed) == {'sha256', 'file', 'parent', 'path'}, 'PREIMAGE_TOKEN_SHAPE')
    require(re.fullmatch(r'[0-9a-f]{64}', str(parsed['sha256'])) is not None
            and isinstance(parsed['file'], list) and len(parsed['file']) == 9
            and isinstance(parsed['parent'], list) and len(parsed['parent']) == 5
            and all(type(x) is int and x >= 0 for x in (*parsed['file'], *parsed['parent'])), 'PREIMAGE_TOKEN_FIELDS')
    require(parsed['path'] in {str(p) for p in TARGETS.values()}, 'PREIMAGE_TOKEN_PATH')
    return parsed


def verify_expected_preimage(path: Path, token: str) -> tuple[bytes, dict]:
    expected = decode_token(token)
    require(path in TARGETS.values() and expected['path'] == str(path), 'PREIMAGE_PATH_PIN')
    raw, current = stable_read(path)
    require(current['sha256'] == expected['sha256'] and current['file_identity'] == expected['file']
            and current['parent_identity'] == expected['parent'], 'PREIMAGE_CAS')
    return raw, current


def assets() -> dict[str, bytes]:
    require(isinstance(BUNDLE, dict) and set(BUNDLE) == {'v135_js', 'v112_py'}, 'SOURCE_BUNDLE_SCOPE')
    result = {}
    pins = (('v135_js', JS_BLOB, JS_SHA256, 22000),
            ('v112_py', PY_BLOB, PY_SHA256, 60000))
    for key, blob_pin, sha_pin, limit in pins:
        encoded = BUNDLE.get(key)
        require(isinstance(encoded, str) and len(encoded) <= limit * 2, 'SOURCE_BUNDLE_SIZE')
        try:
            raw = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise RuntimeError('HOLD_PAIRED_CHAT_SOURCE_BASE64') from exc
        require(0 < len(raw) <= limit and git_blob_id(raw) == blob_pin
                and digest(raw) == sha_pin, 'SOURCE_BLOB_PIN')
        result[key] = raw
    try:
        compile(result['v112_py'], str(PY_PATH), 'exec')
    except Exception as exc:
        raise RuntimeError('HOLD_PAIRED_CHAT_PYTHON_COMPILE') from exc
    return result


def owner_stop() -> bool:
    return any(os.path.lexists(ROOT / name) for name in
               ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP')) or os.path.lexists('/workspace/NOX_STOP') or os.path.lexists(ROOT / 'state/OWNER_MAINTENANCE.flag')


def memory_headroom() -> int:
    current = Path('/sys/fs/cgroup/memory.current')
    maximum = Path('/sys/fs/cgroup/memory.max')
    require(current.is_file() and maximum.is_file(), 'CGROUP_MEMORY_UNAVAILABLE')
    try:
        used = int(current.read_text().strip())
        cap_raw = maximum.read_text().strip()
        require(cap_raw != 'max', 'CGROUP_MEMORY_LIMIT_UNBOUNDED')
        cap = int(cap_raw)
    except Exception as exc:
        if str(exc).startswith('HOLD_'):
            raise
        raise RuntimeError('HOLD_PAIRED_CHAT_CGROUP_MEMORY_PARSE') from exc
    require(cap >= used, 'CGROUP_MEMORY_INVALID')
    return cap - used


def supervisor_state() -> tuple[str, int | None]:
    result = subprocess.run(['supervisorctl', 'status', SERVICE], capture_output=True,
                            timeout=9, check=False, text=True)
    parts = result.stdout.split()
    require(result.returncode in (0, 3) and len(parts) >= 2 and parts[0] == SERVICE, 'SUPERVISOR_STATUS')
    state = parts[1]
    pid = None
    if 'pid' in parts:
        ix = parts.index('pid')
        if ix + 1 < len(parts) and parts[ix + 1].rstrip(',').isdigit():
            pid = int(parts[ix + 1].rstrip(','))
    return state, pid


def process_start(pid: int) -> tuple[str, str]:
    require(pid > 1, 'PROCESS_PID')
    raw = Path(f'/proc/{pid}/cmdline').read_bytes()
    argv = [x.decode(errors='replace') for x in raw.split(b'\0') if x]
    stat_fields = Path(f'/proc/{pid}/stat').read_text().split()
    require(bool(argv) and any('chat_proxy' in x or x.endswith('chat_proxy:app') for x in argv)
            and len(stat_fields) > 21, 'PROCESS_IDENTITY')
    return ' '.join(argv)[:400], stat_fields[21]


def port_listening(port: int) -> bool:
    for name in ('tcp', 'tcp6'):
        rows = Path('/proc/net/' + name).read_text().splitlines()[1:]
        for line in rows:
            fields = line.split()
            if len(fields) > 3 and fields[3] == '0A' and int(fields[1].rsplit(':', 1)[1], 16) == port:
                return True
    return False


def slot_projection(rows: object) -> dict | None:
    """Validate the complete six-slot schema; missing flags never mean idle."""
    if not isinstance(rows, list) or len(rows) != 6:
        return None
    seen = set()
    projected = []
    for row in rows:
        if (not isinstance(row, dict) or type(row.get('id')) is not int
                or not 0 <= row['id'] < 64 or row['id'] in seen):
            return None
        seen.add(row['id'])
        flags = [row[key] for key in ('is_processing', 'processing') if key in row]
        if not flags or any(type(flag) is not bool for flag in flags) or len(set(flags)) != 1:
            return None
        projected.append({'id': row['id'], 'busy': flags[0]})
    return {'schema': 'NOX_PAIRED_CHAT_SLOT_SNAPSHOT_V1', 'slots': projected,
            'count': len(projected), 'busy': sum(row['busy'] for row in projected)}


def slots_idle() -> bool:
    try:
        with urllib.request.urlopen('http://127.0.0.1:8081/slots', timeout=4) as response:
            raw = response.read(30001)
        if len(raw) > 30000:
            return False
        snapshot = slot_projection(json.loads(raw))
        return snapshot is not None and snapshot['busy'] == 0
    except Exception:
        return False


def require_chat_admission_drain() -> None:
    """Do not equate idle model slots with a closed chat admission gate.

    The pinned V112 stream route has no global quiesce/admission-fence API or
    drain receipt. Until that native provider is added and independently read
    back, stopping nox-proxy here could race a new chat request.
    """
    raise RuntimeError('HOLD_PAIRED_CHAT_ADMISSION_DRAIN_PROVIDER_UNAVAILABLE')


def health() -> bool:
    try:
        for port in (8080, 8081):
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=4) as response:
                if response.status != 200:
                    return False
        return True
    except Exception:
        return False


def verify_owner_lock(lock_dir_fd: int, lock_fd: int) -> list[int]:
    """Verify the locked inode is still the exact inode named by the owner path."""
    held = os.fstat(lock_fd)
    named = os.stat(LOCK_PATH.name, dir_fd=lock_dir_fd, follow_symlinks=False)
    require(stat.S_ISREG(held.st_mode) and held.st_uid == 0 and held.st_nlink == 1
            and stat.S_IMODE(held.st_mode) == 0o600
            and stat.S_ISREG(named.st_mode) and named.st_uid == 0 and named.st_nlink == 1
            and stat.S_IMODE(named.st_mode) == 0o600
            and (held.st_dev, held.st_ino, held.st_uid, held.st_gid,
                 stat.S_IMODE(held.st_mode), held.st_nlink) ==
                (named.st_dev, named.st_ino, named.st_uid, named.st_gid,
                 stat.S_IMODE(named.st_mode), named.st_nlink),
            'OWNER_LOCK_PATH_REPLACED')
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        raise RuntimeError('HOLD_PAIRED_CHAT_OWNER_LOCK_LOST') from exc
    return [held.st_dev, held.st_ino, held.st_uid, held.st_gid,
            stat.S_IMODE(held.st_mode), held.st_nlink]


def prepare_service_for_file_rollback(state: str, pid: int | None,
                                      has_swapped_files: bool,
                                      expected_argv: str) -> bool:
    """Return true only after a positively stopped service; otherwise HOLD."""
    stopped_states = {'STOPPED', 'EXITED', 'FATAL', 'BACKOFF'}
    transitioning_states = {'STARTING', 'STOPPING'}
    if state in stopped_states:
        require(pid is None, 'ROLLBACK_TERMINAL_STATE_HAS_PID')
        return True
    if state == 'RUNNING' and not has_swapped_files:
        require(pid is not None and process_start(pid)[0] == expected_argv,
                'ROLLBACK_RUNNING_IDENTITY')
        return False
    if state == 'RUNNING' or state in transitioning_states:
        require(has_swapped_files and pid is not None, 'ROLLBACK_AMBIGUOUS_SERVICE_STATE')
        require(process_start(pid)[0] == expected_argv, 'ROLLBACK_PROCESS_IDENTITY')
        run_supervisor('stop')
        return True
    raise RuntimeError('HOLD_PAIRED_CHAT_ROLLBACK_UNKNOWN_SERVICE_STATE')


def service_restore_readback(expected_argv: str) -> dict | None:
    """Return proof only for a stable, healthy RUNNING owner service.

    A successful `supervisorctl stop/start` command or a previous health sample
    is not enough: the final supervisor PID, process start ticks, listener state,
    and both health routes must agree in a fresh bounded readback.
    """
    try:
        if owner_stop():
            return None
        state, pid = supervisor_state()
        if state != 'RUNNING' or not pid:
            return None
        identity_before = process_start(pid)
        if identity_before[0] != expected_argv:
            return None
        if not (port_listening(8080) and port_listening(8081) and health()):
            return None
        state_after, pid_after = supervisor_state()
        if state_after != 'RUNNING' or pid_after != pid:
            return None
        identity_after = process_start(pid_after)
        if identity_after != identity_before or owner_stop():
            return None
        return {'state': 'RUNNING', 'pid': pid, 'start_ticks': identity_after[1],
                'ports_listening': True, 'health': True}
    except Exception:
        return None


def rollback_status(rollback_ok: bool, expected_argv: str) -> dict:
    """A rollback is complete only after file and fresh service readback pass."""
    readback = service_restore_readback(expected_argv) if rollback_ok else None
    restored = readback is not None
    return {'rollback_verified': bool(rollback_ok and restored),
            'service_restored': restored, 'service_restore_readback': readback}


def run_supervisor(action: str) -> None:
    require(action in ('stop', 'start'), 'SUPERVISOR_ACTION')
    result = subprocess.run(['supervisorctl', action, SERVICE], capture_output=True, timeout=35, check=False)
    require(result.returncode == 0, 'SUPERVISOR_' + action.upper())
    deadline = time.monotonic() + 35
    expected = 'STOPPED' if action == 'stop' else 'RUNNING'
    while time.monotonic() < deadline:
        state, pid = supervisor_state()
        if state == expected and ((action == 'stop' and pid is None)
                                  or (action == 'start' and pid is not None)):
            return
        time.sleep(1)
    raise RuntimeError('HOLD_PAIRED_CHAT_SUPERVISOR_' + expected)


def fsync_dir(fd: int) -> None:
    os.fsync(fd)


def exchange(dir_fd: int, left: str, right: str) -> None:
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    operation = getattr(libc, 'renameat2', None)
    require(operation is not None, 'ATOMIC_EXCHANGE_UNAVAILABLE')
    operation.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    operation.restype = ctypes.c_int
    if operation(dir_fd, os.fsencode(left), dir_fd, os.fsencode(right), 2) != 0:
        raise OSError(ctypes.get_errno(), 'atomic exchange failed')


def write_exclusive(parent_fd: int, name: str, raw: bytes, mode: int, uid: int, gid: int) -> list[int]:
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode, dir_fd=parent_fd)
    try:
        os.fchmod(fd, mode)
        os.fchown(fd, uid, gid)
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            require(count > 0, 'WRITE')
            view = view[count:]
        os.fsync(fd)
        result = identity(os.fstat(fd))
    finally:
        os.close(fd)
    check = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
    try:
        data = os.read(check, len(raw) + 1)
        require(data == raw and identity(os.fstat(check)) == result, 'WRITE_READBACK')
    finally:
        os.close(check)
    fsync_dir(parent_fd)
    return result


def open_backup_dir(request: str) -> tuple[int, Path]:
    rootfd = ensure_directory(BACKUP_ROOT)
    try:
        os.mkdir(request, 0o700, dir_fd=rootfd)
        os.fsync(rootfd)
        dfd = os.open(request, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=rootfd)
        return dfd, BACKUP_ROOT / request
    finally:
        os.close(rootfd)


def backup_file(dfd: int, directory: Path, path: Path, raw: bytes,
                label: str, row: dict) -> tuple[Path, str]:
    name = label + '.preimage'
    write_exclusive(dfd, name, raw, 0o600, 0, 0)
    saved = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dfd)
    try:
        readback = os.read(saved, len(raw) + 1)
    finally:
        os.close(saved)
    require(readback == raw, 'BACKUP_READBACK')
    metadata = {'schema': 'NOX_PAIRED_CHAT_PREIMAGE_BACKUP_V1', 'path': str(path),
        'sha256': digest(raw), 'file_identity': row['file_identity'],
        'parent_identity': row['parent_identity'], 'preimage_token': row['preimage_token'],
        'source_commit': SOURCE_COMMIT}
    meta = json.dumps(metadata, sort_keys=True, separators=(',', ':')).encode() + b'\n'
    write_exclusive(dfd, label + '.metadata.json', meta, 0o600, 0, 0)
    fsync_dir(dfd)
    return directory / name, digest(raw)


def source_readback() -> bool:
    code = r'''import hashlib,sys
from pathlib import Path
sys.path.insert(0,'/root/nox/scripts')
import nox_v29_chat_bridge as bridge
import chat_proxy
from fastapi.routing import APIRoute,Mount
routes={r.path for r in chat_proxy.app.routes if isinstance(r,APIRoute)}
assert {'/api/nox/chat/stream','/api/nox/stop'} <= routes
assert Path(bridge.__file__).resolve()==Path('/root/nox/scripts/nox_v29_chat_bridge.py')
mounts=[r for r in chat_proxy.app.routes if isinstance(r,Mount) and r.path=='/nox-web-v29']
assert len(mounts)==1 and Path(mounts[0].app.directory).resolve()==Path('/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site')
print('NOX_PAIRED_PYTHON=' + hashlib.sha256(Path(bridge.__file__).read_bytes()).hexdigest())'''
    python = '/root/nox/venv/bin/python'
    result = subprocess.run([python, '-c', code], capture_output=True, timeout=30, check=False, text=True)
    return (result.returncode == 0 and ('NOX_PAIRED_PYTHON=' + PY_SHA256) in result.stdout)


def live_route_auth_readback() -> dict | None:
    """Verify route auth at the live listener and read the asset if exposed."""
    result = {'owner_routes_401': True, 'asset_http_status': None,
              'asset_sha256_verified': False, 'asset_owner_auth_gated': False}
    for path in ('/api/nox/chat/stream', '/api/nox/stop'):
        request = urllib.request.Request('http://127.0.0.1:8080' + path, data=b'{}', method='POST',
                                         headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                if response.status != 401:
                    return None
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                return None
        except Exception:
            return None
    request = urllib.request.Request('http://127.0.0.1:8080/nox-web-v29/nox-v135-resonance-owner-bridge.js', method='GET')
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            if response.status != 200:
                return None
            raw = response.read(22001)
            result.update(asset_http_status=200, asset_sha256_verified=(len(raw) <= 22000 and digest(raw) == JS_SHA256))
            return result if result['asset_sha256_verified'] else None
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            result.update(asset_http_status=401, asset_owner_auth_gated=True)
            return result
        return None
    except Exception:
        return None


def wait_ready() -> tuple[int, str] | None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        state, pid = supervisor_state()
        if state == 'RUNNING' and pid:
            try:
                argv, start = process_start(pid)
                if health():
                    return pid, start
            except Exception:
                pass
        time.sleep(1)
    return None


def inspect_phase(request: str) -> bool:
    require(not owner_stop(), 'OWNER_STOP')
    values = {label: stable_read(path)[1] for label, path in TARGETS.items()}
    state, pid = supervisor_state()
    process = process_start(pid) if state == 'RUNNING' and pid else None
    safe_emit('preimage', {'schema': 'NOX_PAIRED_CHAT_PREIMAGE_V1', 'request': request,
        'source_commit': SOURCE_COMMIT, 'targets': values, 'service': SERVICE, 'service_state': state,
        'service_pid': pid,
        'service_process': ({'argv_sha256': digest(process[0].encode()),
                             'start_ticks': process[1]} if process else None),
        'memory_headroom_bytes': memory_headroom(),
        'slots_idle': slots_idle(), 'files_written': 0, 'service_actions': 0})
    return True


def apply_phase(request: str, tokens: dict[str, str], source_blobs: dict[str, bytes]) -> bool:
    require(not owner_stop(), 'OWNER_STOP')
    require(memory_headroom() >= MEMORY_MIN, 'MEMORY_BELOW_2GIB')
    require(slots_idle(), 'ACTIVE_GENERATION')
    require(health(), 'CHAT_HEALTH')
    state, old_pid = supervisor_state()
    require(state == 'RUNNING' and old_pid, 'SERVICE_NOT_RUNNING')
    old_argv, old_start = process_start(old_pid)
    lock_dir = open_directory(LOCK_PATH.parent)
    lock_fd = os.open(LOCK_PATH.name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
                      0o600, dir_fd=lock_dir)
    lock_meta = os.fstat(lock_fd)
    require(stat.S_ISREG(lock_meta.st_mode) and lock_meta.st_uid == 0 and lock_meta.st_nlink == 1,
            'OWNER_LOCK_FILE')
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(lock_fd)
        os.close(lock_dir)
        raise RuntimeError('HOLD_PAIRED_CHAT_OWNER_LOCK_BUSY') from exc
    parent_fds = {}; before = {}; backups = {}; staged = {}; swapped = {}; target_rows = {}
    backup_fd = None; backup_dir = None; stopped = False; started = False
    installed_verified = False
    try:
        verify_owner_lock(lock_dir, lock_fd)
        current_state, current_pid = supervisor_state()
        require(current_state == 'RUNNING' and current_pid == old_pid
                and process_start(current_pid) == (old_argv, old_start), 'SERVICE_IDENTITY_CHANGED')
        require(not owner_stop() and memory_headroom() >= MEMORY_MIN and slots_idle(), 'PREFLIGHT_CHANGED')
        require_chat_admission_drain()
        for label, path in TARGETS.items():
            parent_fds[label] = open_parent(path)
            before[label], target_rows[label] = verify_expected_preimage(path, tokens[label])
        backup_fd, backup_dir = open_backup_dir(request)
        for label, path in TARGETS.items():
            backups[label] = backup_file(backup_fd, backup_dir, path,
                                        before[label], label, target_rows[label])
            base = path.name
            temp = f'.{base}.paired-chat-{request}.pending'
            try:
                os.stat(temp, dir_fd=parent_fds[label], follow_symlinks=False)
                raise RuntimeError('HOLD_PAIRED_CHAT_TEMP_COLLISION')
            except FileNotFoundError:
                pass
            oldinfo = os.stat(base, dir_fd=parent_fds[label], follow_symlinks=False)
            staged[label] = {'temp': temp, 'new_identity': write_exclusive(parent_fds[label], temp,
                source_blobs['v135_js' if label == 'js' else 'v112_py'], stat.S_IMODE(oldinfo.st_mode),
                oldinfo.st_uid, oldinfo.st_gid)}
        for label, path in TARGETS.items():
            verify_expected_preimage(path, tokens[label])
        current_state, current_pid = supervisor_state()
        require(current_state == 'RUNNING' and current_pid == old_pid
                and process_start(current_pid) == (old_argv, old_start), 'SERVICE_IDENTITY_CHANGED')
        require(not owner_stop() and memory_headroom() >= MEMORY_MIN and slots_idle(), 'PREFLIGHT_CHANGED')
        require_chat_admission_drain()
        verify_owner_lock(lock_dir, lock_fd)
        run_supervisor('stop')
        stopped = True
        require(not port_listening(8080) and not port_listening(8081), 'SERVICE_PORT_STILL_OPEN')
        for label, path in TARGETS.items():
            verify_expected_preimage(path, tokens[label])
            require(parent_token(parent_fds[label]) == target_rows[label]['parent_identity'], 'PARENT_IDENTITY_CHANGED')
            verify_owner_lock(lock_dir, lock_fd)
            swapped[label] = 'attempted'
            exchange(parent_fds[label], staged[label]['temp'], path.name)
            swapped[label] = 'done'
            os.fsync(parent_fds[label])
            current = os.stat(path.name, dir_fd=parent_fds[label], follow_symlinks=False)
            displaced = os.stat(staged[label]['temp'], dir_fd=parent_fds[label], follow_symlinks=False)
            installed = source_blobs['v135_js' if label == 'js' else 'v112_py']
            require(moved_equal(identity(current), staged[label]['new_identity'])
                    and digest(read_at(parent_fds[label], path.name)) == digest(installed), 'POST_EXCHANGE')
            require(moved_equal(identity(displaced), target_rows[label]['file_identity'])
                    and digest(read_at(parent_fds[label], staged[label]['temp'])) == target_rows[label]['sha256'],
                    'DISPLACED_PREIMAGE')
        require(not owner_stop() and memory_headroom() >= MEMORY_MIN, 'RESTART_ADMISSION')
        started = True
        run_supervisor('start')
        stopped = False
        ready = wait_ready()
        require(ready is not None and not owner_stop(), 'POST_START_HEALTH')
        require(ready[0] != old_pid or ready[1] != old_start, 'SERVICE_IDENTITY_UNCHANGED')
        for label, path in TARGETS.items():
            raw, observed = stable_read(path)
            wanted = JS_SHA256 if label == 'js' else PY_SHA256
            require(observed['sha256'] == wanted, 'INSTALLED_DISK_READBACK')
        require(source_readback(), 'PYTHON_ROUTE_IMPORT_READBACK')
        live_boundary = live_route_auth_readback()
        require(live_boundary is not None, 'LIVE_ROUTE_AUTH_READBACK')
        installed_verified = True
        # Keep the durable backups; remove only our displaced exact old inodes.
        for label in TARGETS:
            temp = staged[label]['temp']
            displaced = os.stat(temp, dir_fd=parent_fds[label], follow_symlinks=False)
            require(moved_equal(identity(displaced), target_rows[label]['file_identity'])
                    and digest(read_at(parent_fds[label], temp)) == target_rows[label]['sha256'], 'DISPLACED_CLEANUP_CAS')
            os.unlink(temp, dir_fd=parent_fds[label]); os.fsync(parent_fds[label])
        safe_emit('installed', {'schema': 'NOX_PAIRED_CHAT_DEPLOY_V1', 'request': request,
            'source_commit': SOURCE_COMMIT, 'source_blobs': {'v135_js_git_blob': JS_BLOB, 'v112_py_git_blob': PY_BLOB},
            'targets': {label: {'path': str(TARGETS[label]), 'installed_sha256': JS_SHA256 if label == 'js' else PY_SHA256,
                'preimage_sha256': target_rows[label]['sha256'], 'backup_sha256': backups[label][1]}
                for label in TARGETS}, 'service': SERVICE, 'service_pid': ready[0],
            'service_start_ticks': ready[1], 'service_restart_cycles': 1,
            'static_mount_target_verified': True, 'python_route_import_readback': True,
            'live_boundary_readback': live_boundary, 'native_generation_or_gpu_stop_tested': False})
        return True
    except BaseException as exc:
        if installed_verified:
            safe_emit('hold', {'code': 'HOLD_PAIRED_CHAT_DISPLACED_CLEANUP',
                'installed_pair_verified': True, 'service_restored': False,
                'service_running_readback': service_restore_readback(old_argv),
                'backup_paths': {k: str(v[0]) for k, v in backups.items()}})
            return False
        rollback_ok = True
        try:
            state_now, pid_now = supervisor_state()
            stopped = prepare_service_for_file_rollback(
                state_now, pid_now, bool(swapped), old_argv)
        except Exception:
            stopped = False
            rollback_ok = False
        if rollback_ok:
            for label in reversed(tuple(swapped)):
                try:
                    path = TARGETS[label]; temp = staged[label]['temp']; dfd = parent_fds[label]
                    current = os.stat(path.name, dir_fd=dfd, follow_symlinks=False)
                    expected_new = staged[label]['new_identity']
                    source = source_blobs['v135_js' if label == 'js' else 'v112_py']
                    # A signal may have interrupted immediately after exchange;
                    # detect only our exact postimage before attempting rollback.
                    if (moved_equal(identity(current), target_rows[label]['file_identity'])
                            and digest(read_at(dfd, path.name)) == target_rows[label]['sha256']):
                        swapped.pop(label)
                        continue
                    require(current.st_dev == expected_new[0] and current.st_ino == expected_new[1]
                            and digest(read_at(dfd, path.name)) == digest(source), 'ROLLBACK_POSTIMAGE_CAS')
                    exchange(dfd, temp, path.name); os.fsync(dfd)
                    restored = os.stat(path.name, dir_fd=dfd, follow_symlinks=False)
                    require(moved_equal(identity(restored), target_rows[label]['file_identity'])
                            and digest(read_at(dfd, path.name)) == target_rows[label]['sha256'], 'ROLLBACK_READBACK')
                    swapped.pop(label)
                except Exception:
                    rollback_ok = False
                    break
        if rollback_ok:
            for label, path in TARGETS.items():
                if label not in target_rows:
                    continue
                try:
                    raw, row = stable_read(path)
                    if (row['sha256'] != target_rows[label]['sha256']
                            or not moved_equal(row['file_identity'], target_rows[label]['file_identity'])
                            or row['parent_identity'] != target_rows[label]['parent_identity']):
                        rollback_ok = False
                        break
                except Exception:
                    rollback_ok = False
                    break
        if stopped and rollback_ok and not owner_stop() and not port_listening(8080) and not port_listening(8081):
            try:
                run_supervisor('start'); started = True; stopped = False
                restored_ready = wait_ready()
                rollback_ok = rollback_ok and restored_ready is not None and health()
            except Exception:
                rollback_ok = False
        elif stopped and rollback_ok:
            rollback_ok = False
        for label, dfd in parent_fds.items():
            for name in ([staged.get(label, {}).get('temp')] if label in staged and label not in swapped else []):
                if name:
                    try:
                        item = os.stat(name, dir_fd=dfd, follow_symlinks=False)
                        if item.st_ino == staged[label]['new_identity'][1]:
                            os.unlink(name, dir_fd=dfd); os.fsync(dfd)
                    except FileNotFoundError:
                        pass
                    except Exception:
                        rollback_ok = False
        code = str(exc)
        code = code if re.fullmatch(r'HOLD_PAIRED_CHAT_[A-Z0-9_]{1,100}', code) else 'HOLD_PAIRED_CHAT_' + type(exc).__name__.upper()
        service_status = rollback_status(rollback_ok and not stopped, old_argv)
        safe_emit('hold', {'code': code, **service_status, 'source_commit': SOURCE_COMMIT,
            'backup_paths': {k: str(v[0]) for k, v in backups.items()}})
        return False
    finally:
        for fd in parent_fds.values():
            os.close(fd)
        if backup_fd is not None:
            os.close(backup_fd)
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        os.close(lock_dir)


def read_at(parent_fd: int, name: str) -> bytes:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent_fd)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= MAX_TARGET, 'READ_AT_FILE')
        chunks = []; remaining = info.st_size
        while remaining:
            part = os.read(fd, min(65536, remaining)); require(bool(part), 'READ_AT_TRUNCATED')
            chunks.append(part); remaining -= len(part)
        raw = b''.join(chunks)
        require(identity(info) == identity(os.fstat(fd)) and len(raw) == info.st_size, 'READ_AT_CHANGED')
        return raw
    finally:
        os.close(fd)


def main() -> int:
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    mode = os.environ.get('NOX_PAIRED_CHAT_MODE', '')
    require(re.fullmatch(r'[0-9]{1,24}', request) is not None, 'OWNER_REQUEST')
    require(re.fullmatch(r'[0-9a-f]{40}', source) is not None, 'OWNER_SOURCE_SHA')
    require(mode in ('inspect', 'apply'), 'MODE')
    require(source == os.environ.get('NOX_PINNED_SOURCE_SHA', source), 'OWNER_SOURCE_MISMATCH')
    source_blobs = assets()
    if mode == 'inspect':
        okay = inspect_phase(request)
        if okay:
            print('NOX_MAINT_PAIRED_CHAT_DEPLOY_COMPLETE=true', flush=True)
        return 0 if okay else 2
    require(mode == 'apply', 'MODE')
    tokens = {'js': os.environ.get('NOX_EXPECTED_V135_TOKEN', ''),
              'python': os.environ.get('NOX_EXPECTED_V112_TOKEN', '')}
    if not tokens['js'] or not tokens['python']:
        safe_emit('hold', {'code': 'HOLD_PAIRED_CHAT_PREIMAGE_TOKEN_MISSING', 'files_written': 0, 'service_actions': 0})
        return 2
    okay = apply_phase(request, tokens, source_blobs)
    if okay:
        print('NOX_MAINT_PAIRED_CHAT_DEPLOY_COMPLETE=true', flush=True)
    return 0 if okay else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except BaseException as exc:
        code = str(exc)
        if not re.fullmatch(r'HOLD_PAIRED_CHAT_[A-Z0-9_]{1,100}', code):
            code = 'HOLD_PAIRED_CHAT_' + type(exc).__name__.upper()
        safe_emit('hold', {'code': code, 'files_written': 0, 'service_actions': 0})
        raise SystemExit(2)
