"""Protect only the existing DS41 launcher and attest the retained bytes."""

import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time


LAUNCH = Path('/root/nox/models/deepseek_v41_flash_iq2xxs/launch_ds41_8098_t119u.sh')
LEASE = Path('/root/nox/state/owner_maintenance.lock')
START = Path('/root/onstart.sh')
EXPECTED_START = 'b36b916aadc8bb6047108823bf7b86f00448deafd9f79a824a9f4924c1190507'
STOP = ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP',
        'state/STOP.flag', 'state/OWNER_MAINTENANCE.flag')


def need(value, code):
    if not value:
        raise RuntimeError('HOLD_MODEL_LAUNCH_PREPARE_' + code)


def stop_clear():
    need(not any(os.path.lexists(Path('/root/nox') / name) for name in STOP)
         and not os.path.lexists('/workspace/NOX_STOP'), 'STOP')


def identity(info):
    return info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_nlink, info.st_size


def protected_file(path):
    for parent in path.parents:
        info = parent.lstat()
        need(stat.S_ISDIR(info.st_mode) and info.st_uid == info.st_gid == 0
             and not info.st_mode & 0o022, 'PARENT')
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    fd = os.open(path, flags)
    return os.fdopen(fd, 'rb')


def launch_metadata(handle):
    info = os.fstat(handle.fileno())
    need(stat.S_ISREG(info.st_mode) and (info.st_uid, info.st_gid, info.st_nlink, info.st_size) == (0, 0, 1, 1844)
         and identity(LAUNCH.lstat()) == identity(info), 'FILE_PREIMAGE')
    return info


def live_model():
    pid = 3266857
    try:
        before = Path(f'/proc/{pid}/stat').read_text().rpartition(') ')[2].split()[19]
        if before != '172046662':
            return {'known_generation': False}
        connection = http.client.HTTPConnection('127.0.0.1', 8098, timeout=3)
        try:
            connection.request('GET', '/health', headers={'Connection': 'close'})
            response = connection.getresponse()
            raw = response.read(4097)
            status = response.status
        finally:
            connection.close()
        after = Path(f'/proc/{pid}/stat').read_text().rpartition(') ')[2].split()[19]
        return {'known_generation': after == before, 'status': status,
                'healthy': after == before and status == 200 and len(raw) <= 4096
                and isinstance(json.loads(raw), dict) and json.loads(raw).get('status') == 'ok'}
    except (OSError, ValueError, IndexError, http.client.HTTPException):
        return {'known_generation': False, 'healthy': False}


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    ticks = Path('/proc/1/stat').read_text().rpartition(') ')[2].split()[19]
    need(os.geteuid() == os.getegid() == 0 and re.fullmatch('[1-9][0-9]{0,19}', request)
         and re.fullmatch('[a-f0-9]{40}', source) and ticks == '167790899', 'OWNER_CONTEXT')
    with protected_file(LEASE) as lease, protected_file(START) as startup:
        locked = os.fstat(lease.fileno())
        need(stat.S_ISREG(locked.st_mode) and (locked.st_dev, locked.st_ino, locked.st_uid, locked.st_gid, locked.st_nlink)
             == (36, 59886214, 0, 0, 1) and not locked.st_mode & 0o077, 'OWNER_LEASE')
        until = time.monotonic() + 36
        while True:
            stop_clear()
            try:
                fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= until:
                    raise RuntimeError('HOLD_MODEL_LAUNCH_PREPARE_OWNER_BUSY') from None
                time.sleep(0.25)
        need(identity(LEASE.lstat()) == identity(locked), 'OWNER_LEASE_CHANGED')
        need(hashlib.sha256(startup.read(65537)).hexdigest() == EXPECTED_START, 'STARTUP_CHANGED')
        with protected_file(LAUNCH) as handle:
            preimage = launch_metadata(handle)
            mode = stat.S_IMODE(preimage.st_mode)
            raw = handle.read(1845)
            need(mode in (0o775, 0o755) and len(raw) == 1844 and b'\0' not in raw, 'FILE_BYTES')
            result = subprocess.run(['/bin/bash', '--noprofile', '--norc', '-n', '-s'], input=raw,
                                    env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}, timeout=4,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            need(result.returncode == 0, 'BASH_SYNTAX')
            stop_clear()
            sampled = launch_metadata(handle)
            need(identity(sampled) == identity(preimage) and sampled.st_mtime_ns == preimage.st_mtime_ns
                 and stat.S_IMODE(sampled.st_mode) == mode, 'FILE_CHANGED')
            if mode == 0o775:
                os.fchmod(handle.fileno(), 0o755)
            try:
                os.fsync(handle.fileno())
                handle.seek(0)
                after = launch_metadata(handle)
                need(identity(after) == identity(preimage) and stat.S_IMODE(after.st_mode) == 0o755
                     and handle.read(1845) == raw, 'POSTIMAGE')
            except (OSError, RuntimeError):
                if mode == 0o775 and identity(launch_metadata(handle)) == identity(preimage):
                    os.fchmod(handle.fileno(), 0o775)
                    os.fsync(handle.fileno())
                raise
    output = {'launcher_sha256': hashlib.sha256(raw).hexdigest(), 'source_bytes': len(raw),
              'group_write_removed': mode == 0o775, 'bash_syntax_verified': True,
              'model_tree_reference': os.fsencode(LAUNCH.parent) in raw,
              'engram_reference': b'engram_ram.gguf' in raw, 'port_8098_reference': b'8098' in raw,
              'running_workload_changed': False, 'restart_verified': False,
              'same_client_model': live_model()}
    print('NOX_MAINT_MODEL_LAUNCH_PREPARED=' + json.dumps(output, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        code = str(error)
        print('NOX_MAINT_MODEL_LAUNCH_HOLD=' + (code if re.fullmatch('HOLD_[A-Z0-9_]+', code)
                                               else type(error).__name__), flush=True)
        raise SystemExit(2) from None
