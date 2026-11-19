#!/usr/bin/env python3
"""Install an independent, forced observer-only NOX lifeline systemd unit.

This entrypoint never enables, starts, stops, or edits supervisor.service and
never changes Supervisor program configuration. Its only service mutation is
enable/start of nox-lifeline-observer.service.
"""
from __future__ import annotations

import base64
import configparser
import fcntl
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import signal
import shlex
import socket
import stat
import subprocess
import sys
import tempfile
import time
import xmlrpc.client

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path("/root/nox")
SCRIPT = ROOT / "scripts/nox_lifeline_observer.py"
BOOTSTRAP = ROOT / "scripts/nox_lifeline_observer_bootstrap.py"
POLICY = Path("/etc/nox/lifeline-observer.json")
UNIT = Path("/etc/systemd/system/nox-lifeline-observer.service")
SUPERVISOR_PROGRAM = Path("/etc/supervisor/conf.d/nox-lifeline-observer.conf")
SUPERVISOR_PROGRAM_NAME = "nox-lifeline-observer"
SUPERVISOR_PROGRAM_BUNDLE_KEY = "nox-lifeline-observer.conf"
SUPERVISOR_BOOTSTRAP_BUNDLE_KEY = "nox_lifeline_observer_bootstrap.py"
SUPERVISOR_STATE_POLL_ATTEMPTS = 40
SUPERVISOR_STATE_POLL_INTERVAL_SECONDS = 0.25
SUPERVISOR_SERVER_VERSION = None
STATE_DIR = ROOT / "state/lifeline-observer"
STATE = STATE_DIR / "state.json"
SERVICE = "nox-lifeline-observer.service"
UNIT_SHA256 = "d23c029063f058b3c3b65116fca25733aea359ebe071a51416c1dd2608c5f806"
OWNER_STOP = ROOT / "STOP"
OWNER_MAINTENANCE = ROOT / "state/OWNER_MAINTENANCE.flag"
OWNER_LOCK = ROOT / "state/owner_maintenance.lock"
CGROUP_ROOT = Path("/sys/fs/cgroup")
MODEL_SERVICE = "nox-ds41-8098"
MODEL_PATH = "/root/nox/models/deepseek_v41_flash_iq2xxs/DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf"
MEMORY_FLOOR_BYTES = 2 * 1024**3
MEMORY_RESERVE_BYTES = 512 * 1024**2
LEGACY_POLICY = Path("/etc/nox/lifeline.json")
LEGACY_CONFIG = Path("/etc/supervisor/conf.d/nox-lifeline-guard.conf")
LEGACY_STATE = ROOT / "state/lifeline/state.json"
LEGACY_GUARD = "nox-lifeline-guard"
SUPERVISOR_CONFIG = Path("/etc/supervisor/supervisord.conf")
SYSTEMCTL_PATH = Path("/usr/bin/systemctl")
LEGACY_SCRIPT = ROOT / "scripts/nox_native_lifeline.py"
LEGACY_CONFIG_SHA256 = "266d75d12cb3203dd8200a6b382231105a0fd3fd9ea37379531d86c413ddfba6"
LEGACY_SCRIPT_SHA256 = "a2503c1463738c215bf3cd4eb5cdcb29f5ff65a85128160728033a80e9af1f66"
LEGACY_EXPECTED_ARGV = ("/usr/bin/python3", "-u",
                        "/root/nox/scripts/nox_native_lifeline.py",
                        "--policy", "/etc/nox/lifeline.json",
                        "--state", "/root/nox/state/lifeline/state.json")
LEGACY_SERVICES = frozenset({"nox-dispatcher-t855u", "nox-priority-scheduler",
                             "nox-selfheal", "nox-gpu-watchdog-t865u"})
MAX_BYTES = {"nox_lifeline_observer.py": 262_144,
             "lifeline-observer.json": 8_192,
             "nox-lifeline-observer.service": 8_192}
FILES = {"nox_lifeline_observer.py": SCRIPT,
         "lifeline-observer.json": POLICY,
         "nox-lifeline-observer.service": UNIT}
SUPERVISOR_INSTALL_FILES = {
    "nox_lifeline_observer.py": SCRIPT,
    "lifeline-observer.json": POLICY,
    SUPERVISOR_BOOTSTRAP_BUNDLE_KEY: BOOTSTRAP,
}
BUNDLE_SHA256 = {
    "nox_lifeline_observer.py": "acb7a0174d02ac106e33c4f5c35abfa1a571526454ac65ef70b241247d602990",
    "lifeline-observer.json": "116ef4bcc534d2ad3531156c6581adef40ffbbf7e3c4bdf9a68cfa487fced27b",
    "nox-lifeline-observer.service": UNIT_SHA256,
}
SUPERVISOR_BUNDLE_MAX_BYTES = {
    SUPERVISOR_PROGRAM_BUNDLE_KEY: 8_192,
    SUPERVISOR_BOOTSTRAP_BUNDLE_KEY: 16_384,
}
SUPERVISOR_BUNDLE_SHA256 = {
    SUPERVISOR_PROGRAM_BUNDLE_KEY: "00f58d8a96fb9277f7e5e0f65acc4719b231608fe43e633011cc524ac04f66f4",
    SUPERVISOR_BOOTSTRAP_BUNDLE_KEY: "3c556a5a4e81532aa50e05dbea9c7115740248799a15bfba45df70ae325b5584",
}
SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")
OWNER_LOCK_FD = None
OWNER_LOCK_PARENT_FD = None
OWNER_LOCK_IDENTITY = None
OWNER_FENCE_DIR_FDS = []
OWNER_FENCES_CREATED = []
OWNER_FENCES_PREEXISTING = []
OWNER_FENCE_STATUS = {"state": "NOT_ACQUIRED", "cleanup": "NOT_ATTEMPTED",
                      "retained": False}
NATIVE_MUTATION_ATTEMPTED = False
SYSTEMCTL_PIN = None
PREIMAGES = {}
INSTALLED = {}
UNIT_ENABLED_BEFORE = None
UNIT_ACTIVE_BEFORE = None
STATE_DIR_PREIMAGE = None
STATE_ARTIFACT_PREIMAGES = {}
STATE_ARTIFACTS = {"state.json": STATE, "lifeline.lock": STATE_DIR / "lifeline.lock"}
REQUEST_ID = None
SOURCE_SHA_VALUE = None
MEMORY_PREFLIGHT = None
MEMORY_PRE_ENABLE = None
MEMORY_POST_ENABLE = None
MEMORY_POST_ROLLBACK = None
LEGACY_GUARD_PREIMAGE = None
LEGACY_GUARD_PRE_ENABLE = None
LEGACY_GUARD_POSTCHECK = None
SUPERVISORCTL_PIN = None
SUPERVISORCTL_PRE_ENABLE = None
SUPERVISORCTL_POST_ENABLE = None
SUPERVISORCTL_CANDIDATE_OUTCOMES = [{"backend": "unix_xmlrpc_read_only"}]
OBSERVER_RUNTIME_SOURCE_SHA256 = None
CGROUP_TARGET_EVIDENCE = None
CGROUP_TARGET_PRE_ENABLE = None
CGROUP_TARGET_POST_ENABLE = None
SUPERVISOR_BASELINE_PIN = None
SUPERVISOR_ALLOWED_PROGRAM_CONFIG = None
SUPERVISOR_PROGRAM_PREIMAGE = None
SUPERVISOR_PROGRAM_INSTALLED = None
SUPERVISOR_PROGRAM_RELOADED = False
SUPERVISOR_PROGRAM_ADDED = False
SUPERVISOR_PROGRAM_STARTED = False
SUPERVISOR_PROGRAM_START_IDENTITY = None
SUPERVISOR_PROGRAM_BEFORE_INVENTORY = None
SUPERVISOR_PROGRAM_AFTER_INVENTORY = None
SUPERVISOR_PROGRAM_ACTIVATION = None
SUPERVISOR_PROGRAM_ROLLBACK_PRIOR_GROUPS_UNCHANGED = None
SUPERVISOR_MEMORY_POST_START = None
SUPERVISOR_BACKEND_ACTIVE = False
SUPERVISOR_RESOURCE_RECEIPT = {
    "address_space_limit_bytes": 512 * 1024**2,
    "open_files_limit": 128,
    "core_file_limit_bytes": 0,
    "file_size_limit_bytes": 8 * 1024**2,
    "nice": 10,
    "hard_cgroup_memory_limit": "UNSUPPORTED_BY_SUPERVISOR",
    "hard_cpu_quota": "UNSUPPORTED_BY_SUPERVISOR",
}


class Hold(RuntimeError):
    pass


def fail(code: str) -> None:
    raise Hold("HOLD_LIFELINE_OBSERVER_" + code)


def mark_native_mutation_attempted():
    global NATIVE_MUTATION_ATTEMPTED
    NATIVE_MUTATION_ATTEMPTED = True


def _supervisorctl_snapshot(path: Path, max_size=1_048_576):
    for parent in (path.parent, *path.parent.parents):
        try:
            meta = parent.lstat()
        except OSError:
            raise FileNotFoundError("parent")
        if (stat.S_ISLNK(meta.st_mode) or not stat.S_ISDIR(meta.st_mode) or
                meta.st_uid != 0 or meta.st_mode & 0o022):
            fail("SUPERVISORCTL_PARENT_UNSAFE")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                     getattr(os, "O_CLOEXEC", 0))
    except OSError:
        fail("SUPERVISORCTL_OPEN_FAILED")
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or
                before.st_mode & 0o022 or not before.st_mode & 0o111 or
                before.st_size <= 0 or before.st_size > max_size):
            fail("SUPERVISORCTL_FILE_UNSAFE")
        digest = hashlib.sha256()
        total = 0
        remaining = max_size + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
            remaining -= len(chunk)
        after = os.fstat(fd)
        path_meta = path.lstat()
        fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_uid", "st_gid",
                  "st_size", "st_mtime_ns", "st_ctime_ns")
        if (total > max_size or total != before.st_size or
                any(getattr(before, field) != getattr(after, field) for field in fields) or
                any(getattr(after, field) != getattr(path_meta, field) for field in fields)):
            fail("SUPERVISORCTL_CHANGED_DURING_READ")
    finally:
        os.close(fd)
    return {"path": str(path), "device": before.st_dev, "inode": before.st_ino,
            "mode": stat.S_IMODE(before.st_mode), "nlink": before.st_nlink,
            "uid": before.st_uid,
            "gid": before.st_gid, "size": before.st_size,
            "mtime_ns": before.st_mtime_ns, "ctime_ns": before.st_ctime_ns,
            "sha256": digest.hexdigest()}


def _supervisor_config_snapshot():
    for parent in (SUPERVISOR_CONFIG.parent, *SUPERVISOR_CONFIG.parent.parents):
        try:
            meta = parent.lstat()
        except OSError:
            fail("SUPERVISOR_CONFIG_PARENT_UNAVAILABLE")
        if (stat.S_ISLNK(meta.st_mode) or not stat.S_ISDIR(meta.st_mode) or
                meta.st_uid != 0 or meta.st_mode & 0o022):
            fail("SUPERVISOR_CONFIG_PARENT_UNSAFE")
    try:
        fd = os.open(SUPERVISOR_CONFIG, os.O_RDONLY | os.O_NOFOLLOW |
                     os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
    except OSError:
        fail("SUPERVISOR_CONFIG_UNAVAILABLE")
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or
                before.st_mode & 0o022 or before.st_size <= 0 or before.st_size > 262144):
            fail("SUPERVISOR_CONFIG_UNSAFE")
        raw = os.read(fd, 262145)
        after = os.fstat(fd)
        path_after = SUPERVISOR_CONFIG.lstat()
        fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_uid", "st_gid",
                  "st_size", "st_mtime_ns", "st_ctime_ns")
        if (len(raw) != before.st_size or len(raw) > 262144 or
                any(getattr(before, f) != getattr(after, f) or
                    getattr(after, f) != getattr(path_after, f) for f in fields)):
            fail("SUPERVISOR_CONFIG_CHANGED")
    finally:
        os.close(fd)
    return {"path": str(SUPERVISOR_CONFIG), "device": before.st_dev,
            "inode": before.st_ino, "mode": stat.S_IMODE(before.st_mode),
            "uid": before.st_uid, "gid": before.st_gid,
            "size": before.st_size, "mtime_ns": before.st_mtime_ns,
            "ctime_ns": before.st_ctime_ns, "sha256": hashlib.sha256(raw).hexdigest()}


