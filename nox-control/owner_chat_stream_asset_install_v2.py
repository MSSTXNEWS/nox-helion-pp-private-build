#!/usr/bin/env python3
"""Install one exact public JS asset; never restart a service or generate text.

Shared maintenance keeps dispatcher guard ticks available. The private journal
retains both a verified backup and the displaced inode. Atomic exchanges never
discard a destination; a foreign replacement is held and preserved.
"""
from __future__ import annotations

import base64
from contextlib import ExitStack, contextmanager
import ctypes
import fcntl
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import struct
import sys
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
STATE = ROOT / 'state'
SCRIPTS = ROOT / 'scripts'
SITE = ROOT / 'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site'
AREA = STATE / 'owner_chat_stream_installs'
ASSET = 'nox-v135-resonance-owner-bridge.js'
URL = '/nox-web-v29/' + ASSET
PAGE = '/nox-web-v29/pc/resonance.html'
CANDIDATE = 'nox-v135-resonance-owner-bridge-coalesced.js'
OLD_SHA = '8781126ee4fccce89ea43c9b7852b67af627874e8a6580931ff379ced8261237'
NEW_SHA = '02d6a0fe1d67dd6d19c020d9cb7540611b1c5ed1dbefa304e483277d140ebffc'
OLD_BYTES, NEW_BYTES = 18723, 20171
SCHEMA = 'NOX_OWNER_STREAM_ASSET_INSTALL_V2'
ACCEPTED = 'COALESCED_STREAM_ASSET_SOURCE_AND_HTTP_VERIFIED_BROWSER_PENDING'
MODEL = {'pid': 7637, 'starttime': '149189867', 'pgrp': 7059}
PINS = {
    'owner_media_acceptance_entry.py': '73107aed7d1eaa72d92fe15d4f91c8c5878e560e9efcffaf4dbf583f500fbf60',
    'owner_native_repair.py': 'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0',
    CANDIDATE: NEW_SHA,
}
PROTECTED = {
    SCRIPTS / 'chat_proxy.py': 'a427aa68ed7760380880c5d1c9ddb0714bef367ee5162a20602dbe43b6722d90',
    SCRIPTS / 'owner_chat_ui.py': 'da2cea21d21d3c1129bcb6621cd5293469a085ad861924a8c5cc63981577a866',
    SCRIPTS / 'nox_v29_chat_bridge.py': '7669bf1c3158c0f30f0f4ee6302427e540618041c9a8c554320464045973dc6c',
    SITE / 'pc/resonance.html': '9a5ee14787f4fc529926576339f86e07ce6ec838fe6e34fe6b2523f102719194',
    SITE / 'owner-chat-ui.js': '00fe841ffda05ef88a0c0b606be880fd2c6e48d55a13da70510ef58aa59cfd67',
}
# Native readonly metadata6914673851. These are two specific root-owned
# directory inodes, not a general exception for writable UI directories.
DIRECTORY_PREIMAGES = {
    SITE: {'device': 39, 'inode': 3357787162, 'uid': 0, 'gid': 0, 'mode': 0o775},
    SITE / 'pc': {'device': 39, 'inode': 1168994452, 'uid': 0, 'gid': 0, 'mode': 0o775},
}
DIRECTORY_METADATA_SHA = 'b7f0187e8c0468dbbe5b9e7a03efbd5518f1869ab03b1b36a5f29be316c6a17c'
# Builder COLD installation6910606701 applied exact77199.patch_js to62ad,
# yielding00fe/17962B. Its current RAM/SSD UI text must remain installed.
COLD_UI_RECEIPT_SHA = 'a71acb02aa401300eb348d41cf1cb519ca6ea04915a7a6ab417aa44e8602a92a'


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_STREAM_ASSET_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode() + b'\n'


def safe(exc):
    value = str(exc)
    return value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,140}', value) else 'HOLD_STREAM_ASSET_' + type(exc).__name__.upper()


def identity(info):
    return dict(device=info.st_dev, inode=info.st_ino, bytes=info.st_size,
                mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns, uid=info.st_uid,
                gid=info.st_gid, mode=stat.S_IMODE(info.st_mode), nlink=info.st_nlink,
                regular=stat.S_ISREG(info.st_mode))


def moved_equal(left, right):
    # rename changes ctime, but never permits a different inode/mode/content.
    return all(left[key] == right[key] for key in left if key != 'ctime_ns')


