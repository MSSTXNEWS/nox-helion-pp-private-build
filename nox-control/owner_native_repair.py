"""Remove the unintended group write bit and call the installed NOX cache pass once."""

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types


ROOT = Path('/root/nox')
OPS = Path('ops/cache-maintenance')
MARKER = Path('state/chat_active')
LEASE = Path('state/owner_maintenance.lock')
BOOT = '9c0ecc02-85c1-452b-b8ae-521e9a11fd03'
MODEL = (3266857, 172046662, 114)
WORKER = (747159, 189183257, 114)
ASSETS = {
    'owner_storage_reclaim': '085403de23d817f1f1307df757901b914115c4745a78dea7ddda53a7fca350f8',
    'owner_memory_governor': '9cdcc97d333a4b2ea07f3003930f260d567a2b6a7cdebb1adcd36220befe617b',
    'owner_memory_cleanup_entry': 'a308933a6df312ad6601bebae4e39ef8f0cd9794cea0f9c4ebc325ea45aac403',
    'nox_cache_maintenance': '5113e633d66026b5821394a3d9e87433ddc14711fe59df1f09ff0dd6974a593c',
}
SAFE_OPEN = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


def require(condition, code):
    if not condition:
        raise RuntimeError('HOLD_CACHE_MARKER_' + code)


def identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_nlink,
            info.st_size, info.st_mtime_ns)


@contextmanager
def trusted_open(relative, *, allow_insecure_marker=False):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    directory = os.open('/', flags)
    try:
        path = ROOT / relative
        for component in path.parts[1:-1]:
            child = os.open(component, flags, dir_fd=directory)
            os.close(directory)
            directory = child
            info = os.fstat(directory)
            require(info.st_uid == os.geteuid() and not info.st_mode & 0o022, 'PARENT')
        fd = os.open(path.name, SAFE_OPEN, dir_fd=directory)
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                    and info.st_nlink == 1 and (allow_insecure_marker or not info.st_mode & 0o022), 'FILE')

            def named():
                return os.stat(path.name, dir_fd=directory, follow_symlinks=False)

            yield handle, named
    finally:
        os.close(directory)


def fix_marker():
    with trusted_open(MARKER, allow_insecure_marker=True) as (handle, named):
        fd = handle.fileno()
        before = os.fstat(fd)
        original_name = named()
        mode = stat.S_IMODE(before.st_mode)
        require(stat.S_ISREG(original_name.st_mode) and identity(original_name) == identity(before)
                and stat.S_IMODE(original_name.st_mode) == mode, 'PREIMAGE')
        require(mode in (0o664, 0o644) and time.time_ns() - before.st_mtime_ns >= 3_000_000_000,
                'MODE_OR_RECENT_ACTIVITY')
        if mode == 0o664:
            os.fchmod(fd, 0o644)
            os.fsync(fd)
        after = os.fstat(fd)
        verified_name = named()
        require(identity(after) == identity(before) == identity(verified_name)
                and stat.S_IMODE(after.st_mode) == stat.S_IMODE(verified_name.st_mode) == 0o644, 'READBACK')
    return {'before_mode': oct(mode), 'after_mode': '0o644', 'mtime_and_inode_unchanged': True,
            'mode_changed': mode != 0o644}


def exact_process(expected):
    pid, ticks, parent = expected
    with Path(f'/proc/{pid}/stat').open('rb') as stream:
        state = stream.read(8193)
    fields = state.rpartition(b') ')[2].split()
    require(len(state) <= 8192 and state.startswith(str(pid).encode() + b' (') and len(fields) >= 20
            and fields[0] not in (b'Z', b'X') and fields[1] == str(parent).encode()
            and fields[19] == str(ticks).encode(), 'PROCESS_CHANGED')


def assets():
    compiled = {}
    for name, expected in ASSETS.items():
        relative = OPS / (name + '.py')
        with trusted_open(relative) as (handle, named):
            before = os.fstat(handle.fileno())
            raw = handle.read(256 * 1024 + 1)
            require(0 < len(raw) <= 256 * 1024 and identity(before) == identity(named())
                    and identity(before) == identity(os.fstat(handle.fileno()))
                    and hashlib.sha256(raw).hexdigest() == expected, 'INSTALLED_SOURCE')
        compiled[name] = str(ROOT / relative), compile(raw, str(ROOT / relative), 'exec')
    for name, (path, code) in compiled.items():
        module = types.ModuleType(name)
        module.__file__ = path
        sys.modules[name] = module
        exec(code, module.__dict__)
    return sys.modules['nox_cache_maintenance']


def emit(key, value):
    print('NOX_MAINT_' + key + '=' + json.dumps(value, separators=(',', ':')), flush=True)


def main():
    labels = {os.environ[name].removeprefix('C.') for name in ('VAST_CONTAINERLABEL', 'CONTAINER_ID')
              if os.environ.get(name)}
    require(os.geteuid() == 0 and labels == {'60509551'}
            and re.fullmatch(r'[1-9][0-9]{0,19}', os.environ.get('NOX_OWNER_REQUEST_ID', ''))
            and re.fullmatch(r'[a-f0-9]{40}', os.environ.get('NOX_OWNER_SOURCE_SHA', ''))
            and Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT, 'OWNER_CONTEXT')
    with trusted_open(LEASE) as (handle, named):
        lease = os.fstat(handle.fileno())
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        require(identity(lease) == identity(named()), 'LEASE_CHANGED')
        exact_process(MODEL)
        exact_process(WORKER)
        service = assets()
        service.cache.require_stop_clear()
        service.current_scope()
        emit('CACHE_MARKER_FIXED', fix_marker())
        service.assert_chat_idle()
        result = service.run_once(ASSETS['nox_cache_maintenance'])
        exact_process(MODEL)
        exact_process(WORKER)
        require(identity(lease) == identity(named()), 'LEASE_CHANGED')
        emit('CACHE_BOUNDED_PASS', result)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        code = str(error)
        code = code if re.fullmatch(r'HOLD_[A-Z_0-9]+', code) else type(error).__name__
        emit('CACHE_MARKER_HOLD', {'reason': code})
        raise SystemExit(2) from None
