"""Release cache associated only with the closed, unpublished WOW snapshot."""

import fcntl
import json
import os
from pathlib import Path
import stat


ROOT = Path('/root/nox/incoming_t800u/wow-r62-full')
CGROUP = Path('/sys/fs/cgroup')
RECEIPT = 'receipt.json'
ARCHIVE = 'NOX_WEB_V14_CINEMA_ASSIST_20261119_R6_2_WOW_NO_DUPLICATES.zip'
MAX_FILES = 1271
MAX_BYTES = 263657685
LOCK = Path('/root/nox/state/owner_maintenance.lock')
STOP = ('/root/nox/STOP', '/root/nox/STOP.flag', '/root/nox/state/STOP', '/workspace/NOX_STOP')


def require(ok, reason):
    if not ok:
        raise RuntimeError('HOLD_WOW_CACHE_' + reason)


def current():
    return int((CGROUP / 'memory.current').read_text())


def advice():
    require(os.geteuid() == 0, 'OWNER')
    require(not any(os.path.lexists(path) for path in STOP), 'STOP')
    with os.fdopen(os.open(LOCK, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC), 'rb') as locked:
        identity = os.fstat(locked.fileno())
        require(stat.S_ISREG(identity.st_mode) and identity.st_uid == 0 and identity.st_nlink == 1
                and identity.st_mode & 0o077 == 0, 'LEASE')
        fcntl.flock(locked.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        stage = ROOT.lstat()
        require(stat.S_ISDIR(stage.st_mode) and stage.st_uid == 0 and stage.st_mode & 0o022 == 0,
                'STAGE_SCOPE')
        receipt = ROOT / RECEIPT
        with os.fdopen(os.open(receipt, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC), 'rb') as stream:
            details = os.fstat(stream.fileno())
            require(stat.S_ISREG(details.st_mode) and details.st_uid == 0 and 0 < details.st_size < 4096,
                    'RECEIPT_SCOPE')
            data = json.loads(stream.read(4096))
        require(data.get('request') == '7015397105' and data.get('active_site_changed') is False
                and data.get('files') == 1270 and data.get('zip_sha256') ==
                'f10d2437f45018b846d0dca87691ab65d35c04c9c1ca8d0d7b0bab1538a0090c', 'RECEIPT_PIN')
        before = current()
        rows, total = 0, 0
        for directory, dirs, files, dfd in os.fwalk(ROOT, follow_symlinks=False):
            child = os.fstat(dfd)
            require(child.st_dev == stage.st_dev and child.st_uid == 0 and child.st_mode & 0o022 == 0,
                    'CHILD_DIRECTORY')
            if directory == str(ROOT):
                dirs[:] = [name for name in dirs if name == 'site']
                files = [name for name in files if name == ARCHIVE]
            for name in files:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dfd)
                try:
                    item = os.fstat(fd)
                    require(stat.S_ISREG(item.st_mode) and item.st_uid == 0 and item.st_nlink == 1
                            and item.st_mode & 0o222 == 0 and item.st_dev == stage.st_dev, 'CHILD_FILE')
                    rows += 1
                    total += item.st_size
                    require(rows <= MAX_FILES and total <= MAX_BYTES, 'BUDGET')
                    os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
                finally:
                    os.close(fd)
        after = current()
        return {'files_advised': rows, 'bytes_advised': total, 'cgroup_current_before': before,
                'cgroup_current_after': after, 'cgroup_observed_delta': before - after,
                'cgroup_headroom_after': int((CGROUP / 'memory.max').read_text()) - after}
