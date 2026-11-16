#!/usr/bin/env python3
"""Restore one public, revision-pinned Hermes file into its existing RAM path.

Finite storage helper for the existing downloader. It never starts a model or
changes training flags. No token, proxy, arbitrary URL or arbitrary path input.
"""
from __future__ import annotations
import copy
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
import ssl
import stat
import time
import types
import urllib.parse
import urllib.request

ROOT = Path('/root/nox')
SHM = Path('/dev/shm')
STATE = ROOT / 'state/owner_hermes_warm'
CONFIG = ROOT / 'config/owner_hermes_warm.json'
LEASE = ROOT / 'state/owner_hermes_warm.lock'
MAINTENANCE = ROOT / 'state/owner_maintenance.lock'
NAME = 'Hermes-3-Llama-3.1-8B.Q4_K_M.gguf'
WARM = SHM / 'nox_t802u/teachers' / NAME
SSD = ROOT / 'offload_shm_t888u/teachers' / NAME
SIZE = 4920733824
SHA = 'd4403ce5a6e930f4c2509456388c20d633a15ff08dd52ef3b142ff1810ec3553'
REPO = 'NousResearch/Hermes-3-Llama-3.1-8B-GGUF'
REVISION = 'ad1d6b27c4ebc45cdb43e10871324742d771e1c4'
URL = 'https://huggingface.co/' + REPO + '/resolve/' + REVISION + '/' + NAME
SCHEMA = 'NOX_HERMES_WARM_MANIFEST_V1'
REVISION_SCHEMA = 'NOX_HERMES_WARM_EXECUTION_MANIFEST_V1'
REVISION_VERIFIER_SHA = 'd3b2905c568d088cde2d8267f02f9e913f9fe1d3e46f590992c3a7fcb138ae14'
DOWNLOADER_SHA = 'ae9027cef772f34a552712f52adb13317acae7c44052ceaed293eed65be7a59e'
REVISION_ENTRY = 'qwen_student_training_entry_revision.py'
GIB = 1024 ** 3
MIN_HEADROOM = 72 * GIB
TMPFS_RESERVE = 3 * GIB
CHUNK = 1024 ** 2
SECONDS = 1200
PROFILE_PINS = {
    'qwen_student_training_entry.py': '259ac097f3ceec5be217748667a421ab5c39ebb56b9b2817fd1368d278f99cb0',
    'owner_qwen_memfd.py': '938335009efe691a9cef7b41daa7c55f3c8d3d8618a10a5eb5db125fd45afa82',
    'qwen35_9b_manifest.json': '2275fc88370ca8ba409a791819e13c8ab7d4e38cce4576a13170b05bcb8b839b',
}
FIELDS = ('st_dev', 'st_ino', 'st_size', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_mtime_ns', 'st_ctime_ns')


class Hold(RuntimeError): pass


def require(ok, code):
    if not ok: raise Hold('HOLD_HERMES_HYDRATE_' + code)


def digest(raw): return hashlib.sha256(raw).hexdigest()
def encode(value): return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()
def identity(info): return {key: getattr(info, key) for key in FIELDS}
def safe(exc):
    code = str(exc)
    return code if re.fullmatch('HOLD_[A-Z0-9_]{1,110}', code) else 'HOLD_HERMES_HYDRATE_' + type(exc).__name__.upper()


def directory(path):
    path = Path(path); require(path.is_absolute() and '..' not in path.parts, 'PATH')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd); fd = child
        return fd
    except BaseException:
        os.close(fd); raise


def read(path, maximum=65536, *, pseudo=False):
    parent = directory(Path(path).parent)
    try:
        fd = os.open(Path(path).name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
                     | getattr(os, 'O_NOATIME', 0), dir_fd=parent)
    finally: os.close(parent)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and (pseudo or 0 <= before.st_size <= maximum), 'READ_SCOPE')
        raw = os.read(fd, maximum + 1); require(len(raw) <= maximum, 'READ_BOUND')
        if not pseudo:
            require(len(raw) == before.st_size and identity(before) == identity(os.fstat(fd))
                    == identity(Path(path).stat(follow_symlinks=False)), 'READ_CHANGED')
        return raw
    finally: os.close(fd)


