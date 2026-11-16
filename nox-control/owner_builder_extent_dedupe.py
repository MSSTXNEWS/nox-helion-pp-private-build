#!/usr/bin/env python3
"""Compare-and-share only two exact historical builder files, if supported.

No file is deleted, replaced, linked, chmodded, truncated, or rewritten. The
only target-file mutation is kernel FIDEDUPERANGE, in 1 MiB aligned ranges.
Each range is atomically compared by the filesystem, including concurrent
writes; subsequent writes use CoW. This does not prove a decrease in disk use.

OverlayFS is deliberately rejected BEFORE opening a destination for writing:
that open alone can cause copy_up. Only direct XFS/Btrfs descriptors qualify.
Sources: man7.org/linux/man-pages/man2/ioctl_fideduperange.2.html and
docs.kernel.org/filesystems/overlayfs.html#non-directories.
"""
from __future__ import annotations

import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import stat
import struct
import time

ROOT = Path('/root/nox')
STATE = ROOT / 'state'
SCHEMA = 'NOX_OWNER_BUILDER_EXTENT_DEDUPE_V1'
SIZE = 306787336
SHA = '3030a2623b279ec0586bbdf403cf7ee13a32bd0fe2bf5094538d59b7c854ddb9'
FILES = (
    ('BUILDER_ARCHIVE', ROOT / 'progress_pull_t784u/workspace-2-2/nox_jp_backup_20261113/nox/state/stage3/builder/best_holdout/adapter_model.safetensors'),
    ('BUILDER_KEPT', ROOT / 'progress_pull_t784u/workspace-2-2/nox36/ckpt/builder_best_holdout_kept/adapter_model.safetensors'),
)
CHUNK = 1024 * 1024
HASH_RATE = 32 * 1024 * 1024
TOTAL_SECONDS = 80
POST_RESERVE = 30
FIDEDUPERANGE = 0xC0189436  # Linux x86_64 _IOWR(0x94, 54, 24-byte header).
REQUEST = struct.Struct('<QQHHIqQQiI')  # header24 + exactly one destination32.
SUPPORTED = {0x58465342: 'XFS', 0x9123683E: 'BTRFS'}
UNSUPPORTED_ERRNOS = {errno.EOPNOTSUPP, errno.ENOTTY}
IMMUTABLE_FIELDS = ('st_dev', 'st_ino', 'st_size', 'st_mode', 'st_uid', 'st_gid', 'st_nlink')
HASH_FIELDS = IMMUTABLE_FIELDS + ('st_mtime_ns', 'st_ctime_ns')


class Hold(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise Hold('HOLD_BUILDER_EXTENT_' + code)


def safe(exc):
    code = str(exc)
    return code if re.fullmatch('HOLD_[A-Z0-9_]+', code) else 'HOLD_BUILDER_EXTENT_' + type(exc).__name__.upper()


def identity(info, fields=IMMUTABLE_FIELDS):
    return tuple(getattr(info, field) for field in fields)


def open_regular(path, flags=os.O_RDONLY):
    """Resolve each parent through a no-follow directory descriptor."""
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'PATH')
    parent = os.open('/', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:-1]:
            next_fd = os.open(part, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                              dir_fd=parent)
            os.close(parent)
            parent = next_fd
        fd = os.open(path.name, flags | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOATIME,
                     dir_fd=parent)
    finally:
        os.close(parent)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode), 'NOT_REGULAR')
        return fd
    except BaseException:
        os.close(fd)
        raise


class StatFs(ctypes.Structure):
    _fields_ = [('type', ctypes.c_long), ('bsize', ctypes.c_long),
               ('blocks', ctypes.c_ulong), ('bfree', ctypes.c_ulong), ('bavail', ctypes.c_ulong),
               ('files', ctypes.c_ulong), ('ffree', ctypes.c_ulong), ('fsid', ctypes.c_int * 2),
               ('namelen', ctypes.c_long), ('frsize', ctypes.c_long), ('flags', ctypes.c_long),
               ('spare', ctypes.c_long * 4)]


