"""Add only the approved NOX cache-maintenance process group to Supervisor."""

from contextlib import ExitStack
from dataclasses import dataclass
import fcntl
import hashlib
import http.client
import os
from pathlib import Path
import re
import select
import socket
import stat
import struct
import time
import xmlrpc.client

from atomic_engram_stage import (
    DIR_FLAGS, FILE_FLAGS, LEASE, Payload, assert_directory, directory, exact_file,
    inode, path_stat, publish, stamp, trusted_directory, unlink_own_inode, verify_lease,
)
from owner_supervisor_background_release import (
    cgroup, config_parse, plain_socket_path, process, read, resolve_socket, trusted_parents,
)


INSTANCE = "60509551"
NAME = "nox-cache-maintenance"
MAIN = Path("/etc/supervisor/supervisord.conf")
INCLUDES = MAIN.parent / "conf.d"
UNIT_NAME = NAME + ".conf"
LOG = Path("/root/nox/logs/nox-cache-maintenance.log")
WORKER_DIR = ("root", "nox", "ops", "cache-maintenance")
WORKERS = ("nox_cache_maintenance.py", "owner_memory_cleanup_entry.py",
           "owner_memory_governor.py", "owner_storage_reclaim.py")
ARGV = ("/usr/bin/python3", "-E", "-s", "-B", "/" + "/".join((*WORKER_DIR, WORKERS[0])))
STOP = ("STOP", "STOP.flag", "stop.flag", ".stop", "program/STOP", "state/STOP",
        "state/STOP.flag", "state/OWNER_MAINTENANCE.flag")
MAX_CFG_BYTES = 256 * 1024
MAX_WORKER_BYTES = 512 * 1024
MAX_PIN_AGE = 180
RUNNABLE = (b"R", b"S", b"D", b"I")
TERMINAL = ("STOPPED", "FATAL", "EXITED")
READ_METHODS = {"getPID": (), "getState": (), "getProcessInfo": (NAME,)}
SCOPED_METHODS = {"reloadConfig": ((), "parse"), "addProcessGroup": ((NAME,), "add"),
                  "stopProcess": ((NAME, True), "rollback_stop"),
                  "removeProcessGroup": ((NAME,), "rollback_remove")}


class Hold(RuntimeError):
    pass


def need(value, reason):
    if not value:
        raise Hold("HOLD_CACHE_ACTIVATION_" + reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def hex_pin(value, length=64):
    return isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) and value != "0" * length


@dataclass(frozen=True)
class OwnerPin:
    request_id: str
    source_commit: str
    observed_at: float
    expires_at: float
    boot_id: str
    pid1_ticks: int
    supervisor_pid: int
    supervisor_ticks: int
    supervisor_argv_sha256: str
    main_sha256: str
    socket_path: str
    include_sha256: tuple[tuple[str, str], ...]
    unit_sha256: str
    worker_sha256: tuple[tuple[str, str], ...]

    def verify(self):
        need(isinstance(self.request_id, str) and re.fullmatch(r"[1-9][0-9]{0,19}", self.request_id)
             and hex_pin(self.source_commit, 40) and isinstance(self.boot_id, str)
             and re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", self.boot_id)
             and type(self.observed_at) in (int, float) and type(self.expires_at) in (int, float)
             and self.observed_at <= time.time() < self.expires_at <= self.observed_at + MAX_PIN_AGE
             and all(type(v) is int and v > 0 for v in (self.pid1_ticks, self.supervisor_pid, self.supervisor_ticks))
             and self.supervisor_ticks >= self.pid1_ticks
             and hex_pin(self.main_sha256) and hex_pin(self.supervisor_argv_sha256)
             and hex_pin(self.unit_sha256), "OWNER_PIN")
        socket_path = plain_socket_path(self.socket_path, MAIN.parent)
        need(str(socket_path) == self.socket_path and len(os.fsencode(socket_path)) <= 103, "SOCKET_PIN")
        need(isinstance(self.worker_sha256, tuple) and len(self.worker_sha256) == len(WORKERS)
             and set(dict(self.worker_sha256)) == set(WORKERS)
             and all(hex_pin(sha) for _, sha in self.worker_sha256)
             and isinstance(self.include_sha256, tuple) and 0 <= len(self.include_sha256) <= 96
             and len(dict(self.include_sha256)) == len(self.include_sha256)
             and all(name != UNIT_NAME and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\.conf", name)
                     and hex_pin(sha) for name, sha in self.include_sha256), "ASSET_PINS")