def owner_stop():
    return any(path.exists() or path.is_symlink() for path in tuple(ROOT / name for name in
        ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP')) + (Path('/workspace/NOX_STOP'),))


def tick(deadline):
    require(time.monotonic() < deadline, 'DEADLINE')
    require(not owner_stop(), 'OWNER_STOP')


def headroom():
    values = [read(Path('/sys/fs/cgroup') / name, 128, pseudo=True).strip()
              for name in ('memory.current', 'memory.max')]
    require(all(value.isdigit() for value in values), 'CGROUP_UNKNOWN')
    current, maximum = map(int, values)
    require(0 <= current <= maximum, 'CGROUP_RANGE')
    return maximum - current


def allocation_gate(remaining, next_bytes=0):
    require(type(remaining) is int and 0 <= remaining <= SIZE and type(next_bytes) is int
            and 0 <= next_bytes <= CHUNK, 'ALLOCATION_SCOPE')
    available = headroom(); fs = os.statvfs(SHM); free = fs.f_bavail * fs.f_frsize
    require(available >= MIN_HEADROOM + next_bytes, 'RAM_72GIB_RESERVE')
    require(free >= TMPFS_RESERVE + remaining, 'TMPFS_3GIB_RESERVE')
    return {'cgroup_headroom_bytes': available, 'tmpfs_free_bytes': free}


def tmpfs_verified():
    raw = read(Path('/proc') / str(os.getpid()) / 'mountinfo', 262144, pseudo=True)
    rows = [line.split(b' - ', 1)[1].split()[0] for line in raw.splitlines() if b' - ' in line
            and len(line.split(b' - ', 1)[0].split()) >= 5
            and line.split(b' - ', 1)[0].split()[4] == b'/dev/shm']
    require(rows == [b'tmpfs'], 'EXPECTED_TMPFS')


def private_record(path, value):
    raw = encode(value); require(0 < len(raw) <= 65536, 'RECORD_BOUND')
    parent = directory(path.parent)
    try:
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno()); before = identity(os.fstat(stream.fileno()))
        os.fsync(parent)
        after = path.stat(follow_symlinks=False)
        require(stat.S_ISREG(after.st_mode) and after.st_uid == os.geteuid() and after.st_nlink == 1
                and stat.S_IMODE(after.st_mode) == 0o600 and identity(after) == before
                and read(path, len(raw)) == raw, 'RECORD_READBACK')
        return digest(raw)
    finally: os.close(parent)


def lease(path, operation):
    parent = directory(path.parent)
    try: fd = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    finally: os.close(parent)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1, 'LEASE_SCOPE')
        fcntl.flock(fd, operation | fcntl.LOCK_NB)
        require(identity(info) == identity(path.stat(follow_symlinks=False)), 'LEASE_CHANGED')
        return fd
    except BaseException: os.close(fd); raise


def rename(old_parent, old_name, new_parent, new_name, flags):
    require(flags in (1, 2), 'RENAME_FLAG')  # NOREPLACE or EXCHANGE, never a blind overwrite.
    fn = getattr(ctypes.CDLL(None, use_errno=True), 'renameat2', None)
    require(fn is not None, 'RENAMEAT2_UNAVAILABLE')
    fn.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    fn.restype = ctypes.c_int
    if fn(old_parent, os.fsencode(old_name), new_parent, os.fsencode(new_name), flags):
        raise OSError(ctypes.get_errno(), 'renameat2')


