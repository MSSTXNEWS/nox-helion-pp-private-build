"""Launch a temporary, isolated Quick Tunnel to the pinned NOX chat gateway."""

from contextlib import contextmanager, suppress
import fcntl
from hashlib import sha256
import http.client
import json
import os
from pathlib import Path
import platform
import re
import resource
import signal
import socket
import stat
import subprocess
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


ROOT = Path('/root/nox')
WORK = ROOT / 'ops/nox-quick-chat'
LEASE = ROOT / 'state/owner_maintenance.lock'
VERSION = '2026.11.1'
PIN = '97bb3b02d23a5980fc9c15a1a270e692da1923f103f920d5b16d4931d5ab55e7'
RELEASE = f'https://github.com/cloudflare/cloudflared/releases/download/{VERSION}/cloudflared-linux-amd64'
DOWNLOAD_HOSTS = {'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
BINARY = WORK / ('cloudflared-' + VERSION)
RECEIPT = WORK / 'active.json'
GATEWAY = 18777
METRICS = 18778
LOCAL = '127.0.0.1'
TTL_SECONDS = 86400
MAX_BINARY = 80 * 1024 * 1024
HASH = re.compile(r'[a-f0-9]{64}')
DOMAIN = re.compile(r'[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?\.trycloudflare\.com')
READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


class Hold(RuntimeError):
    pass


def require(value, reason):
    if not value:
        raise Hold('HOLD_NOX_QUICK_TUNNEL_' + reason)


def path_trusted(path):
    for part in (path, *path.parents):
        info = part.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == info.st_gid == 0
                and not info.st_mode & 0o022, 'DIRECTORY_TRUST')


def read_fd(path, limit, executable=False):
    fd = os.open(path, READ)
    try:
        meta = os.fstat(fd)
        require(stat.S_ISREG(meta.st_mode) and meta.st_uid == meta.st_gid == 0
                and meta.st_nlink == 1 and 0 <= meta.st_size <= limit
                and not meta.st_mode & 0o7022 and (not executable or meta.st_mode & stat.S_IXUSR),
                'FILE_TRUST')
        return fd
    except BaseException:
        os.close(fd)
        raise


@contextmanager
def maintenance_lease():
    path_trusted(LEASE.parent)
    fd = read_fd(LEASE, 4096)
    try:
        original = os.fstat(fd)
        require(not original.st_mode & 0o077, 'LEASE_MODE')
        deadline = time.monotonic() + 15
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                require(time.monotonic() < deadline, 'LEASE_BUSY')
                time.sleep(0.2)

        def current():
            require(os.path.samestat(original, LEASE.lstat()), 'LEASE_CHANGED')

        current()
        yield current
    finally:
        os.close(fd)


class ReleaseRedirects(HTTPRedirectHandler):
    max_redirections = 3
    max_repeats = 1

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        route = urlsplit(newurl)
        require(route.scheme == 'https' and route.hostname in DOWNLOAD_HOSTS
                and route.username is None and route.password is None
                and route.port in (None, 443), 'RELEASE_REDIRECT')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def copy_pinned(stream, output):
    digest = sha256()
    size = 0
    deadline = time.monotonic() + 45
    while chunk := stream.read(512 * 1024):
        size += len(chunk)
        require(size <= MAX_BINARY and time.monotonic() <= deadline, 'RELEASE_BOUND')
        digest.update(chunk)
        if output is not None:
            output.write(chunk)
    return digest.hexdigest() == PIN


def sync_dir(path):
    fd = os.open(path, READ | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def pinned_binary():
    for path in (BINARY, Path('/usr/bin/cloudflared'), Path('/usr/local/bin/cloudflared')):
        try:
            path_trusted(path.parent)
            with os.fdopen(read_fd(path, MAX_BINARY, executable=True), 'rb') as stream:
                if copy_pinned(stream, None):
                    return path
        except (FileNotFoundError, Hold):
            if path == BINARY and os.path.lexists(path):
                raise
    require(not os.path.lexists(BINARY), 'BINARY_PREIMAGE')
    fd, path = tempfile.mkstemp(prefix='.cloudflared-', dir=WORK)
    try:
        with os.fdopen(fd, 'wb') as target:
            opener = build_opener(ProxyHandler({}), ReleaseRedirects())
            with opener.open(RELEASE, timeout=8) as source:
                require(source.status == 200 and copy_pinned(source, target), 'RELEASE_SHA')
            target.flush()
            os.fchmod(target.fileno(), 0o500)
            os.fsync(target.fileno())
        os.link(path, BINARY)
    finally:
        os.unlink(path)
    sync_dir(WORK)
    with os.fdopen(read_fd(BINARY, MAX_BINARY, executable=True), 'rb') as stream:
        require(copy_pinned(stream, None), 'BINARY_READBACK')
    return BINARY


def get(port, path, parse=False):
    conn = http.client.HTTPConnection(LOCAL, port, timeout=0.8)
    try:
        conn.request('GET', path, headers={'Connection': 'close'})
        response = conn.getresponse()
        value = None
        if parse and response.status == 200:
            body = response.read(4097)
            if 0 < len(body) <= 4096:
                value = json.loads(body)
        return response.status, value
    except (OSError, ValueError, RecursionError, http.client.HTTPException):
        return None, None
    finally:
        conn.close()


def start_ticks(pid):
    row = (Path('/proc') / str(pid) / 'stat').read_bytes().rpartition(b') ')[2].split()
    require(len(row) > 19 and row[0] not in (b'Z', b'X'), 'PROCESS_STATE')
    return int(row[19])


def owned_cloudflared(parent, binary):
    process = Path('/proc') / str(parent)
    children = (process / 'task' / str(parent) / 'children').read_text().split()
    if len(children) != 1 or not children[0].isdecimal():
        return None
    pid = int(children[0])
    child = Path('/proc') / str(pid)
    if not os.path.samestat((child / 'exe').stat(), binary.stat()):
        return None
    expected = f'{socket.inet_aton(LOCAL)[::-1].hex().upper()}:{METRICS:04X}'
    inodes = {fields[9] for line in Path('/proc/net/tcp').read_text().splitlines()[1:]
              if len(fields := line.split()) > 9 and fields[1] == expected and fields[3] == '0A'}
    if not inodes or not any(fd.is_symlink() and fd.readlink().name in {'socket:[' + i + ']' for i in inodes}
                            for fd in (child / 'fd').iterdir()):
        return None
    return pid, start_ticks(pid)


def route():
    status, value = get(METRICS, '/quicktunnel', parse=True)
    host = value.get('hostname') if isinstance(value, dict) else None
    if isinstance(host, str):
        host = host.removeprefix('https://')
    if status == 200 and isinstance(host, str) and DOMAIN.fullmatch(host) and get(METRICS, '/ready')[0] == 200:
        return 'https://' + host + '/chat'
    return None


def write_receipt(value):
    raw = (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()
    fd, path = tempfile.mkstemp(prefix='.active-', dir=WORK)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(path, RECEIPT)
        sync_dir(WORK)
        with os.fdopen(read_fd(RECEIPT, 4096), 'rb') as stream:
            require(stream.read(len(raw) + 1) == raw, 'RECEIPT_READBACK')
    finally:
        with suppress(FileNotFoundError):
            os.unlink(path)


def child_limits():
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024 * 1024,) * 2)


