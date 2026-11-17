"""One exact source-file repair through the existing owner maintenance lease.

Only the launcher source, a private backup/receipt directory, and one temporary
source stage may change. No application imports, subprocesses, network, model,
services, queue, TRAIN_HOLD, or application counter are accessed. A partial
attempt is retained for reconciliation; the entry never retries or rolls back
an uncertain effect automatically. rollback_owned() is an explicit continuation
for the same retained transaction, after read-only reconciliation.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time


ROOT = Path('/root/nox')
OWNER_UID = 0
LOCK_PIN = {'dev': 36, 'ino': 59886214}
BEFORE = {
    'dev': 36, 'ino': 1152408707, 'uid': 0, 'gid': 0, 'mode': 0o775,
    'bytes': 3577, 'mtime_ns': 1794895746508029718,
    'sha256': '533ac6e89e3514cef30af6678e7dba50e5465bb07f1bff8f530b38486f38906b',
}
AFTER = {'bytes': 3719, 'sha256': '0979b33716d19f9c209acdbc6ba7025c635725319ab3fe6cfb2b0d6677737522'}
TARGET = 'post8098_chain_exec09.sh'
ATTEMPT = 'owner_post8098_headroom_patch'
MAX_FILE = 16384
MAX_SECONDS = 20.0
OLD = b'''CG=$(python3 /root/nox/scripts/cgroup_headroom_gib.py)
[ "$CG" -lt 40 ] && { st TRAIN_SKIP_RAM "cgroup headroom (memory.max-anon-shmem)=${CG}GiB < 40GiB: trainer stages 19.3G Qwen base as shmem; would starve 8098 page cache / risk cgroup OOM; not starting"; exit 3; }
'''
NEW = b'''CG=$(python3 /root/nox/scripts/cgroup_headroom_gib.py) || { st TRAIN_SKIP_RAM "cgroup headroom read failed; training remains on hold"; exit 3; }
[[ "$CG" =~ ^-?[0-9]+$ ]] && [ "$CG" -ge 40 ] 2>/dev/null || { st TRAIN_SKIP_RAM "cgroup headroom (memory.max-anon-shmem)=${CG}GiB invalid or < 40GiB: trainer stages 19.3G Qwen base as shmem; would starve 8098 page cache / risk cgroup OOM; not starting"; exit 3; }
'''


class Hold(Exception):
    pass


def require(value, code):
    if not value:
        raise Hold(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def fingerprint(info):
    return tuple(getattr(info, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid',
        'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def directory_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


def metadata(info):
    return {'dev': info.st_dev, 'ino': info.st_ino, 'uid': info.st_uid, 'gid': info.st_gid,
            'mode': stat.S_IMODE(info.st_mode), 'bytes': info.st_size, 'mtime_ns': info.st_mtime_ns}


class Transaction:
    def __init__(self, request, source):
        require(isinstance(request, str) and re.fullmatch(r'[0-9]{1,24}', request)
                and isinstance(source, str) and re.fullmatch(r'[a-f0-9]{40}', source),
                'HOLD_HEADROOM_OWNER_CONTEXT')
        require(os.geteuid() == OWNER_UID, 'HOLD_HEADROOM_OWNER_UID')
        self.request, self.source = request, source
        self.deadline = time.monotonic() + MAX_SECONDS
        self.fds, self.edges = [], []
        self.state_fd = self.scripts_fd = self.lock_fd = self.attempt_fd = None
        self.before_raw = self.before_info = self.after_raw = self.stage_info = None
        self.installed_identity = None
        self.stage_name = '.post8098_headroom.' + request + '.' + source[:12] + '.stage'
        self.phase = 'NEW'
        self.attempt_created = self.replace_attempted = self.replace_returned = False
        self.accepted = self.rollback_attempted = self.prior_attempt_detected = False

    def check(self):
        require(time.monotonic() <= self.deadline, 'HOLD_HEADROOM_DEADLINE')

    def directory(self, path):
        require(path.is_absolute() and '..' not in path.parts, 'HOLD_HEADROOM_DIRECTORY_SCOPE')
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        parent = os.open('/', flags); self.fds.append(parent)
        for part in path.parts[1:]:
            self.check()
            child = os.open(part, flags, dir_fd=parent); self.fds.append(child)
            info = os.fstat(child)
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == OWNER_UID,
                    'HOLD_HEADROOM_DIRECTORY_OWNER')
            self.edges.append((parent, part, child, directory_identity(info)))
            parent = child
        return parent

    def guard(self):
        self.check()
        for parent, name, child, expected in self.edges:
            require(directory_identity(os.fstat(child)) == expected
                    == directory_identity(os.stat(name, dir_fd=parent, follow_symlinks=False)),
                    'HOLD_HEADROOM_DIRECTORY_DRIFT')
        require(self.lock_fd is not None, 'HOLD_HEADROOM_LEASE_MISSING')
        opened = os.fstat(self.lock_fd)
        named = os.stat('owner_maintenance.lock', dir_fd=self.state_fd, follow_symlinks=False)
        require(stat.S_ISREG(opened.st_mode) and opened.st_uid == OWNER_UID
                and opened.st_nlink == 1 and not opened.st_mode & 0o022
                and directory_identity(opened) == directory_identity(named)
                and {'dev': opened.st_dev, 'ino': opened.st_ino} == LOCK_PIN,
                'HOLD_HEADROOM_LEASE_PIN')
        fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def acquire(self):
        self.state_fd = self.directory(ROOT / 'state')
        self.scripts_fd = self.directory(ROOT / 'scripts')
        self.lock_fd = os.open('owner_maintenance.lock', os.O_RDONLY | os.O_NOFOLLOW
                              | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=self.state_fd)
        self.fds.append(self.lock_fd)
        self.guard()

    def read(self, parent, name):
        require('/' not in name and name not in ('', '.', '..'), 'HOLD_HEADROOM_FILE_SCOPE')
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid == OWNER_UID
                    and before.st_nlink == 1 and 0 < before.st_size <= MAX_FILE,
                    'HOLD_HEADROOM_FILE_TYPE_OWNER_BOUND')
            raw = os.pread(fd, MAX_FILE + 1, 0)
            require(len(raw) == before.st_size and fingerprint(before) == fingerprint(os.fstat(fd))
                    == fingerprint(os.stat(name, dir_fd=parent, follow_symlinks=False)),
                    'HOLD_HEADROOM_FILE_DRIFT')
            self.check()
            return raw, before
        finally:
            os.close(fd)

    def write_new(self, parent, name, raw, mode, *, uid=None, gid=None):
        self.guard()
        uid = OWNER_UID if uid is None else uid
        gid = BEFORE['gid'] if gid is None else gid
        require('/' not in name and name not in ('', '.', '..') and 0 < len(raw) <= MAX_FILE,
                'HOLD_HEADROOM_WRITE_SCOPE')
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=parent)
        try:
            view = memoryview(raw)
            while view:
                self.check()
                count = os.write(fd, view)
                require(count > 0, 'HOLD_HEADROOM_SHORT_WRITE'); view = view[count:]
            os.fchown(fd, uid, gid)
            os.fchmod(fd, mode)
            os.fsync(fd)
        finally:
            os.close(fd)
        actual, info = self.read(parent, name)
        require(actual == raw and info.st_uid == uid and info.st_gid == gid
                and stat.S_IMODE(info.st_mode) == mode, 'HOLD_HEADROOM_WRITE_READBACK')
        os.fsync(parent)
        return info

    def record(self, name, fields):
        value = {'schema': 'NOX_POST8098_SOURCE_REPAIR_V1', 'request': self.request,
                 'source_commit': self.source, 'before': BEFORE, 'after': AFTER,
                 'active_launcher_changed': False, **fields}
        return self.write_new(self.attempt_fd, name, encoded(value), 0o600)

    def exact_before(self):
        raw, info = self.read(self.scripts_fd, TARGET)
        require(raw == self.before_raw and fingerprint(info) == fingerprint(self.before_info),
                'HOLD_HEADROOM_TARGET_CAS_DRIFT')
        return info

    def backup(self):
        raw, info = self.read(self.attempt_fd, 'original.sh')
        require(raw == self.before_raw and digest(raw) == BEFORE['sha256']
                and stat.S_IMODE(info.st_mode) == 0o600, 'HOLD_HEADROOM_BACKUP_DRIFT')
        return raw

    def owned_postimage(self):
        raw, info = self.read(self.scripts_fd, TARGET)
        require(self.stage_info is not None and (info.st_dev, info.st_ino)
                == (self.stage_info.st_dev, self.stage_info.st_ino)
                and raw == self.after_raw and digest(raw) == AFTER['sha256']
                and len(raw) == AFTER['bytes']
                and (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode))
                == (BEFORE['uid'], BEFORE['gid'], BEFORE['mode']),
                'HOLD_HEADROOM_OWNED_POSTIMAGE_CAS')
        return info

    def install(self):
        require(self.phase == 'NEW', 'HOLD_HEADROOM_REENTRY')
        self.acquire()
        # Retained directory is a durable attempt marker, not a second lock.
        # Any prior attempt requires read-only reconciliation before another run.
        try:
            os.stat(ATTEMPT, dir_fd=self.state_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            self.prior_attempt_detected = True
            raise Hold('HOLD_HEADROOM_PRIOR_ATTEMPT_RECONCILE')
        raw, info = self.read(self.scripts_fd, TARGET)
        require(metadata(info) == {key: value for key, value in BEFORE.items() if key != 'sha256'}
                and digest(raw) == BEFORE['sha256'], 'HOLD_HEADROOM_EXACT_NATIVE_PREIMAGE')
        require(raw.count(OLD) == 1, 'HOLD_HEADROOM_EDIT_ANCHOR')
        after = raw.replace(OLD, NEW, 1)
        require(len(after) == AFTER['bytes'] and digest(after) == AFTER['sha256'],
                'HOLD_HEADROOM_POSTIMAGE_PIN')
        self.before_raw, self.before_info, self.after_raw = raw, info, after
        self.guard(); self.exact_before()
        os.mkdir(ATTEMPT, 0o700, dir_fd=self.state_fd)
        self.attempt_created = True
        self.attempt_fd = os.open(ATTEMPT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                  dir_fd=self.state_fd)
        self.fds.append(self.attempt_fd)
        info = os.fstat(self.attempt_fd)
        require(info.st_uid == OWNER_UID and stat.S_IMODE(info.st_mode) == 0o700,
                'HOLD_HEADROOM_PRIVATE_ATTEMPT')
        self.edges.append((self.state_fd, ATTEMPT, self.attempt_fd, directory_identity(info)))
        os.fsync(self.state_fd)
        self.record('00_intent.json', {'phase': 'PREPARE', 'stage_name': self.stage_name})
        self.write_new(self.attempt_fd, 'original.sh', raw, 0o600)
        self.backup()
        self.stage_info = self.write_new(self.scripts_fd, self.stage_name, after, BEFORE['mode'],
                                         uid=BEFORE['uid'], gid=BEFORE['gid'])
        self.record('10_staged.json', {'phase': 'STAGED', 'stage_identity': metadata(self.stage_info)})
        self.phase = 'STAGED'
        self.guard(); self.backup(); self.exact_before()
        self.record('20_replace_intent.json', {'phase': 'REPLACE_INTENT',
                    'stage_identity': metadata(self.stage_info)})
        self.guard(); self.exact_before()
        staged, staged_info = self.read(self.scripts_fd, self.stage_name)
        require(staged == after and fingerprint(staged_info) == fingerprint(self.stage_info),
                'HOLD_HEADROOM_STAGE_CAS_DRIFT')
        self.replace_attempted = True; self.phase = 'REPLACE_OUTCOME_PENDING'
        os.replace(self.stage_name, TARGET, src_dir_fd=self.scripts_fd, dst_dir_fd=self.scripts_fd)
        self.replace_returned = True
        os.fsync(self.scripts_fd)
        self.guard(); actual = self.owned_postimage(); self.backup()
        self.record('30_installed.json', {'phase': 'SOURCE_FILE_INSTALLED',
                    'installed_identity': metadata(actual), 'backup_verified': True})
        self.guard(); self.installed_identity = metadata(self.owned_postimage())
        self.accepted = True; self.phase = 'SOURCE_FILE_INSTALLED'
        return self.snapshot()

    def reconcile(self):
        """Read-only classification; never clears an attempt or initiates retry."""
        self.guard()
        raw, info = self.read(self.scripts_fd, TARGET)
        if self.before_info is not None and raw == self.before_raw and fingerprint(info) == fingerprint(self.before_info):
            state = 'EXACT_ORIGINAL_PREIMAGE'
        elif self.stage_info is not None and raw == self.after_raw and (info.st_dev, info.st_ino) == (self.stage_info.st_dev, self.stage_info.st_ino):
            state = 'OWNED_POSTIMAGE_PRESENT_UNACCEPTED' if not self.accepted else 'OWNED_POSTIMAGE_ACCEPTED'
        else:
            state = 'FOREIGN_OR_UNKNOWN_CURRENT_FILE'
        return {'state': state, 'sha256': digest(raw), 'bytes': len(raw), 'identity': metadata(info)}

    def rollback_owned(self):
        """Explicit same-transaction continuation, never called by entry()."""
        require(self.replace_attempted and not self.accepted and not self.rollback_attempted,
                'HOLD_HEADROOM_ROLLBACK_PHASE')
        self.guard(); self.owned_postimage(); original = self.backup()
        self.record('40_rollback_intent.json', {'phase': 'EXPLICIT_UNACCEPTED_ROLLBACK'})
        restored = self.write_new(self.scripts_fd, self.stage_name + '.restore', original,
                                 BEFORE['mode'], uid=BEFORE['uid'], gid=BEFORE['gid'])
        self.guard(); self.owned_postimage(); self.backup()
        staged, info = self.read(self.scripts_fd, self.stage_name + '.restore')
        require(staged == original and fingerprint(info) == fingerprint(restored),
                'HOLD_HEADROOM_ROLLBACK_STAGE_CAS')
        self.rollback_attempted = True; self.phase = 'ROLLBACK_OUTCOME_PENDING'
        os.replace(self.stage_name + '.restore', TARGET, src_dir_fd=self.scripts_fd, dst_dir_fd=self.scripts_fd)
        os.fsync(self.scripts_fd)
        actual, info = self.read(self.scripts_fd, TARGET)
        require(actual == original and (info.st_dev, info.st_ino) == (restored.st_dev, restored.st_ino)
                and (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode))
                == (BEFORE['uid'], BEFORE['gid'], BEFORE['mode']), 'HOLD_HEADROOM_ROLLBACK_READBACK')
        self.record('50_rolled_back.json', {'phase': 'SOURCE_RESTORED_UNACCEPTED',
                    'restored_identity': metadata(info), 'new_attempt_requires_fresh_native_pin': True})
        self.phase = 'SOURCE_RESTORED_UNACCEPTED'
        return self.snapshot()

    def snapshot(self):
        return {'schema': 'NOX_POST8098_SOURCE_REPAIR_V1', 'status': self.phase,
                'request': self.request, 'source_commit': self.source,
                'before_sha256': BEFORE['sha256'], 'after_sha256': AFTER['sha256'],
                'source_file_installed': True if self.accepted else None if self.replace_attempted or self.prior_attempt_detected else False,
                'installation_accepted': self.accepted, 'active_launcher_changed': False,
                'installed_identity': dict(self.installed_identity) if self.accepted else None,
                'attempt_created': self.attempt_created, 'replace_attempted': self.replace_attempted,
                'replace_returned': self.replace_returned, 'rollback_attempted': self.rollback_attempted,
                'reconcile_required': self.prior_attempt_detected or self.attempt_created and not self.accepted,
                'services_changed': 0, 'training_hold_changed': 0, 'queue_changed': 0,
                'counter_changed': 0, 'network_calls': 0, 'model_calls': 0,
                'automatic_retry': False, 'automatic_rollback': False}

    def close(self):
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds.clear()


def entry():
    transaction = None
    try:
        transaction = Transaction(os.environ.get('NOX_OWNER_REQUEST_ID', ''),
                                  os.environ.get('NOX_OWNER_SOURCE_SHA', ''))
        return transaction.install()
    except BaseException as exc:
        text = str(exc)
        code = text if isinstance(exc, Hold) and re.fullmatch(r'HOLD_[A-Z0-9_]{1,100}', text) else 'HOLD_HEADROOM_NATIVE_OPERATION'
        result = transaction.snapshot() if transaction is not None else {'schema': 'NOX_POST8098_SOURCE_REPAIR_V1'}
        result.update(status=code, installation_accepted=False)
        if transaction is not None and transaction.lock_fd is not None:
            try:
                result['read_only_reconciliation'] = transaction.reconcile()
            except BaseException:
                result['read_only_reconciliation'] = {'state': 'UNKNOWN_RECONCILE_BEFORE_ANY_RETRY'}
        return result
    finally:
        if transaction is not None:
            transaction.close()


def main():
    report = entry()
    raw = encoded({'kind': 'post8098_source_repair', 'data': report})
    require(len(raw) < 10000, 'HOLD_HEADROOM_OUTPUT_BOUND')
    complete = report.get('status') == 'SOURCE_FILE_INSTALLED' and report.get('source_file_installed') is True
    print('NOX_MAINT_REPAIR=' + raw.decode().strip(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(complete).lower(), flush=True)
    return 0 if complete else 2


if __name__ == '__main__':
    raise SystemExit(main())
