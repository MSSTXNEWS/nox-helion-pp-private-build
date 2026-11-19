"""Stage the pinned loopback gateway and launch the separate temporary tunnel."""

from contextlib import suppress
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import tempfile
import time

from owner_quick_tunnel_launch import (
    GATEWAY, LOCAL, METRICS, TTL_SECONDS, WORK, Hold, child_limits, get, launch,
    maintenance_lease, path_trusted, read_fd, require, start_ticks, sync_dir,
)


DESTINATION = WORK / 'owner_resonance_gateway.py'
GATEWAY_PIN = '5b95b7f8ce43b209e325d5435b0f975f8a75bdfdb721cf5910426f50582f8c42'
MAX_GATEWAY = 48 * 1024
PYTHON = '/usr/bin/python3'


def require_closed(port):
    with socket.socket() as probe:
        probe.settimeout(0.7)
        require(probe.connect_ex((LOCAL, port)) != 0, 'LOCAL_PORT_BUSY')


def install_source(raw):
    path_trusted(WORK.parent)
    WORK.mkdir(mode=0o700, exist_ok=True)
    path_trusted(WORK)
    require(stat.S_IMODE(WORK.lstat().st_mode) == 0o700, 'WORK_MODE')
    sync_dir(WORK.parent)
    if not os.path.lexists(DESTINATION):
        fd, temporary = tempfile.mkstemp(prefix='.gateway-', dir=WORK)
        try:
            with os.fdopen(fd, 'wb') as stream:
                require(stream.write(raw) == len(raw), 'GATEWAY_WRITE')
                stream.flush()
                os.fchmod(stream.fileno(), 0o400)
                os.fsync(stream.fileno())
            os.link(temporary, DESTINATION)
        finally:
            os.unlink(temporary)
        sync_dir(WORK)
    with os.fdopen(read_fd(DESTINATION, MAX_GATEWAY), 'rb') as stream:
        require(stat.S_IMODE(os.fstat(stream.fileno()).st_mode) == 0o400
                and stream.read(MAX_GATEWAY + 1) == raw, 'GATEWAY_READBACK')


def gateway_process(parent):
    entry = Path('/proc') / str(parent)
    children = (entry / 'task' / str(parent) / 'children').read_text().split()
    if len(children) != 1 or not children[0].isdecimal():
        return None
    pid = int(children[0])
    child = Path('/proc') / str(pid)
    expected = [os.fsencode(PYTHON), b'-I', b'-B', os.fsencode(DESTINATION), b'']
    if (child / 'cmdline').read_bytes().split(b'\0') != expected:
        return None
    return pid, start_ticks(pid)


def wait_gateway(parent, pin):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        require(parent.poll() is None, 'GATEWAY_EXIT')
        try:
            identity = gateway_process(parent.pid)
        except FileNotFoundError:
            identity = None
        status, health = get(GATEWAY, '/_nox_edge_health', parse=True)
        if (identity is not None and status == 200 and isinstance(health, dict)
                and health.get('ready') is True and health.get('service') == 'nox-quick-chat-gateway'
                and health.get('source_sha256') == pin):
            return identity
        time.sleep(0.1)
    raise Hold('HOLD_NOX_QUICK_TUNNEL_GATEWAY_READINESS')


def stop_started(parent):
    if parent.poll() is None:
        with suppress(ProcessLookupError):
            os.killpg(parent.pid, signal.SIGTERM)
        try:
            parent.wait(timeout=5)
        except subprocess.TimeoutExpired:
            with suppress(ProcessLookupError):
                os.killpg(parent.pid, signal.SIGKILL)
            parent.wait(timeout=3)


def install_and_launch(gateway_raw):
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    labels = {os.environ[name].removeprefix('C.') for name in ('VAST_CONTAINERLABEL', 'CONTAINER_ID')
              if os.environ.get(name)}
    require(os.geteuid() == os.getegid() == 0 and labels == {'60509551'}
            and re.fullmatch(r'[1-9][0-9]{0,19}', request)
            and re.fullmatch(r'[a-f0-9]{40}', source), 'OWNER_SOURCE')
    require(isinstance(gateway_raw, bytes) and 0 < len(gateway_raw) <= MAX_GATEWAY
            and sha256(gateway_raw).hexdigest() == GATEWAY_PIN, 'GATEWAY_PIN')
    compile(gateway_raw, str(DESTINATION), 'exec')

    parent = None
    try:
        with maintenance_lease() as assert_lease:
            require_closed(GATEWAY)
            require_closed(METRICS)
            require(get(8080, '/health')[0] == 200 and get(8080, '/chat/session')[0] == 401,
                    'NATIVE_CHAT_GUARD')
            install_source(gateway_raw)
            options = ['/usr/bin/timeout', '--foreground', '--signal=TERM', '--kill-after=5s',
                       str(TTL_SECONDS + 180), PYTHON, '-I', '-B', str(DESTINATION)]
            fd, log_path = tempfile.mkstemp(prefix='gateway-', suffix='.log', dir=WORK)
            with os.fdopen(fd, 'wb') as log:
                assert_lease()
                parent = subprocess.Popen(options, stdin=subprocess.DEVNULL, stdout=log,
                                          stderr=subprocess.STDOUT, start_new_session=True,
                                          close_fds=True, cwd=WORK, preexec_fn=child_limits,
                                          env={'PATH': '/usr/bin:/bin', 'HOME': str(WORK), 'LC_ALL': 'C'})
            pid, ticks = wait_gateway(parent, GATEWAY_PIN)
            identity = {'gateway_pid': pid, 'gateway_start_ticks': ticks,
                        'gateway_ttl_pid': parent.pid, 'gateway_ttl_start_ticks': start_ticks(parent.pid),
                        'gateway_log_name': Path(log_path).name}
        # launch() acquires its own existing maintenance lease.
        value = launch(GATEWAY_PIN)
        return {**value, **identity}
    except BaseException:
        if parent is not None:
            stop_started(parent)
        raise


def main(gateway_raw):
    try:
        receipt = install_and_launch(gateway_raw)
    except (Hold, OSError, ValueError, SyntaxError) as error:
        code = str(error) if isinstance(error, Hold) else type(error).__name__
        print('NOX_MAINT_QUICK_CHAT_HOLD=' + code, flush=True)
        return 2
    print('NOX_MAINT_QUICK_CHAT_TUNNEL=' + json.dumps(receipt, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0