def launch(gateway_sha):
    """Call only inside the externally owner-authorized source-pinned action."""
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    labels = {os.environ[key].removeprefix('C.') for key in ('VAST_CONTAINERLABEL', 'CONTAINER_ID')
              if os.environ.get(key)}
    require(os.geteuid() == os.getegid() == 0 and labels == {'60509551'}
            and re.fullmatch(r'[1-9][0-9]{0,19}', request) and re.fullmatch(r'[a-f0-9]{40}', source)
            and isinstance(gateway_sha, str) and HASH.fullmatch(gateway_sha), 'OWNER_SOURCE')
    require(platform.machine() == 'x86_64', 'ARCH')

    with maintenance_lease() as current_lease:
        status, gateway = get(GATEWAY, '/_nox_edge_health', parse=True)
        require(status == 200 and isinstance(gateway, dict) and gateway.get('ready') is True
                and gateway.get('service') == 'nox-quick-chat-gateway'
                and gateway.get('source_sha256') == gateway_sha, 'GATEWAY_ATTESTATION')
        path_trusted(WORK.parent)
        WORK.mkdir(mode=0o700, exist_ok=True)
        path_trusted(WORK)
        require(stat.S_IMODE(WORK.lstat().st_mode) == 0o700, 'WORK_MODE')
        binary = pinned_binary()
        with socket.socket() as test:
            test.settimeout(0.6)
            require(test.connect_ex((LOCAL, METRICS)) != 0, 'METRICS_BUSY')

        options = ['/usr/bin/timeout', '--foreground', '--signal=TERM', '--kill-after=5s', str(TTL_SECONDS),
                   str(binary), 'tunnel', '--no-autoupdate', '--loglevel', 'warn',
                   '--metrics', f'{LOCAL}:{METRICS}', '--url', f'http://{LOCAL}:{GATEWAY}']
        fd, log_path = tempfile.mkstemp(prefix='cloudflared-', suffix='.log', dir=WORK)
        expires_at = int(time.time()) + TTL_SECONDS
        with os.fdopen(fd, 'wb') as log:
            current_lease()
            child = subprocess.Popen(options, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=True, close_fds=True, cwd=WORK, preexec_fn=child_limits,
                                     env={'PATH': '/usr/bin:/bin', 'HOME': str(WORK), 'LC_ALL': 'C'})
        try:
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                require(child.poll() is None, 'CLOUDFLARED_EXIT')
                try:
                    identity = owned_cloudflared(child.pid, binary)
                except FileNotFoundError:
                    identity = None
                endpoint = route() if identity is not None else None
                if endpoint:
                    current_lease()
                    value = {'schema': 'NOX_QUICK_CHAT_TUNNEL_V1', 'request': request, 'source_sha': source,
                             'gateway_sha256': gateway_sha, 'cloudflared_sha256': PIN, 'url': endpoint,
                             'ttl_pid': child.pid, 'ttl_start_ticks': start_ticks(child.pid),
                             'cloudflared_pid': identity[0], 'cloudflared_start_ticks': identity[1],
                             'expires_unix': expires_at, 'temporary': True,
                             'external_stream_verified': False, 'log_name': Path(log_path).name}
                    write_receipt(value)
                    return value
                time.sleep(0.25)
            raise Hold('HOLD_NOX_QUICK_TUNNEL_READINESS')
        except BaseException:
            if child.poll() is None:
                with suppress(ProcessLookupError):
                    os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    with suppress(ProcessLookupError):
                        os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=3)
            raise


def main(gateway_sha):
    try:
        receipt = launch(gateway_sha)
    except (Hold, OSError, ValueError) as error:
        code = str(error) if isinstance(error, Hold) else type(error).__name__
        print('NOX_MAINT_QUICK_CHAT_HOLD=' + code, flush=True)
        return 2
    print('NOX_MAINT_QUICK_CHAT_TUNNEL=' + json.dumps(receipt, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0