def stopped():
    return any(os.path.lexists(ROOT / name) for name in (
        'STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP')) or os.path.lexists('/workspace/NOX_STOP')


def gate():
    require(not stopped(), 'OWNER_STOP')


def timeout_signal(signum, frame):
    raise RuntimeError('HOLD_STREAM_ASSET_DEADLINE')


def plain(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts
            and not any(item.is_symlink() for item in (*path.parents, path)), 'PATH')
    return path


def directory(path):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        require(info.st_uid == os.geteuid() and not info.st_mode & 0o022, 'DIRECTORY')
        require((info.st_dev, info.st_ino) == (path.stat().st_dev, path.stat().st_ino), 'DIRECTORY_CHANGED')
        return fd
    except BaseException:
        os.close(fd)
        raise


def named_directory(path, fd):
    other = directory(path)
    try:
        require((os.fstat(fd).st_dev, os.fstat(fd).st_ino)
                == (os.fstat(other).st_dev, os.fstat(other).st_ino), 'DIRECTORY_CHANGED')
    finally:
        os.close(other)


def permission_identity(info):
    return {'device': info.st_dev, 'inode': info.st_ino, 'uid': info.st_uid,
            'gid': info.st_gid, 'mode': stat.S_IMODE(info.st_mode)}


def fixed_directory(path):
    require(path in DIRECTORY_PREIMAGES, 'PERMISSION_PATH_SCOPE')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for name in path.parts[1:]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd); fd = child
        return fd
    except BaseException:
        os.close(fd); raise


def named_permission_directory(path, fd):
    other = fixed_directory(path)
    try:
        held, named = os.fstat(fd), os.fstat(other)
        require(stat.S_ISDIR(held.st_mode) and permission_identity(held) == permission_identity(named),
                'PERMISSION_NAMED_DIRECTORY_CHANGED')
        expected = DIRECTORY_PREIMAGES[path]
        require(all(permission_identity(held)[key] == expected[key] for key in ('device', 'inode', 'uid', 'gid')),
                'PERMISSION_DIRECTORY_IDENTITY')
        return permission_identity(held)
    finally:
        os.close(other)


def observed_directory(path):
    fd = fixed_directory(path)
    try:
        require(named_permission_directory(path, fd) == DIRECTORY_PREIMAGES[path], 'PERMISSION_PREIMAGE')
        return fd
    except BaseException:
        os.close(fd); raise


def directory_projection(directories):
    return {('SITE' if path == SITE else 'SITE_PC'): named_permission_directory(path, fd)
            for path, fd in directories.items()}


def permission_intent(journal_fd, directories):
    before = directory_projection(directories)
    require(all(value == DIRECTORY_PREIMAGES[SITE if label == 'SITE' else SITE / 'pc']
                for label, value in before.items()), 'PERMISSION_INTENT_PREIMAGE')
    return private_json(journal_fd, 'directory_permission_intent.json', {
        'schema': 'NOX_OWNER_UI_DIRECTORY_PERMISSION_INTENT_V1',
        'owner_readback_sha256': DIRECTORY_METADATA_SHA, 'before': before,
        'after_mode': 0o755, 'scope': 'TWO_EXACT_ROOT_DIRECTORY_INODES_ONLY',
        'chown_performed': False})


def protect_directory(path, fd, changes):
    gate()
    require(named_permission_directory(path, fd) == DIRECTORY_PREIMAGES[path], 'PERMISSION_PREIMAGE_CHANGED')
    # Intent is already fsynced/read back. Latch before chmod, including a
    # signal or filesystem error immediately after a successful syscall.
    changes[path] = {'attempted': True, 'restored': False}
    os.fchmod(fd, 0o755)
    changes[path]['after'] = permission_identity(os.fstat(fd))
    os.fsync(fd)
    require(named_permission_directory(path, fd) == {**DIRECTORY_PREIMAGES[path], 'mode': 0o755},
            'PERMISSION_POSTIMAGE')
    named_directory(path, fd)  # Original strict guard is now mandatory.


def permission_rollback_plan(directories, changes):
    plan = []
    for path in reversed(tuple(changes)):
        current = named_permission_directory(path, directories[path])
        before = DIRECTORY_PREIMAGES[path]
        after = {**before, 'mode': 0o755}
        require(current in (before, after), 'PERMISSION_ROLLBACK_FOREIGN_MODE')
        plan.append((path, current == after))
    return plan


