#!/usr/bin/env python3
"""NOX lifeline: independent bounded safety guard, not a second dispatcher.

Controls only explicitly named, locally approved Supervisor programs.
No shell, external network, model promotion, training restarts or deletions.
Python 3.9+ / Linux. Install on the existing OneHost only after local acceptance.
"""
import argparse
import datetime as dt
import fcntl
import glob
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import stat
import tempfile
import time
import xmlrpc.client
import struct

SCHEMA = "NOX_LIFELINE_V2"
try:
    SUPERVISOR_SOCKET_PATH = __NOX_SUPERVISOR_SOCKET_PATH__
    SUPERVISOR_IDENTITY_PIN = __NOX_SUPERVISOR_IDENTITY_PIN__
    SUPERVISOR_PID = SUPERVISOR_IDENTITY_PIN["pid"]
    SUPERVISOR_START_TICKS = SUPERVISOR_IDENTITY_PIN["start_ticks"]
    SUPERVISOR_ARGV_SHA256 = SUPERVISOR_IDENTITY_PIN["argv_sha256"]
    SUPERVISOR_EXE_PATH = SUPERVISOR_IDENTITY_PIN["exe"]
    SUPERVISOR_UID = SUPERVISOR_IDENTITY_PIN["credentials"]["uid"]
    SUPERVISOR_GID = SUPERVISOR_IDENTITY_PIN["credentials"]["gid"]
    SUPERVISOR_SOCKET_PIN = __NOX_SUPERVISOR_SOCKET_PIN__
except NameError:
    # Source-only builds remain non-operational until owner installation pins
    # the exact active daemon and UDS endpoint.
    SUPERVISOR_SOCKET_PATH = ""
    SUPERVISOR_IDENTITY_PIN = {}
    SUPERVISOR_PID = 0
    SUPERVISOR_START_TICKS = 0
    SUPERVISOR_ARGV_SHA256 = ""
    SUPERVISOR_EXE_PATH = ""
    SUPERVISOR_UID = SUPERVISOR_GID = -1
    SUPERVISOR_SOCKET_PIN = {}
SERVICES = frozenset({
    "nox-dispatcher-t855u", "nox-priority-scheduler",
    "nox-selfheal", "nox-gpu-watchdog-t865u",
})
STOP_FILES = (
    "/root/nox/STOP", "/root/nox/STOP.flag", "/root/nox/stop.flag",
    "/root/nox/.stop", "/root/nox/program/STOP",
    "/workspace/NOX_STOP", "/root/nox/state/STOP", "/root/nox/state/STOP.flag",
    "/root/nox/state/OWNER_MAINTENANCE.flag",
)
STATUS = re.compile(r"^([a-zA-Z0-9_.:-]+)\s+([A-Z]+)(?:\s+pid\s+([0-9]+))?")
REPAIRABLE = frozenset(("STOPPED", "EXITED"))
SERVICE_STATES = {"RUNNING", "STOPPED", "STARTING", "STOPPING", "BACKOFF", "EXITED", "FATAL", "UNKNOWN"}
MAX_EVENT_ROWS = 100
CGROUP_MEMORY_CURRENT = Path("/sys/fs/cgroup/memory.current")
CGROUP_MEMORY_MAX = Path("/sys/fs/cgroup/memory.max")
MEMORY_READ_MAX_BYTES = 64
MEMORY_FLOOR_BYTES = 2 * 1024 ** 3
MAX_CGROUP_COUNTER = (1 << 64) - 1

def policy_check(value):
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ValueError("HOLD_POLICY_SCHEMA")
    if type(value.get("enabled")) is not bool:
        raise ValueError("HOLD_POLICY_ENABLED_TYPE")
    items = value.get("services")
    if not isinstance(items, list) or not 1 <= len(items) <= len(SERVICES):
        raise ValueError("HOLD_POLICY_SERVICES")
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"name", "restart"}:
            raise ValueError("HOLD_POLICY_SERVICE_FIELDS")
        name = item["name"]
        if name not in SERVICES or name in seen or type(item["restart"]) is not bool:
            raise ValueError("HOLD_POLICY_UNAPPROVED_SERVICE")
        seen.add(name)
    for field,lo,hi in (
        ("poll_seconds",15,600),("consecutive_failures",2,10),
        ("cooldown_seconds",60,86400),("daily_limit",0,3)):
        n = value.get(field)
        if type(n) is not int or not lo <= n <= hi:
            raise ValueError("HOLD_POLICY_LIMIT_"+field.upper())
    return value