def full_hash(fd, deadline, expected_path=None):
    before = os.fstat(fd)
    require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid() and before.st_nlink == 1
            and before.st_size == SIZE, 'MODEL_SCOPE')
    value = hashlib.sha256(); offset = 0
    while offset < SIZE:
        tick(deadline); allocation_gate(0)
        raw = os.pread(fd, min(CHUNK, SIZE - offset), offset)
        require(raw, 'MODEL_EOF'); offset += len(raw); value.update(raw)
    require(value.hexdigest() == SHA and identity(os.fstat(fd)) == identity(before), 'MODEL_SHA_OR_CHANGE')
    if expected_path is not None:
        require(identity(expected_path.stat(follow_symlinks=False)) == identity(before), 'MODEL_NAME_CHANGED')
    return identity(before)


def revision_reference(value):
    require(isinstance(value, dict) and set(value) == {'request', 'source_sha', 'receipt_sha256'}
            and type(value['request']) is str and re.fullmatch('[0-9]{1,24}', value['request'])
            and re.fullmatch('[a-f0-9]{40}', str(value['source_sha']))
            and re.fullmatch('[a-f0-9]{64}', str(value['receipt_sha256'])), 'EXECUTION_REFERENCE')
    return dict(value)


def revision_profiles(runtime_entry_sha256):
    require(re.fullmatch('[a-f0-9]{64}', str(runtime_entry_sha256))
            and re.fullmatch('[a-f0-9]{64}', str(REVISION_VERIFIER_SHA)), 'EXECUTION_PROFILE_PINS')
    return {**PROFILE_PINS, REVISION_ENTRY: runtime_entry_sha256,
            'owner_qwen_execution_revision.py': REVISION_VERIFIER_SHA}


def make_revision_hydrate_manifest(previous, revision_ref, *, source_sha256, runtime_entry_sha256):
    """Pure transition preserving public bytes, aliases, downloader and RAM floors."""
    require(isinstance(previous, dict) and previous.get('schema') == SCHEMA
            and previous.get('public_repository') == REPO and previous.get('public_revision') == REVISION
            and previous.get('public_filename') == NAME and previous.get('bytes') == SIZE and previous.get('sha256') == SHA
            and previous.get('ram_path') == str(WARM) and previous.get('ssd_path') == str(SSD)
            and previous.get('minimum_cgroup_headroom_bytes') == MIN_HEADROOM
            and previous.get('minimum_tmpfs_reserve_bytes') == TMPFS_RESERVE
            and previous.get('profile_pins') == PROFILE_PINS
            and previous.get('download_source_sha256') == DOWNLOADER_SHA
            and re.fullmatch('[a-f0-9]{64}', str(source_sha256)), 'REVISION_MANIFEST_PREIMAGE')
    value = copy.deepcopy(previous)
    value.update(schema=REVISION_SCHEMA, hydrate_source_sha256=source_sha256,
                 execution_revision=revision_reference(revision_ref),
                 execution_verifier_sha256=REVISION_VERIFIER_SHA,
                 profile_pins=revision_profiles(runtime_entry_sha256))
    return value


