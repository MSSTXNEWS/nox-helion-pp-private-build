"""Install the exact private cognition overlay and restart only the NOX proxy."""

import ctypes
import errno
import fcntl
import hashlib
import http.client
import json
import os
import re
import socket
import stat
import struct
import time
import uuid
import xmlrpc.client
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path


INSTANCE = "60509551"
SERVICE = "nox-proxy"
SCRIPTS = Path("/root/nox/scripts")
STATE = Path("/root/nox/state")
LEASE = STATE / "owner_maintenance.lock"
BACKUPS = STATE / "owner_cognition_backups"
SECRETS = Path("/root/nox/secrets")
SOCKET = Path("/run/supervisor.sock")
CONFIG = Path("/etc/supervisor/conf.d/nox-proxy.conf")
CONFIG_SHA = "ddec2af7e644f9bfae231ae47d1975542b9eddf6f2bee1d2e14a0ff34db3c18b"
PROXY = "chat_proxy.py"
BRIDGE = "nox_v29_chat_bridge.py"
PREIMAGE = {
    PROXY: "cc1437ce8c3bfbbc4259ffdbe299bf3b8721d4b1bb09c88565ccb6cb9fdb95eb",
    BRIDGE: "2d7145293fa5566fee38a61e772780b4b0dd0e2d1bcad71b5ceedf77974a75a7",
}
KEEP = {
    "owner_chat_stream.py": "a26ec83aadac240d7284959b53cf7e59575e8e487d27c962cec7236892ccc7af",
    "s03_memory.py": "776a6dc25726540d75ec51216d1e333ca89b24e803ba3620f9b5e470a3c81476",
    "common.py": "177fbe5df042ba75a94cf9b7c03c8ffe58bde99f12599193db0cf383cc1305dd",
}
STOP = tuple(Path("/root/nox") / name for name in (
    "STOP", "STOP.flag", "stop.flag", ".stop", "program/STOP",
    "state/STOP", "state/STOP.flag", "state/OWNER_MAINTENANCE.flag",
)) + (Path("/workspace/NOX_STOP"),)
DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
WRITE = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
MAX = 256 << 10
RELEASE_PIN = re.compile(r"[a-f0-9]{64}")
HELPERS = ("nox_v38_native_context.py", "nox_v38_s03_native.py")


class Hold(RuntimeError):
    pass