def _socket_peer(endpoint):
    path = Path(endpoint["path"])
    before = path.lstat()
    parent_before = [{"path": row["path"], **{
        key: getattr(Path(row["path"]).lstat(), field) for key, field in
        (("device", "st_dev"), ("inode", "st_ino"), ("mode", "st_mode"),
         ("uid", "st_uid"), ("gid", "st_gid"))}} for row in endpoint["parent_chain"]]
    expected = endpoint["socket"]
    if (before.st_dev != expected["device"] or before.st_ino != expected["inode"] or
            stat.S_IMODE(before.st_mode) != expected["mode"] or
            before.st_uid != expected["uid"] or before.st_gid != expected["gid"] or
            before.st_nlink != expected["nlink"]):
        fail("SUPERVISOR_SOCKET_PIN_CHANGED")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(5)
        sock.connect(str(path))
        pid, uid, gid = __import__("struct").unpack(
            "3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        after = path.lstat()
        parent_after = [{"path": row["path"], **{
            key: getattr(Path(row["path"]).lstat(), field) for key, field in
            (("device", "st_dev"), ("inode", "st_ino"), ("mode", "st_mode"),
             ("uid", "st_uid"), ("gid", "st_gid"))}} for row in endpoint["parent_chain"]]
        if (pid <= 1 or uid != 0 or gid != 0 or
                parent_before != endpoint["parent_chain"] or
                parent_after != endpoint["parent_chain"] or
                any(getattr(before, key) != getattr(after, key) for key in
                    ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink"))):
            fail("SUPERVISOR_SOCKET_PEER_INVALID")
        return {"pid": pid, "uid": uid, "gid": gid}
    except OSError:
        fail("SUPERVISOR_UDS_CONNECT_FAILED")
    finally:
        sock.close()


def _unix_listener_evidence(pid, endpoint):
    raw = _proc_file(Path("/proc/net/unix"), 2 * 1024**2,
                     "SUPERVISOR_UNIX_TABLE_UNAVAILABLE")
    accepted = {endpoint["path"], endpoint.get("configured_path", endpoint["path"])}
    exact_path_rows = []
    for line in raw.decode("utf-8", "strict").splitlines()[1:]:
        fields = line.split()
        if len(fields) < 7:
            continue
        path = fields[7] if len(fields) > 7 else ""
        if path not in accepted:
            continue
        try:
            flags, socket_type, state, inode = (
                int(fields[3], 16), int(fields[4], 16), fields[5], int(fields[6]))
        except ValueError:
            fail("SUPERVISOR_LISTENER_ROW_INVALID")
        exact_path_rows.append({"inode": inode, "path": path, "flags": fields[3],
                               "socket_type": fields[4], "state": state,
                               "flags_value": flags, "type_value": socket_type})
    if len(exact_path_rows) != 1:
        fail("SUPERVISOR_LISTENER_ROW_NOT_UNIQUE")
    row = exact_path_rows[0]
    if row["type_value"] != 0x0001 or row["state"] != "01" or not row["flags_value"] & 0x10000:
        fail("SUPERVISOR_LISTENER_ROW_NOT_LISTENING")
    listener_row = {"inode": row["inode"], "path": row["path"],
                    "flags": row["flags"], "socket_type": row["socket_type"],
                    "state": row["state"]}
    inode = row["inode"]
    fd_rows = []
    try:
        entries = list(os.scandir(Path("/proc") / str(pid) / "fd"))
    except OSError:
        fail("SUPERVISOR_FD_TABLE_UNAVAILABLE")
    if len(entries) > 4096:
        fail("SUPERVISOR_FD_LIMIT")
    for entry in entries:
        try:
            target = os.readlink(entry.path)
        except OSError:
            continue
        if target == f"socket:[{inode}]":
            fd_rows.append(entry.name)
    if len(fd_rows) != 1:
        fail("SUPERVISOR_LISTENER_FD_NOT_UNIQUE")
    return {**listener_row, "owner_pid": pid, "fd": fd_rows[0]}


def _supervisord_identity(endpoint=None):
    endpoint = endpoint or _socket_config_snapshot()
    peer = _socket_peer(endpoint)
    pid = peer["pid"]
    proc = Path("/proc") / str(pid)
    before = _proc_start_ticks(pid)
    creds = _proc_effective_credentials(pid)
    if creds != {"uid": peer["uid"], "gid": peer["gid"]}:
        fail("SUPERVISOR_PEER_CREDENTIAL_MISMATCH")
    try:
        exe = os.readlink(proc / "exe")
        cmdline = _proc_read(pid, "cmdline", 16384, "SUPERVISORD_IDENTITY_UNAVAILABLE")
    except OSError:
        fail("SUPERVISORD_IDENTITY_UNAVAILABLE")
    exe_after = os.readlink(proc / "exe")
    cmdline_after = _proc_read(pid, "cmdline", 16384,
                               "SUPERVISORD_IDENTITY_UNAVAILABLE")
    after = _proc_start_ticks(pid)
    args = tuple(x.decode("utf-8", "strict") for x in cmdline[:-1].split(b"\0"))
    config_flags = [i for i, arg in enumerate(args)
                    if arg in ("-c", "--configuration")]
    inline_or_ambiguous_config = [arg for arg in args
                                  if ((arg.startswith("--configuration") and
                                       arg != "--configuration") or
                                      (arg.startswith("-c") and arg != "-c"))]
    if (before != after or exe != exe_after or cmdline != cmdline_after or
            not cmdline.endswith(b"\0") or not args or len(config_flags) != 1 or
            inline_or_ambiguous_config):
        fail("SUPERVISORD_IDENTITY_NOT_ALLOWLISTED")
    try:
        idx = config_flags[0]
        if idx + 1 >= len(args) or args[idx + 1].startswith("-"):
            raise ValueError
        configured = args[idx + 1]
    except (ValueError, IndexError):
        fail("SUPERVISORD_CONFIG_ARG_INVALID")
    if configured != str(SUPERVISOR_CONFIG):
        fail("SUPERVISORD_CONFIG_MISMATCH")
    script_args = [arg for arg in args if Path(arg).name == "supervisord"]
    if (len(script_args) != 1 or not script_args[0].startswith("/") or
            Path(script_args[0]).is_symlink()):
        fail("SUPERVISORD_SCRIPT_ARG_MISMATCH")
    script_identity = _supervisorctl_snapshot(Path(script_args[0]))
    executable_identity = _supervisorctl_snapshot(Path(exe), max_size=64 * 1024**2)
    cgroup = process_cgroup_info(pid)
    start_epoch_ns = _proc_start_epoch_ns(pid, before)
    allowed_program = SUPERVISOR_ALLOWED_PROGRAM_CONFIG
    for row in endpoint["config_inputs"]:
        if allowed_program is not None and row["path"] == allowed_program["path"]:
            if row["sha256"] != allowed_program["sha256"]:
                fail("SUPERVISOR_OBSERVER_CONFIG_PIN_CHANGED")
            continue
        if row["ctime_ns"] > start_epoch_ns - 1_500_000_000:
            fail("SUPERVISOR_CONFIG_NOT_PREEXISTING_AT_START")
    listener = _unix_listener_evidence(pid, endpoint)
    try:
        exe_final = os.readlink(proc / "exe")
        cmdline_final = _proc_read(pid, "cmdline", 16384,
                                   "SUPERVISORD_IDENTITY_REREAD_UNAVAILABLE")
    except OSError:
        fail("SUPERVISORD_IDENTITY_REREAD_UNAVAILABLE")
    if (_proc_start_ticks(pid) != before or exe_final != exe or
            cmdline_final != cmdline or
            _proc_effective_credentials(pid) != creds or
            _supervisorctl_snapshot(Path(exe), max_size=64 * 1024**2) != executable_identity or
            _supervisorctl_snapshot(Path(script_args[0])) != script_identity or
            process_cgroup_info(pid) != cgroup or
            _unix_listener_evidence(pid, endpoint) != listener or
            _socket_peer(endpoint) != peer):
        fail("SUPERVISORD_PROCESS_CHANGED_AFTER_QUERY")
    return {"pid": pid, "start_ticks": before, "exe": exe, "credentials": creds,
            "argv_sha256": hashlib.sha256(cmdline).hexdigest(),
            "executable": executable_identity, "script": script_identity,
            "cgroup": cgroup, "process_start_epoch_ns": start_epoch_ns,
            "listener": listener, "config": str(SUPERVISOR_CONFIG),
            "config_inputs": endpoint["config_inputs"]}


def _socket_config_snapshot():
    """Parse the pinned main file and exact bounded conf.d include set."""
    main_identity = _supervisor_config_snapshot()
    def read_trusted(path):
        for parent in (path.parent, *path.parent.parents):
            meta = parent.lstat()
            if (stat.S_ISLNK(meta.st_mode) or not stat.S_ISDIR(meta.st_mode) or
                    meta.st_uid != 0 or meta.st_mode & 0o022):
                fail("SUPERVISOR_INCLUDE_PARENT_UNSAFE")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                     getattr(os, "O_CLOEXEC", 0))
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or
                    before.st_mode & 0o022 or before.st_size < 0 or before.st_size > 262144):
                fail("SUPERVISOR_INCLUDE_FILE_UNSAFE")
            raw = b""
            while len(raw) <= 262144:
                chunk = os.read(fd, min(65536, 262145 - len(raw)))
                if not chunk:
                    break
                raw += chunk
            after = os.fstat(fd)
            leaf = path.lstat()
            fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_uid", "st_gid",
                      "st_size", "st_mtime_ns", "st_ctime_ns")
            if (len(raw) != before.st_size or len(raw) > 262144 or
                    any(getattr(before, f) != getattr(after, f) or
                        getattr(after, f) != getattr(leaf, f) for f in fields)):
                fail("SUPERVISOR_INCLUDE_CHANGED")
        finally:
            os.close(fd)
        return raw, {"path": str(path), "device": before.st_dev,
                     "inode": before.st_ino, "mode": stat.S_IMODE(before.st_mode),
                     "uid": before.st_uid, "gid": before.st_gid,
                     "size": before.st_size, "mtime_ns": before.st_mtime_ns,
                     "ctime_ns": before.st_ctime_ns,
                     "sha256": hashlib.sha256(raw).hexdigest()}
    main_raw, main_receipt = read_trusted(SUPERVISOR_CONFIG)
    if main_receipt["sha256"] != main_identity["sha256"]:
        fail("SUPERVISOR_MAIN_CONFIG_SNAPSHOT_MISMATCH")
    parser = configparser.ConfigParser(interpolation=None, strict=True, delimiters=("=", ":"))
    try:
        parser.read_string(main_raw.decode("utf-8", "strict"))
        include_files = parser.get("include", "files", fallback=None)
    except (UnicodeError, configparser.Error):
        fail("SUPERVISOR_UDS_CONFIG_INVALID")
    inputs = [main_receipt]
    include_glob = None
    if include_files:
        patterns = include_files.split()
        if patterns != ["/etc/supervisor/conf.d/*.conf"]:
            fail("SUPERVISOR_INCLUDE_PATTERN_NOT_ALLOWLISTED")
        include_glob = patterns[0]
        paths = sorted(Path("/etc/supervisor/conf.d").glob("*.conf"))
        if len(paths) > 256 or not paths:
            fail("SUPERVISOR_INCLUDE_SET_INVALID")
        parser.remove_section("include")
        for path in paths:
            raw, receipt = read_trusted(path)
            try:
                parser.read_string(raw.decode("utf-8", "strict"), source=str(path))
            except (UnicodeError, configparser.Error):
                fail("SUPERVISOR_INCLUDED_CONFIG_INVALID")
            inputs.append(receipt)
    if any(b"%(env_" in read_trusted(Path(row["path"]))[0].lower() for row in inputs):
        fail("SUPERVISOR_CONFIG_ENV_EXPANSION_UNSUPPORTED")
    parser = configparser.ConfigParser(interpolation=None, strict=True, delimiters=("=", ":"))
    try:
        for row in inputs:
            parser.read_string(read_trusted(Path(row["path"]))[0].decode("utf-8", "strict"),
                               source=row["path"])
        server = parser["unix_http_server"]
        client = parser["supervisorctl"]
        sock_path = server.get("file", "").strip()
        serverurl = client.get("serverurl", "").strip()
        here = str(SUPERVISOR_CONFIG.parent)
        sock_path = sock_path.replace("%(here)s", here)
        serverurl = serverurl.replace("%(here)s", here)
    except (UnicodeError, configparser.Error, KeyError):
        fail("SUPERVISOR_UDS_CONFIG_INVALID")
    if ("%(" in sock_path or "%(" in serverurl or not sock_path.startswith("/") or
            serverurl != "unix://" + sock_path or "\x00" in sock_path):
        fail("SUPERVISOR_UDS_ENDPOINT_MISMATCH")
    if any(part in (".", "..") for part in Path(sock_path).parts) or any(
            char.isspace() for char in sock_path):
        fail("SUPERVISOR_UDS_PATH_AMBIGUOUS")
    configured_sock_path = sock_path
    var_run_alias = None
    endpoint = Path(sock_path)
    if sock_path.startswith("/var/run/"):
        alias_path = Path("/var/run")
        alias = alias_path.lstat()
        if stat.S_ISLNK(alias.st_mode):
            target = os.readlink(alias_path)
            if target not in ("/run", "run"):
                fail("SUPERVISOR_VAR_RUN_ALIAS_UNSUPPORTED")
            suffix = endpoint.relative_to(alias_path)
            endpoint = Path("/run") / suffix
            sock_path = str(endpoint)
            var_run_alias = {"path": str(alias_path), "target": target,
                             "device": alias.st_dev, "inode": alias.st_ino,
                             "mode": alias.st_mode, "uid": alias.st_uid,
                             "gid": alias.st_gid, "mtime_ns": alias.st_mtime_ns,
                             "ctime_ns": alias.st_ctime_ns}
    if len(os.fsencode(sock_path)) > 103:
        fail("SUPERVISOR_UDS_PATH_TOO_LONG")
    parent_chain = []
    for parent in (endpoint.parent, *endpoint.parent.parents):
        try:
            meta = parent.lstat()
        except OSError:
            fail("SUPERVISOR_UDS_PARENT_UNAVAILABLE")
        if (stat.S_ISLNK(meta.st_mode) or not stat.S_ISDIR(meta.st_mode) or
                meta.st_uid != 0 or meta.st_mode & 0o022):
            fail("SUPERVISOR_UDS_PARENT_UNSAFE")
        parent_chain.append({"path": str(parent), "device": meta.st_dev,
                             "inode": meta.st_ino, "mode": meta.st_mode,
                             "uid": meta.st_uid, "gid": meta.st_gid})
    try:
        meta = endpoint.lstat()
    except OSError:
        fail("SUPERVISOR_UDS_SOCKET_UNAVAILABLE")
    if (not stat.S_ISSOCK(meta.st_mode) or meta.st_mode & 0o077 or meta.st_nlink != 1):
        fail("SUPERVISOR_UDS_SOCKET_UNSAFE")
    for receipt in inputs:
        _, current = read_trusted(Path(receipt["path"]))
        if current != receipt:
            fail("SUPERVISOR_CONFIG_INPUT_CHANGED_DURING_PARSE")
    if var_run_alias is not None:
        current_alias = Path(var_run_alias["path"]).lstat()
        if (not stat.S_ISLNK(current_alias.st_mode) or
                os.readlink(var_run_alias["path"]) != var_run_alias["target"] or
                any(getattr(current_alias, key) != var_run_alias[field] for key, field in
                    (("st_dev", "device"), ("st_ino", "inode"), ("st_mode", "mode"),
                     ("st_uid", "uid"), ("st_gid", "gid"), ("st_mtime_ns", "mtime_ns"),
                     ("st_ctime_ns", "ctime_ns")))):
            fail("SUPERVISOR_VAR_RUN_ALIAS_CHANGED")
    return {"config": main_identity, "config_inputs": inputs, "path": sock_path,
            "configured_path": configured_sock_path, "var_run_alias": var_run_alias,
            "include_glob": include_glob,
            "parent_chain": parent_chain,
            "socket": {"device": meta.st_dev, "inode": meta.st_ino,
                       "mode": stat.S_IMODE(meta.st_mode), "uid": meta.st_uid,
                       "gid": meta.st_gid, "nlink": meta.st_nlink,
                       "mtime_ns": meta.st_mtime_ns, "ctime_ns": meta.st_ctime_ns}}


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, endpoint, peer_identity, timeout, parent_chain):
        super().__init__("supervisor.local", timeout=timeout)
        self.endpoint = endpoint
        self.expected_peer = peer_identity
        self.parent_chain = parent_chain
        self.peer = None

    def connect(self):
        before = Path(self.endpoint).lstat()
        parent_before = [{"path": row["path"], **{
            key: getattr(Path(row["path"]).lstat(), field) for key, field in
            (("device", "st_dev"), ("inode", "st_ino"), ("mode", "st_mode"),
             ("uid", "st_uid"), ("gid", "st_gid"))}}
            for row in self.parent_chain]
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(self.endpoint)
            raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            pid, uid, gid = __import__("struct").unpack("3i", raw)
            if (pid != self.expected_peer["pid"] or uid != self.expected_peer["uid"] or
                    gid != self.expected_peer["gid"]):
                raise OSError("unexpected supervisor socket peer")
            after = Path(self.endpoint).lstat()
            parent_after = [{"path": row["path"], **{
                key: getattr(Path(row["path"]).lstat(), field) for key, field in
                (("device", "st_dev"), ("inode", "st_ino"), ("mode", "st_mode"),
                 ("uid", "st_uid"), ("gid", "st_gid"))}}
                for row in self.parent_chain]
            fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink")
            if (not stat.S_ISSOCK(after.st_mode) or
                    any(getattr(before, f) != getattr(after, f) for f in fields) or
                    parent_before != self.parent_chain or parent_after != self.parent_chain):
                raise OSError("supervisor socket changed")
            self.peer = {"pid": pid, "uid": uid, "gid": gid}
            self.sock = sock
        except BaseException:
            sock.close()
            raise


class _UnixXMLRPCTransport(xmlrpc.client.Transport):
    def __init__(self, endpoint, peer_identity, parent_chain, timeout=5):
        super().__init__()
        self.endpoint, self.peer_identity_expected = endpoint, peer_identity
        self.parent_chain, self.timeout = parent_chain, timeout
        self._connection = (None, None)
        self.last_peer = None

    def make_connection(self, host):
        if self._connection and self._connection[0] == host:
            conn = self._connection[1]
            if conn.sock is not None:
                self.last_peer = conn.peer
                return conn
        conn = _UnixHTTPConnection(self.endpoint, self.peer_identity_expected,
                                   self.timeout, self.parent_chain)
        self._connection = (host, conn)
        return conn

    def peer_identity(self):
        try:
            return self._connection[1].peer
        except (IndexError, AttributeError, TypeError):
            return None


def _supervisor_client_snapshot():
    endpoint = _socket_config_snapshot()
    daemon = _supervisord_identity(endpoint)
    if (endpoint["socket"]["uid"] != daemon["credentials"]["uid"] or
            endpoint["socket"]["gid"] != daemon["credentials"]["gid"]):
        fail("SUPERVISOR_SOCKET_CREDENTIAL_MISMATCH")
    transport = _UnixXMLRPCTransport(endpoint["path"],
        {"pid": daemon["pid"], **daemon["credentials"]}, endpoint["parent_chain"])
    proxy = xmlrpc.client.ServerProxy("http://supervisor.local/RPC2", transport=transport,
                                      allow_none=False, use_builtin_types=True)
    peer = None
    try:
        version = proxy.supervisor.getAPIVersion()
        state = proxy.supervisor.getState()
        pid = proxy.supervisor.getPID()
        identification = proxy.supervisor.getIdentification()
        if (version != "3.0" or state != {"statecode": 1, "statename": "RUNNING"} or
                pid != daemon["pid"]):
            fail("SUPERVISOR_UDS_IDENTITY_MISMATCH")
        row_guard = proxy.supervisor.getProcessInfo(LEGACY_GUARD)
        row_model = proxy.supervisor.getProcessInfo(MODEL_SERVICE)
        peer = transport.peer_identity()
        if peer != {"pid": daemon["pid"], **daemon["credentials"]}:
            fail("SUPERVISOR_UDS_PEER_MISMATCH")
    except (xmlrpc.client.Error, OSError, ValueError, KeyError, TypeError):
        fail("SUPERVISOR_UDS_QUERY_FAILED")
    finally:
        proxy.close()
    if (not isinstance(identification, str) or not isinstance(row_guard, dict) or
            not isinstance(row_model, dict) or row_guard.get("name") != LEGACY_GUARD or
            row_guard.get("group") != LEGACY_GUARD or row_model.get("name") != MODEL_SERVICE or
            row_model.get("group") != MODEL_SERVICE):
        fail("SUPERVISOR_UDS_ROWS_INVALID")
    if _socket_config_snapshot() != endpoint or _supervisord_identity(endpoint) != daemon:
        fail("SUPERVISOR_ENDPOINT_CHANGED_DURING_PROBE")
    daemon["identification_sha256"] = hashlib.sha256(identification.encode()).hexdigest()
    daemon["api_version"] = version
    daemon["configured_socket_path"] = endpoint["configured_path"]
    daemon["include_glob"] = endpoint["include_glob"]
    daemon["socket_parent_chain"] = endpoint["parent_chain"]
    daemon["var_run_alias"] = endpoint["var_run_alias"]
    return {"backend": "unix_xmlrpc_read_only", "endpoint": endpoint,
            "daemon": daemon, "api_version": version,
            "identification_sha256": hashlib.sha256(identification.encode()).hexdigest(),
            "legacy_pid": row_guard.get("pid"), "legacy_state": row_guard.get("statename"),
            "model_pid": row_model.get("pid"), "model_state": row_model.get("statename"),
            "model_group": row_model.get("group")}


def resolve_supervisorctl():
    """Compatibility name retained for receipts; no supervisorctl is resolved or run."""
    global SUPERVISORCTL_CANDIDATE_OUTCOMES
    snapshot = _supervisor_client_snapshot()
    SUPERVISORCTL_CANDIDATE_OUTCOMES = [{"backend": "unix_xmlrpc_read_only",
                                         "state": "MATCH"}]
    return snapshot


def refresh_supervisor_pin_for_program(expected_config):
    global SUPERVISORCTL_PIN
    current = _supervisor_client_snapshot()
    if not supervisor_runtime_delta(current, SUPERVISOR_BASELINE_PIN, expected_config):
        fail("SUPERVISOR_PROGRAM_CONFIG_DELTA_NOT_EXACT")
    SUPERVISORCTL_PIN = current
    return current


def verify_supervisorctl_pin():
    if not isinstance(SUPERVISORCTL_PIN, dict):
        fail("SUPERVISORCTL_PIN_UNAVAILABLE")
    current = resolve_supervisorctl()
    if current != SUPERVISORCTL_PIN:
        fail("SUPERVISORCTL_PIN_CHANGED")
    return current


SUPERVISOR_RPC_CALLS = {
    "system.listMethods": (),
    "supervisor.getVersion": (),
    "supervisor.getAllProcessInfo": (),
    "supervisor.reloadConfig": (),
    "supervisor.addProcessGroup": (SUPERVISOR_PROGRAM_NAME,),
    "supervisor.startProcess": (SUPERVISOR_PROGRAM_NAME, True),
    "supervisor.stopProcess": (SUPERVISOR_PROGRAM_NAME, True),
    "supervisor.removeProcessGroup": (SUPERVISOR_PROGRAM_NAME,),
}


def supervisor_rpc(method, *args):
    """Call one fixed Supervisor UDS method and bind it to the pinned daemon."""
    if method not in SUPERVISOR_RPC_CALLS or tuple(args) != SUPERVISOR_RPC_CALLS[method]:
        fail("SUPERVISOR_RPC_OPERATION_NOT_ALLOWLISTED")
    before = verify_supervisorctl_pin()
    endpoint, daemon = before["endpoint"], before["daemon"]
    transport = _UnixXMLRPCTransport(endpoint["path"],
        {"pid": daemon["pid"], **daemon["credentials"]}, endpoint["parent_chain"],
        timeout=8)
    proxy = xmlrpc.client.ServerProxy("http://supervisor.local/RPC2", transport=transport,
                                      allow_none=False, use_builtin_types=True)
    try:
        namespace, name = method.split(".", 1)
        if method in {"supervisor.reloadConfig", "supervisor.addProcessGroup",
                      "supervisor.startProcess", "supervisor.stopProcess",
                      "supervisor.removeProcessGroup"}:
            mark_native_mutation_attempted()
        result = getattr(getattr(proxy, namespace), name)(*args)
        peer = transport.peer_identity()
    except (xmlrpc.client.Error, OSError, ValueError, KeyError, TypeError):
        fail("SUPERVISOR_RPC_CALL_FAILED")
    finally:
        proxy.close()
    if peer != {"pid": daemon["pid"], **daemon["credentials"]}:
        fail("SUPERVISOR_RPC_PEER_MISMATCH")
    after = verify_supervisorctl_pin()
    if after != before:
        fail("SUPERVISOR_RPC_PIN_CHANGED_DURING_CALL")
    return result


def validate_supervisor_none_log_version(version):
    """Require Supervisor 3.0+, where stdout_logfile=NONE is supported."""
    if not isinstance(version, str) or len(version) > 64:
        fail("SUPERVISOR_VERSION_UNVERIFIED")
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?(?:[-+][A-Za-z0-9.+-]+)?", version)
    if not match:
        fail("SUPERVISOR_VERSION_UNVERIFIED")
    parsed = tuple(int(part or 0) for part in match.groups())
    if parsed < (3, 0, 0):
        fail("SUPERVISOR_NONE_LOG_UNSUPPORTED")
    return version


