#!/usr/bin/env python3
"""Only stage pinned Python source; never import, bind or run installed runtime."""
import argparse
import base64
import contextlib
import fcntl
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat

ROOT = Path('/root/nox')
BUNDLE_SHA = 'BUNDLE_SHA256_VALUE'
PACKED_BUNDLE_B64 = 'BUNDLE_JSON_BASE64_VALUE'
MAX_BUNDLE_BYTES = 2 * 1024 * 1024
MAX_PACKED_BYTES = 512 * 1024
MAX_SOURCE_BYTES = 250000
EXPECTED_PATHS = frozenset([
    'runtime/nox_integrations/__init__.py', 'runtime/nox_integrations/__main__.py',
    'runtime/nox_integrations/config.py', 'runtime/nox_integrations/core.py',
    'runtime/nox_integrations/drive.py', 'runtime/nox_integrations/host.py',
    'runtime/nox_integrations/memfd.py', 'runtime/nox_integrations/providers.py',
    'runtime/nox_warm/__init__.py', 'runtime/nox_warm/__main__.py',
    'runtime/nox_warm/cache.py', 'runtime/nox_warm/controller.py',
])

class Hold(RuntimeError):
    pass

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(bundle):
    return json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')

def sources(bundle, expected_sha):
    if not isinstance(bundle, dict) or set(bundle) != {'files', 'sha256'}:
        raise Hold('HOLD_BUNDLE_SCHEMA')
    if not isinstance(bundle['files'], dict) or not isinstance(bundle['sha256'], dict):
        raise Hold('HOLD_BUNDLE_SCHEMA')
    if set(bundle['files']) != EXPECTED_PATHS or set(bundle['sha256']) != EXPECTED_PATHS:
        raise Hold('HOLD_BUNDLE_FILE_SET')
    raw_bundle = canonical(bundle)
    if len(raw_bundle) > MAX_BUNDLE_BYTES or digest(raw_bundle) != expected_sha:
        raise Hold('HOLD_BUNDLE_SHA_OR_LIMIT')
    rows = []
    for relative in sorted(EXPECTED_PATHS):
        text, pin = bundle['files'][relative], bundle['sha256'][relative]
        if not isinstance(text, str) or not isinstance(pin, str) or not re.fullmatch('[a-f0-9]{64}', pin):
            raise Hold('HOLD_SOURCE_SCHEMA')
        raw = text.encode('utf-8')
        if len(raw) > MAX_SOURCE_BYTES or digest(raw) != pin:
            raise Hold('HOLD_SOURCE_PIN')
        rows.append((relative, raw, pin))
    return rows

