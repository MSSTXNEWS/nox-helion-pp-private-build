"""Stream the exact original NOX IQ3_XXS Engram to one verified SSD file."""

import argparse
import fcntl
import hashlib
import http.client
import json
import os
import stat
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from nox_drive_prefetch import ENGRAM_PARTS, GiB, Hold, cgroup_raw_free, stopped


REVISION = '81fd6e0a6f063344001bdecc6119ac53c80c8e63'
SOURCE = 'https://huggingface.co/kerem266/DeepSeek-V4.1-Flash-Engram-IQ3_XXS/resolve/' + REVISION
TARGET = 'engram_iq3xxs.ssd.gguf'
RECEIPT = TARGET + '.receipt.json'
SIZE = sum(size for size, _ in ENGRAM_PARTS.values())
DISK_RESERVE = 2 * GiB
MEMORY_RESERVE = 256 << 20
BLOCK = 1 << 20
CACHE_WINDOW = 8 << 20
LOCAL_FILESYSTEMS = {'btrfs', 'ext4', 'xfs'}
DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
NEW = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC


def require(condition, reason):
    if not condition:
        raise Hold('HOLD_ENGRAM_SSD_' + reason)


@contextmanager
def directory(path):
    path = Path(path)
    require(path.is_absolute() and path != Path('/') and '..' not in path.parts, 'DESTINATION')
    fd = os.open('/', DIR)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, DIR, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        location = os.fstat(fd)
        require(location.st_uid == os.geteuid() and not location.st_mode & 0o022,
                'DESTINATION_OWNER')
        yield fd
    finally:
        os.close(fd)


def filesystem(fd):
    with Path(f'/proc/self/fdinfo/{fd}').open() as info:
        mounts = [row.split()[1] for row in info if row.startswith('mnt_id:')]
    require(len(mounts) == 1, 'MOUNT_ID')
    with Path('/proc/self/mountinfo').open() as table:
        for row in table:
            fields = row.split()
            if fields[0] == mounts[0]:
                marker = fields.index('-')
                return fields[marker + 1]
    raise Hold('HOLD_ENGRAM_SSD_MOUNT_ID')


def available_disk_bytes(fd):
    volume = os.fstatvfs(fd)
    return volume.f_bavail * volume.f_frsize


def check_admission():
    require(not stopped(), 'STOP')
    require(cgroup_raw_free() >= MEMORY_RESERVE, 'RAW_MEMORY_RESERVE')


def allow_url(value):
    url = urlsplit(value)
    host = url.hostname or ''
    require(url.scheme == 'https' and url.username is None and url.password is None
            and url.port in (None, 443)
            and (host == 'huggingface.co' or host.endswith(('.huggingface.co', '.hf.co'))),
            'SOURCE_ENDPOINT')


class SourceRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, url):
        allow_url(url)
        return super().redirect_request(request, fp, code, msg, headers, url)


def discard_cache(fd, start, end):
    page = os.sysconf('SC_PAGESIZE')
    end -= end % page
    if end > start:
        os.posix_fadvise(fd, start, end - start, os.POSIX_FADV_DONTNEED)
    return end


def discard_synced_cache(fd, start, end):
    os.fdatasync(fd)
    return discard_cache(fd, start, end)


def stream_parts(output, opener):
    whole = hashlib.sha256()
    cached_from = 0
    offset = 0
    for name, (size, expected) in sorted(ENGRAM_PARTS.items()):
        check_admission()
        request = urllib.request.Request(f'{SOURCE}/{name}', headers={'Accept-Encoding': 'identity'})
        part = hashlib.sha256()
        remaining = size
        with opener.open(request, timeout=30) as response:
            allow_url(response.geturl())
            length = response.headers.get('Content-Length')
            require(response.status == 200 and response.headers.get('Content-Encoding', 'identity')
                    == 'identity' and (length is None or length == str(size)), 'SOURCE_RESPONSE')
            while remaining:
                check_admission()
                data = response.read(min(BLOCK, remaining))
                require(0 < len(data) <= remaining, 'PART_LENGTH')
                if offset == 0:
                    require(data.startswith(b'GGUF'), 'FORMAT')
                require(output.write(data) == len(data), 'SHORT_WRITE')
                part.update(data)
                whole.update(data)
                offset += len(data)
                remaining -= len(data)
                if offset - cached_from >= CACHE_WINDOW:
                    cached_from = discard_synced_cache(output.fileno(), cached_from, offset)
            require(not response.read(1) and part.hexdigest() == expected, 'PART_INTEGRITY')
    require(offset == SIZE, 'TOTAL_LENGTH')
    discard_synced_cache(output.fileno(), cached_from, offset)
    return whole.hexdigest()


