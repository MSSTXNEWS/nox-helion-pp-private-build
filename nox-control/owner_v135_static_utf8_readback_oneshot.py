"""Read one exact V135 deployment transaction without authentication or writes."""

from contextlib import contextmanager, ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

ROOT = Path('/root/nox')
STATE = ROOT / 'state'
SITE = ROOT / 'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site'
PROXY_SOURCE = ROOT / 'scripts/chat_proxy.py'
PROXY_SHA = '54b1932c3e408c91c3086de994eb9b85709d65066746b5ca520582829ab94d89'
ASSET = 'nox-v135-resonance-owner-bridge.js'
URL = '/nox-web-v29/' + ASSET
OLD_SHA = '3de9f87874534e603e4040f4fc10a018679820569431a7a0b230bda035552af3'
NEW_SHA = 'a1b0b0e2475c40e55586f5c14f9afccb0b88b38382876ed9690ad4bd3c9e4537'
TARGET = '7019720718'
TARGET_SOURCE = '3a4dfb3a75757368b731b1885602d1898fbe1b0e'
JOURNAL = STATE / 'owner_chat_stream_installs' / TARGET
STOPS = tuple(ROOT / name for name in (
    'STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP',
    'state/STOP', 'state/STOP.flag', 'state/OWNER_MAINTENANCE.flag',
)) + (Path('/workspace/NOX_STOP'),)


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_STREAM_ASSET_' + code)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def safe(exc):
    value = str(exc)
    return value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,140}', value) else 'HOLD_STREAM_ASSET_' + type(exc).__name__.upper()

def identity(info):
    return dict(device=info.st_dev, inode=info.st_ino, bytes=info.st_size,
                mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns, uid=info.st_uid,
                gid=info.st_gid, mode=stat.S_IMODE(info.st_mode), nlink=info.st_nlink,
                regular=stat.S_ISREG(info.st_mode))

def plain(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts
            and not any(item.is_symlink() for item in (*path.parents, path)), 'PATH')
    for parent in path.parents:
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o002
                and (not info.st_mode & 0o020 or info.st_gid == 0), 'TRUSTED_PATH_PARENT')
    return path

def named_directory(path, fd):
    other = directory(path)
    try:
        require((os.fstat(fd).st_dev, os.fstat(fd).st_ino)
                == (os.fstat(other).st_dev, os.fstat(other).st_ino), 'DIRECTORY_CHANGED')
    finally:
        os.close(other)

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

@contextmanager
def lease(path):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022
                and info.st_nlink == 1, 'LEASE')
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        current = path.lstat()
        require((info.st_dev, info.st_ino) == (current.st_dev, current.st_ino), 'LEASE_CHANGED')
        yield
        current = path.lstat()
        require((info.st_dev, info.st_ino) == (current.st_dev, current.st_ino), 'LEASE_CHANGED')
    finally:
        os.close(fd)


def bounded(path, limit):
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'LOCAL_READ_BOUND')
    return raw

def proxy_identity():
    result = subprocess.run(('supervisorctl', 'status', 'nox-proxy'),
                            capture_output=True, text=True, timeout=5, check=False)
    match = re.fullmatch(r'nox-proxy\s+RUNNING\s+pid\s+([1-9]\d*),[^\n]*\n?', result.stdout)
    require(result.returncode == 0 and match is not None, 'PROXY_NOT_RUNNING')
    pid = int(match[1])
    proc = Path('/proc') / str(pid)
    data = bounded(proc / 'stat', 8192)
    fields = data[data.rfind(b')') + 2:].split()
    argv = bounded(proc / 'cmdline', 65536).split(b'\0')
    require(len(fields) > 19 and fields[0] not in (b'Z', b'X')
            and fields[19].isdigit() and os.fsencode(PROXY_SOURCE) in argv, 'PROXY_IDENTITY')
    return pid, int(fields[19])

def bind_listener(expected):
    require(proxy_identity() == expected, 'PROXY_LIFETIME')
    sockets = set()
    for index, fd in enumerate((Path('/proc') / str(expected[0]) / 'fd').iterdir()):
        require(index < 4096, 'PROXY_FD_BOUND')
        try:
            target = os.readlink(fd)
        except FileNotFoundError:
            continue
        match = re.fullmatch(r'socket:\[(\d+)\]', target)
        if match:
            sockets.add(match[1])
    listen = set()
    for protocol in ('tcp', 'tcp6'):
        data = bounded(Path('/proc/net') / protocol, 2 * 1024 * 1024)
        for row in data.decode('ascii').splitlines()[1:]:
            fields = row.split()
            if len(fields) >= 10 and fields[3] == '0A' and fields[1].endswith(':1F90'):
                listen.add(fields[9])
    require(listen and listen <= sockets and proxy_identity() == expected, 'LISTENER_8080')
    return tuple(sorted(listen))

def gate():
    require(not any(os.path.lexists(path) for path in STOPS), 'OWNER_STOP')

def directory(path):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        require(info.st_uid == 0 and not info.st_mode & 0o002
                and (not info.st_mode & 0o020 or info.st_gid == 0), 'DIRECTORY')
        current = path.lstat()
        require((info.st_dev, info.st_ino) == (current.st_dev, current.st_ino), 'DIRECTORY_CHANGED')
        return fd
    except BaseException:
        os.close(fd)
        raise


def optional_file(fd, name, limit):
    try:
        return read_at(fd, name, limit, private=True)[0]
    except FileNotFoundError:
        return None