def make_successor_hydrate_manifest(previous, revision_ref, *, source_sha256, runtime_entry_sha256):
    """Preserve public storage identity and rebind only explicit execution pins."""
    predecessor = {'request': '6914959637', 'source_sha': 'a06c6a039ebccd6eaa754914624ab5477beca47b',
                   'receipt_sha256': '2f16be7a0bf648621f845c898dd2cc078a98f608fa5b01b3153890c7e3dc41d9'}
    old_verifier = '0dbb06d3384b3436165056ccf4e35bff937fda4f85d96ab2a97ab16a6619998e'
    old_runtime = 'ce7dcbef53c61c63ebab96553ef4c48d9f138a3c426008fa329eb5fd66ee041c'
    keys = {'schema', 'context', 'public_repository', 'public_revision', 'public_filename', 'bytes', 'sha256',
            'ram_path', 'ssd_path', 'hydrate_source_sha256', 'download_source_sha256', 'profile_pins',
            'minimum_cgroup_headroom_bytes', 'minimum_tmpfs_reserve_bytes', 'durability', 'new_daemon',
            'execution_revision', 'execution_verifier_sha256'}
    require(isinstance(previous, dict) and set(previous) == keys and previous['schema'] == REVISION_SCHEMA
            and previous['execution_revision'] == predecessor and previous['execution_verifier_sha256'] == old_verifier
            and previous['hydrate_source_sha256'] == '65daf1acd5dd937e23b9f960dedb720b8259793729115bab153993a282e735a3'
            and previous['public_repository'] == REPO and previous['public_revision'] == REVISION
            and previous['public_filename'] == NAME and previous['bytes'] == SIZE and previous['sha256'] == SHA
            and previous['ram_path'] == str(WARM) and previous['ssd_path'] == str(SSD)
            and previous['minimum_cgroup_headroom_bytes'] == MIN_HEADROOM
            and previous['minimum_tmpfs_reserve_bytes'] == TMPFS_RESERVE
            and previous['profile_pins'] == {**PROFILE_PINS, REVISION_ENTRY: old_runtime,
                                            'owner_qwen_execution_revision.py': old_verifier}
            and previous['download_source_sha256'] == DOWNLOADER_SHA
            and previous['durability'] == 'VOLATILE_RAM_PUBLIC_REVISION_RESTORABLE'
            and previous['new_daemon'] is False, 'SUCCESSOR_MANIFEST_PREIMAGE')
    context = previous['context']
    require(isinstance(context, dict) and set(context) == {'request', 'source_sha'}
            and type(context['request']) is str and re.fullmatch('[0-9]{1,24}', context['request'])
            and re.fullmatch('[a-f0-9]{40}', str(context['source_sha'])), 'SUCCESSOR_STORAGE_CONTEXT')
    current = revision_reference(revision_ref)
    require(current['request'] != predecessor['request'] and re.fullmatch('[a-f0-9]{64}', str(source_sha256)),
            'SUCCESSOR_MANIFEST_PINS')
    value = copy.deepcopy(previous)
    value.update(hydrate_source_sha256=source_sha256, execution_revision=current,
                 execution_verifier_sha256=REVISION_VERIFIER_SHA,
                 profile_pins=revision_profiles(runtime_entry_sha256))
    return value


def revision_context(reference):
    path = ROOT / 'scripts/owner_qwen_execution_revision.py'; raw = read(path, 2 * 1024 ** 2)
    require(re.fullmatch('[a-f0-9]{64}', str(REVISION_VERIFIER_SHA)) and digest(raw) == REVISION_VERIFIER_SHA,
            'EXECUTION_VERIFIER_PIN')
    value = types.ModuleType('_nox_hermes_execution_verifier'); value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value.current_context(revision_reference(reference))


def manifest():
    info = CONFIG.stat(follow_symlinks=False)
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and info.st_nlink == 1
            and stat.S_IMODE(info.st_mode) == 0o600, 'MANIFEST_MODE')
    raw = read(CONFIG); value = json.loads(raw)
    require(isinstance(value, dict) and value.get('schema') in {SCHEMA, REVISION_SCHEMA}
            and value.get('public_repository') == REPO and value.get('public_revision') == REVISION
            and value.get('public_filename') == NAME and value.get('bytes') == SIZE and value.get('sha256') == SHA
            and value.get('ram_path') == str(WARM) and value.get('ssd_path') == str(SSD)
            and value.get('minimum_cgroup_headroom_bytes') == MIN_HEADROOM
            and value.get('minimum_tmpfs_reserve_bytes') == TMPFS_RESERVE, 'MANIFEST_SCOPE')
    pins = PROFILE_PINS
    if value['schema'] == REVISION_SCHEMA:
        require(value.get('execution_verifier_sha256') == REVISION_VERIFIER_SHA
                and value.get('download_source_sha256') == DOWNLOADER_SHA, 'EXECUTION_MANIFEST_SCOPE')
        ctx = revision_context(value.get('execution_revision'))
        require(ctx['context'] == value['execution_revision'], 'EXECUTION_CONTEXT_CHANGED')
        pins = revision_profiles(ctx['execution']['runtime_entry_sha256'])
    require(value.get('profile_pins') == pins, 'MANIFEST_PROFILE_PINS')
    own = Path(__file__)
    require(own == ROOT / 'scripts/owner_hermes_hydrate.py'
            and digest(read(own)) == value.get('hydrate_source_sha256'), 'SELF_SOURCE')
    require(digest(read(ROOT / 'scripts/download_t802u.sh')) == value.get('download_source_sha256'), 'DOWNLOADER_SOURCE')
    for name, pin in pins.items():
        require(digest(read(ROOT / 'scripts' / name)) == pin, 'PROFILE_SOURCE')
    return value, digest(raw)


