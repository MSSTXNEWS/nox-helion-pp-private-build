"""Owner one-shot V135 static asset CAS using the exact reviewed predecessor."""

import base64
from contextlib import contextmanager, ExitStack
import ctypes
import fcntl
import hashlib
import http.client
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
STATE = ROOT / 'state'
SITE = ROOT / 'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site'
AREA = STATE / 'owner_chat_stream_installs'
PROXY_SOURCE = ROOT / 'scripts/chat_proxy.py'
PROXY_SHA = '54b1932c3e408c91c3086de994eb9b85709d65066746b5ca520582829ab94d89'
AUTH = 'owner_media_acceptance_entry.py'
AUTH_SHA = '73107aed7d1eaa72d92fe15d4f91c8c5878e560e9efcffaf4dbf583f500fbf60'
ASSET = 'nox-v135-resonance-owner-bridge.js'
OLD_SHA = '3de9f87874534e603e4040f4fc10a018679820569431a7a0b230bda035552af3'
NEW_SHA = 'a1b0b0e2475c40e55586f5c14f9afccb0b88b38382876ed9690ad4bd3c9e4537'
OLD_BYTES, NEW_BYTES = 24669, 24942
URL = '/nox-web-v29/' + ASSET
PAGE = '/nox-web-v29/pc/resonance.html'
STOPS = tuple(ROOT / name for name in (
    'STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP',
    'state/STOP', 'state/STOP.flag', 'state/OWNER_MAINTENANCE.flag',
)) + (Path('/workspace/NOX_STOP'),)


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

def timeout_signal(signum, frame):
    raise RuntimeError('HOLD_STREAM_ASSET_DEADLINE')

def plain(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts
            and not any(item.is_symlink() for item in (*path.parents, path)), 'PATH')
    for parent in path.parents:
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o002
                and (not info.st_mode & 0o020 or info.st_gid == 0), 'TRUSTED_PATH_PARENT')
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


def load_bundle():
    require(isinstance(BUNDLE, dict) and set(BUNDLE) == {AUTH, ASSET}, 'BUNDLE_SCOPE')
    values = {}
    for name, pin in ((AUTH, AUTH_SHA), (ASSET, NEW_SHA)):
        value = BUNDLE[name]
        require(isinstance(value, str) and 0 < len(value) <= 131072, 'BUNDLE_BOUND')
        raw = base64.b64decode(value, validate=True)
        require(digest(raw) == pin, 'BUNDLE_PIN')
        values[name] = raw
    require(len(values[ASSET]) == NEW_BYTES, 'CANDIDATE_SIZE')
    module = types.ModuleType('nox_v135_reviewed_owner_auth')
    exec(compile(values[AUTH], AUTH, 'exec'), module.__dict__)
    return module, values[ASSET]


class ScriptReference(HTMLParser):
    def __init__(self):
        super().__init__()
        self.matches = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('src') == URL:
            self.matches += 1


