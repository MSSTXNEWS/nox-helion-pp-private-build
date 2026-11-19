#!/usr/bin/env python3
"""Read metadata of the three exact builder parent directories only.

Completion means all three metadata observations completed. It never means
permissions were repaired or that a cold-storage transition was accepted.
No contents, credentials, unknown paths or raw exception text are exported.
"""
from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import re
import stat
import time

SCHEMA = 'NOX_BUILDER_PARENT_METADATA_PROBE_V1'
PARENTS = (
    ('CANONICAL_PARENT', Path('/root/nox/progress_pull_t784u/workspace-2-2/nox36/ckpt/builder_best_holdout_kept')),
    ('RAM_PARENT', Path('/dev/shm/nox_drive/3t724u')),
    ('STATE_PARENT', Path('/root/nox/state')),
)
IDENTITY_FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid')


def require(value, code):
    if not value:
        raise RuntimeError('HOLD_BUILDER_PARENT_PROBE_' + code)


def identity(info):
    return {name: getattr(info, name) for name in IDENTITY_FIELDS}


def directory(path):
    require(path in {row[1] for row in PARENTS} and path.is_absolute()
            and '..' not in path.parts and len(path.parts) <= 32, 'EXACT_PATH')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for name in path.parts[1:]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd); fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def observe(label, path):
    require((label, path) in PARENTS, 'EXACT_LABEL_PATH')
    fd = again = None
    try:
        fd = directory(path); before = os.fstat(fd)
        # A second no-follow traversal verifies the currently named path, not
        # merely an open descriptor to a detached or replaced directory.
        again = directory(path); named = os.fstat(again); after = os.fstat(fd)
        stable = identity(before) == identity(named) == identity(after)
        is_directory = stat.S_ISDIR(before.st_mode)
        owner_matches = before.st_uid == os.geteuid()
        group_other_writable = bool(before.st_mode & 0o022)
        return {'label': label, 'state': 'METADATA_OBSERVED' if stable else 'METADATA_CHANGED',
                'uid': before.st_uid, 'gid': before.st_gid,
                'mode_octal': format(stat.S_IMODE(before.st_mode), '04o'),
                'device': before.st_dev, 'inode': before.st_ino,
                'is_directory': is_directory, 'owner_matches_effective_uid': owner_matches,
                'group_other_write_bits_present': group_other_writable,
                'same_fd_and_named_path_identity_verified': stable,
                'strict_parent_guard_passes': stable and is_directory and owner_matches and not group_other_writable}
    except Exception as exc:
        number = exc.errno if isinstance(exc, OSError) else None
        code = errno.errorcode.get(number, 'OS_ERROR') if number is not None else type(exc).__name__.upper()
        return {'label': label, 'state': 'METADATA_UNAVAILABLE', 'error_class': code,
                'errno': number, 'strict_parent_guard_passes': False,
                'same_fd_and_named_path_identity_verified': False}
    finally:
        if again is not None: os.close(again)
        if fd is not None: os.close(fd)


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch(r'[0-9]{1,24}', request) and re.fullmatch(r'[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    started = time.time()
    rows = [observe(label, path) for label, path in PARENTS]
    complete = len(rows) == 3 and all(row['state'] == 'METADATA_OBSERVED' for row in rows)
    result = {'schema': SCHEMA, 'request': request, 'source_sha': source,
              'state': 'THREE_PARENT_METADATA_OBSERVED' if complete else 'PARENT_METADATA_INCOMPLETE',
              'scope': 'READ_ONLY_THREE_FIXED_PARENT_DIRECTORIES', 'started_at': started,
              'finished_at': time.time(), 'effective_uid': os.geteuid(), 'parents': rows,
              'all_strict_parent_guards_pass': complete and all(row['strict_parent_guard_passes'] for row in rows),
              'permissions_repaired': False, 'cold_transition_accepted': False,
              'file_contents_read': False, 'files_written': 0, 'chmod_calls': 0, 'service_actions': 0,
              'training_actions': 0, 'private_paths_or_content_exported': False}
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'builder_parent_probe', 'data': result},
                                          sort_keys=True, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(complete).lower(), flush=True)
    return 0 if complete else 2


if __name__ == '__main__':
    raise SystemExit(main())