def reversed_alias():
    parent = directory(SSD.parent)
    try:
        info = os.stat(SSD.name, dir_fd=parent, follow_symlinks=False)
        require(stat.S_ISLNK(info.st_mode) and info.st_uid == os.geteuid()
                and os.readlink(SSD.name, dir_fd=parent) == str(WARM), 'SSD_REVERSE_ALIAS')
        return identity(info)
    finally: os.close(parent)


def allowed_url(url):
    parsed = urllib.parse.urlsplit(url); host = parsed.hostname or ''
    require(parsed.scheme == 'https' and parsed.username is None and parsed.password is None
            and parsed.port in (None, 443) and not parsed.fragment and len(url) <= 16384
            and (host == 'huggingface.co' or host.endswith('.huggingface.co') or host.endswith('.hf.co')), 'PUBLIC_URL_SCOPE')
    return url


class PublicConnection(http.client.HTTPSConnection):
    def connect(self):
        require(not self._tunnel_host and self.port == 443, 'PUBLIC_CONNECTION_SCOPE')
        choices = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        require(0 < len(choices) <= 32 and all(ipaddress.ip_address(row[4][0]).is_global for row in choices), 'PUBLIC_DNS_SCOPE')
        last = None
        for family, kind, protocol, _, address in choices:
            sock = socket.socket(family, kind, protocol); sock.settimeout(self.timeout)
            try:
                sock.connect(address)
                self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
                return
            except (OSError, ssl.SSLError) as exc:
                sock.close(); last = exc
            except BaseException:
                sock.close(); raise
        raise last


class PublicHTTPS(urllib.request.HTTPSHandler):
    def https_open(self, request):
        allowed_url(request.full_url)
        return self.do_open(PublicConnection, request, context=ssl.create_default_context())


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    max_redirections = 4
    max_repeats = 2
    def redirect_request(self, request, fp, code, message, headers, new_url):
        allowed_url(new_url)
        return super().redirect_request(request, fp, code, message, headers, new_url)


def download(fd, deadline):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), PublicHTTPS(), PublicRedirect())
    request = urllib.request.Request(URL, headers={'User-Agent': 'NOX-Pinned-Hermes-Hydrate/1', 'Accept-Encoding': 'identity'})
    value = hashlib.sha256(); total = 0
    with opener.open(request, timeout=10) as response:
        require(response.status == 200 and response.headers.get('Content-Encoding', 'identity') == 'identity', 'HTTP_STATUS')
        length = response.headers.get('Content-Length')
        require(length is None or (length.isdigit() and int(length) == SIZE), 'HTTP_SIZE')
        while total < SIZE:
            tick(deadline); allocation_gate(SIZE - total, min(CHUNK, SIZE - total))
            raw = response.read(min(CHUNK, SIZE - total)); require(raw, 'HTTP_EOF')
            # Reading TLS buffers can change cgroup usage; recheck before allocation.
            allocation_gate(SIZE - total, len(raw))
            view = memoryview(raw)
            while view:
                count = os.write(fd, view); require(count > 0, 'WRITE_PROGRESS'); view = view[count:]
            total += len(raw); value.update(raw); allocation_gate(SIZE - total)
        require(not response.read(1), 'HTTP_EXTRA_BYTES')
    require(total == SIZE and value.hexdigest() == SHA, 'DOWNLOAD_FULL_SHA')
    os.fsync(fd)
    return total