def journal_observation(stack, asset_sha, asset_info):
    try:
        fd = directory(JOURNAL)
    except FileNotFoundError:
        return {'present': False, 'deployment_verified': False}
    stack.callback(os.close, fd)
    require(stat.S_IMODE(os.fstat(fd).st_mode) == 0o700, 'JOURNAL_MODE')
    prepared_raw = optional_file(fd, 'prepared.json', 8192)
    receipt_raw = optional_file(fd, 'receipt.json', 8192)
    original = optional_file(fd, 'original.js', 65536)
    try:
        exchanged, exchange_info = read_at(fd, 'exchange.js', 65536)
    except FileNotFoundError:
        exchanged, exchange_info = None, None
    result = {'present': True, 'prepared_present': prepared_raw is not None,
              'receipt_present': receipt_raw is not None, 'deployment_verified': False}
    if original is not None:
        result['original_sha256'] = digest(original)
    if exchanged is not None:
        result['exchange_sha256'] = digest(exchanged)
    if prepared_raw is not None:
        prepared = json.loads(prepared_raw)
        require(isinstance(prepared, dict) and prepared.get('request') == TARGET
                and prepared.get('source_sha') == TARGET_SOURCE and prepared.get('target') == URL
                and prepared.get('old_sha256') == OLD_SHA and prepared.get('new_sha256') == NEW_SHA,
                'PREPARED_BINDING')
        result['prepared_sha256'] = digest(prepared_raw)
    if receipt_raw is not None:
        receipt = json.loads(receipt_raw)
        require(isinstance(receipt, dict) and receipt.get('schema') == 'NOX_OWNER_V135_STATIC_UTF8_CAS_V1'
                and receipt.get('request') == TARGET and receipt.get('source_sha') == TARGET_SOURCE,
                'RECEIPT_BINDING')
        result['receipt_sha256'] = digest(receipt_raw)
        result['receipt_reports_pass'] = (receipt.get('status') == 'V135_AUTHENTICATED_STATIC_ASSET_VERIFIED'
                and receipt.get('repair_complete') is True and receipt.get('asset_replaced') is True
                and receipt.get('authenticated_disk_postimage_equal') is True
                and receipt.get('authenticated_disk_preimage_equal') is True
                and receipt.get('postimage_sha256') == NEW_SHA and receipt.get('preimage_sha256') == OLD_SHA
                and receipt.get('proxy_generation_unchanged') is True and receipt.get('proxy_restarted') is False)
        if result['receipt_reports_pass'] and prepared_raw is not None and exchange_info is not None:
            def same_inode(left, right):
                return isinstance(left, dict) and all(left.get(key) == right[key] for key in ('device','inode','uid','gid','mode','bytes'))
            prepared_pin = receipt.get('prepared_receipt')
            result['deployment_verified'] = (asset_sha == NEW_SHA and result.get('original_sha256') == OLD_SHA
                    and result.get('exchange_sha256') == OLD_SHA and isinstance(prepared_pin, dict)
                    and prepared_pin.get('sha256') == result['prepared_sha256']
                    and same_inode(prepared.get('candidate'), asset_info)
                    and same_inode(prepared.get('before'), exchange_info))
    named_directory(JOURNAL, fd)
    return result


def main():
    record = {'schema': 'NOX_OWNER_V135_STATIC_UTF8_READBACK_V1', 'target_request': TARGET,
              'target_source_sha': TARGET_SOURCE, 'status': 'HOLD', 'host_files_written': 0,
              'network_requests': 0, 'auth_attempted': False, 'content_exported': False}
    complete = False
    try:
        labels = {os.environ[name].removeprefix('C.') for name in ('VAST_CONTAINERLABEL', 'CONTAINER_ID')
                  if os.environ.get(name)}
        require(os.geteuid() == 0 and labels == {'60509551'}
                and re.fullmatch('[1-9][0-9]{0,19}', os.environ.get('NOX_OWNER_REQUEST_ID', ''))
                and re.fullmatch('[a-f0-9]{40}', os.environ.get('NOX_OWNER_SOURCE_SHA', '')), 'OWNER_CONTEXT')
        with ExitStack() as stack:
            stack.enter_context(lease(STATE / 'owner_maintenance.lock'))
            fd = directory(SITE)
            stack.callback(os.close, fd)
            raw, info = read_at(fd, ASSET, 65536)
            asset_sha = digest(raw)
            record.update(asset_sha256=asset_sha, asset_bytes=len(raw))
            record['journal'] = journal_observation(stack, asset_sha, info)
            before = proxy_identity()
            presence = bind_listener(before)
            proxy_sha = digest(read(PROXY_SOURCE, 150000))
            require(presence and bind_listener(before) == presence, 'PROXY_GENERATION_CHANGED')
            record.update(proxy_pid=before[0], proxy_start_ticks=before[1], proxy_sha256=proxy_sha,
                          proxy_matches_reviewed_source=proxy_sha == PROXY_SHA)
            named_directory(SITE, fd)
            require(read_at(fd, ASSET, 65536) == (raw, info), 'ASSET_CHANGED')
            gate()
            record['status'] = ('INSTALLED_EXACT_WITH_SEALED_RECEIPT' if record['journal']['deployment_verified']
                                else 'DISK_POSTIMAGE_RECEIPT_UNVERIFIED' if asset_sha == NEW_SHA
                                else 'DISK_PREIMAGE_PRESENT' if asset_sha == OLD_SHA
                                else 'DISK_ASSET_OUTSIDE_REVIEWED_PAIR')
            complete = True
    except Exception as error:
        record['reason'] = safe(error)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'v135_static_utf8_readback', 'data': record},
                                           separators=(',', ':'), allow_nan=False), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(complete).lower(), flush=True)
    return 0 if complete else 2


if __name__ == '__main__':
    raise SystemExit(main())