def rollback_transaction(site_fd, journal_fd, prepared, latch, directories, changes, record):
    # Classify both directory identities/modes before touching either. A
    # directory's mtime/ctime can change during our own asset rename; ownership
    # here means exact named inode/uid/gid plus the mode we applied, not a claim
    # that all directory metadata or unrelated entries are immutable.
    plan = permission_rollback_plan(directories, changes)
    if latch.get('exchange_attempted'):
        named_permission_directory(SITE, site_fd)
        restore_owned(site_fd, journal_fd, prepared)
    for path, needed in plan:
        fd = directories[path]; current = named_permission_directory(path, fd)
        require(current in (DIRECTORY_PREIMAGES[path], {**DIRECTORY_PREIMAGES[path], 'mode': 0o755}),
                'PERMISSION_ROLLBACK_CHANGED')
        if current['mode'] == 0o755:
            os.fchmod(fd, DIRECTORY_PREIMAGES[path]['mode']); os.fsync(fd)
        require(named_permission_directory(path, fd) == DIRECTORY_PREIMAGES[path], 'PERMISSION_ROLLBACK_VERIFY')
        changes[path]['restored'] = True
    record['directory_permission_rollback_verified'] = True
    record['directory_permissions_hardened'] = False
    return True


def source_guards_observed(directories):
    # Before hardening only these two exact held directory FDs may be used.
    # Every source still requires its original full SHA/regular-file checks.
    values = {}
    for path, pin in PROTECTED.items():
        if path.parent in directories:
            named_permission_directory(path.parent, directories[path.parent])
            raw, _ = read_at(directories[path.parent], path.name, 1048576, expected=pin)
        else:
            raw = read(path)
        values[str(path.relative_to(ROOT))] = digest(raw)
    require(values == {str(path.relative_to(ROOT)): pin for path, pin in PROTECTED.items()}, 'PROTECTED_SOURCE')
    return values


def read_at(parent, name, maximum=262144, *, expected=None, private=False):
    require('/' not in name and name not in ('', '.', '..'), 'BASENAME')
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
    try:
        before = identity(os.fstat(fd))
        require(before['regular'] and before['uid'] == os.geteuid() and before['nlink'] == 1
                and not before['mode'] & 0o022 and 0 <= before['bytes'] <= maximum, 'FILE')
        require(not private or before['mode'] == 0o600, 'PRIVATE_MODE')
        parts = []; total = 0
        while True:
            part = os.read(fd, min(65536, maximum + 1 - total))
            if not part:
                break
            parts.append(part); total += len(part); require(total <= maximum, 'FILE_SIZE')
        raw = b''.join(parts)
        require(before == identity(os.fstat(fd)) == identity(os.stat(name, dir_fd=parent, follow_symlinks=False))
                and len(raw) == before['bytes'], 'FILE_CHANGED')
        require(expected is None or digest(raw) == expected, 'FILE_SHA')
        return raw, before
    finally:
        os.close(fd)


def read(path, maximum=1048576):
    parent = directory(Path(path).parent)
    try:
        return read_at(parent, Path(path).name, maximum)[0]
    finally:
        os.close(parent)


def create(parent, name, raw, mode=0o600):
    require('/' not in name and len(raw) <= 262144, 'PRIVATE_WRITE_SCOPE')
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode, dir_fd=parent)
    try:
        os.fchmod(fd, mode)
        view = memoryview(raw)
        while view:
            count = os.write(fd, view); require(count > 0, 'WRITE'); view = view[count:]
        os.fsync(fd); made = identity(os.fstat(fd))
    finally:
        os.close(fd)
    os.fsync(parent)
    actual, observed = read_at(parent, name, expected=digest(raw), private=(mode == 0o600))
    require(actual == raw and observed == made, 'WRITE_READBACK')
    return made


def private_json(parent, name, value):
    raw = encode(value)
    create(parent, name, raw)
    return {'sha256': digest(raw), 'bytes': len(raw)}


def exchange(left_dir, left_name, right_dir, right_name):
    # Linux RENAME_EXCHANGE preserves both entries, including an unexpected
    # concurrent destination; os.replace would discard that destination.
    libc = ctypes.CDLL(None, use_errno=True)
    operation = getattr(libc, 'renameat2', None)
    require(operation is not None, 'ATOMIC_EXCHANGE_UNAVAILABLE')
    operation.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    operation.restype = ctypes.c_int
    if operation(left_dir, os.fsencode(left_name), right_dir, os.fsencode(right_name), 2) != 0:
        raise OSError(ctypes.get_errno(), 'atomic exchange failed')