def normalize_supervisor_inventory(rows):
    """Keep only stable public process fields; reject ambiguous or unbounded rows."""
    if not isinstance(rows, list) or len(rows) > 512:
        fail("SUPERVISOR_INVENTORY_INVALID")
    result = []
    seen = set()
    states = {"RUNNING", "STOPPED", "STARTING", "STOPPING", "BACKOFF",
              "EXITED", "FATAL", "UNKNOWN"}
    for row in rows:
        if not isinstance(row, dict):
            fail("SUPERVISOR_INVENTORY_ROW_INVALID")
        group, name, state, pid = (row.get("group"), row.get("name"),
                                   row.get("statename"), row.get("pid"))
        if (not isinstance(group, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", group) or
                not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", name) or
                state not in states or type(pid) is not int or not 0 <= pid <= 2**31 - 1 or
                (state == "RUNNING" and pid <= 1) or (state == "STOPPED" and pid != 0)):
            fail("SUPERVISOR_INVENTORY_ROW_INVALID")
        key = (group, name)
        if key in seen:
            fail("SUPERVISOR_INVENTORY_DUPLICATE")
        seen.add(key)
        result.append({"group": group, "name": name, "state": state, "pid": pid})
    return sorted(result, key=lambda item: (item["group"], item["name"]))


def supervisor_inventory():
    return normalize_supervisor_inventory(supervisor_rpc("supervisor.getAllProcessInfo"))


def validate_reload_config_delta(result, *, added_name=SUPERVISOR_PROGRAM_NAME,
                                 removed=False):
    """Require a single explicit add (or rollback removal), with no other diff."""
    added, changed, removed_groups = normalize_reload_config_result(result)
    expected_added = [] if removed else [added_name]
    expected_removed = [added_name] if removed else []
    if (added != expected_added or changed or removed_groups != expected_removed or
            len(set(added)) != len(added) or len(set(removed_groups)) != len(removed_groups)):
        fail("SUPERVISOR_RELOAD_SCOPE_CHANGED")
    return {"added": added, "changed": changed, "removed": removed_groups}


def normalize_reload_config_result(result):
    """Decode Supervisor API 3.0's one-element wrapper around its three arrays."""
    # Supervisor 4.2.5/API 3.0 serializes this as one outer item containing
    # [added, changed, removed]. Accept the documented flat equivalent too.
    if (isinstance(result, (list, tuple)) and len(result) == 1 and
            isinstance(result[0], (list, tuple)) and len(result[0]) == 3):
        result = result[0]
    if (not isinstance(result, (list, tuple)) or len(result) != 3 or
            any(not isinstance(group_list, (list, tuple)) or
                any(not isinstance(name, str) for name in group_list)
                for group_list in result)):
        fail("SUPERVISOR_RELOAD_DELTA_INVALID")
    added, changed, removed_groups = (list(group_list) for group_list in result)
    if (len(set(added)) != len(added) or len(set(changed)) != len(changed) or
            len(set(removed_groups)) != len(removed_groups)):
        fail("SUPERVISOR_RELOAD_DELTA_DUPLICATE")
    return added, changed, removed_groups


def supervisor_old_rows(inventory):
    return [row for row in inventory if row["group"] != SUPERVISOR_PROGRAM_NAME]


def supervisor_old_rows_match(baseline, current):
    return supervisor_old_rows(current) == supervisor_old_rows(baseline)


def assert_supervisor_old_rows_unchanged(baseline, current):
    if not supervisor_old_rows_match(baseline, current):
        fail("SUPERVISOR_EXISTING_GROUP_CHANGED")


def assert_observer_group(inventory, state=None):
    rows = [row for row in inventory if row["group"] == SUPERVISOR_PROGRAM_NAME]
    if state is None:
        if rows:
            fail("SUPERVISOR_OBSERVER_GROUP_UNEXPECTED")
        return None
    if (len(rows) != 1 or rows[0]["name"] != SUPERVISOR_PROGRAM_NAME or
            rows[0]["state"] != state or
            (state == "RUNNING" and rows[0]["pid"] <= 1) or
            (state == "STOPPED" and rows[0]["pid"] != 0)):
        fail("SUPERVISOR_OBSERVER_GROUP_STATE")
    return rows[0]


def wait_for_observer_running(inventory_fn, baseline, *, max_polls=SUPERVISOR_STATE_POLL_ATTEMPTS,
                              poll_interval=SUPERVISOR_STATE_POLL_INTERVAL_SECONDS,
                              sleep_fn=time.sleep):
    """Boundedly wait for the one new observer group to reach RUNNING."""
    prior_pid = None
    for index in range(max_polls):
        current = inventory_fn()
        assert_supervisor_old_rows_unchanged(baseline, current)
        rows = [row for row in current if row["group"] == SUPERVISOR_PROGRAM_NAME]
        if (len(rows) != 1 or rows[0]["name"] != SUPERVISOR_PROGRAM_NAME):
            fail("SUPERVISOR_OBSERVER_START_INVENTORY")
        target = rows[0]
        if target["state"] == "RUNNING":
            if prior_pid is not None and target["pid"] != prior_pid:
                fail("SUPERVISOR_OBSERVER_START_PID_CHANGED")
            return target, current
        if target["state"] != "STARTING" or target["pid"] <= 1:
            fail("SUPERVISOR_OBSERVER_START_STATE")
        if prior_pid is not None and target["pid"] != prior_pid:
            fail("SUPERVISOR_OBSERVER_START_PID_CHANGED")
        prior_pid = target["pid"]
        if index + 1 < max_polls:
            sleep_fn(poll_interval)
    fail("SUPERVISOR_OBSERVER_START_TIMEOUT")


def wait_for_observer_quiescent(inventory_fn, prior_inventory, initial_pid, *,
                                max_polls=SUPERVISOR_STATE_POLL_ATTEMPTS,
                                poll_interval=SUPERVISOR_STATE_POLL_INTERVAL_SECONDS,
                                sleep_fn=time.sleep):
    """Boundedly wait for our observer process to stop, recording unrelated drift."""
    global SUPERVISOR_PROGRAM_ROLLBACK_PRIOR_GROUPS_UNCHANGED
    for index in range(max_polls):
        current = inventory_fn()
        SUPERVISOR_PROGRAM_ROLLBACK_PRIOR_GROUPS_UNCHANGED = (
            bool(SUPERVISOR_PROGRAM_ROLLBACK_PRIOR_GROUPS_UNCHANGED) and
            supervisor_old_rows_match(prior_inventory, current))
        rows = [row for row in current if row["group"] == SUPERVISOR_PROGRAM_NAME]
        if (len(rows) != 1 or rows[0]["name"] != SUPERVISOR_PROGRAM_NAME):
            fail("SUPERVISOR_ROLLBACK_OBSERVER_INVENTORY")
        target = rows[0]
        if (target["state"] == "STOPPED" and target["pid"] == 0 or
                target["state"] in {"BACKOFF", "EXITED", "FATAL"} and target["pid"] == 0):
            return target, current
        if (target["state"] not in {"RUNNING", "STARTING", "STOPPING"} or
                target["pid"] <= 1 or target["pid"] != initial_pid):
            fail("SUPERVISOR_ROLLBACK_TARGET_STATE_AMBIGUOUS")
        if index + 1 < max_polls:
            sleep_fn(poll_interval)
    fail("SUPERVISOR_ROLLBACK_STOP_TIMEOUT")


def read_supervisor_config_inputs(endpoint):
    """Parse the exact already-pinned root-owned config files without globbing new files."""
    parser = configparser.ConfigParser(interpolation=None, strict=True,
                                       delimiters=("=", ":"))
    for row in endpoint.get("config_inputs", []):
        path = Path(row["path"])
        raw, identity = bounded_read(path, 262_144)
        if hashlib.sha256(raw).hexdigest() != row.get("sha256"):
            fail("SUPERVISOR_CONFIG_INPUT_READBACK")
        if identity is None or (identity[0], identity[1], stat.S_IMODE(identity[2]),
                                identity[3], identity[4], identity[5], identity[6],
                                identity[7], identity[8]) != (
                row.get("device"), row.get("inode"), row.get("mode"), row.get("nlink"),
                row.get("uid"), row.get("gid"), row.get("size"), row.get("mtime_ns"),
                row.get("ctime_ns")):
            fail("SUPERVISOR_CONFIG_INPUT_IDENTITY")
        try:
            parser.read_string(raw.decode("utf-8", "strict"), source=str(path))
        except (UnicodeError, configparser.Error):
            fail("SUPERVISOR_CONFIG_INPUT_INVALID")
    if _socket_config_snapshot() != endpoint:
        fail("SUPERVISOR_CONFIG_INPUTS_CHANGED_AFTER_PARSE")
    return parser


def supervisor_program_config_preflight(endpoint, config_raw):
    validate_supervisor_program_config(config_raw)
    if endpoint.get("include_glob") != "/etc/supervisor/conf.d/*.conf":
        fail("SUPERVISOR_INCLUDE_PATTERN_NOT_ALLOWLISTED")
    if SUPERVISOR_PROGRAM.exists() or SUPERVISOR_PROGRAM.is_symlink():
        fail("SUPERVISOR_PROGRAM_CONFIG_PREEXISTS")
    parser = read_supervisor_config_inputs(endpoint)
    if "program:" + SUPERVISOR_PROGRAM_NAME in parser.sections():
        fail("SUPERVISOR_PROGRAM_NAME_ALREADY_CONFIGURED")
    if "group:" + SUPERVISOR_PROGRAM_NAME in parser.sections():
        fail("SUPERVISOR_PROGRAM_NAME_ALREADY_GROUPED")
    return {"input_count": len(endpoint["config_inputs"]),
            "include_match": endpoint.get("include_glob") == "/etc/supervisor/conf.d/*.conf",
            "observer_section_absent": True}


def supervisor_runtime_delta(current, baseline, expected_config):
    """Allow only the exact new config input while pinning the same running daemon."""
    if not isinstance(current, dict) or not isinstance(baseline, dict):
        return False
    current_base = json.loads(json.dumps(current))
    baseline_base = json.loads(json.dumps(baseline))
    for value in (current_base, baseline_base):
        value["endpoint"].pop("config_inputs", None)
        value["daemon"].pop("config_inputs", None)
    if current_base != baseline_base:
        return False
    expected_path = str(SUPERVISOR_PROGRAM)
    def inputs(pin):
        return pin.get("endpoint", {}).get("config_inputs")
    before, after = inputs(baseline), inputs(current)
    if not isinstance(before, list) or not isinstance(after, list):
        return False
    old_by_path = {row.get("path"): row for row in before if isinstance(row, dict)}
    new_by_path = {row.get("path"): row for row in after if isinstance(row, dict)}
    if (len(old_by_path) != len(before) or len(new_by_path) != len(after) or
            set(new_by_path) != set(old_by_path) | {expected_path} or
            any(new_by_path[path] != row for path, row in old_by_path.items()) or
            new_by_path.get(expected_path) != expected_config):
        return False
    if pin_inputs := current.get("daemon", {}).get("config_inputs"):
        return pin_inputs == after
    return False


def run_supervisor_group_activation(inventory_fn, rpc_fn, baseline, pre_start_fn=None,
                                    sleep_fn=time.sleep):
    """Apply only one new process group, checking the complete preexisting inventory."""
    global SUPERVISOR_PROGRAM_RELOADED, SUPERVISOR_PROGRAM_ADDED
    global SUPERVISOR_PROGRAM_STARTED, SUPERVISOR_PROGRAM_AFTER_INVENTORY
    global SUPERVISOR_PROGRAM_ACTIVATION
    SUPERVISOR_PROGRAM_RELOADED = True
    delta = validate_reload_config_delta(rpc_fn("supervisor.reloadConfig"))
    after_reload = inventory_fn()
    assert_supervisor_old_rows_unchanged(baseline, after_reload)
    assert_observer_group(after_reload)

    result = rpc_fn("supervisor.addProcessGroup", SUPERVISOR_PROGRAM_NAME)
    if result is not True:
        fail("SUPERVISOR_ADD_PROCESS_GROUP_FAILED")
    SUPERVISOR_PROGRAM_ADDED = True
    after_add = inventory_fn()
    assert_supervisor_old_rows_unchanged(baseline, after_add)
    assert_observer_group(after_add, "STOPPED")

    if pre_start_fn is not None:
        pre_start_fn()
    SUPERVISOR_PROGRAM_STARTED = True
    result = rpc_fn("supervisor.startProcess", SUPERVISOR_PROGRAM_NAME, True)
    if result is not True:
        fail("SUPERVISOR_START_PROCESS_FAILED")
    target, after_start = wait_for_observer_running(
        inventory_fn, baseline, sleep_fn=sleep_fn)
    SUPERVISOR_PROGRAM_AFTER_INVENTORY = after_start
    receipt = {"reload_delta": delta, "process_inventory_count_before": len(baseline),
               "process_inventory_count_after": len(after_start),
               "existing_process_inventory_unchanged": True,
               "observer_process": target}
    SUPERVISOR_PROGRAM_ACTIVATION = receipt
    return receipt


def run(args, timeout=20):
    global NATIVE_MUTATION_ATTEMPTED
    argv = list(args)
    if argv and argv[0] == "supervisorctl":
        verify_supervisorctl_pin()
        if len(argv) != 3 or argv[1] != "status" or argv[2] not in (MODEL_SERVICE, LEGACY_GUARD):
            fail("SUPERVISOR_RPC_OPERATION_NOT_ALLOWLISTED")
        row = _supervisor_process_info(argv[2])
        state = row.get("statename")
        pid = row.get("pid")
        if state not in {"RUNNING", "STOPPED", "EXITED", "FATAL", "BACKOFF", "UNKNOWN"}:
            fail("SUPERVISOR_RPC_STATE_INVALID")
        if state == "RUNNING":
            if type(pid) is not int or pid <= 0:
                fail("SUPERVISOR_RPC_RUNNING_PID_INVALID")
            output = f"{argv[2]} RUNNING pid {pid}, rpc readback"
            rc = 0
        else:
            if pid not in (0, None):
                fail("SUPERVISOR_RPC_STOPPED_PID_INVALID")
            output = f"{argv[2]} {state}, rpc readback"
            rc = 3
        return subprocess.CompletedProcess(args, rc, output + "\n", "")
    if argv and argv[0] == "systemctl":
        allowed = {
            ("is-active", SERVICE),
            ("is-enabled", SERVICE),
            ("daemon-reload",),
            ("enable", "--now", SERVICE),
            ("show", SERVICE, "--property=MainPID", "--value"),
            ("stop", SERVICE),
            ("disable", SERVICE),
        }
        if tuple(argv[1:]) not in allowed:
            fail("SYSTEMCTL_OPERATION_NOT_ALLOWLISTED")
        if tuple(argv[1:]) in {("daemon-reload",), ("enable", "--now", SERVICE),
                               ("stop", SERVICE), ("disable", SERVICE)}:
            mark_native_mutation_attempted()
        return _systemctl_run(argv[1:], timeout)
    try:
        return subprocess.run(argv, capture_output=True, text=True, shell=False,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        fail("COMMAND_UNAVAILABLE")


def _systemctl_run(arguments, timeout):
    if not isinstance(SYSTEMCTL_PIN, dict):
        fail("SYSTEMCTL_PIN_UNAVAILABLE")
    if _supervisorctl_snapshot(SYSTEMCTL_PATH, max_size=64 * 1024**2) != SYSTEMCTL_PIN:
        fail("SYSTEMCTL_PIN_CHANGED_BEFORE_QUERY")
    try:
        result = subprocess.run([str(SYSTEMCTL_PATH), *arguments], capture_output=True,
                                text=True, shell=False, timeout=timeout, check=False,
                                close_fds=True,
                                env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                                     "LANG": "C", "LC_ALL": "C"})
    except (OSError, subprocess.TimeoutExpired):
        fail("SYSTEMCTL_COMMAND_FAILED")
    if _supervisorctl_snapshot(SYSTEMCTL_PATH, max_size=64 * 1024**2) != SYSTEMCTL_PIN:
        fail("SYSTEMCTL_PIN_CHANGED_AFTER_QUERY")
    return result


def _supervisor_process_info(name):
    if name not in (MODEL_SERVICE, LEGACY_GUARD):
        fail("SUPERVISOR_RPC_NAME_NOT_ALLOWLISTED")
    endpoint = _socket_config_snapshot()
    daemon = _supervisord_identity(endpoint)
    pin = SUPERVISORCTL_PIN.get("daemon") if isinstance(SUPERVISORCTL_PIN, dict) else None
    if pin is not None:
        pinned_daemon = dict(pin)
        current_daemon = dict(daemon)
        if SUPERVISOR_ALLOWED_PROGRAM_CONFIG is not None:
            pinned_daemon.pop("config_inputs", None)
            current_daemon.pop("config_inputs", None)
        if pinned_daemon != current_daemon:
            fail("SUPERVISOR_RPC_DAEMON_PIN_CHANGED")
    if (endpoint["socket"]["uid"] != daemon["credentials"]["uid"] or
            endpoint["socket"]["gid"] != daemon["credentials"]["gid"]):
        fail("SUPERVISOR_SOCKET_CREDENTIAL_MISMATCH")
    transport = _UnixXMLRPCTransport(endpoint["path"],
        {"pid": daemon["pid"], **daemon["credentials"]}, endpoint["parent_chain"])
    proxy = xmlrpc.client.ServerProxy("http://supervisor.local/RPC2", transport=transport,
                                      allow_none=False, use_builtin_types=True)
    try:
        if proxy.supervisor.getAPIVersion() != "3.0":
            fail("SUPERVISOR_RPC_API_VERSION")
        if proxy.supervisor.getState() != {"statecode": 1, "statename": "RUNNING"}:
            fail("SUPERVISOR_RPC_DAEMON_NOT_RUNNING")
        if proxy.supervisor.getPID() != daemon["pid"]:
            fail("SUPERVISOR_RPC_PID_MISMATCH")
        identification = proxy.supervisor.getIdentification()
        if (pin is not None and (not isinstance(identification, str) or
                hashlib.sha256(identification.encode()).hexdigest() !=
                pin.get("identification_sha256"))):
            fail("SUPERVISOR_RPC_IDENTIFICATION_MISMATCH")
        row = proxy.supervisor.getProcessInfo(name)
        peer = transport.peer_identity()
    except (xmlrpc.client.Error, OSError, ValueError, KeyError, TypeError):
        fail("SUPERVISOR_RPC_QUERY_FAILED")
    finally:
        proxy.close()
    if (peer is None or peer != {"pid": daemon["pid"], **daemon["credentials"]} or
            _socket_config_snapshot() != endpoint or _supervisord_identity(endpoint) != daemon or
            not isinstance(row, dict) or row.get("name") != name or row.get("group") != name or
            not isinstance(row.get("statename"), str)):
        fail("SUPERVISOR_RPC_IDENTITY_CHANGED")
    return row


def _cgroup_scalar(path: Path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                     getattr(os, "O_CLOEXEC", 0))
    except OSError:
        fail("CGROUP_MEMORY_UNAVAILABLE")
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode):
            fail("CGROUP_MEMORY_UNSAFE")
        raw = os.read(fd, 65)
        if len(raw) > 64:
            fail("CGROUP_MEMORY_LIMIT")
    finally:
        os.close(fd)
    value = raw.strip()
    if not re.fullmatch(rb"(?:0|[1-9][0-9]{0,19})", value):
        fail("CGROUP_MEMORY_VALUE")
    return int(value)


def _proc_file(path: Path, limit, error_code):
    try:
        with path.open("rb") as stream:
            raw = stream.read(limit + 1)
    except OSError:
        fail(error_code)
    if len(raw) > limit:
        fail(error_code)
    return raw


def _proc_read(pid, name, limit, error_code):
    return _proc_file(Path("/proc") / str(pid) / name, limit, error_code)


def _proc_start_ticks(pid):
    raw = _proc_read(pid, "stat", 8192, "CGROUP_PROCESS_IDENTITY_UNAVAILABLE")
    if not raw.startswith(str(pid).encode() + b" ("):
        fail("CGROUP_PROCESS_STAT_INVALID")
    boundary = raw.rfind(b") ")
    try:
        value = raw[boundary + 2:].split()[19]
        if not value.isdigit():
            raise ValueError
        return int(value)
    except (ValueError, IndexError):
        fail("CGROUP_PROCESS_STAT_INVALID")


def _proc_effective_credentials(pid):
    raw = _proc_read(pid, "status", 65536, "SUPERVISORD_CREDENTIALS_UNAVAILABLE")
    uids = [line.split()[1:] for line in raw.splitlines() if line.startswith(b"Uid:")]
    gids = [line.split()[1:] for line in raw.splitlines() if line.startswith(b"Gid:")]
    try:
        if len(uids) != 1 or len(gids) != 1 or len(uids[0]) != 4 or len(gids[0]) != 4:
            raise ValueError
        return {"uid": int(uids[0][1]), "gid": int(gids[0][1])}
    except (ValueError, IndexError):
        fail("SUPERVISORD_CREDENTIALS_INVALID")


def _proc_start_epoch_ns(pid, ticks):
    raw = _proc_file(Path("/proc/stat"), 65536, "PROCESS_BOOT_TIME_UNAVAILABLE")
    rows = [line.split()[1] for line in raw.splitlines()
            if line.startswith(b"btime ") and len(line.split()) == 2]
    try:
        hz = os.sysconf("SC_CLK_TCK")
        if len(rows) != 1 or not rows[0].isdigit() or type(hz) is not int or hz <= 0:
            raise ValueError
        boot_epoch = int(rows[0])
        return boot_epoch * 1_000_000_000 + ticks * 1_000_000_000 // hz
    except (OSError, ValueError, TypeError):
        fail("PROCESS_BOOT_TIME_INVALID")


