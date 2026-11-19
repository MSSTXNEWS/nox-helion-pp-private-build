#!/usr/bin/env python3
"""Read exact UI directory/file metadata and bounded hashes; modify nothing."""
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import time

ROOT = Path('/root/nox')
SITE = ROOT / 'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site'
TARGETS = (
    ('SITE_PC', SITE / 'pc'),
    ('SITE_PC_V24', SITE / 'pc/v24'),
    ('V24_CHAT_ASSET', SITE / 'pc/v24/nox-v24-chat.js'),
)
SCHEMA = 'NOX_CHAT_MARKDOWN_FIXED_METADATA_V1'
MAX_FILE = 1024 ** 2


class Deadline(BaseException):
    pass


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_CHAT_ASSET_METADATA_' + code)


def identity(value):
    return tuple(getattr(value, name) for name in ('st_dev', 'st_ino', 'st_uid', 'st_gid',
        'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def permission_identity(value):
    return identity(value)[:5]


def parent(path):
    require(path in {item[1] for item in TARGETS} and path.is_absolute()
            and '..' not in path.parts and len(path.parts) <= 32, 'FIXED_PATH')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for name in path.parts[1:-1]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd); fd = child
        return fd
    except BaseException:
        os.close(fd); raise


def observe(label, path):
    require((label, path) in TARGETS, 'FIXED_LABEL_PATH')
    parent_fd = check_parent = file_fd = None
    try:
        parent_fd = parent(path)
        before = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        row = {'label': label, 'state': 'METADATA_OBSERVED', 'uid': before.st_uid, 'gid': before.st_gid,
            'mode_octal': format(stat.S_IMODE(before.st_mode), '04o'), 'device': before.st_dev,
            'inode': before.st_ino, 'nlink': before.st_nlink, 'bytes': before.st_size,
            'is_directory': stat.S_ISDIR(before.st_mode), 'is_regular': stat.S_ISREG(before.st_mode),
            'is_symlink': stat.S_ISLNK(before.st_mode), 'mtime_ns': before.st_mtime_ns,
            'ctime_ns': before.st_ctime_ns, 'owner_matches_effective_uid': before.st_uid == os.geteuid(),
            'group_other_write_bits_present': bool(before.st_mode & 0o022), 'content_bytes_read': 0,
            'sha256': None, 'hash_state': 'NOT_A_BOUNDED_REGULAR_FILE'}
        if row['is_regular'] and 0 <= before.st_size <= MAX_FILE:
            file_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent_fd)
            require(identity(before) == identity(os.fstat(file_fd)), 'FILE_CHANGED_BEFORE_READ')
            digest = hashlib.sha256(); count = 0
            while count < before.st_size:
                data = os.read(file_fd, min(65536, before.st_size - count))
                require(bool(data), 'TRUNCATED_FILE'); count += len(data); digest.update(data)
            require(not os.read(file_fd, 1) and identity(before) == identity(os.fstat(file_fd)), 'FILE_CHANGED_DURING_READ')
            row.update(sha256=digest.hexdigest(), content_bytes_read=count, hash_state='FULL_STABLE_SHA256')
        # Reopen the entire known parent chain; never follow a symlink or rely
        # only on a descriptor to a directory which another actor replaced.
        check_parent = parent(path)
        named = os.stat(path.name, dir_fd=check_parent, follow_symlinks=False)
        after = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        compare = permission_identity if row['is_directory'] else identity
        require(compare(before) == compare(after) == compare(named), 'NAMED_PATH_CHANGED')
        row.update(same_identity_verified=True,
            identity_scope='DIRECTORY_PERMISSION_IDENTITY' if row['is_directory'] else 'FULL_FILE_METADATA',
            strict_parent_guard_passes=(row['is_directory'] and row['owner_matches_effective_uid']
                and not row['group_other_write_bits_present']),
            strict_file_guard_passes=(row['is_regular'] and row['owner_matches_effective_uid']
                and before.st_nlink == 1 and not row['group_other_write_bits_present']))
        return row
    except Exception as exc:
        number = exc.errno if isinstance(exc, OSError) else None
        code = errno.errorcode.get(number, 'OS_ERROR') if number is not None else type(exc).__name__.upper()
        return {'label': label, 'state': 'METADATA_UNAVAILABLE', 'error_class': code, 'errno': number,
                'same_identity_verified': False, 'sha256': None}
    finally:
        for fd in (file_fd, check_parent, parent_fd):
            if fd is not None:
                os.close(fd)


def snapshot():
    rows = [observe(label, path) for label, path in TARGETS]
    complete = len(rows) == len(TARGETS) and all(row['state'] == 'METADATA_OBSERVED' for row in rows)
    return {'schema': SCHEMA, 'state': 'FIXED_UI_METADATA_OBSERVED' if complete else 'FIXED_UI_METADATA_PARTIAL',
        'observation_complete': complete, 'effective_uid': os.geteuid(), 'rows': rows,
        'files_written': 0, 'permissions_repaired': False, 'service_actions': 0, 'training_actions': 0,
        'contents_or_private_paths_exported': False, 'maximum_regular_file_hash_bytes': MAX_FILE}


def main():
    request, source = (os.environ.get(name, '') for name in ('NOX_OWNER_REQUEST_ID', 'NOX_OWNER_SOURCE_SHA'))
    require(re.fullmatch('[0-9]{1,24}', request) and re.fullmatch('[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    def expired(_signum, _frame):
        raise Deadline()
    previous = signal.signal(signal.SIGALRM, expired); signal.alarm(20); started = time.monotonic()
    try:
        value = snapshot(); rc = 0 if value['observation_complete'] else 2
    except Deadline:
        value = {'schema': SCHEMA, 'state': 'HOLD_METADATA_DEADLINE', 'observation_complete': False,
                 'files_written': 0, 'permissions_repaired': False, 'contents_or_private_paths_exported': False}
        rc = 2
    finally:
        signal.alarm(0); signal.signal(signal.SIGALRM, previous)
    value.update(request=request, source_sha=source, elapsed_seconds=round(time.monotonic() - started, 3))
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'chat_asset_metadata', 'data': value},
        sort_keys=True, separators=(',', ':'), allow_nan=False), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(rc == 0).lower(), flush=True)
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