def current_asset(site_fd):
    raw, info = read_at(site_fd, ASSET)
    return {'sha256': digest(raw), **info}


def verify_pair(site_fd, journal_fd, prepared, *, installed):
    public_raw, public = read_at(site_fd, ASSET)
    saved_raw, saved = read_at(journal_fd, 'exchange.js')
    wanted_public = prepared['candidate' if installed else 'before']
    wanted_saved = prepared['before' if installed else 'candidate']
    require(moved_equal(public, wanted_public) and moved_equal(saved, wanted_saved), 'EXCHANGE_INODE_CHANGED')
    require(digest(public_raw) == (NEW_SHA if installed else OLD_SHA)
            and digest(saved_raw) == (OLD_SHA if installed else NEW_SHA), 'EXCHANGE_CONTENT_CHANGED')
    return public, saved


def checked_exchange(site_fd, journal_fd, left, right, latch):
    latch['exchange_attempted'] = True
    exchange(site_fd, ASSET, journal_fd, 'exchange.js')
    latch['exchange_returned'] = True  # before any readback/fsync can raise
    public = identity(os.stat(ASSET, dir_fd=site_fd, follow_symlinks=False))
    displaced = identity(os.stat('exchange.js', dir_fd=journal_fd, follow_symlinks=False))
    if moved_equal(public, right) and moved_equal(displaced, left):
        return
    # A replacement between our check and the kernel exchange is captured,
    # never deleted. Put it back only while our moved entry still occupies the
    # public name and both exact entries are unchanged. No foreign bytes read.
    require(moved_equal(public, right), 'EXCHANGE_FOREIGN_PUBLIC_PRESERVED')
    require(public == identity(os.stat(ASSET, dir_fd=site_fd, follow_symlinks=False))
            and displaced == identity(os.stat('exchange.js', dir_fd=journal_fd, follow_symlinks=False)),
            'EXCHANGE_FOREIGN_CHANGED')
    exchange(site_fd, ASSET, journal_fd, 'exchange.js')
    os.fsync(site_fd); os.fsync(journal_fd)
    require(moved_equal(identity(os.stat(ASSET, dir_fd=site_fd, follow_symlinks=False)), displaced)
            and moved_equal(identity(os.stat('exchange.js', dir_fd=journal_fd, follow_symlinks=False)), right),
            'EXCHANGE_FOREIGN_COMPENSATION_UNVERIFIED')
    latch['foreign_namespace_restored'] = True
    require(False, 'EXCHANGE_FOREIGN_RESTORED')


def publish(site_fd, journal_fd, prepared, latch):
    left, right = verify_pair(site_fd, journal_fd, prepared, installed=False)
    checked_exchange(site_fd, journal_fd, left, right, latch)
    os.fsync(site_fd); os.fsync(journal_fd)
    verify_pair(site_fd, journal_fd, prepared, installed=True)


def rollback(site_fd, journal_fd, prepared):
    # Unknown public bytes/inode/mode are never accepted as our postimage.
    left, right = verify_pair(site_fd, journal_fd, prepared, installed=True)
    checked_exchange(site_fd, journal_fd, left, right, {})
    os.fsync(site_fd); os.fsync(journal_fd)
    verify_pair(site_fd, journal_fd, prepared, installed=False)
    return True


def restore_owned(site_fd, journal_fd, prepared):
    # Also settles a signal arriving between the kernel return and our latch.
    try:
        verify_pair(site_fd, journal_fd, prepared, installed=False)
        return True
    except (OSError, RuntimeError):
        return rollback(site_fd, journal_fd, prepared)


def seal_result(journal_fd, record, undo=None):
    try:
        return private_json(journal_fd, 'receipt.json', record)
    except BaseException as exc:
        record.update(state='HOLD_STREAM_ASSET_RECEIPT', success=False, receipt_error=safe(exc))
        if undo is not None:
            record['rollback_requested'] = True
            try:
                record['rollback_verified'] = undo()
                record['rollback_verification_scope'] = 'EXACT_SOURCE_PAIR_AND_OWN_DIRECTORY_IDENTITY_MODE'
            except BaseException as rollback_error:
                record.update(rollback_verified=False, rollback_reason=safe(rollback_error),
                              displaced_file_retained=True, foreign_file_not_deleted=True)
        # Never overwrite a partial/foreign receipt. No sealed context is
        # emitted for it, even if the bytes of that attempted receipt exist.
        try:
            private_json(journal_fd, 'receipt_failure.json', record)
        except BaseException:
            record['failure_receipt_saved'] = False
        return None