def unpack_bundle():
    if len(PACKED_BUNDLE_B64) > (MAX_PACKED_BYTES * 4 // 3 + 4):
        raise Hold('HOLD_PACKED_BUNDLE_LIMIT')
    try:
        packed = base64.b64decode(PACKED_BUNDLE_B64, validate=True)
        if len(packed) > MAX_PACKED_BYTES:
            raise Hold('HOLD_PACKED_BUNDLE_LIMIT')
        with gzip.GzipFile(fileobj=io.BytesIO(packed), mode='rb') as archive:
            raw = archive.read(MAX_BUNDLE_BYTES + 1)
        if len(raw) > MAX_BUNDLE_BYTES or digest(raw) != BUNDLE_SHA:
            raise Hold('HOLD_BUNDLE_SHA_OR_LIMIT')
        bundle = json.loads(raw)
    except Hold:
        raise
    except Exception:
        raise Hold('HOLD_BUNDLE_ENCODING') from None
    sources(bundle, BUNDLE_SHA)
    return bundle

def directory(path, *, create=True):
    """Adapted from the previously reviewed native release directory helper."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise Hold('HOLD_DIRECTORY_PATH')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise Hold('HOLD_REQUIRED_DIRECTORY_MISSING') from None
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.fsync(fd)
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise Hold('HOLD_DIRECTORY_OWNER_OR_MODE')
        return fd
    except BaseException:
        os.close(fd)
        raise

def owner_idle():
    parent = directory(ROOT / 'state/priority', create=False)
    try:
        fd = os.open('CHAT_ACTIVE', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022 or info.st_size > 32:
                raise Hold('HOLD_OWNER_CHAT_ACTIVE_OR_UNKNOWN')
            value = stream.read(33)
            if value.strip() != b'0':
                raise Hold('HOLD_OWNER_CHAT_ACTIVE_OR_UNKNOWN')
    finally:
        os.close(parent)

@contextlib.contextmanager
def maintenance_lease(borrowed_fd=None):
    parent = directory(ROOT / 'state', create=False)
    owned = borrowed_fd is None
    fd = None
    try:
        fd = os.open('owner_maintenance.lock', os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent) if owned else borrowed_fd
        actual = os.fstat(fd)
        expected = os.stat('owner_maintenance.lock', dir_fd=parent, follow_symlinks=False)
        if (not stat.S_ISREG(actual.st_mode) or not stat.S_ISREG(expected.st_mode)
            or actual.st_uid != os.geteuid() or actual.st_mode & 0o022
            or (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino)):
            raise Hold('HOLD_MAINTENANCE_FD_BINDING')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Hold('HOLD_MAINTENANCE_BUSY') from None
        yield
    finally:
        if owned and fd is not None:
            os.close(fd)
        os.close(parent)

def stage(bundle, expected_sha, *, destination=None, before_file=None):
    """No overwrite: O_EXCL publication and exact byte/owner readback, as before."""
    rows = sources(bundle, expected_sha)  # All input pins checked before any write.
    destination = ROOT / 'extensions' / ('drive_first_20261117_' + expected_sha[:12]) if destination is None else Path(destination)
    output = []
    for relative, raw, pin in rows:
        if before_file is not None:
            before_file()
        target = destination / relative
        parent = directory(target.parent)
        created = False
        try:
            try:
                fd = os.open(target.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            except FileExistsError:
                fd = None
            if fd is not None:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.fsync(parent)
                created = True
            fd = os.open(target.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o022 or info.st_size != len(raw)
                    or stream.read(len(raw) + 1) != raw):
                    raise Hold('HOLD_STAGE_COLLISION')
        finally:
            os.close(parent)
        output.append({'path': relative, 'bytes': len(raw), 'sha256': pin, 'created': created})
    return {'status': 'SOURCE_INSTALLED_NOT_BOUND', 'source_staging_only': True,
            'directory': str(destination), 'files': len(output), 'bytes': sum(x['bytes'] for x in output),
            'bundle_sha256': expected_sha, 'file_pins': output, 'runtime_imported': False,
            'runtime_bound': False, 'model_downloads': 0, 'model_requests': 0,
            'new_services': 0, 'workers_started': 0, 'legacy_patch_repeated': False,
            'native_chat_canary_pass': False, 'credentials_read_or_exported': False}

def run(*, maintenance_lock_fd=None):
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch('[0-9]{1,24}', request) or not re.fullmatch('[a-f0-9]{40}', source):
        raise Hold('HOLD_OWNER_REQUEST_CONTEXT')
    bundle = unpack_bundle()
    owner_idle()
    with maintenance_lease(maintenance_lock_fd):
        owner_idle()
        result = stage(bundle, BUNDLE_SHA, before_file=owner_idle)
        result.update(owner_request_id=request, owner_source_sha=source,
                      completion_scope='SOURCE_STAGING_ONLY_NOT_CHAT_ACCEPTANCE',
                      serialization='existing owner_maintenance.lock; cooperating writers only')
        return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--maintenance-lock-fd', type=int)
    args = parser.parse_args()
    complete = False
    try:
        result = run(maintenance_lock_fd=args.maintenance_lock_fd)
        complete = result.get('status') == 'SOURCE_INSTALLED_NOT_BOUND'
    except Exception as error:
        result = {'status': str(error) if isinstance(error, Hold) else 'HOLD_STAGING_FAILURE',
                  'error_type': type(error).__name__, 'source_staging_only': True,
                  'runtime_bound': False, 'native_chat_canary_pass': False,
                  'partial_destination_may_exist': True, 'raw_error_exported': False}
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'drive_first_runtime_sources', 'data': result}, ensure_ascii=False, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(complete).lower(), flush=True)
    return 0 if complete else 2

if __name__ == '__main__':
    raise SystemExit(main())