def need(condition, code):
    if not condition:
        raise Hold("HOLD_NATIVE_COGNITION_" + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def trusted(info, kind):
    need(kind(info.st_mode) and info.st_uid == info.st_gid == 0
         and not info.st_mode & 0o7022, "PATH_TRUST")


def inode(info):
    return info.st_dev, info.st_ino


def stamp(info):
    return (inode(info), info.st_uid, info.st_gid, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def directory(stack, path):
    fd = os.open("/", DIR)
    stack.callback(os.close, fd)
    trusted(os.fstat(fd), stat.S_ISDIR)
    for name in path.parts[1:]:
        fd = os.open(name, DIR, dir_fd=fd)
        stack.callback(os.close, fd)
        trusted(os.fstat(fd), stat.S_ISDIR)
    return fd


def node(directory_fd, name):
    try:
        return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def read(directory_fd, name):
    first = node(directory_fd, name)
    if first is None:
        return None, None
    trusted(first, stat.S_ISREG)
    need(first.st_nlink == 1 and 0 < first.st_size <= MAX, "SOURCE_SIZE_OR_ALIAS")
    fd = os.open(name, READ, dir_fd=directory_fd)
    with os.fdopen(fd, "rb") as handle:
        raw = handle.read(first.st_size + 1)
        last = os.fstat(fd)
    final = node(directory_fd, name)
    need(final is not None and stamp(first) == stamp(last) == stamp(final)
         and len(raw) == first.st_size, "SOURCE_CHANGED")
    return raw, final


def write(directory_fd, name, raw, mode):
    fd = os.open(name, WRITE, 0o600, dir_fd=directory_fd)
    with os.fdopen(fd, "wb") as handle:
        need(handle.write(raw) == len(raw), "WRITE_FAILED")
        handle.flush()
        os.fchmod(fd, mode)
        os.fsync(fd)
    checked, info = read(directory_fd, name)
    need(checked == raw and stat.S_IMODE(info.st_mode) == mode, "WRITE_READBACK")
    return info


def lease(stack):
    scope = directory(stack, LEASE.parent)
    fd = os.open(LEASE.name, READ, dir_fd=scope)
    stack.callback(os.close, fd)
    original = os.fstat(fd)
    trusted(original, stat.S_ISREG)
    need(original.st_nlink == 1, "OWNER_LEASE_TRUST")
    deadline = time.monotonic() + 24
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError as error:
            if error.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                raise
            need(time.monotonic() < deadline, "OWNER_LEASE_BUSY")
            time.sleep(0.2)

    def assert_current():
        named = node(scope, LEASE.name)
        need(named is not None and stamp(named) == stamp(os.fstat(fd)) == stamp(original),
             "OWNER_LEASE_CHANGED")

    assert_current()
    return assert_current


def stop_clear():
    for path in STOP:
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        raise Hold("HOLD_NATIVE_COGNITION_OWNER_STOP")


def proc(pid):
    base = Path("/proc") / str(pid)
    with (base / "stat").open("rb") as handle:
        raw = handle.read(4097)
    need(0 < len(raw) <= 4096, "PROC_STAT")
    fields = raw.rpartition(b") ")[2].split()
    need(len(fields) > 19 and fields[0] not in (b"Z", b"X"), "PROC_STATE")
    return int(fields[19]), int(fields[1]), int(fields[2])


class UnixHTTP(http.client.HTTPConnection):
    def __init__(self, expected_peer=None):
        super().__init__("localhost", timeout=30)
        self.expected_peer = expected_peer
        self.peer = None

    def connect(self):
        channel = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            channel.settimeout(self.timeout)
            channel.connect(str(SOCKET))
            pid, uid, gid = struct.unpack("3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            need(uid == gid == 0 and pid > 1 and self.expected_peer in (None, pid), "RPC_PEER")
            self.peer = pid
            self.sock = channel
        except BaseException:
            channel.close()
            raise


class ProxyControl:
    def __init__(self):
        with ExitStack() as local:
            directory(local, SOCKET.parent)
            config = directory(local, CONFIG.parent)
            config_raw, _ = read(config, CONFIG.name)
        need(config_raw is not None and digest(config_raw) == CONFIG_SHA, "PROXY_UNIT_SHA")
        entry = SOCKET.lstat()
        trusted(entry, stat.S_ISSOCK)
        need(entry.st_nlink == 1 and stat.S_IMODE(entry.st_mode) == 0o700, "SUPERVISOR_SOCKET_SCOPE")
        self.socket_inode = inode(entry)
        self.peer = None
        self.epoch = None
        server_pid = self.rpc("getPID")
        need(type(server_pid) is int and server_pid == self.peer, "SUPERVISOR_RPC_PID")
        self.epoch = proc(server_pid)
        with (Path("/proc") / str(server_pid) / "cmdline").open("rb") as handle:
            cmdline = handle.read(16385)
        need(len(cmdline) <= 16384 and any(Path(os.fsdecode(item)).name == "supervisord"
              for item in cmdline.split(b"\0")[:2]), "SUPERVISOR_PROCESS")

    def rpc(self, method, *args):
        need(method in ("getPID", "getProcessInfo", "stopProcess", "startProcess"), "RPC_METHOD")
        need(method == "getPID" or args and args[0] == SERVICE, "RPC_TARGET_SCOPE")
        live = SOCKET.lstat()
        trusted(live, stat.S_ISSOCK)
        need(inode(live) == self.socket_inode and stat.S_IMODE(live.st_mode) == 0o700, "SOCKET_GENERATION")
        if self.epoch is not None:
            need(proc(self.peer) == self.epoch, "SUPERVISOR_GENERATION")
        http = UnixHTTP(self.peer)
        try:
            body = xmlrpc.client.dumps(args, methodname="supervisor." + method)
            http.request("POST", "/RPC2", body, {"Content-Type": "text/xml", "Connection": "close"})
            response = http.getresponse()
            raw = response.read(65537)
            need(response.status == 200 and 0 < len(raw) <= 65536, "SUPERVISOR_RPC_RESPONSE")
            self.peer = http.peer
            values, _ = xmlrpc.client.loads(raw)
            need(len(values) == 1, "SUPERVISOR_RPC_SCHEMA")
            return values[0]
        finally:
            http.close()

    def status(self):
        record = self.rpc("getProcessInfo", SERVICE)
        need(isinstance(record, dict) and record.get("name") == record.get("group") == SERVICE
             and record.get("statename") in ("RUNNING", "STARTING", "STOPPING", "STOPPED",
                                             "EXITED", "BACKOFF", "FATAL"), "PROXY_RPC_SCOPE")
        return record

    def active(self, record=None):
        row = self.status() if record is None else record
        pid = row.get("pid")
        need(type(pid) is int and pid > 1, "PROXY_PID")
        start, ppid, group = proc(pid)
        need(ppid == self.peer and group == pid, "PROXY_PROCESS_GROUP")
        base = Path("/proc") / str(pid)
        with (base / "cmdline").open("rb") as handle:
            raw = handle.read(16385)
        need(len(raw) <= 16384 and raw.split(b"\0").count(os.fsencode(SCRIPTS / PROXY)) == 1
             and proc(pid) == (start, ppid, group), "PROXY_PROCESS_SIGNER")
        return pid, start


def local_http(port, path, limit=65536, *, external_boundary=False):
    endpoint = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        headers = {"Connection": "close"}
        if external_boundary:
            headers["X-Forwarded-For"] = "192.0.2.2"
        endpoint.request("GET", path, headers=headers)
        response = endpoint.getresponse()
        raw = response.read(limit + 1)
        need(len(raw) <= limit, "HTTP_LIMIT")
        return response.status, raw
    finally:
        endpoint.close()


def auth_anchor():
    """Check the existing owner login data without returning secret bytes."""
    records = []
    with ExitStack() as stack:
        secrets = directory(stack, SECRETS)
        for name, minimum in (("chat_password", 1), ("chat_session_key", 32)):
            raw, item = read(secrets, name)
            need(raw is not None and minimum <= len(raw.strip()) <= 4096, "OWNER_AUTH_FILES")
            records.append(stamp(item))
    return tuple(records)


def idle():
    status, raw = local_http(8098, "/slots")
    rows = json.loads(raw)
    need(status == 200 and isinstance(rows, list) and 1 <= len(rows) <= 64, "CHAT_SLOTS_UNKNOWN")
    for row in rows:
        flags = [row[key] for key in ("is_processing", "processing") if key in row] if isinstance(row, dict) else []
        need(flags and all(flag is False for flag in flags), "CHAT_BUSY_OR_UNKNOWN")
    for path in (STATE / "chat_active", STATE / "priority" / "LAST_OWNER_CHAT"):
        try:
            mark = path.lstat()
        except FileNotFoundError:
            continue
        age = time.time() - mark.st_mtime
        need(stat.S_ISREG(mark.st_mode) and mark.st_uid == mark.st_gid == 0
             and mark.st_nlink == 1 and not mark.st_mode & 0o002 and age >= 3,
             "CHAT_BUSY_OR_UNKNOWN")


def ready(control, *, previous=None):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        row = control.status()
        if row["statename"] == "RUNNING":
            active = control.active(row)
            if (previous is None or active != previous):
                try:
                    live, _ = local_http(8080, "/health")
                    auth, _ = local_http(8080, "/nox-web-v29/pc/resonance.html", external_boundary=True)
                    if live == 200 and auth == 401:
                        return active
                except (OSError, http.client.HTTPException):
                    pass
        if row["statename"] in ("FATAL", "EXITED", "STOPPED"):
            break
        time.sleep(0.25)
    raise Hold("HOLD_NATIVE_COGNITION_PROXY_NOT_READY")


@dataclass
class Change:
    name: str
    before: bytes | None
    original: os.stat_result | None
    candidate: bytes
    temp: str = ""
    installed: bool = False
    installed_inode: tuple | None = None
    temp_inode: tuple | None = None


def backup(stack, changes, request, source):
    state = directory(stack, BACKUPS.parent)
    try:
        os.mkdir(BACKUPS.name, 0o700, dir_fd=state)
        os.fsync(state)
    except FileExistsError:
        pass
    parent = directory(stack, BACKUPS)
    need(stat.S_IMODE(os.fstat(parent).st_mode) == 0o700, "BACKUP_PRIVATE_MODE")
    name = request
    os.mkdir(name, 0o700, dir_fd=parent)
    os.fsync(parent)
    out = os.open(name, DIR, dir_fd=parent)
    stack.callback(os.close, out)
    trusted(os.fstat(out), stat.S_ISDIR)
    for change in changes:
        if change.before is not None:
            write(out, change.name, change.before, 0o600)
    manifest = (json.dumps({"schema": "NOX_COGNITION_PROXY_ROLLBACK_V1", "request_id": request,
                            "source_sha": source, "files": {
                                c.name: {"before": None if c.before is None else digest(c.before),
                                         "after": digest(c.candidate),
                                         "mode": None if c.original is None else stat.S_IMODE(c.original.st_mode)}
                                for c in changes}}, sort_keys=True) + "\n").encode()
    write(out, "manifest.json", manifest, 0o600)
    os.fsync(out)
    return digest(manifest)


def assert_live_sources(scripts, changes, *, after=False):
    for name, pin in KEEP.items():
        raw, _ = read(scripts, name)
        need(raw is not None and digest(raw) == pin, "UNCHANGED_SOURCE_DRIFT")
    for change in changes:
        raw, info = read(scripts, change.name)
        if after:
            need(raw == change.candidate and info is not None and inode(info) == change.installed_inode,
                 "INSTALL_READBACK")
        else:
            want = change.original
            aligned = ((want is None and info is None)
                       or (want is not None and info is not None and stamp(info) == stamp(want)))
            need(raw == change.before and aligned, "SOURCE_CAS")


def native_rename(directory_fd, old, new, flag):
    function = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
    need(function is not None, "ATOMIC_RENAME_UNAVAILABLE")
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    result = function(directory_fd, os.fsencode(old), directory_fd, os.fsencode(new), flag)
    if result != 0:
        raise OSError(ctypes.get_errno(), "cognition source rename")


def put_sources(scripts, changes):
    for change in changes:
        raw, old = read(scripts, change.name)
        need(raw == change.before and ((change.original is None and old is None)
             or (old is not None and change.original is not None and stamp(old) == stamp(change.original))),
             "SOURCE_CAS")
        candidate, info = read(scripts, change.temp)
        need(candidate == change.candidate and info is not None and inode(info) == change.temp_inode,
             "TEMP_SOURCE_CHANGED")
        change.installed_inode = inode(info)
        # NOREPLACE for new helpers, EXCHANGE on replacements retains the original inode.
        native_rename(scripts, change.temp, change.name, 1 if old is None else 2)
        change.installed = True
        if old is not None:
            preimage, anchored = read(scripts, change.temp)
            need(preimage == change.before and inode(anchored) == inode(old), "SWAP_PREIMAGE")
    os.fsync(scripts)


def restore(scripts, changes):
    for change in reversed(changes):
        if not change.installed:
            continue
        raw, item = read(scripts, change.name)
        need(raw == change.candidate and item is not None and inode(item) == change.installed_inode,
             "ROLLBACK_CAS")
        if change.before is None:
            os.unlink(change.name, dir_fd=scripts)
        else:
            preimage, info = read(scripts, change.temp)
            need(preimage == change.before and info is not None and inode(info) == inode(change.original),
                 "ROLLBACK_PREIMAGE")
            native_rename(scripts, change.temp, change.name, 2)
            restored, item = read(scripts, change.name)
            need(restored == change.before and item is not None and inode(item) == inode(change.original),
                 "ROLLBACK_READBACK")
        change.installed = False
    os.fsync(scripts)


def current_patch_preimages():
    """Return only the exact pinned root sources needed by the private caller."""
    data = {}
    with ExitStack() as stack:
        scripts = directory(stack, SCRIPTS)
        for name, expected in PREIMAGE.items():
            raw, _ = read(scripts, name)
            need(raw is not None and digest(raw) == expected, "SOURCE_PREIMAGE")
            data[name] = raw
    return data


def activate(*, payloads, sha256):
    """Caller supplies the four artifacts from an exact authenticated bundle."""
    request = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    source = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    labels = {os.environ[key].removeprefix("C.") for key in ("VAST_CONTAINERLABEL", "CONTAINER_ID")
              if os.environ.get(key)}
    need(os.geteuid() == os.getegid() == 0 and labels == {INSTANCE}
         and re.fullmatch(r"[1-9][0-9]{0,19}", request) and re.fullmatch(r"[a-f0-9]{40}", source),
         "OWNER_CONTEXT")
    order = (*HELPERS, BRIDGE, PROXY)
    need(set(payloads) == set(sha256) == set(order), "BUNDLE_SCOPE")
    for name in order:
        raw = payloads[name]
        need(type(raw) is bytes and 0 < len(raw) <= MAX and isinstance(sha256[name], str)
             and RELEASE_PIN.fullmatch(sha256[name]) and digest(raw) == sha256[name], "ASSET_PIN")
        need(name not in PREIMAGE or sha256[name] != PREIMAGE[name], "UNMODIFIED_ASSET")
        compile(raw, name, "exec")
    with ExitStack() as stack:
        assert_lease = lease(stack)
        stop_clear()
        scripts = directory(stack, SCRIPTS)
        control = ProxyControl()
        auth = auth_anchor()
        old = ready(control)
        idle()
        changes = []
        for name in order:
            raw, info = read(scripts, name)
            need((raw is None and name in HELPERS) or (name in PREIMAGE and raw is not None
                 and digest(raw) == PREIMAGE[name]), "SOURCE_PREIMAGE")
            changes.append(Change(name, raw, info, payloads[name]))
        assert_live_sources(scripts, changes)
        backup_pin = backup(stack, changes, request, source)
        stop_attempted = False
        commit_ready = False
        try:
            for change in changes:
                change.temp = ".nox-cognition-stage-" + uuid.uuid4().hex
                info = write(scripts, change.temp, change.candidate,
                             0o644 if change.original is None else stat.S_IMODE(change.original.st_mode))
                change.temp_inode = inode(info)
            assert_lease()
            stop_clear()
            assert_live_sources(scripts, changes)
            need(control.active() == old, "PROXY_GENERATION_CHANGED")
            need(auth_anchor() == auth, "OWNER_AUTH_DRIFT")
            idle()
            stop_attempted = True
            need(control.rpc("stopProcess", SERVICE, True) is True, "PROXY_STOP_ACK")
            after_stop = control.status()
            need(after_stop["statename"] == "STOPPED" and after_stop.get("pid") == 0, "PROXY_STOP_GENERATION")
            assert_lease()
            put_sources(scripts, changes)
            assert_live_sources(scripts, changes, after=True)
            stop_clear()
            need(control.rpc("startProcess", SERVICE, False) is True, "PROXY_START_ACK")
            successor = ready(control, previous=old)
            assert_live_sources(scripts, changes, after=True)
            need(auth_anchor() == auth, "OWNER_AUTH_DRIFT")
            commit_ready = True
        except Exception as error:
            if not stop_attempted:
                raise
            try:
                active = control.status()
                if active["statename"] in ("RUNNING", "STARTING") and active.get("pid"):
                    recovering = control.active(active)
                    if recovering == old and not any(change.installed for change in changes):
                        raise Hold("HOLD_NATIVE_COGNITION_OLD_PROXY_NEVER_STOPPED") from error
                    need(recovering != old, "ROLLBACK_PROXY_GENERATION")
                    idle()
                    need(control.rpc("stopProcess", SERVICE, True) is True, "ROLLBACK_STOP_ACK")
                deadline = time.monotonic() + 25
                while control.status()["statename"] == "STOPPING" and time.monotonic() < deadline:
                    time.sleep(0.25)
                need(control.status().get("pid") == 0, "ROLLBACK_PROXY_NOT_STOPPED")
                assert_lease()
                restore(scripts, changes)
                stop_clear()
                need(control.rpc("startProcess", SERVICE, False) is True, "ROLLBACK_START_ACK")
                ready(control, previous=old)
            except Exception as rollback:
                if str(rollback) == "HOLD_NATIVE_COGNITION_OLD_PROXY_NEVER_STOPPED":
                    raise
                raise Hold("HOLD_NATIVE_COGNITION_ROLLBACK_RECONCILIATION") from rollback
            raise Hold("HOLD_NATIVE_COGNITION_ROLLBACK_ORIGINAL_READY") from error
        finally:
            for change in changes:
                if change.temp and node(scripts, change.temp) is not None:
                    raw, item = read(scripts, change.temp)
                    owned_candidate = raw == change.candidate and inode(item) == change.temp_inode
                    owned_original = (commit_ready and change.installed and change.original is not None
                                      and raw == change.before and inode(item) == inode(change.original))
                    if owned_candidate or owned_original:
                        os.unlink(change.temp, dir_fd=scripts)
            os.fsync(scripts)
    return {"schema": "NOX_NATIVE_COGNITION_PROXY_ACTIVATED_V1", "request_id": request,
            "source_sha": source, "proxy_previous_generation": old, "proxy_new_generation": successor,
            "proxy_http_200": True, "protected_resonance_still_requires_auth": True,
            "files_sha256": {name: sha256[name] for name in order}, "backup_manifest_sha256": backup_pin,
            "model_restarted": False, "other_services_restarted": False, "s03_source_changed": False,
            "authenticated_dialog_acceptance_verified": False}