def policy_load(path):
    # A model, public repository or user-supplied URL is never a policy source.
    if path.is_symlink():
        raise ValueError("HOLD_POLICY_SYMLINK")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 32768 or info.st_nlink != 1:
            raise ValueError("HOLD_POLICY_FILE")
        if (info.st_mode & 0o022) or info.st_uid not in (0, os.geteuid()):
            raise ValueError("HOLD_POLICY_PERMISSIONS")
        # Bound the actual read, not just the pre-read size: another writer
        # can grow a file between fstat and JSON parsing.
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            raw = stream.read(32769)
        if len(raw) > 32768:
            raise ValueError("HOLD_POLICY_FILE")
    finally:
        if fd >= 0:
            os.close(fd)
    try:
        # A duplicate 'enabled'/'restart' key must not silently replace an
        # earlier owner value. JSON NaN/Infinity or fractional policy numbers
        # are not a supported admission format.
        value = json.loads(raw, object_pairs_hook=_unique_state_pairs,
                           parse_constant=_reject_state_nonfinite,
                           parse_float=_reject_state_nonfinite)
    except (ValueError, UnicodeError, TypeError) as exc:
        raise ValueError("HOLD_POLICY_CORRUPT") from exc
    return policy_check(value)

def observer_only_policy(policy):
    """Force a strict no-restart view, regardless of the persisted policy."""
    forced = dict(policy)
    forced["enabled"] = False
    forced["services"] = [dict(item, restart=False) for item in policy["services"]]
    return forced

def atomic(path, obj):
    if path.is_symlink():
        raise ValueError("HOLD_STATE_SYMLINK")
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".lifeline-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as writer:
            json.dump(obj, writer, sort_keys=True, ensure_ascii=False, allow_nan=False)
            writer.write("\n")
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def _unique_state_pairs(pairs):
    """A duplicate persisted key can erase a previous repair attempt."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("HOLD_STATE_DUPLICATE_KEY")
        result[key] = value
    return result


def _reject_state_nonfinite(value):
    raise ValueError("HOLD_STATE_NONFINITE")


def resource_limit_receipt():
    """Read the bootstrap's sanitized RLIMIT report without exposing its environment."""
    raw = os.environ.get("NOX_LIFELINE_RESOURCE_LIMITS")
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        raise ValueError("HOLD_RESOURCE_LIMIT_RECEIPT") from None
    expected = {"address_space_bytes", "open_files", "core_bytes", "file_size_bytes",
                "nice", "hard_cgroup_memory_limit", "cpu_quota", "cpu_scheduling"}
    if (not isinstance(value, dict) or set(value) != expected or
            type(value.get("address_space_bytes")) is not int or
            not 0 < value["address_space_bytes"] <= 512 * 1024**2 or
            type(value.get("open_files")) is not int or
            not 1 <= value["open_files"] <= 128 or
            value.get("core_bytes") != 0 or
            value.get("file_size_bytes") != 8 * 1024**2 or
            type(value.get("nice")) is not int or value["nice"] < 10 or
            value.get("hard_cgroup_memory_limit") != "unsupported_by_supervisor" or
            value.get("cpu_quota") != "unsupported_by_supervisor" or
            value.get("cpu_scheduling") != "nice_only_no_hard_quota"):
        raise ValueError("HOLD_RESOURCE_LIMIT_RECEIPT")
    return value