def process_cgroup_info(pid):
    before = _proc_start_ticks(pid)
    raw_before = _proc_read(pid, "cgroup", 8192, "CGROUP_PROCESS_PATH_UNAVAILABLE")
    rows = [line.split(b":", 2)[2] for line in raw_before.splitlines()
            if line.startswith(b"0::") and len(line.split(b":", 2)) == 3]
    if len(rows) != 1:
        fail("CGROUP_V2_PATH_AMBIGUOUS")
    try:
        relative = rows[0].decode("utf-8", "strict")
        components = relative.split("/")
        if not relative.startswith("/") or any(item in (".", "..") for item in components):
            raise ValueError
        root = CGROUP_ROOT.resolve(strict=True)
        target = (root / relative.lstrip("/")).resolve(strict=True)
        if os.path.commonpath((str(root), str(target))) != str(root):
            raise ValueError
        raw_after = _proc_read(pid, "cgroup", 8192, "CGROUP_PROCESS_PATH_UNAVAILABLE")
    except (OSError, UnicodeError, ValueError):
        fail("CGROUP_PROCESS_PATH_UNSAFE")
    after = _proc_start_ticks(pid)
    if before != after or raw_before != raw_after:
        fail("CGROUP_PROCESS_IDENTITY_CHANGED")
    return {"pid": pid, "start_ticks": before, "cgroup_path": str(target)}


def resolve_cgroup_target(legacy_snapshot):
    self_info = process_cgroup_info(os.getpid())
    if (self_info["start_ticks"] != _proc_start_ticks(os.getpid()) or
            self_info["cgroup_path"] != str(CGROUP_ROOT.resolve(strict=True))):
        fail("SELF_CGROUP_NOT_SHARED_MEMORY_TARGET")
    legacy = legacy_snapshot.get("process", {})
    legacy_info = process_cgroup_info(legacy.get("pid"))
    if (legacy_info["start_ticks"] != legacy.get("start_ticks") or
            legacy_info["cgroup_path"] != self_info["cgroup_path"]):
        fail("LEGACY_CGROUP_TARGET_MISMATCH")
    model_before = _supervisor_process_info(MODEL_SERVICE)
    if model_before.get("group") != "nox-ds41-8098" or model_before.get("statename") not in ("RUNNING", "STOPPED", "EXITED"):
        fail("MODEL_SERVICE_STATE_UNSUPPORTED")
    model_pid = model_before.get("pid")
    if model_before["statename"] == "RUNNING":
        if type(model_pid) is not int or model_pid <= 0:
            fail("MODEL_RUNNING_PID_INVALID")
        model_info = process_cgroup_info(model_pid)
        model_info["state"] = "RUNNING"
        if model_info["cgroup_path"] != self_info["cgroup_path"]:
            fail("MODEL_CGROUP_TARGET_MISMATCH")
    else:
        if model_pid != 0:
            fail("MODEL_STOPPED_PID_INVALID")
        census = model_runtime_census(self_info["cgroup_path"])
        if census["matches"]:
            fail("MODEL_RUNTIME_PRESENT_WHILE_STOPPED")
        model_info = {"pid": None, "state": model_before["statename"],
                      "cgroup_path": self_info["cgroup_path"],
                      "census": census, "anchor": "installer_and_legacy_guard"}
    model_after = _supervisor_process_info(MODEL_SERVICE)
    if (model_after.get("statename") != model_before.get("statename") or
            model_after.get("pid") != model_before.get("pid") or
            model_after.get("group") != model_before.get("group")):
        fail("MODEL_STATUS_CHANGED_DURING_CGROUP_MAP")
    return {"target": self_info["cgroup_path"], "self": self_info,
            "legacy_guard": legacy_info, "model": model_info,
            "mapping": "proc_0_unified_to_sys_fs_cgroup_verified"}


def model_runtime_census(target_path):
    """Bounded, sanitized census for detached llama-server model workers."""
    started = time.monotonic()
    rows = []
    bytes_read = 0
    try:
        pids = sorted((int(p.name) for p in Path("/proc").iterdir() if p.name.isdigit()))
    except OSError:
        fail("MODEL_CENSUS_PROC_UNAVAILABLE")
    if len(pids) > 16384:
        fail("MODEL_CENSUS_PID_LIMIT")
    for pid in pids:
        try:
            if time.monotonic() - started > 5.0:
                fail("MODEL_CENSUS_DEADLINE")
            ticks = _proc_start_ticks(pid)
            exe = os.readlink(Path("/proc") / str(pid) / "exe")
            raw = _proc_read(pid, "cmdline", 32768, "MODEL_CENSUS_CMDLINE_UNAVAILABLE")
            env = _proc_read(pid, "environ", 65536, "MODEL_CENSUS_ENV_UNAVAILABLE")
            bytes_read += len(raw) + len(env)
            if bytes_read > 32 * 1024**2:
                fail("MODEL_CENSUS_BYTE_BUDGET")
            cgroup = process_cgroup_info(pid)["cgroup_path"]
            has_model = (MODEL_PATH.encode() in raw or
                         b"LLAMA_ARG_MODEL=" + MODEL_PATH.encode() in env)
            if Path(exe).name == "llama-server" and has_model:
                if (_proc_start_ticks(pid) != ticks or
                        os.readlink(Path("/proc") / str(pid) / "exe") != exe or
                        _proc_read(pid, "cmdline", 32768, "MODEL_CENSUS_CMDLINE_UNAVAILABLE") != raw or
                        _proc_read(pid, "environ", 65536, "MODEL_CENSUS_ENV_UNAVAILABLE") != env):
                    fail("MODEL_CENSUS_PROCESS_CHANGED")
                rows.append({"pid": pid, "start_ticks": ticks,
                             "exe_path_sha256": hashlib.sha256(os.fsencode(exe)).hexdigest(),
                             "argv_sha256": hashlib.sha256(raw).hexdigest(),
                             "environment_sha256": hashlib.sha256(env).hexdigest(),
                             "cgroup_path": cgroup,
                             "in_memory_target_cgroup": cgroup == target_path})
        except FileNotFoundError:
            continue
        if len(rows) > 64:
            fail("MODEL_CENSUS_MATCH_LIMIT")
    return {"target": target_path, "scope": "all_visible_proc_pids",
            "count": len(rows), "matches": rows,
            "pids_scanned": len(pids), "bytes_read": bytes_read,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "method": "proc_exe_basename_and_model_path_argv_or_env"}


def cgroup_memory_snapshot(target_path):
    target = Path(target_path)
    root = CGROUP_ROOT.resolve(strict=True)
    try:
        resolved = target.resolve(strict=True)
        if (resolved != target or os.path.commonpath((str(root), str(resolved))) != str(root)):
            raise ValueError
    except (OSError, ValueError):
        fail("CGROUP_TARGET_PATH_CHANGED")
    current_first = _cgroup_scalar(resolved / "memory.current")
    maximum = _cgroup_scalar(resolved / "memory.max")
    current_last = _cgroup_scalar(resolved / "memory.current")
    # Use the higher of two immediate reads so concurrent allocation cannot
    # make the admission estimate optimistic.
    current = max(current_first, current_last)
    headroom = maximum - current
    return {"cgroup_path": str(resolved),
            "memory.current": current, "memory.max": maximum,
            "memory.current_samples": [current_first, current_last],
            "raw_headroom_bytes": headroom,
            "sampled_at": time.time(), "status": "OK" if headroom >= 0 else "INCONSISTENT"}


def require_memory_headroom(snapshot, minimum, code):
    if (not isinstance(snapshot, dict) or
            type(snapshot.get("raw_headroom_bytes")) is not int or
            snapshot.get("status") != "OK" or
            snapshot["raw_headroom_bytes"] < minimum):
        fail(code)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_KEY")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError("NONFINITE")


def legacy_policy_snapshot():
    raw, identity = bounded_read(LEGACY_POLICY, 8192)
    try:
        policy = json.loads(raw.decode("utf-8", "strict"),
                            object_pairs_hook=_unique_pairs,
                            parse_constant=_reject_constant)
    except (ValueError, UnicodeError, TypeError):
        fail("LEGACY_POLICY_INVALID")
    if (not isinstance(policy, dict) or policy.get("schema") != "NOX_LIFELINE_V2" or
            policy.get("enabled") is not False or
            not isinstance(policy.get("services"), list) or
            len(policy["services"]) != len(LEGACY_SERVICES)):
        fail("LEGACY_POLICY_NOT_DISABLED")
    seen = set()
    for row in policy["services"]:
        if (not isinstance(row, dict) or set(row) != {"name", "restart"} or
                row.get("name") not in LEGACY_SERVICES or
                row.get("name") in seen or row.get("restart") is not False):
            fail("LEGACY_POLICY_NOT_DISABLED")
        seen.add(row["name"])
    if seen != LEGACY_SERVICES:
        fail("LEGACY_POLICY_SERVICES_INCOMPLETE")
    return {"sha256": hashlib.sha256(raw).hexdigest(),
            "device": identity[0], "inode": identity[1],
            "services": sorted(seen), "enabled": False,
            "all_restart_flags_false": True}


def legacy_config_snapshot():
    raw, identity = bounded_read(LEGACY_CONFIG, 8192)
    config_sha = hashlib.sha256(raw).hexdigest()
    if config_sha != LEGACY_CONFIG_SHA256:
        fail("LEGACY_CONFIG_SHA_MISMATCH")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeError:
        fail("LEGACY_CONFIG_INVALID")
    section = None
    sections = 0
    fields = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            if section == "program:" + LEGACY_GUARD:
                sections += 1
            continue
        if section == "program:" + LEGACY_GUARD and "=" in line:
            key, value = (part.strip() for part in line.split("=", 1))
            if key in ("autostart", "autorestart", "command"):
                if key in fields:
                    fail("LEGACY_CONFIG_DUPLICATE_FIELD")
                fields[key] = value if key == "command" else value.lower()
    if (sections != 1 or fields.get("autostart") != "false" or
            fields.get("autorestart") not in ("true", "false") or
            not isinstance(fields.get("command"), str) or "%(" in fields["command"]):
        fail("LEGACY_CONFIG_UNSAFE")
    try:
        command_argv = tuple(shlex.split(fields["command"], posix=True))
    except ValueError:
        fail("LEGACY_CONFIG_COMMAND_INVALID")
    if command_argv != LEGACY_EXPECTED_ARGV:
        fail("LEGACY_CONFIG_COMMAND_NOT_ALLOWLISTED")
    return {"sha256": config_sha,
            "device": identity[0], "inode": identity[1],
            "autostart": False,
            "autorestart": fields["autorestart"] == "true",
            "command_matches_expected_argv": True}


def legacy_script_snapshot():
    raw, identity = bounded_read(LEGACY_SCRIPT, 32768)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != LEGACY_SCRIPT_SHA256:
        fail("LEGACY_SCRIPT_SHA_MISMATCH")
    return {"sha256": digest, "device": identity[0], "inode": identity[1],
            "mode": stat.S_IMODE(identity[2]), "nlink": identity[3],
            "uid": identity[4], "gid": identity[5], "size": identity[6],
            "mtime_ns": identity[7], "ctime_ns": identity[8]}


def legacy_state_worker_starts():
    raw, identity = bounded_read(LEGACY_STATE, 262144)
    try:
        state = json.loads(raw.decode("utf-8", "strict"),
                           object_pairs_hook=_unique_pairs,
                           parse_constant=_reject_constant)
    except (ValueError, UnicodeError, TypeError):
        fail("LEGACY_STATE_INVALID")
    services = state.get("services") if isinstance(state, dict) else None
    if not isinstance(services, dict) or set(services) != LEGACY_SERVICES:
        fail("LEGACY_STATE_INCOMPLETE")
    starts = 0
    for name in LEGACY_SERVICES:
        row = services.get(name)
        attempts = row.get("attempts") if isinstance(row, dict) else None
        if not isinstance(attempts, list):
            fail("LEGACY_STATE_ATTEMPTS_INVALID")
        for item in attempts:
            if type(item) is int:
                valid = item >= 0
            elif type(item) is float:
                valid = math.isfinite(item) and item >= 0
            else:
                valid = False
            if not valid:
                fail("LEGACY_STATE_ATTEMPTS_INVALID")
        starts += len(attempts)
    # Older NOX state stores start counts as per-service attempt ledgers rather
    # than a scalar. If a scalar is present, it must agree with those ledgers.
    scalar = state.get("worker_starts")
    if scalar is not None and (type(scalar) is not int or scalar != starts):
        fail("LEGACY_STATE_WORKER_STARTS_MISMATCH")
    if starts != 0:
        fail("LEGACY_STATE_WORKER_STARTS_NONZERO")
    return {"worker_starts": starts, "count_source": "empty_service_attempt_ledgers",
            "device": identity[0], "inode": identity[1]}


def legacy_guard_process():
    status = run(["supervisorctl", "status", LEGACY_GUARD], timeout=10)
    lines = status.stdout.strip().splitlines()
    match = re.fullmatch(r"nox-lifeline-guard\s+RUNNING\s+pid\s+([1-9][0-9]{0,9})(?:,.*)?",
                         lines[0]) if status.returncode == 0 and len(lines) == 1 else None
    if match is None:
        fail("LEGACY_GUARD_NOT_EXACTLY_RUNNING")
    pid = int(match.group(1))
    proc = Path("/proc") / str(pid)

    def stat_ticks():
        raw = _proc_read(pid, "stat", 4096, "LEGACY_GUARD_IDENTITY_UNAVAILABLE")
        if not raw.startswith(str(pid).encode() + b" ("):
            fail("LEGACY_GUARD_STAT_INVALID")
        boundary = raw.rfind(b") ")
        try:
            ticks = raw[boundary + 2:].split()[19]
            if not ticks.isdigit():
                raise ValueError
            return int(ticks)
        except (ValueError, IndexError):
            fail("LEGACY_GUARD_STAT_INVALID")

    first_ticks = stat_ticks()
    try:
        exe_before = os.readlink(proc / "exe")
        argv_before = _proc_read(pid, "cmdline", 16384,
                                 "LEGACY_GUARD_IDENTITY_UNAVAILABLE")
    except OSError:
        fail("LEGACY_GUARD_IDENTITY_UNAVAILABLE")
    if not argv_before or len(argv_before) > 16384 or not argv_before.endswith(b"\0"):
        fail("LEGACY_GUARD_ARGV_INVALID")
    try:
        argv = tuple(item.decode("utf-8", "strict")
                     for item in argv_before[:-1].split(b"\0"))
    except UnicodeError:
        fail("LEGACY_GUARD_ARGV_INVALID")
    if argv != LEGACY_EXPECTED_ARGV or exe_before != os.path.realpath("/usr/bin/python3"):
        fail("LEGACY_GUARD_COMMAND_NOT_ALLOWLISTED")
    second_ticks = stat_ticks()
    try:
        exe_after = os.readlink(proc / "exe")
        argv_after = _proc_read(pid, "cmdline", 16384,
                                "LEGACY_GUARD_IDENTITY_UNAVAILABLE")
    except OSError:
        fail("LEGACY_GUARD_IDENTITY_UNAVAILABLE")
    if (len(os.fsencode(exe_before)) > 4096 or first_ticks != second_ticks or exe_before != exe_after or
            argv_before != argv_after or stat_ticks() != first_ticks):
        fail("LEGACY_GUARD_IDENTITY_CHANGED")
    final_status = run(["supervisorctl", "status", LEGACY_GUARD], timeout=10)
    final_lines = final_status.stdout.strip().splitlines()
    final_match = re.fullmatch(
        r"nox-lifeline-guard\s+RUNNING\s+pid\s+([1-9][0-9]{0,9})(?:,.*)?",
        final_lines[0]) if final_status.returncode == 0 and len(final_lines) == 1 else None
    if final_match is None or int(final_match.group(1)) != pid:
        fail("LEGACY_GUARD_STATUS_CHANGED")
    return {"pid": pid, "start_ticks": first_ticks, "exe": exe_before,
            "argv_sha256": hashlib.sha256(argv_before).hexdigest(),
            "process_start_epoch_ns": _proc_start_epoch_ns(pid, first_ticks),
            "script_sha256": LEGACY_SCRIPT_SHA256}


def legacy_guard_snapshot():
    policy = legacy_policy_snapshot()
    config = legacy_config_snapshot()
    script = legacy_script_snapshot()
    state = legacy_state_worker_starts()
    process = legacy_guard_process()
    # /proc stat start time has jiffy precision and btime is second precision;
    # the 1.5 s margin makes this a conservative proof the pinned script file
    # predated process start, rather than a later replacement at the same path.
    if script["ctime_ns"] > process["process_start_epoch_ns"] - 1_500_000_000:
        fail("LEGACY_SCRIPT_NOT_PREEXISTING_AT_PROCESS_START")
    return {"policy": policy, "config": config, "script": script, "state": state,
            "process": process,
            "script_preexisting_at_process_start": True,
            "script_binding_margin_ns": 1_500_000_000}


def recheck_legacy_guard(expected):
    current = legacy_guard_snapshot()
    if current != expected:
        fail("LEGACY_GUARD_CHANGED_DURING_INSTALL")
    return current