def authenticated_preimage(client, old):
    anonymous, _ = http_get('127.0.0.1', URL)
    require(anonymous == 401, 'ANONYMOUS')
    status, body = http_get('127.0.0.1', PAGE, client.cookie)
    parser = ScriptReference()
    parser.feed(body.decode('utf-8', errors='strict'))
    parser.close()
    require(status == 200 and parser.matches == 1, 'PAGE_BINDING')
    status, raw = http_get('127.0.0.1', URL, client.cookie)
    require(status == 200 and raw == old and digest(raw) == OLD_SHA, 'AUTHENTICATED_PREIMAGE')
    return digest(body)


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    record = {'schema': 'NOX_OWNER_V135_STATIC_UTF8_CAS_V1', 'request': request, 'source_sha': source,
              'status': 'HOLD', 'repair_complete': False, 'asset_replaced': False,
              'proxy_restarted': False, 'model_requests': 0, 'content_exported': False}
    client = None
    latch = {}
    journal_fd = None
    old_alarm = signal.signal(signal.SIGALRM, timeout_signal)
    signal.setitimer(signal.ITIMER_REAL, 75)
    with ExitStack() as stack:
        try:
            require(os.geteuid() == 0 and re.fullmatch('[1-9][0-9]{0,19}', request)
                    and re.fullmatch('[a-f0-9]{40}', source)
                    and os.environ.get('NOX_OWNER_INSTANCE_ID') == '60509551', 'OWNER_CONTEXT')
            gate()
            stack.enter_context(lease(STATE / 'owner_maintenance.lock', shared=True))
            site_fd = directory(SITE)
            stack.callback(os.close, site_fd)
            old, old_info = read_at(site_fd, ASSET, expected=OLD_SHA)
            require(len(old) == OLD_BYTES and old_info['gid'] == os.getegid(), 'DISK_PREIMAGE')
            require(digest(read(PROXY_SOURCE, 150000)) == PROXY_SHA, 'PROXY_SOURCE')
            before = proxy_identity()
            listener = bind_listener(before)
            auth, candidate = load_bundle()
            client = auth.OwnerClient.authenticate()
            preimage_page = authenticated_preimage(client, old)
            gate()
            require(bind_listener(before) == listener, 'PROXY_LISTENER_CHANGED')
            named_directory(SITE, site_fd)
            require(read_at(site_fd, ASSET, expected=OLD_SHA) == (old, old_info), 'DISK_PREIMAGE_CHANGED')
            record.update(preimage_sha256=OLD_SHA, authenticated_disk_preimage_equal=True)
            stack.enter_context(lease(STATE / 'owner_chat_stream_asset.lock', create_file=True))
            state_fd = directory(STATE)
            stack.callback(os.close, state_fd)
            plain(AREA)
            try:
                os.mkdir(AREA.name, mode=0o700, dir_fd=state_fd)
                os.fsync(state_fd)
            except FileExistsError:
                pass
            area_fd = directory(AREA)
            stack.callback(os.close, area_fd)
            require(stat.S_IMODE(os.fstat(area_fd).st_mode) == 0o700, 'JOURNAL_MODE')
            os.mkdir(request, mode=0o700, dir_fd=area_fd)
            os.fsync(area_fd)
            journal_path = AREA / request
            journal_fd = directory(journal_path)
            stack.callback(os.close, journal_fd)
            require(os.fstat(site_fd).st_dev == os.fstat(journal_fd).st_dev, 'JOURNAL_FILESYSTEM')
            create(journal_fd, 'original.js', old)
            new_info = create(journal_fd, 'exchange.js', candidate, old_info['mode'])
            require(new_info['gid'] == old_info['gid'], 'CANDIDATE_GROUP')
            prepared = {'request': request, 'source_sha': source, 'target': URL, 'before': old_info,
                        'candidate': new_info, 'old_sha256': OLD_SHA, 'new_sha256': NEW_SHA}
            record['prepared_receipt'] = private_json(journal_fd, 'prepared.json', prepared)
            gate()
            require(bind_listener(before) == listener and digest(read(PROXY_SOURCE, 150000)) == PROXY_SHA,
                    'PROXY_CHANGED')
            named_directory(SITE, site_fd)
            named_directory(journal_path, journal_fd)
            require(authenticated_preimage(client, old) == preimage_page, 'PAGE_CHANGED')
            gate()
            publish(site_fd, journal_fd, prepared, latch)
            state, wire = http_get('127.0.0.1', URL, client.cookie)
            page_status, page = http_get('127.0.0.1', PAGE, client.cookie)
            require(state == 200 and wire == candidate and page_status == 200 and digest(page) == preimage_page,
                    'AUTHENTICATED_POSTIMAGE')
            require(bind_listener(before) == listener and digest(read(PROXY_SOURCE, 150000)) == PROXY_SHA,
                    'POSTIMAGE_PROXY_CHANGED')
            named_directory(SITE, site_fd)
            verify_pair(site_fd, journal_fd, prepared, installed=True)
            gate()
            client.close()
            client = None
            record.update(status='V135_AUTHENTICATED_STATIC_ASSET_VERIFIED', asset_replaced=True,
                          authenticated_disk_postimage_equal=True, postimage_sha256=NEW_SHA,
                          proxy_generation_unchanged=True, repair_complete=True)
            record['receipt'] = private_json(journal_fd, 'receipt.json', record)
        except BaseException as error:
            signal.setitimer(signal.ITIMER_REAL, 0)
            record.update(status='HOLD', repair_complete=False, reason=safe(error))
            if latch.get('exchange_attempted'):
                try:
                    signal.setitimer(signal.ITIMER_REAL, 15)
                    named_directory(SITE, site_fd)
                    named_directory(journal_path, journal_fd)
                    record['rollback_verified'] = restore_owned(site_fd, journal_fd, prepared)
                    record['asset_replaced'] = False
                except BaseException as rollback_error:
                    record.update(rollback_verified=False, rollback_reason=safe(rollback_error),
                                  asset_state_requires_readback=True)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if client is not None:
                try:
                    client.close()
                except Exception:
                    record['owner_session_close_verified'] = False
            signal.signal(signal.SIGALRM, old_alarm)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'v135_static_utf8_cas', 'data': record},
                                           separators=(',', ':'), allow_nan=False), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(record['repair_complete']).lower(), flush=True)
    return 0 if record['repair_complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