def _read_cgroup_counter(path, *, allow_unlimited=False):
    """Read one small cgroup-v2 scalar without following symlinks or unbounded I/O."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                     getattr(os, "O_CLOEXEC", 0))
    except OSError:
        return None
    try:
        raw = os.read(fd, MEMORY_READ_MAX_BYTES + 1)
    except OSError:
        return None
    finally:
        os.close(fd)
    if not raw or len(raw) > MEMORY_READ_MAX_BYTES:
        return None
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if not raw or b"\n" in raw or b"\r" in raw:
        return None
    if allow_unlimited and raw == b"max":
        return "max"
    if not re.fullmatch(rb"(?:0|[1-9][0-9]{0,19})", raw):
        return None
    value = int(raw)
    return value if value <= MAX_CGROUP_COUNTER else None


def cgroup_memory_snapshot():
    """Report raw cgroup-v2 RAM headroom; missing evidence fails closed in the flag."""
    current = _read_cgroup_counter(CGROUP_MEMORY_CURRENT)
    maximum = _read_cgroup_counter(CGROUP_MEMORY_MAX, allow_unlimited=True)
    if type(current) is int and type(maximum) is int:
        headroom = maximum - current
        status = "OK" if headroom >= 0 else "INCONSISTENT"
        below_floor = headroom < MEMORY_FLOOR_BYTES
    else:
        headroom = None
        status = "UNKNOWN"
        # An unavailable or unlimited limit does not prove the 2 GiB floor.
        below_floor = True
    return {"memory.current": current,
            "memory.max": maximum,
            "raw_headroom_bytes": headroom,
            "below_2GiB": below_floor,
            "memory_floor_bytes": MEMORY_FLOOR_BYTES,
            "severity": "CRITICAL" if below_floor else "OK",
            "status": status}


def read_state(path):
    # Missing state is a first-install bootstrap. Existing unreadable state must
    # HOLD; resetting its retry history could silently reopen the start budget.
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise ValueError("HOLD_STATE_ACCESS") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 262144 or info.st_nlink != 1:
            raise ValueError("HOLD_STATE_FILE")
        # Repair attempts are a security boundary: a mutable or foreign-owned
        # history file could erase hourly/daily limits and authorize extra starts.
        if (info.st_mode & 0o022) or info.st_uid not in (0, os.geteuid()):
            raise ValueError("HOLD_STATE_PERMISSIONS")
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            fd = -1
            try:
                obj = json.load(stream, object_pairs_hook=_unique_state_pairs,
                                parse_constant=_reject_state_nonfinite)
            except (ValueError, UnicodeError) as exc:
                raise ValueError("HOLD_STATE_CORRUPT") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("HOLD_STATE_CORRUPT") from exc
    finally:
        if fd >= 0:
            os.close(fd)
    if not isinstance(obj, dict) or ("services" in obj and not isinstance(obj["services"], dict)):
        raise ValueError("HOLD_STATE_STRUCTURE")
    services = obj.get("services", {})
    # Preserve persisted restart history: never reset a malformed service row.
    if any(not isinstance(name, str) or not isinstance(row, dict)
           for name, row in services.items()):
        raise ValueError("HOLD_STATE_SERVICE_ROW")
    return obj

def stopped():
    # The owner inspector accepts /state/STOP and /state/STOP.flag; lifeline
    # must honor the same manual fences. lstat also fails CLOSED on EACCES
    # (Path.exists/is_symlink may otherwise report both false).
    for name in STOP_FILES:
        try:
            os.lstat(name)
        except FileNotFoundError:
            continue
        except OSError:
            return True
        else:
            return True
    # The original owner's maintenance lease also inhibits repair, even if
    # the legacy flag is absent during an interrupted maintenance operation.
    lease = Path("/root/nox/state/owner_maintenance.lock")
    try:
        fd = os.open(lease, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return False
    except OSError:
        return True
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True
    finally:
        os.close(fd)

class _UnixHTTPConnection(http.client.HTTPConnection):
    def connect(self):
        if not SUPERVISOR_SOCKET_PATH:
            raise OSError("UDS endpoint is not pinned")
        path = Path(SUPERVISOR_SOCKET_PATH)
        parent_chain = []
        for parent in (path.parent, *path.parent.parents):
            meta = parent.lstat()
            if (stat.S_ISLNK(meta.st_mode) or not stat.S_ISDIR(meta.st_mode) or
                    meta.st_uid != 0 or meta.st_mode & 0o022):
                raise OSError("unsafe Supervisor socket parent")
            parent_chain.append({"path": str(parent), "device": meta.st_dev,
                                 "inode": meta.st_ino, "mode": meta.st_mode,
                                 "uid": meta.st_uid, "gid": meta.st_gid})
        if parent_chain != SUPERVISOR_IDENTITY_PIN.get("socket_parent_chain"):
            raise OSError("Supervisor socket parent pin changed")
        before = path.lstat()
        if (not stat.S_ISSOCK(before.st_mode) or before.st_mode & 0o077 or
                before.st_nlink != 1):
            raise OSError("unsafe Supervisor socket")
        if before.st_uid != SUPERVISOR_UID or before.st_gid != SUPERVISOR_GID:
            raise OSError("Supervisor socket credentials changed")
        socket_snapshot = {"device": before.st_dev, "inode": before.st_ino,
                           "mode": stat.S_IMODE(before.st_mode), "uid": before.st_uid,
                           "gid": before.st_gid, "nlink": before.st_nlink,
                           "mtime_ns": before.st_mtime_ns, "ctime_ns": before.st_ctime_ns}
        if socket_snapshot != SUPERVISOR_SOCKET_PIN:
            raise OSError("Supervisor socket inode pin changed")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(5)
            sock.connect(SUPERVISOR_SOCKET_PATH)
            peer = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if peer[0] != SUPERVISOR_PID or peer[1] != SUPERVISOR_UID or peer[2] != SUPERVISOR_GID:
                raise OSError("unexpected Supervisor peer")
            after = path.lstat()
            after_chain = []
            for parent in (path.parent, *path.parent.parents):
                meta = parent.lstat()
                after_chain.append({"path": str(parent), "device": meta.st_dev,
                                    "inode": meta.st_ino, "mode": meta.st_mode,
                                    "uid": meta.st_uid, "gid": meta.st_gid})
            if any(getattr(before, key) != getattr(after, key) for key in
                   ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink")) or \
                    parent_chain != after_chain or after_chain != \
                    SUPERVISOR_IDENTITY_PIN.get("socket_parent_chain"):
                raise OSError("Supervisor socket changed")
        except BaseException:
            sock.close()
            raise
        self.peer = peer
        self.sock = sock


class _UnixTransport(xmlrpc.client.Transport):
    def make_connection(self, host):
        if self._connection and self._connection[0] == host and self._connection[1].sock:
            return self._connection[1]
        conn = _UnixHTTPConnection("supervisor.local", timeout=5)
        self._connection = (host, conn)
        return conn


def _supervisor_row(name):
    if name not in SERVICES or not SUPERVISOR_IDENTITY_PIN:
        raise ValueError("HOLD_SUPERVISOR_IDENTITY_UNPINNED")
    try:
        _verify_supervisor_identity()
        transport = _UnixTransport()
        proxy = xmlrpc.client.ServerProxy("http://supervisor.local/RPC2",
                                          transport=transport, allow_none=False)
        try:
            if (proxy.supervisor.getAPIVersion() != "3.0" or
                    proxy.supervisor.getState() != {"statecode": 1, "statename": "RUNNING"} or
                    proxy.supervisor.getPID() != SUPERVISOR_PID or
                    hashlib.sha256(proxy.supervisor.getIdentification().encode()).hexdigest() !=
                    SUPERVISOR_IDENTITY_PIN["identification_sha256"]):
                raise ValueError("HOLD_SUPERVISOR_RPC_IDENTITY")
            row = proxy.supervisor.getProcessInfo(name)
            peer = transport._connection[1].peer
            if peer != (SUPERVISOR_PID, SUPERVISOR_UID, SUPERVISOR_GID):
                raise ValueError("HOLD_SUPERVISOR_RPC_PEER")
        finally:
            proxy.close()
        _verify_supervisor_identity()
        if (not isinstance(row, dict) or row.get("name") != name or
                row.get("group") != name):
            raise ValueError("HOLD_SUPERVISOR_RPC_ROW")
        return row
    except (OSError, IndexError, ValueError, xmlrpc.client.Error):
        raise


def _bounded_proc_read(path, limit):
    with open(path, "rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("HOLD_PROC_IDENTITY_TOO_LARGE")
    return raw


def _runtime_file_snapshot(path, max_size=64 * 1024**2, require_exec=True):
    path = Path(path)
    for parent in (path.parent, *path.parent.parents):
        meta = parent.lstat()
        if (stat.S_ISLNK(meta.st_mode) or not stat.S_ISDIR(meta.st_mode) or
                meta.st_uid != 0 or meta.st_mode & 0o022):
            raise ValueError("HOLD_SYSTEMCTL_PARENT_UNSAFE")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or
                before.st_mode & 0o022 or (require_exec and not before.st_mode & 0o111) or
                before.st_size <= 0 or before.st_size > max_size):
            raise ValueError("HOLD_SYSTEMCTL_FILE_UNSAFE")
        digest = hashlib.sha256()
        total = 0
        while total <= max_size:
            chunk = os.read(fd, min(65536, max_size + 1 - total))
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
        after = os.fstat(fd)
        leaf = path.lstat()
        fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_uid", "st_gid",
                  "st_size", "st_mtime_ns", "st_ctime_ns")
        if (total != before.st_size or total > max_size or
                any(getattr(before, key) != getattr(after, key) or
                    getattr(after, key) != getattr(leaf, key) for key in fields)):
            raise ValueError("HOLD_SYSTEMCTL_CHANGED_DURING_READ")
    finally:
        os.close(fd)
    return {"path": str(path), "device": before.st_dev, "inode": before.st_ino,
            "mode": stat.S_IMODE(before.st_mode), "nlink": before.st_nlink,
            "uid": before.st_uid, "gid": before.st_gid, "size": before.st_size,
            "mtime_ns": before.st_mtime_ns, "ctime_ns": before.st_ctime_ns,
            "sha256": digest.hexdigest()}


def _runtime_unix_listener():
    raw = _bounded_proc_read("/proc/net/unix", 2 * 1024**2)
    paths = {SUPERVISOR_SOCKET_PATH,
             SUPERVISOR_IDENTITY_PIN.get("configured_socket_path", SUPERVISOR_SOCKET_PATH)}
    exact_path_rows = []
    for line in raw.decode("utf-8", "strict").splitlines()[1:]:
        fields = line.split()
        if len(fields) < 7:
            continue
        path = fields[7] if len(fields) > 7 else ""
        if path not in paths:
            continue
        try:
            flags, socket_type, state, inode = (
                int(fields[3], 16), int(fields[4], 16), fields[5], int(fields[6]))
        except ValueError:
            raise ValueError("HOLD_SUPERVISOR_LISTENER_ROW_INVALID")
        exact_path_rows.append({"inode": inode, "path": path, "flags": fields[3],
                                "socket_type": fields[4], "state": state,
                                "flags_value": flags, "type_value": socket_type})
    if len(exact_path_rows) != 1:
        raise ValueError("HOLD_SUPERVISOR_LISTENER_ROW")
    row = exact_path_rows[0]
    if row["type_value"] != 0x0001 or row["state"] != "01" or not row["flags_value"] & 0x10000:
        raise ValueError("HOLD_SUPERVISOR_LISTENER_NOT_LISTENING")
    listener_row = {"inode": row["inode"], "path": row["path"],
                    "flags": row["flags"], "socket_type": row["socket_type"],
                    "state": row["state"]}
    try:
        entries = list(os.scandir(f"/proc/{SUPERVISOR_PID}/fd"))
    except OSError as exc:
        raise ValueError("HOLD_SUPERVISOR_FD_TABLE") from exc
    if len(entries) > 4096:
        raise ValueError("HOLD_SUPERVISOR_FD_LIMIT")
    fds = []
    for entry in entries:
        try:
            if os.readlink(entry.path) == f"socket:[{row['inode']}]":
                fds.append(entry.name)
        except OSError:
            continue
    if len(fds) != 1:
        raise ValueError("HOLD_SUPERVISOR_LISTENER_FD")
    return {**listener_row, "owner_pid": SUPERVISOR_PID, "fd": fds[0]}


def _proc_identity(pid):
    raw = _bounded_proc_read(f"/proc/{pid}/stat", 8192)
    boundary = raw.rfind(b") ")
    ticks = int(raw[boundary + 2:].split()[19])
    status = _bounded_proc_read(f"/proc/{pid}/status", 65536)
    uid_rows = [line.split()[1:] for line in status.splitlines() if line.startswith(b"Uid:")]
    gid_rows = [line.split()[1:] for line in status.splitlines() if line.startswith(b"Gid:")]
    if len(uid_rows) != 1 or len(gid_rows) != 1 or len(uid_rows[0]) != 4 or len(gid_rows[0]) != 4:
        raise ValueError("HOLD_SUPERVISOR_CREDENTIALS")
    cmd = _bounded_proc_read(f"/proc/{pid}/cmdline", 16384)
    exe = os.readlink(f"/proc/{pid}/exe")
    cgroup = _bounded_proc_read(f"/proc/{pid}/cgroup", 8192)
    rows = [line.split(b":", 2)[2] for line in cgroup.splitlines()
            if line.startswith(b"0::") and len(line.split(b":", 2)) == 3]
    if len(rows) != 1:
        raise ValueError("HOLD_SUPERVISOR_CGROUP")
    rel = rows[0].decode("utf-8", "strict")
    target = (Path("/sys/fs/cgroup") / rel.lstrip("/")).resolve(strict=True)
    if os.path.commonpath(("/sys/fs/cgroup", str(target))) != "/sys/fs/cgroup":
        raise ValueError("HOLD_SUPERVISOR_CGROUP_ESCAPE")
    return {"pid": pid, "start_ticks": ticks, "uid": int(uid_rows[0][1]),
            "gid": int(gid_rows[0][1]), "cmdline": cmd, "exe": exe,
            "cgroup_path": str(target)}


def _verify_supervisor_identity():
    pin = SUPERVISOR_IDENTITY_PIN
    identity = _proc_identity(SUPERVISOR_PID)
    expected = pin.get("cgroup", {}).get("cgroup_path")
    if (identity["start_ticks"] != SUPERVISOR_START_TICKS or
            identity["uid"] != SUPERVISOR_UID or identity["gid"] != SUPERVISOR_GID or
            identity["exe"] != SUPERVISOR_EXE_PATH or
            hashlib.sha256(identity["cmdline"]).hexdigest() != SUPERVISOR_ARGV_SHA256 or
            identity["cgroup_path"] != expected):
        raise ValueError("HOLD_SUPERVISOR_PROCESS_IDENTITY")
    if _runtime_file_snapshot(identity["exe"]) != pin["executable"]:
        raise ValueError("HOLD_SUPERVISOR_EXECUTABLE_PIN")
    args = identity["cmdline"].rstrip(b"\0").split(b"\0")
    for flag in (b"-c", b"--configuration"):
        if flag in args:
            idx = args.index(flag)
            if idx + 1 >= len(args) or args[idx + 1].decode() != "/etc/supervisor/supervisord.conf":
                raise ValueError("HOLD_SUPERVISOR_CONFIG_ARG")
    if _runtime_file_snapshot(pin["script"]["path"]) != pin["script"]:
        raise ValueError("HOLD_SUPERVISOR_SCRIPT_PIN")
    for config in pin["config_inputs"]:
        if _runtime_file_snapshot(config["path"], max_size=262144, require_exec=False) != config:
            raise ValueError("HOLD_SUPERVISOR_CONFIG_PIN")
    if any(row["ctime_ns"] > pin["process_start_epoch_ns"] - 1_500_000_000
           for row in pin["config_inputs"]):
        raise ValueError("HOLD_SUPERVISOR_CONFIG_START_BOUND")
    include_glob = pin.get("include_glob")
    if include_glob:
        discovered = sorted(glob.glob(include_glob))
        pinned = sorted(row["path"] for row in pin["config_inputs"]
                        if row["path"] != "/etc/supervisor/supervisord.conf")
        if discovered != pinned:
            raise ValueError("HOLD_SUPERVISOR_CONFIG_INCLUDE_SET_CHANGED")
    alias = pin.get("var_run_alias")
    if alias is not None:
        meta = Path(alias["path"]).lstat()
        if (not stat.S_ISLNK(meta.st_mode) or os.readlink(alias["path"]) != alias["target"] or
                meta.st_dev != alias["device"] or meta.st_ino != alias["inode"] or
                meta.st_mode != alias["mode"] or meta.st_uid != alias["uid"] or
                meta.st_gid != alias["gid"] or meta.st_mtime_ns != alias["mtime_ns"] or
                meta.st_ctime_ns != alias["ctime_ns"]):
            raise ValueError("HOLD_SUPERVISOR_VAR_RUN_ALIAS")
    if _runtime_unix_listener() != pin["listener"]:
        raise ValueError("HOLD_SUPERVISOR_LISTENER_PIN")
    sock_meta = Path(SUPERVISOR_SOCKET_PATH).lstat()
    socket_pin = SUPERVISOR_SOCKET_PIN
    if ({"device": sock_meta.st_dev, "inode": sock_meta.st_ino,
         "mode": stat.S_IMODE(sock_meta.st_mode), "uid": sock_meta.st_uid,
         "gid": sock_meta.st_gid, "nlink": sock_meta.st_nlink,
         "mtime_ns": sock_meta.st_mtime_ns, "ctime_ns": sock_meta.st_ctime_ns}
            != socket_pin):
        raise ValueError("HOLD_SUPERVISOR_SOCKET_PIN")
    if (_proc_identity(SUPERVISOR_PID) != identity or
            _runtime_unix_listener() != pin["listener"]):
        raise ValueError("HOLD_SUPERVISOR_IDENTITY_CHANGED_DURING_CHECK")
    return True


def supervise(name, command="status"):
    if name not in SERVICES or command not in ("status", "start"):
        raise ValueError("HOLD_UNAPPROVED_OPERATION")
    if command == "start":
        raise ValueError("HOLD_OBSERVER_ONLY_START_DISABLED")
    try:
        row = _supervisor_row(name)
    except (OSError, ValueError, xmlrpc.client.Error):
        return {"state": "UNKNOWN", "pid": None, "rc": 124}
    state = row.get("statename")
    pid = row.get("pid")
    if state not in SERVICE_STATES or (state == "RUNNING" and (type(pid) is not int or pid <= 0)):
        return {"state": "UNKNOWN", "pid": None, "rc": 1}
    if state != "RUNNING" and pid != 0:
        return {"state": "UNKNOWN", "pid": None, "rc": 1}
    return {"state": state, "pid": pid if state == "RUNNING" else None,
            "rc": 0 if state == "RUNNING" else 3}

def _check_all_repair_histories(records, now):
    """Fail before touching ANY service if even a later service ledger is corrupt."""
    if not isinstance(records, dict):
        raise ValueError("HOLD_REPAIR_HISTORY_CORRUPT")
    for name, row in records.items():
        if not isinstance(name, str) or not isinstance(row, dict):
            raise ValueError("HOLD_REPAIR_HISTORY_CORRUPT")
        attempts = row.get("attempts", [])
        failures = row.get("failures", 0)
        if (not isinstance(attempts, list) or
            any(type(x) not in (int, float) or not 0 <= x <= now for x in attempts) or
            attempts != sorted(attempts) or
            type(failures) is not int or not 0 <= failures <= 1000):
            raise ValueError("HOLD_REPAIR_HISTORY_CORRUPT")


def tick(policy, state, *, dry_run=False, now=None, status_fn=supervise, stop_fn=stopped):
    now = time.time() if now is None else now
    observed = []
    records = state.setdefault("services", {})
    _check_all_repair_histories(records, now)
    for spec in policy["services"]:
        name = spec["name"]
        current = status_fn(name, "status")
        row = records.setdefault(name, {})
        if not isinstance(row, dict):
            raise ValueError("HOLD_REPAIR_HISTORY_CORRUPT")
        attempts = row.get("attempts", [])
        if not isinstance(attempts, list) or any(
            type(x) not in (int, float) or not 0 <= x <= now for x in attempts
        ) or attempts != sorted(attempts):
            raise ValueError("HOLD_REPAIR_HISTORY_CORRUPT")
        attempts = [x for x in attempts if now - x < 86400]
        row["attempts"] = attempts
        previous = row.get("failures", 0)
        bad = current.get("state") in REPAIRABLE
        row["failures"] = min(previous + 1, 1000) if bad else 0
        action = "observed_healthy" if current.get("state") == "RUNNING" else "observation_only"
        if current.get("state") in ("UNKNOWN", "FATAL", "BACKOFF", "STARTING", "STOPPING"):
            action = "owner_investigation_required"
        elif bad and row["failures"] >= policy["consecutive_failures"]:
            # Disabled observation and per-service restart=False are true
            # no-op modes. Do not touch the shared owner lock on this path;
            # the observer can still persist telemetry while an owner action
            # holds the exclusive maintenance lock.
            if not policy["enabled"] or spec["restart"] is not True:
                action = "owner_authorization_required"
            elif stop_fn():
                action = "stop_or_maintenance_lock"
            elif len(attempts) >= policy["daily_limit"]:
                action = "daily_repair_budget_exhausted"
            elif sum(now - x < 3600 for x in attempts) >= 2:
                action = "hourly_repair_budget_exhausted"
            elif attempts and now - attempts[-1] < policy["cooldown_seconds"]:
                action = "repair_cooldown"
            elif dry_run:
                action = "would_start"
            elif stop_fn():
                action = "stop_or_maintenance_lock"
            else:
                # The first STOPPED sample is not a lease on service state.
                # Recheck immediately before admitting any original Supervisor start.
                fresh = status_fn(name, "status")
                if fresh.get("state") not in REPAIRABLE or fresh.get("pid"):
                    action = "service_changed_before_start_hold"
                elif stop_fn():
                    action = "stop_or_maintenance_lock"
                else:
                    # Persist attempt BEFORE action; a crash must not replay it.
                    attempts.append(now)
                    row["attempts"] = attempts
                    atomic(state["_path"], {k:v for k,v in state.items() if k!="_path"})
                    outcome = status_fn(name, "start")
                    verified = status_fn(name, "status")
                    if outcome.get("rc") == 0 and verified.get("state") == "RUNNING" and verified.get("pid"):
                        row["failures"] = 0
                        action = "started_verified"
                    else:
                        action = "start_failed_hold"
        event = {"name": name, "service_state": current.get("state", "UNKNOWN"),
                 "action": action, "attempts_24h": len(row["attempts"])}
        if action in ("owner_investigation_required", "owner_authorization_required",
                      "daily_repair_budget_exhausted", "hourly_repair_budget_exhausted",
                      "service_changed_before_start_hold", "start_failed_hold"):
            event["question"] = ("Check trusted supervisor journal / exact service command and "
                                 "approve a bounded recovery after preserving STOP and checkpoints.")
        observed.append(event)
    report = {"schema": SCHEMA, "at": dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(),
              "observer_only": not policy["enabled"], "results": observed[:MAX_EVENT_ROWS],
              "cgroup_memory": cgroup_memory_snapshot()}
    state["last_report"] = report
    state["at"] = now
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", default="/etc/nox/lifeline.json")
    parser.add_argument("--state", default="/root/nox/state/lifeline/state.json")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--observer-only", action="store_true",
                        help="force enabled=false and restart=false for every service")
    a = parser.parse_args()
    policy_path = Path(a.policy)
    state_path = Path(a.state)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lockpath = state_path.parent / "lifeline.lock"
    lockfd = os.open(lockpath, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("NOX_LIFELINE_ALREADY_RUNNING", flush=True)
        os.close(lockfd)
        return 2
    try:
        while True:
            interval = 60
            try:
                policy = policy_load(policy_path)
                if a.observer_only:
                    policy = observer_only_policy(policy)
                interval = policy["poll_seconds"]
                state = read_state(state_path)
                state["_path"] = state_path
                report = tick(policy, state, dry_run=a.dry_run)
                report["observer_only_enforced"] = bool(a.observer_only)
                report["worker_starts_permitted"] = False if a.observer_only else None
                limits = resource_limit_receipt() if a.observer_only else None
                if limits is not None:
                    report["resource_limits"] = limits
                if not a.dry_run:
                    atomic(state_path, {k:v for k,v in state.items() if k!="_path"})
                print("NOX_LIFELINE_RESULT=" + json.dumps(report, sort_keys=True), flush=True)
            except Exception as exc:
                # Fail closed, do not mutate services. Log code only; no secret details.
                print("NOX_LIFELINE_HOLD=" + type(exc).__name__, flush=True)
                if a.once:
                    return 2
            if a.once:
                break
            time.sleep(interval)  # local bounded poll; never untrusted remote
    finally:
        os.close(lockfd)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
