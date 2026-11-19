"""Use the existing native writer fence for a private local reboot snapshot."""

import base64
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
import types


BUNDLE = __NOX_BUNDLE_JSON__
BACKUP_CODE_SHA = 'eb3ea798343bb87cc6cec9e176c7e3f3a219b172d7f02eafd149dde193928a0e'
ROOT = Path('/root/nox')
TARGET = ROOT / 'state/reboot-snapshots'
LEASE = ROOT / 'state/owner_maintenance.lock'
OPEN = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK


def need(condition, code):
    if not condition:
        raise RuntimeError('HOLD_NATIVE_REBOOT_BACKUP_' + code)


def trusted_directory(path):
    for item in (path, *path.parents):
        info = item.lstat()
        need(stat.S_ISDIR(info.st_mode) and info.st_uid == info.st_gid == 0
             and not info.st_mode & 0o022, 'PATH_SCOPE')


def flags_clear():
    stops = ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP',
             'state/STOP', 'state/STOP.flag', 'state/OWNER_MAINTENANCE.flag')
    return not any(os.path.lexists(ROOT / name) for name in stops) and not os.path.lexists('/workspace/NOX_STOP')


def helper():
    name = 'owner_s03_queue_backup'
    need(set(BUNDLE) == {name + '.py'}, 'SOURCE_SCOPE')
    data = base64.b64decode(BUNDLE[name + '.py'], validate=True)
    need(0 < len(data) < 65536 and hashlib.sha256(data).hexdigest() == BACKUP_CODE_SHA, 'SOURCE_SHA')
    module = types.ModuleType(name)
    sys.modules[name] = module
    exec(compile(data, name + '.py', 'exec'), module.__dict__)
    return module


def durable(directory, size):
    fields = Path(f'/proc/self/fdinfo/{directory}').read_text().splitlines()
    ids = [line.split(':', 1)[1].strip() for line in fields if line.startswith('mnt_id:')]
    if len(ids) != 1:
        return False
    for row in Path('/proc/self/mountinfo').read_text().splitlines():
        le, _, ri = row.partition(' - ')
        if le.split()[0] == ids[0]:
            usage = os.fstatvfs(directory)
            return (ri.split()[0] in ('overlay', 'ext4', 'xfs', 'btrfs', 'zfs')
                    and usage.f_bavail * usage.f_frsize >= size)
    return False


def run_openssl(*args, output=False):
    result = subprocess.run(['/usr/bin/openssl', *map(os.fspath, args)],
                            env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}, timeout=7,
                            stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            stdout=subprocess.PIPE if output else subprocess.DEVNULL,
                            check=False)
    need(result.returncode == 0, 'ATTESTATION_SIGNATURE')
    return result.stdout


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    need(os.geteuid() == os.getegid() == 0 and re.fullmatch('[1-9][0-9]{0,19}', request)
         and re.fullmatch('[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    backup = helper()
    trusted_directory(TARGET.parent)
    trusted_directory(LEASE.parent)
    with os.fdopen(os.open(LEASE, OPEN), 'rb') as lease:
        initial = os.fstat(lease.fileno())
        need(stat.S_ISREG(initial.st_mode) and initial.st_uid == initial.st_gid == 0
             and initial.st_nlink == 1 and not initial.st_mode & 0o077, 'LEASE_SCOPE')

        def checkpoint():
            current = LEASE.lstat()
            return (flags_clear() and (current.st_dev, current.st_ino) == (initial.st_dev, initial.st_ino)
                    and (current.st_mode, current.st_uid, current.st_gid, current.st_nlink)
                    == (initial.st_mode, initial.st_uid, initial.st_gid, initial.st_nlink))

        deadline = time.monotonic() + 25
        while True:
            need(checkpoint(), 'OWNER_STOP_OR_LEASE_CHANGED')
            try:
                fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('HOLD_NATIVE_REBOOT_BACKUP_OWNER_BUSY') from None
                time.sleep(0.25)

        TARGET.mkdir(mode=0o700, exist_ok=True)
        trusted_directory(TARGET)
        need(stat.S_IMODE(TARGET.lstat().st_mode) == 0o700, 'TARGET_PRIVATE')
        backup.fsync_dir(TARGET.parent)

        @contextmanager
        def already_locked():
            yield checkpoint

        database = (ROOT / backup.DATABASE).lstat()
        queue = backup.hash_file(ROOT / backup.QUEUE, backup.MAX_QUEUE, checkpoint)['sha256']
        journal = backup.hash_file(ROOT / backup.JOURNAL, backup.MAX_JOURNAL, checkpoint)['sha256']
        with tempfile.TemporaryDirectory(prefix='.backup-attest-', dir=TARGET) as path:
            key, public, digest_file, signature_file = (Path(path) / f for f in ('key.pem', 'public.pem', 'sha', 'sig'))
            run_openssl('genpkey', '-algorithm', 'ED25519', '-out', key)
            run_openssl('pkey', '-in', key, '-pubout', '-out', public)

            def sign(digest):
                digest_file.write_bytes(bytes.fromhex(digest))
                return run_openssl('pkeyutl', '-sign', '-rawin', '-inkey', key, '-in', digest_file,
                                   output=True).hex()

            def verify(digest, signature):
                digest_file.write_bytes(bytes.fromhex(digest))
                signature_file.write_bytes(bytes.fromhex(signature))
                run_openssl('pkeyutl', '-verify', '-rawin', '-pubin', '-inkey', public,
                            '-in', digest_file, '-sigfile', signature_file)
                return True

            result = backup.backup(backup.BackupRequest(request, database.st_dev, database.st_ino, queue, journal),
                                   TARGET, native_lease=already_locked, assert_durable=durable,
                                   sign_digest=sign, verify_signature=verify)
            public_key = public.read_bytes()
            key_path = TARGET / ('backup-' + request) / 'verification-key.pem'
            key_fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            with os.fdopen(key_fd, 'wb') as output:
                output.write(public_key)
                output.flush()
                os.fsync(output.fileno())
            backup.fsync_dir(key_path.parent)
    result.update(native_request=request, signature_public_key_sha256=hashlib.sha256(public_key).hexdigest(),
                  off_host_copy_verified=False, checkpoint_weights_copied=False)
    print('NOX_MAINT_LOCAL_REBOOT_BACKUP=' + json.dumps(result, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        code = str(error)
        print('NOX_MAINT_LOCAL_REBOOT_BACKUP_HOLD=' + (code if re.fullmatch(r'[A-Z][A-Z0-9_]{2,80}', code)
                                                     else type(error).__name__), flush=True)
        raise SystemExit(2) from None