def main():
    require(os.geteuid() == 0 and len(os.sys.argv) == 1, 'OWNER_INVOCATION')
    previous = signal.getsignal(signal.SIGALRM)
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'EXISTING_TIMER')
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(Hold('HOLD_HERMES_HYDRATE_DEADLINE')))
    signal.setitimer(signal.ITIMER_REAL, SECONDS)
    deadline = time.monotonic() + SECONDS - 5
    locks = []; parent = tempdir = fd = None; temp = None; published = False; own = None
    result = {'schema': 'NOX_HERMES_HYDRATE_RECEIPT_V1', 'state': 'HELD', 'sha256': SHA,
              'bytes': SIZE, 'training_or_service_actions': 0, 'private_urls_exported': False}
    try:
        tick(deadline); locks.append(lease(LEASE, fcntl.LOCK_EX)); locks.append(lease(MAINTENANCE, fcntl.LOCK_SH))
        value, manifest_sha = manifest(); result['manifest_sha256'] = manifest_sha
        tmpfs_verified(); before_alias = reversed_alias(); parent = directory(WARM.parent)
        try:
            info = os.stat(WARM.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError: info = None
        if info is not None:
            fd = os.open(WARM.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
            full_hash(fd, deadline, WARM); result['state'] = 'ALREADY_WARM_FULL_SHA_VERIFIED'
        else:
            initial = allocation_gate(SIZE)
            require(initial['cgroup_headroom_bytes'] >= MIN_HEADROOM + SIZE, 'INITIAL_RAM_RESERVE')
            token = 'hydrate_' + str(time.time_ns()) + '_' + str(os.getpid())
            temp = WARM.parent / ('.nox_' + token); os.mkdir(temp, 0o700)
            tempdir = directory(temp)
            fd = os.open('payload.gguf', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=tempdir)
            own = os.fstat(fd); download(fd, deadline); full_hash(fd, deadline, temp / 'payload.gguf')
            require(reversed_alias() == before_alias and manifest()[1] == manifest_sha, 'PREPUBLICATION_CHANGED')
            tick(deadline); allocation_gate(0)
            rename(tempdir, 'payload.gguf', parent, WARM.name, 1); published = True
            os.fsync(parent)
            full_hash(fd, deadline, WARM); result['state'] = 'WARM_PUBLIC_REVISION_AND_FULL_SHA_VERIFIED'
        require(reversed_alias() == before_alias, 'POSTPUBLICATION_ALIAS_CHANGED')
        result.update(finished_at=time.time(), full_ram_sha_verified=True, public_revision=REVISION,
                      resources_after=allocation_gate(0))
        private_record(STATE / ('hydrate_' + str(time.time_ns()) + '.json'), result)
    except Exception as exc:
        result.update(state='HELD', reason=safe(exc), ram_publication_completed=published)
    finally:
        if fd is not None: os.close(fd)
        if tempdir is not None:
            if not published and own is not None:
                try:
                    current = os.stat('payload.gguf', dir_fd=tempdir, follow_symlinks=False)
                    if (current.st_dev, current.st_ino) == (own.st_dev, own.st_ino): os.unlink('payload.gguf', dir_fd=tempdir)
                except OSError: pass
            os.close(tempdir)
        if parent is not None: os.close(parent)
        for lock in reversed(locks): os.close(lock)
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)
    print('NOX_HERMES_HYDRATE=' + encode(result).decode(), flush=True)
    return 0 if result['state'] in {'ALREADY_WARM_FULL_SHA_VERIFIED', 'WARM_PUBLIC_REVISION_AND_FULL_SHA_VERIFIED'} else 2


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        print('NOX_HERMES_HYDRATE=' + encode({'state': 'HELD', 'reason': safe(exc)}).decode(), flush=True)
        raise SystemExit(2)