def payloads(pin, workers, unit):
    need(set(workers) == set(WORKERS), "WORKER_SCOPE")
    result = tuple(Payload(name, (*WORKER_DIR, name), workers[name], dict(pin.worker_sha256)[name])
                   for name in WORKERS)
    config = Payload("unit", (*INCLUDES.parts[1:], UNIT_NAME), unit, pin.unit_sha256)
    for file in (*result, config):
        budget = MAX_CFG_BYTES if file.label == "unit" else MAX_WORKER_BYTES
        need(isinstance(file.data, bytes) and 0 < len(file.data) <= budget
             and digest(file.data) == file.digest, "PAYLOAD_PIN")
    for path in result:
        compile(path.data, path.path[-1], "exec")
    parser = config_parse(unit)
    need(parser.sections() == [f"program:{NAME}"], "UNIT_SCOPE")
    required = {"command": " ".join(ARGV), "directory": "/root/nox", "user": "root",
                "autostart": "true", "autorestart": "unexpected", "startsecs": "2",
                "stopasgroup": "true", "killasgroup": "true"}
    options = dict(parser[f"program:{NAME}"])
    need(all(options.get(k) == v for k, v in required.items()), "UNIT_CONTRACT")
    optional = {"numprocs": {"1"}, "startretries": {"0", "1", "2", "3"}, "exitcodes": {"0"},
                "priority": None, "stopsignal": {"TERM"},
                "stopwaitsecs": {"5", "10", "12", "15"}, "redirect_stderr": {"true"},
                "stdout_logfile": {"/dev/stdout", str(LOG)}, "stdout_logfile_maxbytes": {"0", "1MB"},
                "stdout_logfile_backups": {"2"}}
    need(all((key == "priority" and re.fullmatch(r"[1-9][0-9]{1,3}", value))
             or (key in optional and key != "priority" and value in optional[key])
             for key, value in options.items() if key not in required), "UNIT_OPTIONS")
    if options.get("stdout_logfile") == str(LOG):
        need(options.get("stdout_logfile_maxbytes") == "1MB"
             and options.get("stdout_logfile_backups") == "2", "LOG_BOUND")
    return (*result, config)


def stop_clear(root):
    for path in (*(root / "root/nox" / item for item in STOP), root / "workspace/NOX_STOP"):
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        return False
    return True


def config_inventory(pin, directory_path):
    expected = dict(pin.include_sha256)
    names = {file.name for file in directory_path.iterdir() if file.name.endswith(".conf")}
    need(names - {UNIT_NAME} == set(expected), "INCLUDE_CENSUS")
    for name, sha in expected.items():
        raw = read(directory_path / name, MAX_CFG_BYTES, rooted=True)
        need(digest(raw) == sha, "INCLUDE_PIN")
        assert_scope(raw)


def assert_scope(raw):
    conf = config_parse(raw)
    for section in conf.sections():
        kind, sep, name = section.partition(":")
        need(not sep or name != NAME, "OTHER_CONFIG_OWNS_NAME")
        if kind == "group":
            need(NAME not in [part.strip() for part in conf[section].get("programs", "").split(",")],
                 "OTHER_CONFIG_OWNS_GROUP")