def bounded_read(path: Path, limit: int, *, allow_absent=False):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                     getattr(os, "O_CLOEXEC", 0))
    except FileNotFoundError:
        if allow_absent:
            return None, None
        fail("FILE_MISSING")
    except OSError:
        fail("FILE_UNSAFE")
    try:
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1 or
                meta.st_uid != 0 or meta.st_mode & 0o022 or meta.st_size > limit):
            fail("FILE_UNSAFE")
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, min(8192, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(fd)
        ident = (meta.st_dev, meta.st_ino, meta.st_mode, meta.st_nlink,
                 meta.st_uid, meta.st_gid, meta.st_size, meta.st_mtime_ns,
                 meta.st_ctime_ns)
        ident_after = (after.st_dev, after.st_ino, after.st_mode, after.st_nlink,
                       after.st_uid, after.st_gid, after.st_size, after.st_mtime_ns,
                       after.st_ctime_ns)
        if len(raw) > limit or len(raw) != meta.st_size or ident_after != ident:
            fail("FILE_CHANGED_DURING_READ")
        return raw, ident
    finally:
        os.close(fd)


def checked_bundle(name):
    item = BUNDLE.get(name)
    if not isinstance(item, dict) or set(item) != {"content", "sha256"}:
        fail("BUNDLE_SCHEMA")
    try:
        raw = base64.b64decode(item["content"], validate=True)
    except Exception:
        fail("BUNDLE_BASE64")
    digest = hashlib.sha256(raw).hexdigest()
    if (not 10 <= len(raw) <= MAX_BYTES[name] or
            digest != item["sha256"] or digest != BUNDLE_SHA256[name]):
        fail("BUNDLE_DIGEST")
    return raw


def checked_supervisor_bundle(name):
    """Validate only the two extra assets used by the non-systemd fallback."""
    item = BUNDLE.get(name)
    if not isinstance(item, dict) or set(item) != {"content", "sha256"}:
        fail("SUPERVISOR_BUNDLE_SCHEMA")
    try:
        raw = base64.b64decode(item["content"], validate=True)
    except Exception:
        fail("SUPERVISOR_BUNDLE_BASE64")
    if (not 10 <= len(raw) <= SUPERVISOR_BUNDLE_MAX_BYTES[name] or
            hashlib.sha256(raw).hexdigest() != item["sha256"] or
            hashlib.sha256(raw).hexdigest() != SUPERVISOR_BUNDLE_SHA256[name]):
        fail("SUPERVISOR_BUNDLE_DIGEST")
    return raw


def validate_supervisor_program_config(raw):
    """Accept exactly the single bounded observer group, with direct argv only."""
    if not isinstance(raw, bytes) or len(raw) > SUPERVISOR_BUNDLE_MAX_BYTES[
            SUPERVISOR_PROGRAM_BUNDLE_KEY]:
        fail("SUPERVISOR_PROGRAM_CONFIG_SIZE")
    parser = configparser.ConfigParser(interpolation=None, strict=True,
                                       delimiters=("=", ":"))
    try:
        parser.read_string(raw.decode("utf-8", "strict"))
    except (UnicodeError, configparser.Error):
        fail("SUPERVISOR_PROGRAM_CONFIG_INVALID")
    if parser.sections() != ["program:" + SUPERVISOR_PROGRAM_NAME]:
        fail("SUPERVISOR_PROGRAM_CONFIG_SECTIONS")
    section = "program:" + SUPERVISOR_PROGRAM_NAME
    options = dict(parser.items(section, raw=True))
    expected = {
        "command": "/usr/bin/python3 -u /root/nox/scripts/nox_lifeline_observer_bootstrap.py",
        "directory": "/root/nox",
        "user": "root",
        "numprocs": "1",
        "process_name": "%(program_name)s",
        "autostart": "true",
        "autorestart": "unexpected",
        "startsecs": "5",
        "startretries": "2",
        "stopsignal": "TERM",
        "stopwaitsecs": "5",
        "stopasgroup": "false",
        "killasgroup": "false",
        "umask": "0077",
        "redirect_stderr": "true",
        "stdout_logfile": "NONE",
        "environment": 'PYTHONUNBUFFERED="1"',
    }
    if options != expected:
        fail("SUPERVISOR_PROGRAM_CONFIG_POLICY")
    return options


def validate_unit(raw):
    if hashlib.sha256(raw).hexdigest() != UNIT_SHA256:
        fail("UNIT_PIN_MISMATCH")
    lines = [line.strip() for line in raw.decode("utf-8", "strict").splitlines()
             if line.strip() and not line.lstrip().startswith("#") and
             not line.lstrip().startswith(";")]
    exec_line = ("ExecStart=/usr/bin/python3 -u /root/nox/scripts/"
                 "nox_lifeline_observer.py --policy /etc/nox/lifeline-observer.json "
                 "--state /root/nox/state/lifeline-observer/state.json --observer-only")
    if lines.count(exec_line) != 1:
        fail("UNIT_EXECSTART_MISMATCH")
    for line in lines:
        key, _, value = line.partition("=")
        if key in {"Wants", "Requires", "Requisite", "BindsTo", "PartOf", "Upholds",
                   "PropagatesReloadTo", "PropagatesStopTo", "JoinsNamespaceOf"} and (
                "supervisor.service" in value or "nox-" in value):
            fail("UNIT_WORKLOAD_DEPENDENCY_FORBIDDEN")
        if key == "After" and any(token == "supervisor.service" or token.startswith("nox-")
                                   for token in value.split()):
            fail("UNIT_WORKLOAD_ORDERING_FORBIDDEN")
    required = ("Restart=always", "RestartSec=15s", "MemoryMax=256M",
                "MemoryHigh=192M", "CPUQuota=10%", "TasksMax=32", "Nice=10",
                "StartLimitIntervalSec=0", "WantedBy=multi-user.target")
    if (any(lines.count(item) != 1 for item in required) or
            "WantedBy=multi-user.target" not in lines or
            "--observer-only" not in exec_line):
        fail("UNIT_OBSERVER_POLICY_INVALID")


def reject_external_unit_overrides():
    unit_name = UNIT.name
    for candidate in (Path("/run/systemd/system") / unit_name,
                      Path("/usr/lib/systemd/system") / unit_name,
                      Path("/lib/systemd/system") / unit_name):
        if candidate.exists() or candidate.is_symlink():
            fail("EXTERNAL_UNIT_FRAGMENT_PRESENT")
    for base in (Path("/etc/systemd/system"), Path("/run/systemd/system"),
                 Path("/usr/lib/systemd/system"), Path("/lib/systemd/system")):
        dropins = base / (unit_name + ".d")
        if dropins.exists() or dropins.is_symlink():
            try:
                meta = dropins.lstat()
                entries = list(dropins.iterdir()) if stat.S_ISDIR(meta.st_mode) else [dropins]
            except OSError:
                fail("EXTERNAL_UNIT_DROPIN_UNREADABLE")
            if entries:
                fail("EXTERNAL_UNIT_DROPIN_PRESENT")


def protect_parents(path: Path):
    for parent in (path.parent, *path.parent.parents):
        try:
            info = parent.lstat()
        except OSError:
            fail("PARENT_UNAVAILABLE")
        if (stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or
                info.st_uid != 0 or info.st_mode & 0o022):
            fail("PARENT_UNSAFE")
    if path.exists() and path.is_symlink():
        fail("TARGET_SYMLINK")


def atomic_write(path: Path, raw: bytes, mode: int, owner=(0, 0)):
    protect_parents(path)
    old, old_identity = bounded_read(path, max(MAX_BYTES.values(), len(raw)),
                                     allow_absent=True)
    expected = PREIMAGES[str(path)]
    if old != expected[0] or old_identity != expected[1]:
        fail("TARGET_CAS_MISMATCH")
    fd, temp = tempfile.mkstemp(prefix=".nox-lifeline-observer-", dir=path.parent)
    try:
        os.fchown(fd, owner[0], owner[1])
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        current, identity = bounded_read(path, max(MAX_BYTES.values(), len(raw)),
                                         allow_absent=True)
        if current != expected[0] or identity != expected[1]:
            fail("TARGET_CAS_RACE")
        mark_native_mutation_attempted()
        os.replace(temp, path)
        INSTALLED[str(path)] = raw
        dirfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    written, _ = bounded_read(path, max(MAX_BYTES.values(), len(raw)))
    if written != raw:
        fail("TARGET_READBACK")


def unit_state(unit):
    active = run(["systemctl", "is-active", unit], timeout=10)
    enabled = run(["systemctl", "is-enabled", unit], timeout=10)
    active_text = active.stdout.strip()
    enabled_text = enabled.stdout.strip()
    if active_text not in ("active", "inactive", "failed", "unknown"):
        fail("SYSTEMD_ACTIVE_STATE_UNKNOWN")
    if enabled_text not in ("enabled", "disabled", "static", "indirect", "not-found"):
        fail("SYSTEMD_ENABLE_STATE_UNKNOWN")
    if (active_text == "active" and active.returncode != 0) or (
            active_text in ("inactive", "failed", "unknown") and active.returncode == 0):
        fail("SYSTEMD_ACTIVE_RC_CONTRADICTION")
    if (enabled_text == "enabled" and enabled.returncode != 0) or (
            enabled_text in ("disabled", "static", "indirect", "not-found") and
            enabled.returncode == 0):
        fail("SYSTEMD_ENABLE_RC_CONTRADICTION")
    return {"active": active_text, "active_rc": active.returncode,
            "enabled": enabled_text, "enabled_rc": enabled.returncode}


def process_identity(pid):
    if type(pid) is not int or pid <= 0:
        fail("PROCESS_PID")
    base = Path("/proc") / str(pid)

    def read_limit(path, limit):
        try:
            with path.open("rb") as stream:
                return stream.read(limit + 1)
        except OSError:
            fail("PROCESS_IDENTITY_UNAVAILABLE")

    def ticks():
        raw = read_limit(base / "stat", 4096)
        if len(raw) > 4096:
            fail("PROCESS_STAT_LIMIT")
        try:
            pid_raw, rest = raw.split(b" ", 1)
            close = rest.rfind(b")")
            if int(pid_raw) != pid or close < 0:
                raise ValueError
            return int(rest[close + 1:].split()[19])
        except (ValueError, IndexError):
            fail("PROCESS_STAT_INVALID")

    before = ticks()
    try:
        exe_before = os.readlink(base / "exe")
    except OSError:
        fail("PROCESS_IDENTITY_UNAVAILABLE")
    cmd_before = read_limit(base / "cmdline", 16_384)
    env_before = read_limit(base / "environ", 262_144)
    env_after = read_limit(base / "environ", 262_144)
    cmd_after = read_limit(base / "cmdline", 16_384)
    try:
        exe_after = os.readlink(base / "exe")
    except OSError:
        fail("PROCESS_IDENTITY_REREAD_UNAVAILABLE")
    after = ticks()
    if (before != after or exe_before != exe_after or cmd_before != cmd_after or
            env_before != env_after or len(cmd_before) > 16_384 or
            len(env_before) > 262_144 or len(cmd_after) > 16_384 or
            len(env_after) > 262_144 or not cmd_before.endswith(b"\0")):
        fail("PROCESS_IDENTITY_CHANGED")
    argv = tuple(x.decode("utf-8", "strict") for x in cmd_before[:-1].split(b"\0"))
    if argv != EXPECTED_ARGV or exe_before != os.path.realpath("/usr/bin/python3"):
        fail("PROCESS_ARGV_MISMATCH")
    return {"pid": pid, "start_ticks": before, "exe": exe_before, "argv": argv,
            "environment_sha256": hashlib.sha256(env_before).hexdigest()}


EXPECTED_ARGV = ("/usr/bin/python3", "-u", "/root/nox/scripts/nox_lifeline_observer.py",
                 "--policy", "/etc/nox/lifeline-observer.json",
                 "--state", "/root/nox/state/lifeline-observer/state.json",
                 "--observer-only")


def fresh_receipt(started_at, *, require_supervisor_limits=False):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            raw, _ = bounded_read(STATE, 262_144)
            state = json.loads(raw)
            report = state.get("last_report")
            if (not isinstance(report, dict) or
                    report.get("schema") != "NOX_LIFELINE_V2" or
                    report.get("observer_only_enforced") is not True or
                    report.get("worker_starts_permitted") is not False):
                raise ValueError
            if require_supervisor_limits:
                limits = report.get("resource_limits")
                if (not isinstance(limits, dict) or
                        type(limits.get("address_space_bytes")) is not int or
                        not 0 < limits["address_space_bytes"] <= 512 * 1024**2 or
                        type(limits.get("open_files")) is not int or
                        not 1 <= limits["open_files"] <= 128 or
                        limits.get("core_bytes") != 0 or
                        limits.get("file_size_bytes") != 8 * 1024**2 or
                        type(limits.get("nice")) is not int or limits["nice"] < 10 or
                        limits.get("hard_cgroup_memory_limit") != "unsupported_by_supervisor" or
                        limits.get("cpu_quota") != "unsupported_by_supervisor" or
                        limits.get("cpu_scheduling") != "nice_only_no_hard_quota"):
                    raise ValueError
            memory = report.get("cgroup_memory")
            if not isinstance(memory, dict):
                raise ValueError
            current, maximum = memory.get("memory.current"), memory.get("memory.max")
            headroom, below = memory.get("raw_headroom_bytes"), memory.get("below_2GiB")
            if (type(current) is not int or type(maximum) is not int or
                    type(headroom) is not int or type(below) is not bool or
                    memory.get("memory_floor_bytes") != 2 * 1024**3 or
                    memory.get("severity") != ("CRITICAL" if below else "OK") or
                    headroom != maximum - current or below != (headroom < 2 * 1024**3) or
                    memory.get("status") != ("OK" if headroom >= 0 else "INCONSISTENT")):
                raise ValueError
            from datetime import datetime
            at = datetime.fromisoformat(report["at"].replace("Z", "+00:00")).timestamp()
            if at < started_at - 2 or at > time.time() + 5:
                raise ValueError
            return report
        except (OSError, ValueError, TypeError, KeyError, RuntimeError):
            time.sleep(1)
    fail("FRESH_OBSERVER_RECEIPT_TIMEOUT")


def _open_owner_directory(path: Path, owner_uid=0):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        fail("OWNER_FENCE_PARENT_UNSAFE")
    flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
             getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        fd = os.open("/", flags)
    except OSError:
        fail("OWNER_FENCE_PARENT_UNAVAILABLE")
    try:
        info = os.fstat(fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, owner_uid) or
                info.st_mode & 0o022):
            fail("OWNER_FENCE_PARENT_UNSAFE")
        for component in path.parts[1:]:
            if component in ("", ".", ".."):
                fail("OWNER_FENCE_PARENT_UNSAFE")
            try:
                child = os.open(component, flags, dir_fd=fd)
            except OSError:
                fail("OWNER_FENCE_PARENT_UNAVAILABLE")
            child_info = os.fstat(child)
            if (not stat.S_ISDIR(child_info.st_mode) or
                    child_info.st_uid not in (0, owner_uid) or
                    child_info.st_mode & 0o022):
                os.close(child)
                fail("OWNER_FENCE_PARENT_UNSAFE")
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _owner_fence_note(request, source_sha):
    if (not isinstance(request, str) or not re.fullmatch(r"[0-9]{1,24}", request) or
            not isinstance(source_sha, str) or not SOURCE_SHA.fullmatch(source_sha)):
        fail("OWNER_FENCE_CONTEXT")
    # Keep the marker wire format identical to the emergency-stop owner
    # helper, which validates exact request binding before accepting markers.
    return (f"NOX_OWNER_EMERGENCY_STOP_V1\nrequest_id={request}\n"
            f"source_sha={source_sha}\n"
            ).encode("ascii")


def _owner_fence_marker_matches(record):
    name, parent_fd = record["path"].name, record["parent_fd"]
    try:
        entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        return False
    if (not stat.S_ISREG(entry.st_mode) or entry.st_uid != record["owner_uid"] or
            stat.S_IMODE(entry.st_mode) != 0o600 or entry.st_nlink != 1 or
            (entry.st_dev, entry.st_ino) != (record["dev"], record["ino"])):
        return False
    flags = (os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
             getattr(os, "O_CLOEXEC", 0))
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
    except OSError:
        return False
    try:
        current = os.fstat(fd)
        if ((current.st_dev, current.st_ino) != (record["dev"], record["ino"]) or
                not stat.S_ISREG(current.st_mode) or current.st_uid != record["owner_uid"] or
                stat.S_IMODE(current.st_mode) != 0o600 or current.st_nlink != 1):
            return False
        raw = os.read(fd, len(record["content_written"]) + 1)
        return raw == record["content_written"]
    except OSError:
        return False
    finally:
        os.close(fd)


def _create_owner_fence_marker(path, role, parent_fd, note, owner_uid=0, *, track=True):
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW |
             getattr(os, "O_CLOEXEC", 0))
    try:
        fd = os.open(path.name, flags, 0o600, dir_fd=parent_fd)
    except OSError:
        OWNER_FENCE_STATUS.update({"state": "CREATE_CONFLICT", "retained": True,
                                   "untracked_role": role})
        fail("OWNER_FENCE_CREATE")
    try:
        meta = os.fstat(fd)
        parent = os.fstat(parent_fd)
    except OSError:
        os.close(fd)
        OWNER_FENCE_STATUS.update({"state": "CREATE_IDENTITY_UNVERIFIED",
                                   "retained": True, "untracked_role": role})
        fail("OWNER_FENCE_CREATE_IDENTITY_UNVERIFIED")
    record = {"role": role, "path": Path(path), "parent_fd": parent_fd,
              "parent_dev": parent.st_dev, "parent_ino": parent.st_ino,
              "dev": meta.st_dev, "ino": meta.st_ino, "owner_uid": owner_uid,
              "note": note, "content_written": b""}
    if track:
        OWNER_FENCES_CREATED.append(record)
    try:
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != owner_uid or
                meta.st_nlink != 1):
            fail("OWNER_FENCE_CREATE_UNSAFE")
        os.fchmod(fd, 0o600)
        if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
            fail("OWNER_FENCE_CREATE_MODE")
        offset = 0
        while offset < len(note):
            written = os.write(fd, note[offset:])
            if type(written) is not int or written <= 0:
                fail("OWNER_FENCE_CREATE_WRITE")
            record["content_written"] += note[offset:offset + written]
            offset += written
        os.fsync(fd)
        os.fsync(parent_fd)
        if not _owner_fence_marker_matches(record):
            fail("OWNER_FENCE_CREATE_READBACK")
        return record
    except OSError:
        fail("OWNER_FENCE_CREATE_WRITE")
    finally:
        os.close(fd)


def _owner_fence_receipt():
    return {"state": OWNER_FENCE_STATUS.get("state"),
            "created_roles": sorted({row["role"] for row in OWNER_FENCES_CREATED}),
            "preexisting_roles": sorted(set(OWNER_FENCES_PREEXISTING)),
            "untracked_role": OWNER_FENCE_STATUS.get("untracked_role"),
            "cleanup": OWNER_FENCE_STATUS.get("cleanup"),
            "retained": bool(OWNER_FENCES_CREATED or OWNER_FENCE_STATUS.get("retained") or
                             OWNER_FENCE_STATUS.get("untracked_role")),
            "note_sha256": OWNER_FENCE_STATUS.get("note_sha256")}


def _verify_owner_fence_parent(record):
    current_fd = _open_owner_directory(record["path"].parent, record["owner_uid"])
    try:
        current = os.fstat(current_fd)
        if (current.st_dev, current.st_ino) != (record["parent_dev"], record["parent_ino"]):
            return False
        return True
    finally:
        os.close(current_fd)