def filesystem(fd):
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64'
            and ctypes.sizeof(StatFs) == 120 and REQUEST.size == 56, 'PLATFORM_ABI')
    lib = ctypes.CDLL(None, use_errno=True)
    lib.fstatfs.argtypes = [ctypes.c_int, ctypes.POINTER(StatFs)]
    lib.fstatfs.restype = ctypes.c_int
    value = StatFs()
    if lib.fstatfs(fd, ctypes.byref(value)):
        raise OSError(ctypes.get_errno(), 'fstatfs')
    return {'magic': value.type & 0xFFFFFFFF, 'block_size': value.bsize,
            'fsid': tuple(value.fsid), 'read_only': bool(value.flags & 1)}


def metadata(fd):
    info = os.fstat(fd)
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
            and info.st_size == SIZE and info.st_nlink == 1, 'FILE_SCOPE')
    return info


def path_matches(path, fd, baseline):
    current = metadata(fd)
    require(identity(current) == identity(baseline), 'FILE_METADATA_CHANGED')
    other = open_regular(path)
    try:
        require(identity(metadata(other)) == identity(current), 'PATH_IDENTITY_CHANGED')
    finally:
        os.close(other)
    return current


def hash_pair(fds, deadline):
    started, total, observed = time.monotonic(), 0, []
    for fd in fds:
        before = metadata(fd)
        value = hashlib.sha256()
        offset = 0
        while offset < SIZE:
            require(time.monotonic() < deadline, 'HASH_DEADLINE')
            block = os.pread(fd, min(CHUNK, SIZE - offset), offset)
            require(bool(block), 'UNEXPECTED_EOF')
            offset += len(block)
            total += len(block)
            value.update(block)
            delay = total / HASH_RATE - (time.monotonic() - started)
            if delay > 0:
                require(time.monotonic() + delay < deadline, 'HASH_DEADLINE')
                time.sleep(min(delay, .1))
        after = metadata(fd)
        require(identity(before, HASH_FIELDS) == identity(after, HASH_FIELDS), 'HASH_METADATA_CHANGED')
        require(value.hexdigest() == SHA, 'FULL_SHA_MISMATCH')
        observed.append(after)
    require(all(identity(metadata(fd), HASH_FIELDS) == identity(info, HASH_FIELDS)
                for fd, info in zip(fds, observed)), 'PAIR_CHANGED_DURING_HASH')
    return observed


def free_bytes(fd):
    value = os.fstatvfs(fd)
    return value.f_bavail * value.f_frsize


def stopped():
    paths = (ROOT / 'STOP', ROOT / 'STOP.flag', ROOT / 'stop.flag', ROOT / '.stop',
             ROOT / 'program/STOP', STATE / 'STOP', Path('/workspace/NOX_STOP'))
    return any(path.exists() or path.is_symlink() for path in paths)


def range_ioctl(source, destination, offset):
    value = bytearray(REQUEST.pack(offset, CHUNK, 1, 0, 0, destination, offset, 0, 0, 0))
    fcntl.ioctl(source, FIDEDUPERANGE, value, True)
    row = REQUEST.unpack(value)
    require(row[:5] == (offset, CHUNK, 1, 0, 0)
            and row[5:7] == (destination, offset) and row[9] == 0
            and 0 <= row[7] <= CHUNK, 'KERNEL_RESULT')
    return row[7], row[8]