class NativeSupervisor:
    """Exact root Unix peer. Each method has a fixed argument and action scope."""

    def __init__(self, pin, approve):
        self.pin = pin
        self.approve = approve

    def endpoint(self):
        pin = self.pin
        labels = {os.environ[name] for name in ("VAST_CONTAINERLABEL", "CONTAINER_ID") if os.environ.get(name)}
        need((os.geteuid(), os.getegid()) == (0, 0)
             and labels and labels <= {INSTANCE, "C." + INSTANCE}, "INSTANCE_SCOPE")
        boot = read(Path("/proc/sys/kernel/random/boot_id"), 128).decode("ascii").strip()
        need(boot == pin.boot_id and process(1)[:2] == (pin.pid1_ticks, 0), "HOST_EPOCH")
        main = read(MAIN, MAX_CFG_BYTES, rooted=True)
        need(digest(main) == pin.main_sha256, "MAIN_PIN")
        assert_scope(main)
        conf = config_parse(main)
        http, ctl = conf["unix_http_server"], conf["supervisorctl"]
        need(set(http) <= {"file", "chmod", "chown"} and set(ctl) == {"serverurl"}
             and int(http.get("chmod", "0700"), 8) == 0o700
             and http.get("chown", "root:root") in ("root:root", "0:0")
             and not conf.has_section("inet_http_server")
             and conf["rpcinterface:supervisor"]["supervisor.rpcinterface_factory"] ==
             "supervisor.rpcinterface:make_main_rpcinterface"
             and conf["include"]["files"].split() in (["conf.d/*.conf"], [str(INCLUDES / "*.conf")]),
             "MAIN_SCOPE")
        configured = resolve_socket(plain_socket_path(http["file"], MAIN.parent))
        url = ctl["serverurl"]
        need(url.startswith("unix://") and configured == Path(pin.socket_path) ==
             resolve_socket(plain_socket_path(url[7:], MAIN.parent)), "SOCKET_PATH")
        meta = configured.lstat()
        need(stat.S_ISSOCK(meta.st_mode) and (meta.st_uid, meta.st_gid) == (0, 0)
             and meta.st_nlink == 1 and stat.S_IMODE(meta.st_mode) == 0o700, "SOCKET_SCOPE")
        pid = pin.supervisor_pid
        ticks, parent, _, state = process(pid)
        need(ticks == pin.supervisor_ticks and parent == (0 if pid == 1 else 1) and state in RUNNABLE
             and cgroup(pid) == cgroup("self"), "DAEMON_GENERATION")
        raw = read(Path(f"/proc/{pid}/cmdline"), 16 * 1024)
        argv = raw.rstrip(b"\0").split(b"\0")
        daemon = [arg for arg in argv[:2] if arg.startswith(b"/") and arg.endswith(b"/supervisord")]
        need(digest(raw) == pin.supervisor_argv_sha256 and len(daemon) == 1
             and any(argv[i:i + 2] in ([b"-c", os.fsencode(MAIN)], [b"--configuration", os.fsencode(MAIN)])
                     or arg == b"--configuration=" + os.fsencode(MAIN) for i, arg in enumerate(argv)),
             "DAEMON_COMMAND")
        binary = Path(f"/proc/{pid}/exe").stat()
        need(stat.S_ISREG(binary.st_mode) and binary.st_uid == binary.st_gid == 0
             and not binary.st_mode & 0o022, "DAEMON_BINARY")
        return stamp(meta)

    def inspect_configs(self):
        self.endpoint()
        config_inventory(self.pin, INCLUDES)

    def verify_log(self):
        trusted_parents(LOG)
        for path in (LOG, *(LOG.with_name(LOG.name + f".{number}") for number in (1, 2))):
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            need(stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 0
                 and not info.st_mode & 0o022 and info.st_nlink == 1, "LOG_SCOPE")

    def rpc(self, method, params, before=None):
        approved = SCOPED_METHODS.get(method)
        need((approved is None and method in READ_METHODS and params == READ_METHODS[method] and before is None)
             or (approved is not None and params == approved[0] and callable(before)), "RPC_SCOPE")
        self.pin.verify()
        original = self.endpoint()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel, ExitStack() as stack:
            channel.settimeout(20)
            channel.connect(self.pin.socket_path)
            creds = struct.unpack("3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            need(creds == (self.pin.supervisor_pid, 0, 0), "RPC_PEER")
            peer = os.pidfd_open(creds[0])
            stack.callback(os.close, peer)
            poll = select.poll()
            poll.register(peer, select.POLLIN)
            if approved is not None:
                before()
                need(self.approve(self.pin, approved[1]) is True, "OWNER_RPC_GRANT")
            need(not poll.poll(0) and self.endpoint() == original, "RPC_PEER_CHANGED")
            http = http.client.HTTPConnection("localhost", timeout=20)
            stack.callback(http.close)
            http.sock = channel
            body = xmlrpc.client.dumps(params, methodname="supervisor." + method).encode()
            http.request("POST", "/RPC2", body, {"Content-Type": "text/xml", "Connection": "close"})
            reply = http.getresponse()
            need(reply.status == 200 and not reply.chunked and type(reply.length) is int
                 and 0 < reply.length <= 32 * 1024, "RPC_HTTP")
            raw = reply.read()
            need(b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper(), "RPC_XML")
            need(not poll.poll(0) and self.endpoint() == original, "RPC_READBACK")
            values, _ = xmlrpc.client.loads(raw)
            need(len(values) == 1, "RPC_RESULT")
            return values[0]

    def lookup(self):
        try:
            row = self.rpc("getProcessInfo", (NAME,))
        except xmlrpc.client.Fault as fault:
            # Supervisor Faults.BAD_NAME is the exact missing-program response.
            if fault.faultCode == 10:
                return None
            raise
        need(isinstance(row, dict) and row.get("name") == row.get("group") == NAME
             and row.get("statename") in (*TERMINAL, "STARTING", "RUNNING", "BACKOFF", "STOPPING")
             and type(row.get("pid")) is int and row["pid"] >= 0, "RPC_PROGRAM")
        return row["statename"], row["pid"]

    def exact_process(self, pid):
        need(pid > 1, "WORKER_PID")
        before = process(pid)
        root = Path(f"/proc/{pid}")
        argv = read(root / "cmdline", 16 * 1024)
        env = read(root / "environ", MAX_CFG_BYTES).split(b"\0")
        need(before[0] >= self.pin.supervisor_ticks and before[1:3] == (self.pin.supervisor_pid, pid)
             and before[3] in RUNNABLE and cgroup(pid) == cgroup("self")
             and argv == b"\0".join(map(os.fsencode, ARGV)) + b"\0"
             and [row for row in env if row.startswith(b"SUPERVISOR_PROCESS_NAME=")]
             == [f"SUPERVISOR_PROCESS_NAME={NAME}".encode()]
             and [row for row in env if row.startswith(b"SUPERVISOR_GROUP_NAME=")]
             == [f"SUPERVISOR_GROUP_NAME={NAME}".encode()]
             and process(pid)[:3] == before[:3], "WORKER_GENERATION")
        return before[0]


def activate_cache_maintenance(pin, *, workers, unit, authorize, root=Path("/"), host=None):
    """Install pinned bytes and add only the cache group using an external signed grant."""
    need(isinstance(pin, OwnerPin) and callable(authorize), "EXTERNAL_OWNER_REQUIRED")
    pin.verify()
    need(authorize(pin, "activate") is True, "OWNER_GRANT")
    need(host is not None or root == Path("/"), "PRODUCTION_ROOT")
    native = NativeSupervisor(pin, authorize) if host is None else host
    assets = payloads(pin, workers, unit)
    with ExitStack() as stack:
        root_fd = os.open(root, DIR_FLAGS)
        stack.callback(os.close, root_fd)
        trusted_directory(os.fstat(root_fd))
        lease_dir = directory(stack, root_fd, LEASE[:-1])
        lease = os.open(LEASE[-1], FILE_FLAGS, dir_fd=lease_dir)
        stack.callback(os.close, lease)
        verify_lease(lease_dir, lease)
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise Hold("HOLD_CACHE_ACTIVATION_OWNER_BUSY") from error
        ops = directory(stack, root_fd, WORKER_DIR[:-1])
        inc = directory(stack, root_fd, assets[-1].path[:-1])
        native.inspect_configs()
        need(stop_clear(root), "OWNER_STOP")
        need(native.rpc("getPID", ()) == pin.supervisor_pid, "RPC_DAEMON_PID")
        state = native.rpc("getState", ())
        need(isinstance(state, dict) and state.get("statename") == "RUNNING", "DAEMON_NOT_RUNNING")
        existing = native.lookup()
        folder = None
        own_dir = None
        created = []
        known = {}
        add_attempted = False
        added = False
        parsed = False

        def check_files(allow_stop=False):
            pin.verify()
            verify_lease(lease_dir, lease)
            assert_directory(root_fd, LEASE[:-1], lease_dir)
            assert_directory(root_fd, WORKER_DIR, folder)
            assert_directory(root_fd, assets[-1].path[:-1], inc)
            need(allow_stop or stop_clear(root), "OWNER_STOP")
            for item in assets:
                parent = inc if item.label == "unit" else folder
                need(exact_file(parent, item.path[-1], item) == known[item.label], "DESTINATION_CAS")

        def check():
            check_files()
            native.inspect_configs()
            native.verify_log()

        def rollback_preflight():
            check_files(allow_stop=True)
            native.inspect_configs()
            observed = native.lookup()
            need(observed is not None, "ROLLBACK_GROUP_MISSING")
            if observed[1] > 0:
                native.exact_process(observed[1])

        try:
            entry = path_stat(ops, WORKER_DIR[-1])
            if entry is None:
                need(existing is None, "ACTIVE_GROUP_ALREADY_EXISTS")
                os.mkdir(WORKER_DIR[-1], 0o755, dir_fd=ops)
                own_dir = path_stat(ops, WORKER_DIR[-1])
                need(own_dir is not None, "WORKER_DIRECTORY")
                os.fsync(ops)
            folder = directory(stack, root_fd, WORKER_DIR)
            need(own_dir is None or inode(os.fstat(folder)) == inode(own_dir), "DIRECTORY_CAS")
            for item in assets:
                parent = inc if item.label == "unit" else folder
                known[item.label] = exact_file(parent, item.path[-1], item)
            already = all(value is not None for value in known.values())
            if existing is not None:
                need(already and existing[0] == "RUNNING", "PREEXISTING_GROUP_UNPROVEN")
            else:
                for item in assets:
                    if known[item.label] is None:
                        target = inc if item.label == "unit" else folder
                        known[item.label] = publish(target, item, created, check_files)
                check()
                need(native.lookup() is None, "GROUP_APPEARED")
                parsed = True
                diff = native.rpc("reloadConfig", (), check)
                need(diff == [[[NAME], [], []]], "ADDITIVE_DIFF_REQUIRED")
                add_attempted = True
                added = native.rpc("addProcessGroup", (NAME,), check) is True
                need(added, "ADD_NOT_CONFIRMED")

            deadline = time.monotonic() + 12
            while True:
                observed = native.lookup()
                if observed and observed[0] == "RUNNING":
                    pid = observed[1]
                    ticks = native.exact_process(pid)
                    check()
                    need(native.lookup() == observed and native.exact_process(pid) == ticks,
                         "WORKER_READBACK_GENERATION")
                    break
                need(time.monotonic() < deadline and observed and observed[0] not in ("EXITED", "FATAL"),
                     "WORKER_START_UNVERIFIED")
                time.sleep(0.2)
            return {"schema": "NOX_CACHE_MAINTENANCE_ACTIVATION_V1", "instance_id": int(INSTANCE),
                    "request_id": pin.request_id, "source_commit": pin.source_commit, "group": NAME,
                    "pid": pid, "start_ticks": ticks, "unit_sha256": pin.unit_sha256,
                    "installed": True, "running": True, "added": added}
        except BaseException as error:
            try:
                if add_attempted and not added:
                    need(native.lookup() is None, "UNCONFIRMED_ADD")
                if added:
                    rollback_preflight()
                    row = native.lookup()
                    if row[0] not in TERMINAL:
                        need(native.rpc("stopProcess", (NAME, True), rollback_preflight) is True, "ROLLBACK_STOP")
                    need(native.rpc("removeProcessGroup", (NAME,), rollback_preflight) is True
                         and native.lookup() is None, "ROLLBACK_REMOVE")
                files = {item.path[-1]: item for item in assets}
                for parent, name, ident in reversed(created):
                    actual = path_stat(parent, name)
                    if actual is None:
                        continue
                    need(inode(actual) == ident and exact_file(parent, name, files[name]) is not None
                         and unlink_own_inode(parent, name, ident), "ROLLBACK_FILE_OWNERSHIP")
                if own_dir is not None:
                    current = path_stat(ops, WORKER_DIR[-1])
                    if current is not None:
                        need(inode(current) == inode(own_dir), "ROLLBACK_DIRECTORY_OWNERSHIP")
                        os.rmdir(WORKER_DIR[-1], dir_fd=ops)
                        os.fsync(ops)
                if parsed and any(name == UNIT_NAME for _, name, _ in created):
                    after = native.rpc("reloadConfig", (), native.inspect_configs)
                    need(isinstance(after, list) and len(after) == 1 and isinstance(after[0], list)
                         and len(after[0]) == 3
                         and all(isinstance(row, list) and NAME not in row for row in after[0]),
                         "ROLLBACK_PENDING_CONFIG")
            except BaseException as recovery:
                raise Hold("HOLD_CACHE_ACTIVATION_RECONCILE") from recovery
            raise error