def bundle_sources():
    values = {}
    for name, pin in PINS.items():
        encoded = BUNDLE.get(name)
        require(isinstance(encoded, str) and 0 < len(encoded) <= 500000, 'BUNDLE_BOUND')
        raw = base64.b64decode(encoded, validate=True)
        require(0 < len(raw) <= 262144 and digest(raw) == pin, 'BUNDLE_PIN')
        values[name] = raw
    require(len(values[CANDIDATE]) == NEW_BYTES, 'CANDIDATE_SIZE')
    modules = {}
    for name in PINS:
        if not name.endswith('.py'):
            continue
        item = types.ModuleType('_reviewed_stream_asset_' + name.removesuffix('.py'))
        item.__file__ = str(SCRIPTS / name)
        exec(compile(values[name], item.__file__, 'exec'), item.__dict__)
        modules[name] = item
    return values[CANDIDATE], modules['owner_media_acceptance_entry.py'], modules['owner_native_repair.py']


@contextmanager
def lease(path, shared=False, create_file=False):
    path = plain(path)
    flags = (os.O_RDWR | os.O_CREAT) if create_file else os.O_RDONLY
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and not info.st_mode & 0o022 and info.st_nlink == 1, 'LEASE')
        fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        require((info.st_dev, info.st_ino) == (path.stat().st_dev, path.stat().st_ino), 'LEASE_CHANGED')
        yield fd
    finally:
        os.close(fd)


def source_guards():
    values = {str(path.relative_to(ROOT)): digest(read(path)) for path in PROTECTED}
    require(values == {str(path.relative_to(ROOT)): pin for path, pin in PROTECTED.items()}, 'PROTECTED_SOURCE')
    return values


def identities(helper):
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    require(re.fullmatch('[a-f0-9-]{36}', boot), 'BOOT_ID')
    model = helper.process(MODEL['pid'])
    require(model and model.get('state') not in ('Z', 'X')
            and all(model.get(k) == v for k, v in MODEL.items())
            and '/root/nox/models/current.gguf' in model.get('argv', [])
            and any(x == '--port' and i + 1 < len(model['argv']) and model['argv'][i + 1] == '8081'
                    for i, x in enumerate(model['argv'])), 'MODEL_IDENTITY')
    proxy = helper.service_state('nox-proxy'); process = helper.process(proxy.get('pid')) if proxy.get('pid') else None
    require(proxy.get('state') == 'RUNNING' and process and process.get('state') not in ('Z', 'X')
            and process.get('service') == 'nox-proxy' and str(SCRIPTS / 'chat_proxy.py') in process.get('argv', []), 'PROXY_IDENTITY')
    trainer = helper.service_state('nox-train-volta-t866u')
    require(trainer.get('state') in ('RUNNING', 'EXITED', 'FATAL', 'STOPPED', 'BACKOFF', 'STARTING', 'STOPPING'), 'TRAINER_OBSERVATION')
    return {'boot_id': boot, 'model': {k: model[k] for k in ('pid', 'starttime', 'pgrp')},
            'proxy': {k: process[k] for k in ('pid', 'starttime', 'pgrp')},
            'trainer': {k: trainer.get(k) for k in ('state', 'pid')}}


def same_chat(left, right):
    return all(left[k] == right[k] for k in ('boot_id', 'model', 'proxy'))


def health(helper):
    value = helper.health()
    require(value == {'8080': 200, '8081': 200, '8082': 200}, 'HEALTH')
    return value


def local_address():
    for _, name in socket.if_nameindex():
        if name == 'lo':
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                row = fcntl.ioctl(sock.fileno(), 0x8915, struct.pack('256s', name.encode()[:15]))
            value = socket.inet_ntoa(row[20:24])
            if not ipaddress.ip_address(value).is_loopback:
                return value
        except OSError:
            pass
    require(False, 'NONLOOPBACK_UNAVAILABLE')