def operate(result):
    """Finite range sharing; full post-hash is required for verified success."""
    deadline = time.monotonic() + TOTAL_SECONDS
    handles, write_fd = [], None
    snapshots = []
    try:
        for _, path in FILES:
            handles.append(open_regular(path))
        snapshots = [metadata(fd) for fd in handles]
        require(snapshots[0].st_dev == snapshots[1].st_dev
                and snapshots[0].st_ino != snapshots[1].st_ino, 'SEPARATE_INODES_SAME_FS')
        fs = [filesystem(fd) for fd in handles]
        result['filesystem'] = [SUPPORTED.get(row['magic'], 'UNREVIEWED_OR_UNSUPPORTED') for row in fs]
        result['filesystem_magic'] = [row['magic'] for row in fs]
        result['free_bytes_before'] = free_bytes(handles[0])
        result['file_metadata_before'] = [
            {'label': FILES[index][0], 'device': info.st_dev, 'inode': info.st_ino,
             'bytes': info.st_size, 'allocated_bytes': info.st_blocks * 512,
             'uid': info.st_uid, 'gid': info.st_gid, 'mode': stat.S_IMODE(info.st_mode),
             'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}
            for index, info in enumerate(snapshots)]
        if any(row['magic'] not in SUPPORTED for row in fs):
            result.update(state='UNSUPPORTED_FILESYSTEM_NO_WRITE_OPEN',
                          reason='DIRECT_XFS_OR_BTRFS_REQUIRED_OVERLAY_COPY_UP_AVOIDED')
            return
        require(fs[0] == fs[1] and not fs[0]['read_only'], 'FILESYSTEM_IDENTITY')
        block = fs[0]['block_size']
        require(type(block) is int and 512 <= block <= 65536 and block & (block - 1) == 0
                and CHUNK % block == 0, 'RANGE_ALIGNMENT')
        require(not stopped(), 'OWNER_STOP')
        hash_pair(handles, deadline - POST_RESERVE - 5)
        for (_, path), fd, initial in zip(FILES, handles, snapshots):
            path_matches(path, fd, initial)
        result['full_sha_before_verified'] = True
        # Reopen this already verified *descriptor*, not a newly resolved name.
        # This procfs symlink is generated from our own live FD; the target FS
        # has already been proved direct XFS/Btrfs, so no OverlayFS copy_up.
        write_fd = os.open('/proc/self/fd/' + str(handles[1]),
                           os.O_RDWR | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOATIME)
        require(identity(metadata(write_fd)) == identity(snapshots[1])
                and filesystem(write_fd) == fs[1], 'WRITE_DESCRIPTOR_IDENTITY')
        result['destination_write_opened'] = True
        mutation_error = None
        try:
            for offset in range(0, SIZE - SIZE % CHUNK, CHUNK):
                require(time.monotonic() < deadline - POST_RESERVE, 'RANGE_TIME_BUDGET')
                require(not stopped(), 'OWNER_STOP')
                require(all(identity(metadata(fd)) == identity(info)
                            for fd, info in zip(handles, snapshots)), 'FILE_METADATA_CHANGED')
                result['ranges_attempted'] += 1
                try:
                    count, status = range_ioctl(handles[0], write_fd, offset)
                except OSError as exc:
                    result['kernel_errno'] = errno.errorcode.get(exc.errno, 'UNKNOWN')
                    if exc.errno in UNSUPPORTED_ERRNOS:
                        result['range_outcome'] = 'UNSUPPORTED'
                        break
                    raise
                result['kernel_reported_range_bytes'] += count if status == 0 else 0
                if status in {-value for value in UNSUPPORTED_ERRNOS}:
                    result.update(range_outcome='UNSUPPORTED', kernel_errno=errno.errorcode[-status])
                    break
                if status == 1:
                    result['range_outcome'] = 'DATA_DIFFERS_NO_SHARE_FOR_THIS_RANGE'
                    break
                if status < 0:
                    result.update(range_outcome='KERNEL_REJECTED', kernel_errno=errno.errorcode.get(-status, 'UNKNOWN'))
                    break
                require(status == 0, 'KERNEL_STATUS')
                if count != CHUNK:
                    result['range_outcome'] = 'PARTIAL_KERNEL_RANGE'
                    break
                result['ranges_completed'] += 1
            else:
                result['range_outcome'] = 'ALL_SELECTED_RANGES_ACCEPTED'
        except Exception as exc:
            mutation_error = safe(exc)
            result['range_outcome'] = 'INTERRUPTED_OR_HELD'
        finally:
            # No rollback/unsharing attempt: that would rewrite data. Every
            # completed kernel range remains independently atomic and CoW.
            hash_pair(handles, deadline)
            for (_, path), fd, initial in zip(FILES, handles, snapshots):
                path_matches(path, fd, initial)
            result['full_sha_after_verified'] = True
            result['separate_inodes_paths_and_permissions_preserved'] = True
        if mutation_error:
            result.update(state='PARTIAL_OR_HELD_CONTENT_VERIFIED', reason=mutation_error)
        elif result['range_outcome'] == 'ALL_SELECTED_RANGES_ACCEPTED':
            result['state'] = 'SELECTED_RANGES_SHARED_CONTENT_VERIFIED'
        elif result['range_outcome'] == 'UNSUPPORTED':
            result['state'] = 'UNSUPPORTED_CONTENT_VERIFIED' if not result['kernel_reported_range_bytes'] else 'PARTIAL_UNSUPPORTED_CONTENT_VERIFIED'
        else:
            result['state'] = 'KERNEL_DECLINED_OR_PARTIAL_CONTENT_VERIFIED'
    finally:
        try:
            if handles:
                result['free_bytes_after'] = free_bytes(handles[0])
                if 'free_bytes_before' in result:
                    result['global_free_space_delta_bytes'] = result['free_bytes_after'] - result['free_bytes_before']
            if snapshots:
                result['allocated_bytes_after'] = [os.fstat(fd).st_blocks * 512 for fd in handles]
        finally:
            if write_fd is not None:
                os.close(write_fd)
            for fd in handles:
                os.close(fd)


def write_receipt(path, result):
    require(not any(parent.is_symlink() for parent in (path, *path.parents)), 'RECEIPT_PATH')
    raw = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(raw).hexdigest()


def main():
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch('[0-9]{1,24}', request) and re.fullmatch('[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    receipt = STATE / ('owner_builder_extent_' + request + '.json')
    require(not receipt.exists() and not receipt.is_symlink(), 'REQUEST_ALREADY_RECORDED')
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64', 'PLATFORM_ABI')
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'EXISTING_TIMER')
    result = {'schema': SCHEMA, 'instance_id': 60509551, 'request': request, 'source_sha': source,
              'started_at': time.time(), 'state': 'PREFLIGHT', 'file_scope': 'EXACT_TWO_BUILDER_DUPLICATES',
              'expected_file_bytes': SIZE, 'expected_full_sha256': SHA,
              'range_bytes': CHUNK, 'selected_range_count': SIZE // CHUNK,
              'unselected_tail_bytes': SIZE % CHUNK, 'ranges_attempted': 0, 'ranges_completed': 0,
              'kernel_reported_range_bytes': 0, 'destination_write_opened': False,
              'full_sha_before_verified': False, 'full_sha_after_verified': False,
              'files_deleted': 0, 'files_replaced': 0, 'hardlinks_created': 0,
              'chmod_performed': False, 'training_control_performed': False,
              'kernel_range_bytes_are_newly_freed_bytes': False,
              'global_free_delta_attributed_to_this_operation': False,
              'ram_reclaim_claimed_bytes': 0, 'private_content_exported': False}
    maintenance = open_regular(STATE / 'owner_maintenance.lock')
    previous_handler = signal.getsignal(signal.SIGALRM)
    def timeout(_signum, _frame):
        raise Hold('HOLD_BUILDER_EXTENT_WALL_TIME_BUDGET')
    try:
        fcntl.flock(maintenance, fcntl.LOCK_SH | fcntl.LOCK_NB)
        require(not (STATE / 'OWNER_MAINTENANCE.flag').exists()
                and not (STATE / 'OWNER_MAINTENANCE.flag').is_symlink(), 'MAINTENANCE_ACTIVE')
        signal.signal(signal.SIGALRM, timeout)
        signal.setitimer(signal.ITIMER_REAL, TOTAL_SECONDS)
        try:
            operate(result)
        except Exception as exc:
            result.update(state='HOLD_CONTENT_OR_OPERATION_NOT_FULLY_VERIFIED', reason=safe(exc))
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
    finally:
        os.close(maintenance)
    result['finished_at'] = time.time()
    result['receipt_path'] = str(receipt)
    result['receipt_sha256'] = write_receipt(receipt, result)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'builder_extent_dedupe', 'data': result}, sort_keys=True), flush=True)
    good = result['state'] in {'SELECTED_RANGES_SHARED_CONTENT_VERIFIED',
                              'UNSUPPORTED_FILESYSTEM_NO_WRITE_OPEN', 'UNSUPPORTED_CONTENT_VERIFIED'}
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(good).lower(), flush=True)
    return 0 if good else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'builder_extent_dedupe_hold',
              'data': {'state': 'HOLD', 'reason': safe(exc)}}), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