def identity(info):
    return info.st_dev, info.st_ino


def file_stamp(info):
    return (identity(info), info.st_mode, info.st_uid, info.st_gid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def verify(path):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOATIME
    with directory(path) as parent:
        disk_type = filesystem(parent)
        require(disk_type in LOCAL_FILESYSTEMS, 'LOCAL_DISK_FILESYSTEM')
        check_admission()
        require(hasattr(os, 'posix_fadvise'), 'CACHE_CONTROL')
        fd = os.open(TARGET, flags, dir_fd=parent)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                    and stat.S_IMODE(before.st_mode) == 0o400 and before.st_nlink == 1
                    and before.st_size == SIZE, 'VERIFY_FILE_SCOPE')
            digest = hashlib.sha256()
            offset = cached_from = 0
            for _, (size, expected) in sorted(ENGRAM_PARTS.items()):
                current = hashlib.sha256()
                remaining = size
                while remaining:
                    check_admission()
                    data = os.pread(fd, min(BLOCK, remaining), offset)
                    require(0 < len(data) <= remaining, 'VERIFY_PART_LENGTH')
                    if offset == 0:
                        require(data.startswith(b'GGUF'), 'FORMAT')
                    current.update(data)
                    digest.update(data)
                    offset += len(data)
                    remaining -= len(data)
                    if offset - cached_from >= CACHE_WINDOW:
                        cached_from = discard_cache(fd, cached_from, offset)
                require(current.hexdigest() == expected, 'VERIFY_PART_INTEGRITY')
            require(offset == SIZE and not os.pread(fd, 1, offset), 'VERIFY_TOTAL_LENGTH')
            discard_cache(fd, cached_from, offset)
            named = os.stat(TARGET, dir_fd=parent, follow_symlinks=False)
            require(file_stamp(before) == file_stamp(os.fstat(fd)) == file_stamp(named),
                    'VERIFY_FILE_CHANGED')
            with directory(path) as current_parent:
                require(identity(os.fstat(parent)) == identity(os.fstat(current_parent)),
                        'DESTINATION_CHANGED')
            check_admission()
        finally:
            os.close(fd)
    return {'state': 'SSD_READBACK_VERIFIED_NOT_LOADED', 'source_revision': REVISION,
            'sha256': digest.hexdigest(), 'size_bytes': SIZE, 'file': TARGET,
            'filesystem': disk_type, 'device': before.st_dev, 'inode': before.st_ino,
            'mtime_ns': before.st_mtime_ns, 'ctime_ns': before.st_ctime_ns,
            'verified_part_sha256': {name: sha for name, (_, sha) in ENGRAM_PARTS.items()},
            'activation_performed': False, 'disk_readback_verified': True}


def unlink_owned(fd, name, inode):
    try:
        current = os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    require(stat.S_ISREG(current.st_mode) and identity(current) == inode, 'CLEANUP_SCOPE')
    os.unlink(name, dir_fd=fd)


@contextmanager
def new_file(fd):
    name = '.nox-engram-ssd-' + uuid4().hex
    with os.fdopen(os.open(name, NEW, 0o600, dir_fd=fd), 'w+b', buffering=0) as stream:
        inode = identity(os.fstat(stream.fileno()))
        try:
            yield stream, name, inode
        finally:
            unlink_owned(fd, name, inode)


def absent(fd, name):
    try:
        os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return True
    return False