def http_get(host, path, cookie=None, maximum=262144):
    require(path in (URL, PAGE), 'HTTP_PATH')
    require(maximum in (NEW_BYTES + 1, 262144), 'HTTP_BOUND')
    connection = http.client.HTTPConnection(host, 8080, timeout=5)
    try:
        headers = {'Connection': 'close', 'Accept-Encoding': 'identity', 'Cache-Control': 'no-cache'}
        if cookie is not None:
            headers['Cookie'] = 'nox_chat=' + cookie
        connection.request('GET', path, headers=headers)
        response = connection.getresponse(); raw = response.read(maximum + 1)
        require(len(raw) <= maximum and response.getheader('Content-Encoding', 'identity') == 'identity', 'HTTP_SIZE_OR_ENCODING')
        return response.status, raw
    finally:
        connection.close()


def http_asset(host, client, expected):
    gate(); status, raw = http_get(host, URL, client.cookie, NEW_BYTES + 1)
    require(status == 200 and digest(raw) == expected
            and len(raw) == (OLD_BYTES if expected == OLD_SHA else NEW_BYTES), 'HTTP_ASSET')
    return {'authenticated_http': status, 'sha256': digest(raw), 'bytes': len(raw), 'nonloopback_peer': True}


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch('[0-9]{1,24}', request) and re.fullmatch('[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    require(os.geteuid() == 0, 'ROOT_REQUIRED')
    candidate, auth, helper = bundle_sources()
    record = {'schema': SCHEMA, 'request': request, 'source_sha': source, 'started_at': time.time(),
        'state': 'PREPARING', 'success': False, 'target_asset': URL, 'expected_before_sha256': OLD_SHA,
        'expected_after_sha256': NEW_SHA, 'source_pins': PINS, 'content_exported': False,
        'browser_acceptance_verified': False, 'performance_change_verified': False,
        'proxy_restarted': False, 'model_restarted': False, 'training_control_performed': False,
        'flags_or_configuration_modified': False, 'rollback_requested': False, 'rollback_verified': False,
        'maintenance_mode': 'SHARED', 'original_backup_retained': False,
        'directory_permissions_hardened': False, 'directory_permission_rollback_verified': False,
        'directory_metadata_owner_readback_sha256': DIRECTORY_METADATA_SHA,
        'preserved_cold_ui_owner_receipt_sha256': COLD_UI_RECEIPT_SHA}
    client = None; journal_fd = None; prepared = None; latch = {}; outcome = None
    directories = {}; permission_changes = {}
    old_handler = signal.signal(signal.SIGALRM, timeout_signal)
    signal.setitimer(signal.ITIMER_REAL, 100)
    with ExitStack() as stack:
        try:
            gate()
            stack.enter_context(lease(STATE / 'owner_chat_stream_asset.lock', create_file=True))
            stack.enter_context(lease(STATE / 'owner_maintenance.lock', shared=True))
            for path in DIRECTORY_PREIMAGES:
                fd = observed_directory(path); stack.callback(os.close, fd); directories[path] = fd
            site_fd = directories[SITE]
            guards = source_guards_observed(directories); before = identities(helper); record['identities_before'] = before
            record['health_before'] = health(helper)
            old, old_info = read_at(site_fd, ASSET, expected=OLD_SHA)
            require(len(old) == OLD_BYTES, 'PREIMAGE_SIZE')
            record['before_asset'] = {'sha256': OLD_SHA, **old_info}
            gate(); client = auth.OwnerClient.authenticate(); host = local_address()
            anonymous, _ = http_get(host, URL); require(anonymous == 401, 'ANONYMOUS_ASSET_ACCESS')
            page_status, page = http_get(host, PAGE, client.cookie)
            require(page_status == 200 and ('src="' + URL + '"').encode() in page, 'PAGE_ASSET_REFERENCE')
            record.update(anonymous_http=anonymous, owner_page_http=page_status,
                          http_before=http_asset(host, client, OLD_SHA))
            gate()
            plain(AREA); AREA.mkdir(mode=0o700, exist_ok=True)
            area_fd = directory(AREA); stack.callback(os.close, area_fd)
            require(stat.S_IMODE(os.fstat(area_fd).st_mode) == 0o700, 'JOURNAL_MODE')
            os.mkdir(request, mode=0o700, dir_fd=area_fd); os.fsync(area_fd)
            journal_path = AREA / request; journal_fd = directory(journal_path); stack.callback(os.close, journal_fd)
            require(os.fstat(site_fd).st_dev == os.fstat(journal_fd).st_dev, 'JOURNAL_FILESYSTEM')
            create(journal_fd, 'original.js', old)
            candidate_info = create(journal_fd, 'exchange.js', candidate, old_info['mode'])
            prepared = {'schema': 'NOX_OWNER_STREAM_ASSET_PREPARED_V1', 'request': request, 'source_sha': source,
                'target_asset': URL, 'before': old_info, 'before_sha256': OLD_SHA,
                'candidate': candidate_info, 'candidate_sha256': NEW_SHA}
            record['prepared_receipt'] = private_json(journal_fd, 'prepared.json', prepared)
            record['original_backup_retained'] = True
            gate(); named_permission_directory(SITE, site_fd); named_directory(journal_path, journal_fd)
            require(source_guards_observed(directories) == guards and same_chat(before, identities(helper)), 'PREINSTALL_CHANGED')
            record['permission_intent'] = permission_intent(journal_fd, directories)
            for path, fd in directories.items():
                protect_directory(path, fd, permission_changes)
            record['directory_permissions_after'] = directory_projection(directories)
            record['directory_permissions_hardened'] = True
            private_json(journal_fd, 'permissions_applied.json', record['directory_permissions_after'])
            require(source_guards() == guards, 'PROTECTED_SOURCE_AFTER_PERMISSION')
            private_json(journal_fd, 'exchange_intent.json', {'request': request, 'source_sha': source,
                'prepared_sha256': record['prepared_receipt']['sha256'], 'at': time.time()})
            gate(); publish(site_fd, journal_fd, prepared, latch)
            record['installed_asset'] = current_asset(site_fd)
            private_json(journal_fd, 'installed.json', record['installed_asset'])
            record['http_after'] = http_asset(host, client, NEW_SHA)
            record['health_after'] = health(helper); after = identities(helper); record['identities_after'] = after
            require(same_chat(before, after) and source_guards() == guards, 'POSTINSTALL_CHANGED')
            gate(); named_directory(SITE, site_fd); named_directory(journal_path, journal_fd)
            verify_pair(site_fd, journal_fd, prepared, installed=True)
            read_at(journal_fd, 'original.js', expected=OLD_SHA, private=True)
            record.update(state=ACCEPTED, success=True, source_guards_preserved=True,
                          model_identity_preserved=True, proxy_identity_preserved=True)
        except BaseException as exc:
            signal.setitimer(signal.ITIMER_REAL, 0)
            record.update(state='HOLD_STREAM_ASSET_INSTALL', reason=safe(exc), success=False)
            if latch.get('exchange_attempted') or permission_changes:
                record['rollback_requested'] = True
                try:
                    signal.setitimer(signal.ITIMER_REAL, 20)
                    named_directory(journal_path, journal_fd)
                    record['rollback_verified'] = rollback_transaction(site_fd, journal_fd, prepared, latch,
                        directories, permission_changes, record)
                    record['rollback_verification_scope'] = 'EXACT_SOURCE_PAIR_AND_OWN_DIRECTORY_IDENTITY_MODE'
                    record['asset_after_rollback'] = current_asset(site_fd)
                except BaseException as rollback_error:
                    record.update(rollback_verified=False, rollback_reason=safe(rollback_error),
                                  displaced_file_retained=True, foreign_file_not_deleted=True)
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 0)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if client is not None:
                try:
                    client.close(); record['owner_session_closed'] = True
                except Exception:
                    record['owner_session_closed'] = False
            record['finished_at'] = time.time()
            if journal_fd is not None:
                def undo():
                    named_directory(journal_path, journal_fd)
                    return rollback_transaction(site_fd, journal_fd, prepared, latch,
                        directories, permission_changes, record)
                outcome = seal_result(journal_fd, record, undo if (latch.get('exchange_attempted') or permission_changes) else None)
            signal.signal(signal.SIGALRM, old_handler)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'chat_stream_asset_install', 'data': record},
        separators=(',', ':'), allow_nan=False), flush=True)
    if outcome is not None:
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'chat_stream_asset_context', 'data': {
            'request': request, 'source_sha': source, 'receipt_sha256': outcome['sha256'], 'receipt_bytes': outcome['bytes']}},
            separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0 if record['success'] and outcome is not None else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'chat_stream_asset_failure',
            'data': {'state': 'HOLD', 'reason': safe(exc), 'success': False}}, separators=(',', ':')), flush=True)
        raise SystemExit(2)