def _owner_lock_is_held():
    if (OWNER_LOCK_FD is None or OWNER_LOCK_PARENT_FD is None or
            OWNER_LOCK_IDENTITY is None):
        return False
    try:
        held = os.fstat(OWNER_LOCK_FD)
        path = os.stat(Path(OWNER_LOCK).name, dir_fd=OWNER_LOCK_PARENT_FD,
                       follow_symlinks=False)
        if (not stat.S_ISREG(held.st_mode) or not stat.S_ISREG(path.st_mode) or
                held.st_nlink != 1 or path.st_nlink != 1 or
                (held.st_dev, held.st_ino) != OWNER_LOCK_IDENTITY or
                (path.st_dev, path.st_ino) != OWNER_LOCK_IDENTITY or
                held.st_uid != path.st_uid):
            return False
        fcntl.flock(OWNER_LOCK_FD, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (OSError, TypeError, ValueError):
        return False


def cleanup_owner_fences(reason):
    """CAS-remove only this request's markers while the owner flock is held."""
    global OWNER_FENCE_STATUS
    if not OWNER_FENCES_CREATED:
        OWNER_FENCE_STATUS = dict(OWNER_FENCE_STATUS, cleanup="NO_OWNED_MARKERS",
                                  retained=bool(OWNER_FENCE_STATUS.get("retained")))
        return True
    if not _owner_lock_is_held():
        OWNER_FENCE_STATUS = dict(OWNER_FENCE_STATUS, state="RETAINED",
                                  cleanup="OWNER_LOCK_NOT_HELD", retained=True)
        return False
    records = list(OWNER_FENCES_CREATED)
    try:
        for record in records:
            if (not _verify_owner_fence_parent(record) or
                    not _owner_fence_marker_matches(record)):
                OWNER_FENCE_STATUS = dict(OWNER_FENCE_STATUS, state="RETAINED",
                                          cleanup="IDENTITY_CONTENT_CAS_HOLD", retained=True)
                return False
    except BaseException:
        OWNER_FENCE_STATUS = dict(OWNER_FENCE_STATUS, state="RETAINED",
                                  cleanup="PARENT_IDENTITY_HOLD", retained=True)
        return False

    removed = []
    try:
        for record in records:
            if (not _verify_owner_fence_parent(record) or
                    not _owner_fence_marker_matches(record)):
                fail("OWNER_FENCE_CLEANUP_CAS")
            os.unlink(record["path"].name, dir_fd=record["parent_fd"])
            removed.append(record)
            os.fsync(record["parent_fd"])
        for record in records:
            try:
                os.stat(record["path"].name, dir_fd=record["parent_fd"],
                        follow_symlinks=False)
            except FileNotFoundError:
                continue
            fail("OWNER_FENCE_CLEANUP_READBACK")
    except BaseException:
        restored = True
        for old in reversed(removed):
            try:
                try:
                    os.stat(old["path"].name, dir_fd=old["parent_fd"],
                            follow_symlinks=False)
                except FileNotFoundError:
                    new = _create_owner_fence_marker(
                        old["path"], old["role"], old["parent_fd"],
                        old["content_written"], old["owner_uid"], track=False)
                    index = next(i for i, item in enumerate(OWNER_FENCES_CREATED)
                                 if item["role"] == old["role"])
                    OWNER_FENCES_CREATED[index] = new
                else:
                    restored = False
            except BaseException:
                restored = False
        OWNER_FENCE_STATUS = dict(OWNER_FENCE_STATUS, state="RETAINED",
                                  cleanup="UNLINK_OR_RESTORE_HOLD",
                                  retained=True, release_restore_verified=restored)
        return False

    OWNER_FENCES_CREATED.clear()
    conflict = OWNER_FENCE_STATUS.get("untracked_role")
    OWNER_FENCE_STATUS = dict(OWNER_FENCE_STATUS,
                              state="RELEASED_WITH_UNTRACKED_CONFLICT" if conflict else "RELEASED",
                              cleanup=reason + "_IDENTITY_CONTENT_CAS_FSYNC_VERIFIED",
                              retained=bool(conflict))
    return True


def _close_owner_fence_directory_fds():
    while OWNER_FENCE_DIR_FDS:
        fd = OWNER_FENCE_DIR_FDS.pop()
        try:
            os.close(fd)
        except OSError:
            pass


def acquire_owner_lock(owner_uid=0):
    """Acquire the existing exclusive owner lease before creating any fences."""
    global OWNER_LOCK_FD, OWNER_LOCK_PARENT_FD, OWNER_LOCK_IDENTITY, OWNER_FENCE_STATUS
    if OWNER_LOCK_FD is not None:
        fail("OWNER_LOCK_ALREADY_HELD")
    lock_dir_fd = _open_owner_directory(Path(OWNER_LOCK).parent, owner_uid)
    fd = None
    try:
        flags = (os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                 getattr(os, "O_CLOEXEC", 0))
        try:
            fd = os.open(Path(OWNER_LOCK).name, flags, dir_fd=lock_dir_fd)
        except OSError:
            fail("OWNER_LOCK_UNAVAILABLE")
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1 or
                meta.st_uid != owner_uid or meta.st_mode & 0o022):
            fail("OWNER_LOCK_UNSAFE")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("OWNER_LOCK_BUSY")
        lock_meta = os.fstat(fd)
        OWNER_LOCK_FD, fd = fd, None
        OWNER_LOCK_PARENT_FD, lock_dir_fd = lock_dir_fd, None
        OWNER_LOCK_IDENTITY = (lock_meta.st_dev, lock_meta.st_ino)
    finally:
        if fd is not None:
            os.close(fd)
        if lock_dir_fd is not None:
            os.close(lock_dir_fd)

    note = _owner_fence_note(REQUEST_ID, SOURCE_SHA_VALUE)
    OWNER_FENCE_STATUS = {"state": "LOCKED_PREFLIGHT", "cleanup": "NOT_ATTEMPTED",
                          "retained": False,
                          "note_sha256": hashlib.sha256(note).hexdigest()}
    specs = (("stop", Path(OWNER_STOP)),
             ("maintenance", Path(OWNER_MAINTENANCE)))
    absent = []
    for role, path in specs:
        parent_fd = _open_owner_directory(path.parent, owner_uid)
        OWNER_FENCE_DIR_FDS.append(parent_fd)
        parent = os.fstat(parent_fd)
        try:
            os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            absent.append((role, path, parent_fd, parent.st_dev, parent.st_ino))
        except OSError:
            fail("OWNER_FENCE_PREFLIGHT_UNAVAILABLE")
        else:
            OWNER_FENCES_PREEXISTING.append(role)
    if OWNER_FENCES_PREEXISTING:
        OWNER_FENCE_STATUS = dict(OWNER_FENCE_STATUS, state="BLOCKED_PREEXISTING",
                                  retained=True)
        fail("OWNER_FENCE_PREEXISTING")
    if len(absent) != 2:
        fail("OWNER_FENCE_PREFLIGHT_INCOMPLETE")

    try:
        for role, path, parent_fd, _, _ in absent:
            _create_owner_fence_marker(path, role, parent_fd, note, owner_uid)
    except BaseException:
        OWNER_FENCE_STATUS = dict(OWNER_FENCE_STATUS, state="CREATE_FAILED",
                                  retained=True,
                                  cleanup="CREATE_FAILURE_REQUIRES_OWNER_REVIEW")
        raise
    OWNER_FENCE_STATUS = dict(OWNER_FENCE_STATUS, state="CREATED",
                              created_at_lock=True, retained=True)


def save_backup(request, path, raw):
    if raw is None:
        return None
    backup_dir = ROOT / "backup/owner_maintenance" / request
    for directory in (ROOT / "backup", ROOT / "backup/owner_maintenance", backup_dir):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        try:
            info = directory.lstat()
        except OSError:
            fail("BACKUP_DIRECTORY_UNAVAILABLE")
        if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or
                info.st_uid != 0 or info.st_mode & 0o022):
            fail("BACKUP_DIRECTORY_UNSAFE")
    protect_parents(backup_dir / "backup-probe")
    os.chmod(backup_dir, 0o700)
    digest = hashlib.sha256(raw).hexdigest()
    backup = backup_dir / (path.name + ".preimage-" + digest)
    try:
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        existing, _ = bounded_read(backup, max(MAX_BYTES.values(), len(raw)))
        if existing != raw:
            fail("BACKUP_CONFLICT")
        return str(backup)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    checked, _ = bounded_read(backup, max(MAX_BYTES.values(), len(raw)))
    if checked != raw:
        fail("BACKUP_READBACK")
    return str(backup)


def ensure_private_directory(path: Path):
    global STATE_DIR_PREIMAGE
    created = False
    try:
        path.mkdir(mode=0o700)
        created = True
    except FileExistsError:
        created = False
    try:
        info = path.lstat()
    except OSError:
        if created:
            try:
                check = path.lstat()
                if stat.S_ISDIR(check.st_mode) and not stat.S_ISLNK(check.st_mode):
                    path.rmdir()
            except OSError:
                STATE_DIR_PREIMAGE = {"created": True, "capture_failed": True}
        fail("STATE_DIRECTORY_UNAVAILABLE")
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or
            info.st_uid != 0 or info.st_mode & 0o022):
        fail("STATE_DIRECTORY_UNSAFE")
    if created:
        info = path.lstat()
    STATE_DIR_PREIMAGE = {"created": created, "mode": stat.S_IMODE(info.st_mode),
                          "uid": info.st_uid, "gid": info.st_gid,
                          "device": info.st_dev, "inode": info.st_ino}


def snapshot_state_artifacts(request):
    for name, path in STATE_ARTIFACTS.items():
        raw, identity = bounded_read(path, 262_144, allow_absent=True)
        if raw is not None:
            backup = save_backup(request, path, raw)
        else:
            backup = None
        STATE_ARTIFACT_PREIMAGES[name] = (raw, identity)
        STATE_ARTIFACT_PREIMAGES[name + ".receipt"] = {
            "sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None,
            "absent": raw is None,
            "mode": stat.S_IMODE(identity[2]) if identity else None,
            "uid": identity[4] if identity else None,
            "gid": identity[5] if identity else None,
            "device": identity[0] if identity else None,
            "inode": identity[1] if identity else None,
            "backup": backup,
        }


def restore_state_artifacts():
    # The dedicated service has been stopped before this runs. Restore only
    # root-owned regular files in our private state directory.
    for name, path in STATE_ARTIFACTS.items():
        if name not in STATE_ARTIFACT_PREIMAGES:
            # Snapshot reads do not mutate artifacts; if a read failed midway,
            # uncaptured paths remain outside this transaction.
            continue
        original, original_identity = STATE_ARTIFACT_PREIMAGES[name]
        current, current_identity = bounded_read(path, 262_144, allow_absent=True)
        if current == original and current_identity == original_identity:
            continue
        if current is not None and (current_identity is None or current_identity[4] != 0):
            fail("STATE_ARTIFACT_ROLLBACK_UNSAFE")
        if original is None:
            if current is not None:
                path.unlink()
        else:
            parent = path.parent
            fd, temp = tempfile.mkstemp(prefix=".nox-lifeline-restore-", dir=parent)
            try:
                os.fchown(fd, original_identity[4], original_identity[5])
                os.fchmod(fd, stat.S_IMODE(original_identity[2]))
                with os.fdopen(fd, "wb") as stream:
                    stream.write(original)
                    stream.flush()
                    os.fsync(stream.fileno())
                check, check_identity = bounded_read(path, 262_144, allow_absent=True)
                if check != current or check_identity != current_identity:
                    fail("STATE_ARTIFACT_ROLLBACK_CAS")
                os.replace(temp, path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
        dirfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    if STATE_DIR_PREIMAGE is not None:
        info = STATE_DIR.lstat()
        expected = STATE_DIR_PREIMAGE
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != expected["uid"] or
                info.st_gid != expected["gid"] or info.st_dev != expected["device"] or
                info.st_ino != expected["inode"]):
            fail("STATE_DIRECTORY_ROLLBACK_UNSAFE")
        if expected["created"]:
            try:
                STATE_DIR.rmdir()
            except OSError:
                fail("STATE_DIRECTORY_NOT_EMPTY_ON_ROLLBACK")
        elif stat.S_IMODE(info.st_mode) != expected["mode"]:
            os.chmod(STATE_DIR, expected["mode"])


def restore_exact_preimages():
    # Roll back only files that still equal this transaction's installed bytes.
    for name, path in FILES.items():
        installed = INSTALLED.get(str(path))
        if installed is None:
            continue
        current, identity = bounded_read(path, max(MAX_BYTES.values(), len(installed)),
                                         allow_absent=True)
        if current != installed:
            fail("ROLLBACK_FILE_CHANGED")
        original, _ = PREIMAGES[str(path)]
        original_identity = PREIMAGES[str(path)][1]
        if original is None:
            path.unlink()
            dirfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
        else:
            # Compare-and-swap from our installed bytes back to the exact preimage.
            PREIMAGES[str(path)] = (installed, identity)
            atomic_write(path, original, stat.S_IMODE(original_identity[2]),
                         owner=(original_identity[4], original_identity[5]))
    reload_result = run(["systemctl", "daemon-reload"], timeout=20)
    if reload_result.returncode:
        fail("ROLLBACK_DAEMON_RELOAD")