@contextmanager
def stage_lock(fd):
    name = '.nox-engram-ssd.lock'
    lock = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                   0o600, dir_fd=fd)
    try:
        info = os.fstat(lock)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and not info.st_mode & 0o077 and info.st_nlink == 1, 'LOCK_SCOPE')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise Hold('HOLD_ENGRAM_SSD_BUSY') from error
        require(identity(os.stat(name, dir_fd=fd, follow_symlinks=False)) == identity(info),
                'LOCK_CHANGED')
        yield
    finally:
        os.close(lock)


def stage(path, *, execute=False):
    with directory(path) as fd:
        disk_type = filesystem(fd)
        free = available_disk_bytes(fd)
        required = SIZE + DISK_RESERVE
        eligible = disk_type in LOCAL_FILESYSTEMS
        reason = None
        if not eligible:
            reason = 'HOLD_ENGRAM_SSD_LOCAL_DISK_FILESYSTEM'
        elif free < required:
            reason = 'HOLD_ENGRAM_SSD_DISK_SPACE'
        info = {'state': 'HOLD' if reason else 'PLAN_ONLY', 'source_revision': REVISION,
                'size_bytes': SIZE, 'required_free_bytes': required, 'available_free_bytes': free,
                'filesystem': disk_type, 'filesystem_eligible': eligible,
                'capacity_fits': free >= required, 'minimum_raw_memory_reserve_bytes': MEMORY_RESERVE,
                'activation_performed': False}
        if reason:
            info['reason'] = reason
        if not execute or reason:
            return info
        check_admission()
        with stage_lock(fd):
            require(available_disk_bytes(fd) >= required, 'DISK_SPACE')
            require(absent(fd, TARGET) and absent(fd, RECEIPT), 'ALREADY_STAGED')
            require(hasattr(os, 'posix_fadvise') and hasattr(os, 'fdatasync'), 'CACHE_CONTROL')
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), SourceRedirect())
            with new_file(fd) as (output, temporary, inode), new_file(fd) as (receipt, receipt_tmp, receipt_inode):
                digest = stream_parts(output, opener)
                st = os.fstat(output.fileno())
                require(st.st_size == SIZE and identity(st) == inode, 'FILE_POSTIMAGE')
                os.fchmod(output.fileno(), 0o400)
                os.fsync(output.fileno())
                info.update(state='VERIFIED_SSD_STAGE_NOT_LOADED', sha256=digest, file=TARGET,
                            device=st.st_dev, inode=st.st_ino, disk_readback_verified=False,
                            verified_part_sha256={name: sha for name, (_, sha) in ENGRAM_PARTS.items()})
                raw = (json.dumps(info, sort_keys=True) + '\n').encode()
                require(receipt.write(raw) == len(raw), 'SHORT_RECEIPT')
                os.fchmod(receipt.fileno(), 0o400)
                os.fsync(receipt.fileno())
                with directory(path) as named:
                    require(identity(os.fstat(named)) == identity(os.fstat(fd)), 'DESTINATION_CHANGED')
                check_admission()
                os.link(temporary, TARGET, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
                published_receipt = False
                try:
                    check_admission()
                    os.link(receipt_tmp, RECEIPT, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
                    published_receipt = True
                    os.fsync(fd)
                except BaseException:
                    if published_receipt:
                        unlink_owned(fd, RECEIPT, receipt_inode)
                    unlink_owned(fd, TARGET, inode)
                    os.fsync(fd)
                    raise
            os.fsync(fd)
            return info


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True, help='Private local disk directory')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--execute', action='store_true', help='Transfer and verify the four pinned parts')
    action.add_argument('--verify', action='store_true', help='Reread and verify the existing SSD file')
    args = parser.parse_args(argv)
    try:
        result = verify(args.destination) if args.verify else stage(args.destination, execute=args.execute)
    except Hold as error:
        result = {'state': 'HOLD', 'reason': str(error)}
    except (OSError, ValueError, http.client.HTTPException):
        result = {'state': 'HOLD', 'reason': 'HOLD_ENGRAM_SSD_IO_OR_TRANSPORT'}
    print(json.dumps(result, sort_keys=True))
    return 3 if result['state'] == 'HOLD' else 0


if __name__ == '__main__':
    raise SystemExit(main())