def supervisor_inventory_sha256(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def restore_supervisor_file(path, installed, preimage):
    current, identity = bounded_read(path, max(MAX_BYTES.values(), len(installed)),
                                     allow_absent=True)
    if current != installed:
        fail("SUPERVISOR_ROLLBACK_FILE_CHANGED")
    original, original_identity = preimage
    if original is None:
        path.unlink()
        dirfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
        return
    PREIMAGES[str(path)] = (installed, identity)
    atomic_write(path, original, stat.S_IMODE(original_identity[2]),
                 owner=(original_identity[4], original_identity[5]))


def rollback_supervisor_fallback():
    """Undo only this transaction's observer group, config, and exact file preimages."""
    global SUPERVISORCTL_PIN, SUPERVISOR_ALLOWED_PROGRAM_CONFIG
    global SUPERVISOR_PROGRAM_INSTALLED, SUPERVISOR_PROGRAM_ADDED
    global SUPERVISOR_PROGRAM_RELOADED, SUPERVISOR_PROGRAM_STARTED
    global SUPERVISOR_PROGRAM_ROLLBACK_PRIOR_GROUPS_UNCHANGED
    if SUPERVISORCTL_PIN is None:
        return "NOT_NEEDED"
    if (SUPERVISOR_PROGRAM_INSTALLED is not None or
            str(SUPERVISOR_PROGRAM) in INSTALLED) and SUPERVISORCTL_PIN == SUPERVISOR_BASELINE_PIN:
        endpoint = _socket_config_snapshot()
        config_row = next((row for row in endpoint["config_inputs"]
                           if row["path"] == str(SUPERVISOR_PROGRAM)), None)
        if config_row is None or SUPERVISOR_ALLOWED_PROGRAM_CONFIG is None or (
                config_row["sha256"] != SUPERVISOR_ALLOWED_PROGRAM_CONFIG["sha256"]):
            fail("SUPERVISOR_ROLLBACK_CONFIG_PREIMAGE_UNKNOWN")
        refresh_supervisor_pin_for_program(config_row)
    before = supervisor_inventory()
    prior_inventory = SUPERVISOR_PROGRAM_BEFORE_INVENTORY or before
    SUPERVISOR_PROGRAM_ROLLBACK_PRIOR_GROUPS_UNCHANGED = supervisor_old_rows_match(
        prior_inventory, before)
    target = assert_observer_group(before, None) if not any(
        row["group"] == SUPERVISOR_PROGRAM_NAME for row in before) else next(
            row for row in before if row["group"] == SUPERVISOR_PROGRAM_NAME)
    if target is not None:
        state, pid = target["state"], target["pid"]
        if state in {"RUNNING", "STARTING", "STOPPING"} and pid > 1:
            identity = process_identity(pid)
            if (identity.get("pid") != pid or type(identity.get("start_ticks")) is not int or
                    identity["start_ticks"] <= 0):
                fail("SUPERVISOR_ROLLBACK_TARGET_IDENTITY_MISMATCH")
            try:
                stopped = supervisor_rpc("supervisor.stopProcess", SUPERVISOR_PROGRAM_NAME, True)
            except Hold:
                # STOPPING means a scoped stop may already be in flight. Continue only
                # if bounded readback proves this exact PID reaches a non-running state.
                if state != "STOPPING":
                    raise
            else:
                if stopped is not True:
                    fail("SUPERVISOR_ROLLBACK_STOP_FAILED")
            wait_for_observer_quiescent(supervisor_inventory, prior_inventory, pid)
        elif state == "STOPPED" and pid == 0:
            pass
        elif state in {"BACKOFF", "EXITED", "FATAL"} and pid == 0:
            # Supervisor confirms there is no live process to signal. Remove
            # only our failed group and continue the exact config/file rollback.
            pass
        else:
            fail("SUPERVISOR_ROLLBACK_TARGET_STATE_AMBIGUOUS")
        if target is not None:
            removed = supervisor_rpc("supervisor.removeProcessGroup", SUPERVISOR_PROGRAM_NAME)
            if removed is not True:
                fail("SUPERVISOR_ROLLBACK_REMOVE_GROUP_FAILED")
            SUPERVISOR_PROGRAM_ADDED = False

    installed_config = (SUPERVISOR_PROGRAM_INSTALLED or
                        INSTALLED.get(str(SUPERVISOR_PROGRAM)))
    if installed_config is not None:
        restore_supervisor_file(SUPERVISOR_PROGRAM, installed_config,
                                SUPERVISOR_PROGRAM_PREIMAGE)
        SUPERVISOR_PROGRAM_INSTALLED = None
        current_pin = _supervisor_client_snapshot()
        if current_pin != SUPERVISOR_BASELINE_PIN:
            fail("SUPERVISOR_ROLLBACK_ENDPOINT_NOT_PREIMAGE")
        SUPERVISORCTL_PIN = current_pin
        SUPERVISOR_ALLOWED_PROGRAM_CONFIG = None
        if SUPERVISOR_PROGRAM_RELOADED:
            delta = supervisor_rpc("supervisor.reloadConfig")
            added, changed, removed = normalize_reload_config_result(delta)
            if (added or changed or removed not in ([], [SUPERVISOR_PROGRAM_NAME])):
                fail("SUPERVISOR_ROLLBACK_RELOAD_SCOPE_CHANGED")

    after = supervisor_inventory()
    SUPERVISOR_PROGRAM_ROLLBACK_PRIOR_GROUPS_UNCHANGED = (
        SUPERVISOR_PROGRAM_ROLLBACK_PRIOR_GROUPS_UNCHANGED and
        supervisor_old_rows_match(prior_inventory, after))
    assert_observer_group(after, None)
    SUPERVISOR_PROGRAM_STARTED = False
    SUPERVISOR_PROGRAM_RELOADED = False
    for name, path in SUPERVISOR_INSTALL_FILES.items():
        installed = INSTALLED.get(str(path))
        if installed is None:
            continue
        restore_supervisor_file(path, installed, PREIMAGES[str(path)])
    return "OBSERVER_GROUP_STOPPED_REMOVED;EXACT_CONFIG_AND_FILE_PREIMAGES_RESTORED"


def supervisor_fallback_main():
    """Install the observer as one named Supervisor process without touching other groups."""
    global SUPERVISOR_BACKEND_ACTIVE, SUPERVISORCTL_PIN, SUPERVISOR_BASELINE_PIN
    global SUPERVISOR_ALLOWED_PROGRAM_CONFIG, SUPERVISOR_PROGRAM_PREIMAGE
    global SUPERVISOR_PROGRAM_INSTALLED, SUPERVISOR_PROGRAM_BEFORE_INVENTORY
    global SUPERVISOR_PROGRAM_START_IDENTITY, MEMORY_PREFLIGHT, MEMORY_PRE_ENABLE
    global SUPERVISOR_MEMORY_POST_START, LEGACY_GUARD_PREIMAGE
    global LEGACY_GUARD_PRE_ENABLE, LEGACY_GUARD_POSTCHECK
    global CGROUP_TARGET_EVIDENCE, CGROUP_TARGET_PRE_ENABLE, CGROUP_TARGET_POST_ENABLE
    global SUPERVISORCTL_PRE_ENABLE, SUPERVISORCTL_POST_ENABLE
    global OBSERVER_RUNTIME_SOURCE_SHA256
    global SUPERVISOR_SERVER_VERSION

    SUPERVISOR_BACKEND_ACTIVE = True
    acquire_owner_lock()
    SUPERVISORCTL_PIN = resolve_supervisorctl()
    SUPERVISOR_BASELINE_PIN = SUPERVISORCTL_PIN
    methods = supervisor_rpc("system.listMethods")
    required_methods = {name for name in SUPERVISOR_RPC_CALLS
                        if name != "system.listMethods"}
    if (not isinstance(methods, list) or len(methods) > 256 or
            any(not isinstance(name, str) for name in methods) or
            not required_methods.issubset(set(methods))):
        fail("SUPERVISOR_REQUIRED_RPC_METHODS_UNAVAILABLE")
    SUPERVISOR_SERVER_VERSION = validate_supervisor_none_log_version(
        supervisor_rpc("supervisor.getVersion"))

    bundle = {name: checked_bundle(name) for name in
              ("nox_lifeline_observer.py", "lifeline-observer.json")}
    bundle[SUPERVISOR_BOOTSTRAP_BUNDLE_KEY] = checked_supervisor_bundle(
        SUPERVISOR_BOOTSTRAP_BUNDLE_KEY)
    bundle[SUPERVISOR_PROGRAM_BUNDLE_KEY] = checked_supervisor_bundle(
        SUPERVISOR_PROGRAM_BUNDLE_KEY)
    core_source = bundle["nox_lifeline_observer.py"]
    OBSERVER_RUNTIME_SOURCE_SHA256 = hashlib.sha256(core_source).hexdigest()
    token = b"__NOX_SUPERVISOR_SOCKET_PATH__"
    identity_token = b"__NOX_SUPERVISOR_IDENTITY_PIN__"
    socket_token = b"__NOX_SUPERVISOR_SOCKET_PIN__"
    if any(core_source.count(item) != 1 for item in (token, identity_token, socket_token)):
        fail("SUPERVISOR_UDS_SOURCE_TOKEN_MISMATCH")
    bundle["nox_lifeline_observer.py"] = core_source.replace(
        token, json.dumps(SUPERVISORCTL_PIN["endpoint"]["path"]).encode("ascii"), 1)
    for marker, value in ((identity_token, SUPERVISORCTL_PIN["daemon"]),
                          (socket_token, SUPERVISORCTL_PIN["endpoint"]["socket"])):
        bundle["nox_lifeline_observer.py"] = bundle["nox_lifeline_observer.py"].replace(
            marker, json.dumps(value).encode("ascii"), 1)
    policy = json.loads(bundle["lifeline-observer.json"], object_pairs_hook=_unique_pairs,
                        parse_constant=_reject_constant)
    if (policy.get("enabled") is not False or not isinstance(policy.get("services"), list) or
            any(item.get("restart") is not False for item in policy["services"])):
        fail("BUNDLED_POLICY_NOT_OBSERVER_ONLY")
    validate_supervisor_program_config(bundle[SUPERVISOR_PROGRAM_BUNDLE_KEY])
    compile(bundle["nox_lifeline_observer.py"], str(SCRIPT), "exec")
    compile(bundle[SUPERVISOR_BOOTSTRAP_BUNDLE_KEY], str(BOOTSTRAP), "exec")

    inventory = supervisor_inventory()
    assert_observer_group(inventory, None)
    SUPERVISOR_PROGRAM_BEFORE_INVENTORY = inventory
    LEGACY_GUARD_PREIMAGE = legacy_guard_snapshot()
    CGROUP_TARGET_EVIDENCE = resolve_cgroup_target(LEGACY_GUARD_PREIMAGE)
    config_preflight = supervisor_program_config_preflight(
        SUPERVISORCTL_PIN["endpoint"], bundle[SUPERVISOR_PROGRAM_BUNDLE_KEY])
    MEMORY_PREFLIGHT = cgroup_memory_snapshot(CGROUP_TARGET_EVIDENCE["target"])
    require_memory_headroom(MEMORY_PREFLIGHT,
                            MEMORY_FLOOR_BYTES + MEMORY_RESERVE_BYTES,
                            "MEMORY_PREFLIGHT_BELOW_2_5GIB")

    desired = dict(bundle)
    preimage_receipts = {}
    for name, path in SUPERVISOR_INSTALL_FILES.items():
        protect_parents(path)
        max_bytes = MAX_BYTES[name] if name in MAX_BYTES else SUPERVISOR_BUNDLE_MAX_BYTES[name]
        old, identity = bounded_read(path, max_bytes, allow_absent=True)
        target = desired[name]
        if old is not None and old != target:
            fail("UNEXPECTED_PREIMAGE_" + name.upper().replace(".", "_"))
        PREIMAGES[str(path)] = (old, identity)
        preimage_receipts[name] = {
            "sha256": hashlib.sha256(old).hexdigest() if old is not None else None,
            "absent": old is None,
            "backup_created": bool(save_backup(REQUEST_ID, path, old)) if old is not None else False,
        }
    protect_parents(SUPERVISOR_PROGRAM)
    SUPERVISOR_PROGRAM_PREIMAGE = bounded_read(
        SUPERVISOR_PROGRAM, SUPERVISOR_BUNDLE_MAX_BYTES[SUPERVISOR_PROGRAM_BUNDLE_KEY],
        allow_absent=True)
    if SUPERVISOR_PROGRAM_PREIMAGE != (None, None):
        fail("SUPERVISOR_PROGRAM_CONFIG_PREIMAGE_CHANGED")
    save_backup(REQUEST_ID, SUPERVISOR_PROGRAM, None)
    preimage_receipts[SUPERVISOR_PROGRAM_BUNDLE_KEY] = {
        "sha256": None, "absent": True, "backup_created": False,
    }

    protect_parents(STATE_DIR / "state.json")
    ensure_private_directory(STATE_DIR)
    snapshot_state_artifacts(REQUEST_ID)
    started_at = time.time()
    for name, path in SUPERVISOR_INSTALL_FILES.items():
        if PREIMAGES[str(path)][0] is None:
            atomic_write(path, desired[name], 0o600 if path == POLICY else 0o644)
    program_raw = bundle[SUPERVISOR_PROGRAM_BUNDLE_KEY]
    SUPERVISOR_ALLOWED_PROGRAM_CONFIG = {
        "path": str(SUPERVISOR_PROGRAM),
        "sha256": hashlib.sha256(program_raw).hexdigest(),
    }
    PREIMAGES[str(SUPERVISOR_PROGRAM)] = SUPERVISOR_PROGRAM_PREIMAGE
    atomic_write(SUPERVISOR_PROGRAM, program_raw, 0o644)
    SUPERVISOR_PROGRAM_INSTALLED = program_raw

    installed_config, _ = bounded_read(
        SUPERVISOR_PROGRAM, SUPERVISOR_BUNDLE_MAX_BYTES[SUPERVISOR_PROGRAM_BUNDLE_KEY])
    if installed_config != program_raw:
        fail("SUPERVISOR_PROGRAM_CONFIG_READBACK")
    endpoint = _socket_config_snapshot()
    config_row = next((row for row in endpoint["config_inputs"]
                       if row["path"] == str(SUPERVISOR_PROGRAM)), None)
    if (config_row is None or config_row["sha256"] != SUPERVISOR_ALLOWED_PROGRAM_CONFIG["sha256"]):
        fail("SUPERVISOR_PROGRAM_CONFIG_NOT_INCLUDED")
    parser = read_supervisor_config_inputs(endpoint)
    section = "program:" + SUPERVISOR_PROGRAM_NAME
    if parser.sections().count(section) != 1:
        fail("SUPERVISOR_PROGRAM_CONFIG_NOT_UNIQUE")
    refresh_supervisor_pin_for_program(config_row)

    LEGACY_GUARD_PRE_ENABLE = recheck_legacy_guard(LEGACY_GUARD_PREIMAGE)
    CGROUP_TARGET_PRE_ENABLE = resolve_cgroup_target(LEGACY_GUARD_PRE_ENABLE)
    if CGROUP_TARGET_PRE_ENABLE != CGROUP_TARGET_EVIDENCE:
        fail("CGROUP_TARGET_CHANGED_BEFORE_ENABLE")
    SUPERVISORCTL_PRE_ENABLE = verify_supervisorctl_pin()
    MEMORY_PRE_ENABLE = cgroup_memory_snapshot(CGROUP_TARGET_EVIDENCE["target"])
    require_memory_headroom(MEMORY_PRE_ENABLE,
                            MEMORY_FLOOR_BYTES + MEMORY_RESERVE_BYTES,
                            "MEMORY_PRE_START_BELOW_2_5GIB")

    def before_start():
        global LEGACY_GUARD_PRE_ENABLE, CGROUP_TARGET_PRE_ENABLE
        global MEMORY_PRE_ENABLE, SUPERVISORCTL_PRE_ENABLE
        LEGACY_GUARD_PRE_ENABLE = recheck_legacy_guard(LEGACY_GUARD_PREIMAGE)
        CGROUP_TARGET_PRE_ENABLE = resolve_cgroup_target(LEGACY_GUARD_PRE_ENABLE)
        if CGROUP_TARGET_PRE_ENABLE != CGROUP_TARGET_EVIDENCE:
            fail("CGROUP_TARGET_CHANGED_BEFORE_START")
        SUPERVISORCTL_PRE_ENABLE = verify_supervisorctl_pin()
        MEMORY_PRE_ENABLE = cgroup_memory_snapshot(CGROUP_TARGET_EVIDENCE["target"])
        require_memory_headroom(MEMORY_PRE_ENABLE,
                                MEMORY_FLOOR_BYTES + MEMORY_RESERVE_BYTES,
                                "MEMORY_PRE_START_BELOW_2_5GIB")

    activation = run_supervisor_group_activation(
        supervisor_inventory, supervisor_rpc, inventory, pre_start_fn=before_start)
    target = activation["observer_process"]
    SUPERVISOR_PROGRAM_START_IDENTITY = process_identity(target["pid"])
    if SUPERVISOR_PROGRAM_START_IDENTITY["start_ticks"] <= 0:
        fail("SUPERVISOR_OBSERVER_PROCESS_IDENTITY")
    report = fresh_receipt(started_at, require_supervisor_limits=True)
    final_inventory = supervisor_inventory()
    assert_supervisor_old_rows_unchanged(inventory, final_inventory)
    final_target = assert_observer_group(final_inventory, "RUNNING")
    if final_target["pid"] != SUPERVISOR_PROGRAM_START_IDENTITY["pid"]:
        fail("SUPERVISOR_OBSERVER_PID_CHANGED")
    LEGACY_GUARD_POSTCHECK = recheck_legacy_guard(LEGACY_GUARD_PREIMAGE)
    CGROUP_TARGET_POST_ENABLE = resolve_cgroup_target(LEGACY_GUARD_POSTCHECK)
    if CGROUP_TARGET_POST_ENABLE != CGROUP_TARGET_EVIDENCE:
        fail("CGROUP_TARGET_CHANGED_AFTER_START")
    SUPERVISORCTL_POST_ENABLE = verify_supervisorctl_pin()
    SUPERVISOR_MEMORY_POST_START = cgroup_memory_snapshot(CGROUP_TARGET_EVIDENCE["target"])
    require_memory_headroom(SUPERVISOR_MEMORY_POST_START, MEMORY_FLOOR_BYTES,
                            "MEMORY_POST_START_BELOW_2GIB")
    emit({
        "state": "OBSERVER_ACTIVE",
        "reason": None,
        "backend": "supervisor_program",
        "supervisor_scope": "ONE_NAMED_OBSERVER_PROGRAM_ONLY",
        "program_name": SUPERVISOR_PROGRAM_NAME,
        "supervisor_version": SUPERVISOR_SERVER_VERSION,
        "reload_delta": activation["reload_delta"],
        "existing_groups_unchanged": activation["existing_process_inventory_unchanged"],
        "process_inventory_before_count": len(inventory),
        "process_inventory_before_sha256": supervisor_inventory_sha256(inventory),
        "process_inventory_after_count": len(final_inventory),
        "process_inventory_after_sha256": supervisor_inventory_sha256(final_inventory),
        "observer_pid": final_target["pid"],
        "observer_start_ticks": SUPERVISOR_PROGRAM_START_IDENTITY["start_ticks"],
        "observer_exe_path_sha256": hashlib.sha256(
            os.fsencode(SUPERVISOR_PROGRAM_START_IDENTITY["exe"])).hexdigest(),
        "observer_argv_sha256": SUPERVISOR_PROGRAM_START_IDENTITY["argv_sha256"],
        "observer_runtime_source_sha256": OBSERVER_RUNTIME_SOURCE_SHA256,
        "supervisor_program_config_sha256": SUPERVISOR_BUNDLE_SHA256[
            SUPERVISOR_PROGRAM_BUNDLE_KEY],
        "supervisor_bootstrap_sha256": SUPERVISOR_BUNDLE_SHA256[
            SUPERVISOR_BOOTSTRAP_BUNDLE_KEY],
        "memory_preflight": MEMORY_PREFLIGHT,
        "memory_pre_start": MEMORY_PRE_ENABLE,
        "memory_post_start": SUPERVISOR_MEMORY_POST_START,
        "memory_preflight_minimum_bytes": MEMORY_FLOOR_BYTES + MEMORY_RESERVE_BYTES,
        "memory_post_start_minimum_bytes": MEMORY_FLOOR_BYTES,
        "resource_controls": SUPERVISOR_RESOURCE_RECEIPT,
        "runtime_resource_limits": report.get("resource_limits"),
        "systemd_backend_available": False,
        "global_supervisor_restarted": False,
        "other_supervisor_groups_changed": False,
        "supervisor_configured_autostart": True,
        "host_boot_persistence": "UNKNOWN_SUPERVISOR_DAEMON_BOOT_OWNER_NOT_PROVEN_BY_REPOSITORY",
        "config_preflight": config_preflight,
        "preimage_artifacts": preimage_receipts,
        "installed_asset_names": sorted(SUPERVISOR_INSTALL_FILES) + [
            SUPERVISOR_PROGRAM_BUNDLE_KEY],
    })
    return 0


def main():
    global UNIT_ENABLED_BEFORE, UNIT_ACTIVE_BEFORE, REQUEST_ID, SOURCE_SHA_VALUE
    global MEMORY_PREFLIGHT, MEMORY_PRE_ENABLE, MEMORY_POST_ENABLE
    global LEGACY_GUARD_PREIMAGE, LEGACY_GUARD_PRE_ENABLE, LEGACY_GUARD_POSTCHECK
    global CGROUP_TARGET_EVIDENCE, CGROUP_TARGET_PRE_ENABLE, CGROUP_TARGET_POST_ENABLE
    global SUPERVISORCTL_PIN, SUPERVISORCTL_PRE_ENABLE, SUPERVISORCTL_POST_ENABLE
    global SYSTEMCTL_PIN
    global OBSERVER_RUNTIME_SOURCE_SHA256
    source_sha = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    SOURCE_SHA_VALUE = source_sha if SOURCE_SHA.fullmatch(source_sha) else None
    request = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    if not SOURCE_SHA.fullmatch(source_sha) or not request.isdigit():
        fail("OWNER_CONTEXT")
    REQUEST_ID = request
    if os.geteuid() != 0:
        fail("ROOT_REQUIRED")
    if not Path("/run/systemd/system").is_dir():
        return supervisor_fallback_main()
    SYSTEMCTL_PIN = _supervisorctl_snapshot(SYSTEMCTL_PATH, max_size=64 * 1024**2)
    acquire_owner_lock()
    unit_before = unit_state(SERVICE)
    if (unit_before["active"] not in ("active", "inactive", "unknown") or
            unit_before["enabled"] not in ("enabled", "disabled", "not-found")):
        fail("OBSERVER_PREIMAGE_UNIT_STATE_UNSUPPORTED")
    UNIT_ENABLED_BEFORE, UNIT_ACTIVE_BEFORE = unit_before["enabled"], unit_before["active"]
    if UNIT_ACTIVE_BEFORE == "active":
        fail("OBSERVER_ALREADY_ACTIVE")

    bundle = {name: checked_bundle(name) for name in MAX_BYTES}
    SUPERVISORCTL_PIN = resolve_supervisorctl()
    core_source = bundle["nox_lifeline_observer.py"]
    OBSERVER_RUNTIME_SOURCE_SHA256 = hashlib.sha256(core_source).hexdigest()
    token = b"__NOX_SUPERVISOR_SOCKET_PATH__"
    identity_token = b"__NOX_SUPERVISOR_IDENTITY_PIN__"
    socket_token = b"__NOX_SUPERVISOR_SOCKET_PIN__"
    if any(core_source.count(item) != 1 for item in (token, identity_token, socket_token)):
        fail("SUPERVISOR_UDS_SOURCE_TOKEN_MISMATCH")
    bundle["nox_lifeline_observer.py"] = core_source.replace(
        token, json.dumps(SUPERVISORCTL_PIN["endpoint"]["path"]).encode("ascii"), 1)
    for marker, value in ((identity_token, SUPERVISORCTL_PIN["daemon"]),
                          (socket_token, SUPERVISORCTL_PIN["endpoint"]["socket"])):
        bundle["nox_lifeline_observer.py"] = bundle["nox_lifeline_observer.py"].replace(
            marker, json.dumps(value).encode("ascii"), 1)
    policy = json.loads(bundle["lifeline-observer.json"])
    if (policy.get("enabled") is not False or not isinstance(policy.get("services"), list) or
            any(item.get("restart") is not False for item in policy["services"])):
        fail("BUNDLED_POLICY_NOT_OBSERVER_ONLY")
    validate_unit(bundle["nox-lifeline-observer.service"])
    reject_external_unit_overrides()
    compile(bundle["nox_lifeline_observer.py"], str(SCRIPT), "exec")

    # Require headroom for the 2 GiB operating floor plus a 512 MiB startup
    # reserve before any backups, file writes, daemon reload, or service start.
    LEGACY_GUARD_PREIMAGE = legacy_guard_snapshot()
    CGROUP_TARGET_EVIDENCE = resolve_cgroup_target(LEGACY_GUARD_PREIMAGE)
    MEMORY_PREFLIGHT = cgroup_memory_snapshot(CGROUP_TARGET_EVIDENCE["target"])
    require_memory_headroom(MEMORY_PREFLIGHT,
                            MEMORY_FLOOR_BYTES + MEMORY_RESERVE_BYTES,
                            "MEMORY_PREFLIGHT_BELOW_FLOOR_PLUS_RESERVE")

    preimage_receipts = {}
    for name, path in FILES.items():
        protect_parents(path)
        old, identity = bounded_read(path, MAX_BYTES[name], allow_absent=True)
        desired = bundle[name]
        if old is not None and old != desired:
            fail("UNEXPECTED_PREIMAGE_" + name.upper().replace(".", "_"))
        PREIMAGES[str(path)] = (old, identity)
        backup = save_backup(request, path, old)
        preimage_receipts[str(path)] = {
            "sha256": hashlib.sha256(old).hexdigest() if old is not None else None,
            "absent": old is None,
            "mode": stat.S_IMODE(identity[2]) if identity is not None else None,
            "uid": identity[4] if identity is not None else None,
            "gid": identity[5] if identity is not None else None,
            "device": identity[0] if identity is not None else None,
            "inode": identity[1] if identity is not None else None,
            "backup": backup,
        }

    protect_parents(STATE_DIR / "state.json")
    ensure_private_directory(STATE_DIR)
    snapshot_state_artifacts(request)
    started_at = time.time()
    for name, path in FILES.items():
        desired = bundle[name]
        atomic_write(path, desired, 0o600 if path == POLICY else 0o644)
    reloaded = run(["systemctl", "daemon-reload"], timeout=20)
    if reloaded.returncode:
        fail("DAEMON_RELOAD")
    reject_external_unit_overrides()
    installed_unit, _ = bounded_read(UNIT, MAX_BYTES["nox-lifeline-observer.service"])
    if installed_unit != bundle["nox-lifeline-observer.service"]:
        fail("UNIT_BLOB_CHANGED_BEFORE_ENABLE")
    LEGACY_GUARD_PRE_ENABLE = recheck_legacy_guard(LEGACY_GUARD_PREIMAGE)
    CGROUP_TARGET_PRE_ENABLE = resolve_cgroup_target(LEGACY_GUARD_PRE_ENABLE)
    if CGROUP_TARGET_PRE_ENABLE != CGROUP_TARGET_EVIDENCE:
        fail("CGROUP_TARGET_CHANGED_BEFORE_ENABLE")
    SUPERVISORCTL_PRE_ENABLE = verify_supervisorctl_pin()
    MEMORY_PRE_ENABLE = cgroup_memory_snapshot(CGROUP_TARGET_EVIDENCE["target"])
    require_memory_headroom(MEMORY_PRE_ENABLE,
                            MEMORY_FLOOR_BYTES + MEMORY_RESERVE_BYTES,
                            "MEMORY_PRE_ENABLE_BELOW_FLOOR_PLUS_RESERVE")
    enabled = run(["systemctl", "enable", "--now", SERVICE], timeout=35)
    if enabled.returncode:
        fail("OBSERVER_ENABLE_START")

    state = unit_state(SERVICE)
    if state["active"] != "active" or state["enabled"] != "enabled":
        fail("OBSERVER_SYSTEMD_READBACK")
    show = run(["systemctl", "show", SERVICE, "--property=MainPID", "--value"], timeout=10)
    if show.returncode != 0:
        fail("OBSERVER_MAINPID_QUERY")
    try:
        pid = int(show.stdout.strip())
    except ValueError:
        fail("OBSERVER_MAINPID")
    identity = process_identity(pid)
    report = fresh_receipt(started_at)
    LEGACY_GUARD_POSTCHECK = recheck_legacy_guard(LEGACY_GUARD_PREIMAGE)
    CGROUP_TARGET_POST_ENABLE = resolve_cgroup_target(LEGACY_GUARD_POSTCHECK)
    if CGROUP_TARGET_POST_ENABLE != CGROUP_TARGET_EVIDENCE:
        fail("CGROUP_TARGET_CHANGED_AFTER_ENABLE")
    SUPERVISORCTL_POST_ENABLE = verify_supervisorctl_pin()
    MEMORY_POST_ENABLE = cgroup_memory_snapshot(CGROUP_TARGET_EVIDENCE["target"])
    require_memory_headroom(MEMORY_POST_ENABLE, MEMORY_FLOOR_BYTES,
                            "MEMORY_POST_ENABLE_BELOW_2GIB")
    final_state = unit_state(SERVICE)
    final_show = run(["systemctl", "show", SERVICE, "--property=MainPID", "--value"], timeout=10)
    if final_show.returncode != 0:
        fail("OBSERVER_FINAL_MAINPID_QUERY")
    try:
        final_pid = int(final_show.stdout.strip())
    except ValueError:
        fail("OBSERVER_FINAL_MAINPID")
    final_identity = process_identity(final_pid)
    if (final_state["active"] != "active" or final_state["enabled"] != "enabled" or
            final_pid != pid or final_identity["start_ticks"] != identity["start_ticks"] or
            final_identity["argv"] != identity["argv"] or
            final_identity["exe"] != identity["exe"]):
        fail("OBSERVER_IDENTITY_CHANGED_AFTER_RECEIPT")
    memory = report["cgroup_memory"]
    emit({"state": "OBSERVER_ACTIVE_CRITICAL_MEMORY" if memory["below_2GiB"] else "OBSERVER_ACTIVE",
          "source_sha": source_sha, "request_id": request,
          "service": SERVICE, "service_active": state["active"],
          "service_enabled": state["enabled"], "pid": pid,
          "start_ticks": identity["start_ticks"], "argv_sha256": hashlib.sha256(
              b"\0".join(x.encode() for x in identity["argv"])).hexdigest(),
          "script_sha256": hashlib.sha256(bundle["nox_lifeline_observer.py"]).hexdigest(),
          "observer_runtime_source_sha256": OBSERVER_RUNTIME_SOURCE_SHA256,
          "policy_sha256": hashlib.sha256(bundle["lifeline-observer.json"]).hexdigest(),
          "unit_sha256": hashlib.sha256(bundle["nox-lifeline-observer.service"]).hexdigest(),
          "observer_only_enforced": True, "worker_starts_permitted": False,
          "global_supervisor_mutated": False,
          "memory_preflight": MEMORY_PREFLIGHT,
          "memory_pre_enable": MEMORY_PRE_ENABLE,
          "memory_post_enable": MEMORY_POST_ENABLE,
          "memory_startup_reserve_bytes": MEMORY_RESERVE_BYTES,
          "cgroup_target_before": CGROUP_TARGET_EVIDENCE,
          "cgroup_target_pre_enable": CGROUP_TARGET_PRE_ENABLE,
          "cgroup_target_after": CGROUP_TARGET_POST_ENABLE,
          "legacy_guard_before": LEGACY_GUARD_PREIMAGE,
          "legacy_guard_pre_enable": LEGACY_GUARD_PRE_ENABLE,
          "legacy_guard_after": LEGACY_GUARD_POSTCHECK,
          "supervisor_endpoint": SUPERVISORCTL_PIN,
          "supervisor_endpoint_backend": SUPERVISORCTL_CANDIDATE_OUTCOMES,
          "supervisor_endpoint_pre_enable": SUPERVISORCTL_PRE_ENABLE,
          "supervisor_endpoint_post_enable": SUPERVISORCTL_POST_ENABLE,
          "cgroup_memory": memory, "cgroup_memory_at": report["at"],
          "memory_floor_bytes": 2 * 1024**3,
          "preimages_backed_up": True,
          "preimages": preimage_receipts,
          "state_directory_preimage": STATE_DIR_PREIMAGE,
          "state_artifact_preimages": {key: value for key, value in
                                        STATE_ARTIFACT_PREIMAGES.items()
                                        if key.endswith(".receipt")},
          "rollback": "PREIMAGE_CONTENT_MODE_OWNER_CAS;FILE_INODES_NOT_RESTORABLE",
          "weights_training_supervisor_workloads_changed": False})
    return 0


_RECEIPT_PRIVATE_FIELDS = frozenset({
    "argv", "cmdline", "command", "serverurl", "rpc_factory", "rpc_url",
    "legacy_pid", "model_pid", "model_group", "owner_pid", "fd",
})
_RECEIPT_FILE_SUFFIXES = (".conf", ".ini", ".cfg", ".json", ".service", ".py", ".lock")
_RECEIPT_FILE_TOKEN = re.compile(r"\.(?:conf|ini|cfg|json|service|py|lock)(?:\.|$)", re.I)


def _receipt_path_kind(path, hint=""):
    text = os.fspath(path)
    if text.startswith("unix://"):
        text = text[7:]
    normalized = text.lower()
    if normalized.startswith("/sys/fs/cgroup/") or normalized == "/sys/fs/cgroup":
        return "shared_memory_scope"
    if "socket" in hint.lower() or normalized.endswith(".sock"):
        return "unix_socket"
    if "supervisor" in normalized and normalized.endswith(_RECEIPT_FILE_SUFFIXES):
        return "supervisor_config"
    if "supervisor" in normalized and not normalized.endswith(_RECEIPT_FILE_SUFFIXES):
        return "supervisor_process_path"
    if "lifeline" in normalized:
        return "lifeline_artifact"
    return "filesystem_path"


def _receipt_path_digest(path, hint=""):
    raw = os.fsencode(os.fspath(path))
    return {"path_kind": _receipt_path_kind(path, hint),
            "path_sha256": hashlib.sha256(raw).hexdigest()}


def _receipt_key_name(key):
    text = str(key)
    if text.startswith("/") or _RECEIPT_FILE_TOKEN.search(text):
        return "artifact_" + hashlib.sha256(os.fsencode(text)).hexdigest()[:16]
    return text


def _public_memory_scope(snapshot):
    if not isinstance(snapshot, dict):
        return None
    target = snapshot.get("target")
    model = snapshot.get("model")
    model = model if isinstance(model, dict) else {}
    census = model.get("census")
    census = census if isinstance(census, dict) else {}
    rows = census.get("matches")
    rows = rows if isinstance(rows, list) else []
    safe_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        safe_row = {key: row[key] for key in (
            "pid", "start_ticks", "exe_path_sha256", "argv_sha256",
            "environment_sha256") if key in row}
        if "in_memory_target_cgroup" in row:
            safe_row["in_target_memory_scope"] = row["in_memory_target_cgroup"]
        safe_rows.append(safe_row)
    result = {"scope_kind": "shared_memory_limit_scope",
              "mapping": snapshot.get("mapping"),
              "model_state": model.get("state"),
              "model_anchor": model.get("anchor"),
              "model_runtime_count": census.get("count", len(safe_rows)),
              "model_runtime_scan_scope": census.get("scope"),
              "model_runtime_matches_sha256": hashlib.sha256(json.dumps(
                  safe_rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
    if isinstance(target, str):
        result.update(_receipt_path_digest(target, "memory_scope"))
    return result


def _public_receipt_value(value, key_hint=""):
    if isinstance(value, dict):
        result = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            lower = key.lower()
            if lower in _RECEIPT_PRIVATE_FIELDS or "serverurl" in lower or "rpc_factory" in lower:
                continue
            if "cgroup" in lower:
                continue
            if lower in ("path", "configured_path", "include_glob", "filename",
                         "target", "config") or lower.endswith("_path"):
                if isinstance(item, str):
                    digest = _receipt_path_digest(item, key)
                    safe_name = "path" if key == "path" else key.removesuffix("_path")
                    result[safe_name + "_kind"] = digest["path_kind"]
                    result[safe_name + "_sha256"] = digest["path_sha256"]
                elif isinstance(item, dict):
                    result[_receipt_key_name(key)] = _public_receipt_value(item, key)
                continue
            safe_key = _receipt_key_name(key)
            if isinstance(item, str) and (item.startswith("/") or item.startswith("unix://") or
                                          item.startswith("file://")):
                digest = _receipt_path_digest(item, key_hint or key)
                result[safe_key + "_kind"] = digest["path_kind"]
                result[safe_key + "_sha256"] = digest["path_sha256"]
            else:
                result[safe_key] = _public_receipt_value(item, key)
        return result
    if isinstance(value, (list, tuple)):
        return [_public_receipt_value(item, key_hint) for item in value]
    if isinstance(value, str) and (value.startswith("/") or value.startswith("unix://") or
                                   value.startswith("file://")):
        return _receipt_path_digest(value, key_hint)
    return value


def _public_receipt(value):
    if not isinstance(value, dict):
        return _public_receipt_value(value)
    result = {}
    for key, item in value.items():
        if key.startswith("cgroup_target_"):
            result["memory_scope_" + key.removeprefix("cgroup_target_")] = _public_memory_scope(item)
        elif key == "cgroup_memory":
            result["memory_snapshot"] = _public_receipt_value(item, "memory_snapshot")
        elif key == "cgroup_memory_at":
            result["memory_snapshot_at"] = item
        else:
            result[key] = _public_receipt_value(item, key)
    return result


def emit(value):
    public_value = _public_receipt(value)
    print("NOX_MAINT_LIFELINE_OBSERVER_RECEIPT=" +
          json.dumps(public_value, sort_keys=True), flush=True)


def run_owner_entrypoint(main_fn=None):
    global MEMORY_POST_ROLLBACK, OWNER_LOCK_FD, OWNER_LOCK_PARENT_FD
    global OWNER_LOCK_IDENTITY, OWNER_FENCE_STATUS

    class OwnerAbort(BaseException):
        pass

    def _owner_abort(signum, frame):
        raise OwnerAbort("HOLD_LIFELINE_OBSERVER_OWNER_SIGNAL")

    signal.signal(signal.SIGTERM, _owner_abort)
    signal.signal(signal.SIGINT, _owner_abort)
    installation_verified = False
    try:
        result = (main_fn or main)()
        if result == 0:
            # From here on the installed observer has passed its runtime and
            # readback gates. Report finalization failures as HOLD; never roll
            # back an already verified install after fences may be removed.
            installation_verified = True
            if not OWNER_FENCES_CREATED:
                emit({"state": "HOLD", "reason": "HOLD_LIFELINE_OBSERVER_OWNER_FENCE_MISSING",
                      "rollback": "INSTALL_VERIFIED_WITHOUT_OWNED_FENCES",
                      "source_sha": SOURCE_SHA_VALUE, "request_id": REQUEST_ID,
                      "native_mutation_attempted": NATIVE_MUTATION_ATTEMPTED,
                      "owner_fences": _owner_fence_receipt()})
                result = 2
            elif not cleanup_owner_fences("SUCCESS"):
                emit({"state": "HOLD", "reason": "HOLD_LIFELINE_OBSERVER_OWNER_FENCE_CLEANUP",
                      "rollback": "INSTALL_VERIFIED_FENCES_RETAINED",
                      "source_sha": SOURCE_SHA_VALUE, "request_id": REQUEST_ID,
                      "native_mutation_attempted": NATIVE_MUTATION_ATTEMPTED,
                      "owner_fences": _owner_fence_receipt()})
                result = 2
            else:
                emit({"state": "OWNER_FENCES_RELEASED", "reason": None,
                      "source_sha": SOURCE_SHA_VALUE, "request_id": REQUEST_ID,
                      "owner_fences": _owner_fence_receipt()})
                print("NOX_MAINT_LIFELINE_COMPLETE=true", flush=True)
        elif result != 0 and OWNER_FENCES_CREATED:
            if not NATIVE_MUTATION_ATTEMPTED:
                if not cleanup_owner_fences("NO_WRITE_FAILURE"):
                    emit({"state": "HOLD", "reason": "HOLD_LIFELINE_OBSERVER_OWNER_FENCE_CLEANUP",
                          "rollback": "NO_WRITE_FAILURE_FENCES_RETAINED",
                          "source_sha": SOURCE_SHA_VALUE, "request_id": REQUEST_ID,
                          "native_mutation_attempted": False,
                          "owner_fences": _owner_fence_receipt()})
                    result = 2
            else:
                OWNER_FENCE_STATUS = dict(OWNER_FENCE_STATUS, state="RETAINED",
                                          cleanup="NONZERO_AFTER_MUTATION_RETAINED",
                                          retained=True)
                emit({"state": "HOLD", "reason": "HOLD_LIFELINE_OBSERVER_MUTATION_INCOMPLETE",
                      "rollback": "MUTATION_NOT_VERIFIED_FENCES_RETAINED",
                      "source_sha": SOURCE_SHA_VALUE, "request_id": REQUEST_ID,
                      "native_mutation_attempted": True,
                      "owner_fences": _owner_fence_receipt()})
                result = 2
    except BaseException as exc:
        if installation_verified:
            # Fence cleanup may already have removed the markers. Do not
            # initiate rollback from this post-verification reporting path.
            if OWNER_FENCES_CREATED:
                OWNER_FENCE_STATUS = dict(OWNER_FENCE_STATUS, state="RETAINED",
                                          cleanup="INSTALL_VERIFIED_FINALIZATION_HOLD",
                                          retained=True)
            code = str(exc)
            if not re.fullmatch(r"HOLD_LIFELINE_OBSERVER_[A-Z0-9_]+", code):
                code = "HOLD_LIFELINE_OBSERVER_" + type(exc).__name__.upper()
            try:
                emit({"state": "HOLD", "reason": code,
                      "rollback": "INSTALL_VERIFIED_NO_POST_RELEASE_ROLLBACK",
                      "source_sha": SOURCE_SHA_VALUE, "request_id": REQUEST_ID,
                      "native_mutation_attempted": NATIVE_MUTATION_ATTEMPTED,
                      "owner_fences": _owner_fence_receipt()})
            except BaseException:
                pass
            return 2
        rollback = "NOT_NEEDED"
        rollback_verified = not NATIVE_MUTATION_ATTEMPTED
        if SUPERVISOR_BACKEND_ACTIVE:
            try:
                changed = bool(INSTALLED or STATE_DIR_PREIMAGE is not None or
                              SUPERVISOR_PROGRAM_RELOADED or SUPERVISOR_PROGRAM_ADDED or
                              SUPERVISOR_PROGRAM_STARTED)
                if changed:
                    rollback = rollback_supervisor_fallback()
                    restore_state_artifacts()
                    if CGROUP_TARGET_EVIDENCE is not None:
                        MEMORY_POST_ROLLBACK = cgroup_memory_snapshot(
                            CGROUP_TARGET_EVIDENCE["target"])
                    rollback_verified = True
            except BaseException as rollback_exc:
                reason = type(rollback_exc).__name__.upper()
                rollback = "ROLLBACK_INCOMPLETE_" + (reason if re.fullmatch(
                    r"[A-Z0-9_]{1,40}", reason) else "UNKNOWN")
        elif INSTALLED or STATE_DIR_PREIMAGE is not None:
            try:
                if INSTALLED:
                    if UNIT_ACTIVE_BEFORE != "active":
                        stopped = run(["systemctl", "stop", SERVICE], timeout=20)
                        if stopped.returncode:
                            fail("ROLLBACK_SERVICE_STOP")
                        current = unit_state(SERVICE)
                        if current["active"] == "active":
                            fail("ROLLBACK_SERVICE_STILL_ACTIVE")
                    if UNIT_ENABLED_BEFORE != "enabled":
                        disabled = run(["systemctl", "disable", SERVICE], timeout=20)
                        if disabled.returncode:
                            fail("ROLLBACK_SERVICE_DISABLE")
                    restore_exact_preimages()
                    restored_state = unit_state(SERVICE)
                    if (restored_state["active"] != UNIT_ACTIVE_BEFORE or
                            restored_state["enabled"] != UNIT_ENABLED_BEFORE):
                        fail("ROLLBACK_SERVICE_STATE_MISMATCH")
                restore_state_artifacts()
                if CGROUP_TARGET_EVIDENCE is not None:
                    MEMORY_POST_ROLLBACK = cgroup_memory_snapshot(
                        CGROUP_TARGET_EVIDENCE["target"])
                rollback = "PREIMAGE_CONTENT_MODE_OWNER_RESTORED;FILE_INODES_NOT_RESTORABLE"
                rollback_verified = True
            except BaseException as rollback_exc:
                reason = type(rollback_exc).__name__.upper()
                rollback = "ROLLBACK_INCOMPLETE_" + (reason if re.fullmatch(
                    r"[A-Z0-9_]{1,40}", reason) else "UNKNOWN")
        if OWNER_FENCES_CREATED:
            if not NATIVE_MUTATION_ATTEMPTED:
                if not cleanup_owner_fences("NO_WRITE_FAILURE"):
                    rollback += ";OWNER_FENCES_RETAINED"
            elif rollback_verified:
                if not cleanup_owner_fences("VERIFIED_ROLLBACK"):
                    rollback += ";OWNER_FENCES_RETAINED"
            else:
                OWNER_FENCE_STATUS = dict(OWNER_FENCE_STATUS, state="RETAINED",
                                          cleanup="AMBIGUOUS_MUTATION_RETAINED",
                                          retained=True)
        code = str(exc)
        if not re.fullmatch(r"HOLD_LIFELINE_OBSERVER_[A-Z0-9_]+", code):
            code = "HOLD_LIFELINE_OBSERVER_" + type(exc).__name__.upper()
        emit({"state": "HOLD", "reason": code, "rollback": rollback,
              "source_sha": SOURCE_SHA_VALUE, "request_id": REQUEST_ID,
              "memory_preflight": MEMORY_PREFLIGHT,
              "memory_pre_enable": MEMORY_PRE_ENABLE,
              "memory_post_enable": MEMORY_POST_ENABLE,
              "memory_post_rollback": MEMORY_POST_ROLLBACK,
              "memory_floor_bytes": MEMORY_FLOOR_BYTES,
              "memory_startup_reserve_bytes": MEMORY_RESERVE_BYTES,
              "cgroup_target_before": CGROUP_TARGET_EVIDENCE,
              "cgroup_target_pre_enable": CGROUP_TARGET_PRE_ENABLE,
              "cgroup_target_after": CGROUP_TARGET_POST_ENABLE,
              "legacy_guard_before": LEGACY_GUARD_PREIMAGE,
              "legacy_guard_pre_enable": LEGACY_GUARD_PRE_ENABLE,
              "legacy_guard_after": LEGACY_GUARD_POSTCHECK,
              "supervisor_endpoint": SUPERVISORCTL_PIN,
              "supervisor_endpoint_backend": SUPERVISORCTL_CANDIDATE_OUTCOMES,
              "supervisor_endpoint_pre_enable": SUPERVISORCTL_PRE_ENABLE,
              "supervisor_endpoint_post_enable": SUPERVISORCTL_POST_ENABLE,
              "observer_runtime_source_sha256": OBSERVER_RUNTIME_SOURCE_SHA256,
              "supervisor_fallback": {
                  "enabled": SUPERVISOR_BACKEND_ACTIVE,
                  "supervisor_version": SUPERVISOR_SERVER_VERSION,
                  "program_name": SUPERVISOR_PROGRAM_NAME if SUPERVISOR_BACKEND_ACTIVE else None,
                  "reload_delta": (SUPERVISOR_PROGRAM_ACTIVATION or {}).get("reload_delta"),
                  "observer_started": SUPERVISOR_PROGRAM_STARTED,
                  "prior_groups_unchanged_during_rollback":
                      SUPERVISOR_PROGRAM_ROLLBACK_PRIOR_GROUPS_UNCHANGED,
                  "existing_groups_unchanged": (SUPERVISOR_PROGRAM_ACTIVATION or {}).get(
                      "existing_process_inventory_unchanged"),
                  "memory_post_start": SUPERVISOR_MEMORY_POST_START,
                  "resource_controls": (SUPERVISOR_RESOURCE_RECEIPT
                                         if SUPERVISOR_BACKEND_ACTIVE else None),
                  "host_boot_persistence": "UNKNOWN_SUPERVISOR_DAEMON_BOOT_OWNER_NOT_PROVEN_BY_REPOSITORY",
              },
              "state_directory_preimage": STATE_DIR_PREIMAGE,
              "state_artifact_preimages": {key: value for key, value in
                                            STATE_ARTIFACT_PREIMAGES.items()
                                            if key.endswith(".receipt")},
              "global_supervisor_mutated": False,
              "installed_paths": list(INSTALLED),
              "native_mutation_attempted": NATIVE_MUTATION_ATTEMPTED,
              "owner_fences": _owner_fence_receipt()})
        return 2
    finally:
        _close_owner_fence_directory_fds()
        if OWNER_LOCK_FD is not None:
            owner_lock_fd = OWNER_LOCK_FD
            OWNER_LOCK_FD = None
            os.close(owner_lock_fd)
        if OWNER_LOCK_PARENT_FD is not None:
            owner_lock_parent_fd = OWNER_LOCK_PARENT_FD
            OWNER_LOCK_PARENT_FD = None
            os.close(owner_lock_parent_fd)
        OWNER_LOCK_IDENTITY = None
    return result


if __name__ == "__main__":
    sys.exit(run_owner_entrypoint())
