#!/usr/bin/env python3
"""Bounded owner probe and stop via the live Supervisor UNIX socket."""

import configparser
import contextlib
import fcntl
import hashlib
import http.client
import json
import os
import re
import select
import socket
import stat
import struct
import time
import xmlrpc.client
from pathlib import Path
from urllib.parse import urlsplit


CONFIG = Path("/etc/supervisor/supervisord.conf")
INCLUDES = CONFIG.parent / "conf.d"
LEASE = Path("/root/nox/state/owner_maintenance.lock")
PROC = Path("/proc")
CGROUP = Path("/sys/fs/cgroup")
BOOT = "9c0ecc02-85c1-452b-b8ae-521e9a11fd03"
SUPERVISOR = 114, 167791115
MODEL = "nox-ds41-8098", 3266857, 172046662
TARGETS = {
    "nox-fill-idle-t166u": (3352981, 172255926,
                           "ac29d27ad4379fdbe97db8a1a02956ad53a55569933f1ee8f9c74e91dd7fdfaa"),
    "nox-gpu-idle-t170u": (3355350, 172305444,
                          "ccf76f8fd1221e82655e21af51cf496c739f3a7752d3bb6ed21d97275741eab0"),
}
# The published owner action must bind the chosen target in its pinned source.
# The first live dispatch should only qualify the endpoint and enumerate targets.
STOP_TARGET = None
QUEUE = Path("/root/nox/state/dispatcher/state.json")
HTTP_LIMIT = 32 * 1024
issues = {}


class Hold(RuntimeError):
    """A stable reason code suitable for the owner action receipt."""


def need(check, code):
    if not check:
        raise Hold(code)


def stamp(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_gid, value.st_nlink, value.st_ctime_ns)


def read(path, limit, *, rooted=False):
    if rooted:
        trusted_parents(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as file:
        before = os.fstat(file.fileno())
        need(stat.S_ISREG(before.st_mode) and (not rooted or
             (before.st_uid == before.st_gid == 0 and not before.st_mode & 0o022
              and before.st_nlink == 1)), "FILE_IDENTITY")
        data = file.read(limit + 1)
        after = os.fstat(file.fileno())
    need(len(data) <= limit and stamp(before) == stamp(after) == stamp(path.lstat()),
         "FILE_CHANGED_OR_TOO_LARGE")
    return data


def trusted_parents(path):
    for part in path.parents:
        meta = part.lstat()
        need(stat.S_ISDIR(meta.st_mode) and meta.st_uid == meta.st_gid == 0,
             "PATH_PARENT_IDENTITY")
        if part == Path("/tmp"):
            need(meta.st_mode & stat.S_ISVTX, "TMP_PARENT_NOT_STICKY")
        else:
            need(not meta.st_mode & 0o022, "PATH_PARENT_WRITABLE")


def process(pid):
    row = read(PROC / str(pid) / "stat", 8192)
    head, marker, tail = row.rpartition(b") ")
    need(marker and head.startswith(f"{pid} (".encode()), "PROC_IDENTITY")
    fields = tail.split()
    return int(fields[19]), int(fields[1]), int(fields[2]), fields[0]


def cgroup(pid):
    root = PROC / str(pid)
    return read(root / "cgroup", 8192), os.readlink(root / "ns/cgroup")


def config_parse(data):
    # Match Supervisor's space-prefixed semicolon comment handling, while
    # deliberately retaining strict duplicate-key/section rejection.
    parser = configparser.ConfigParser(interpolation=None, strict=True,
                                       inline_comment_prefixes=(";",))
    parser.read_string(data.decode())
    need(not parser.defaults(), "CONFIG_DEFAULTS_UNSUPPORTED")
    return parser


def plain_socket_path(value, here):
    expanded = value.replace("%(here)s", str(here))
    path = Path(expanded)
    need(re.fullmatch(r"/[A-Za-z0-9_./-]+", expanded)
         and ".." not in path.parts and str(path) == expanded, "SOCKET_PATH_SHAPE")
    return path


def resolve_socket(path):
    if path.is_relative_to("/var/run") and Path("/var/run").is_symlink():
        alias = Path("/var/run")
        link = alias.lstat()
        need(link.st_uid == link.st_gid == 0 and
             os.readlink(alias) in ("/run", "../run"), "VAR_RUN_ALIAS")
        trusted_parents(alias)
        path = Path("/run") / path.relative_to(alias)
    trusted_parents(path)
    return path


def endpoint_config(data, here):
    parser = config_parse(data)
    server = parser["unix_http_server"]
    client = parser["supervisorctl"]
    need(set(server) <= {"file", "chmod", "chown"} and set(client) == {"serverurl"},
         "ENDPOINT_CONFIG_AUTH_UNSUPPORTED")
    need(parser["rpcinterface:supervisor"]["supervisor.rpcinterface_factory"] ==
         "supervisor.rpcinterface:make_main_rpcinterface", "RPC_FACTORY")
    need(parser["include"]["files"] == str(INCLUDES / "*.conf"), "INCLUDE_SCOPE")
    mode = server.get("chmod", "0700")
    need(re.fullmatch(r"0?[0-7]{3}", mode) and int(mode, 8) == 0o700 and
         server.get("chown", "root:root") in ("root:root", "0:0"), "SOCKET_MODE_CONFIG")
    path = plain_socket_path(server["file"], here)
    uri = urlsplit(client["serverurl"].replace("%(here)s", str(here)))
    need(uri.scheme == "unix" and not (uri.netloc or uri.query or uri.fragment),
         "CLIENT_ENDPOINT_SCHEME")
    client_path = plain_socket_path(uri.path, here)
    return path, client_path


def endpoint():
    main = read(CONFIG, 256 * 1024, rooted=True)
    server, client = endpoint_config(main, CONFIG.parent)
    resolved = resolve_socket(server)
    need(resolve_socket(client) == resolved, "SERVER_CLIENT_ENDPOINT_DIFFER")
    need(len(os.fsencode(resolved)) <= 103, "SOCKET_PATH_LIMIT")
    info = resolved.lstat()
    need(stat.S_ISSOCK(info.st_mode) and info.st_uid == info.st_gid == 0
         and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o700, "SOCKET_MODE_LIVE")
    pid, start_ticks = SUPERVISOR
    expected = process(pid)
    need(expected[:2] == (start_ticks, 1) and expected[3] != b"Z" and
         cgroup(pid) == cgroup("self"), "SUPERVISOR_PROCESS_GENERATION")
    argv_raw = read(PROC / str(pid) / "cmdline", 16384)
    argv = argv_raw.split(b"\0")[:-1] if argv_raw.endswith(b"\0") else []
    scripts = [index for index, arg in enumerate(argv) if
               arg.startswith(b"/") and arg.endswith(b"/supervisord")]
    need(len(scripts) == 1 and argv[scripts[0] + 1:] in
         ([b"-c", os.fsencode(CONFIG)], [b"--configuration", os.fsencode(CONFIG)]),
         "SUPERVISOR_CONFIG_ARGV")
    exe = (PROC / str(pid) / "exe").stat()
    need(stat.S_ISREG(exe.st_mode) and exe.st_uid == exe.st_gid == 0
         and not exe.st_mode & 0o022, "SUPERVISOR_EXECUTABLE_IDENTITY")
    rows = []
    known_names = {str(server), str(client), str(resolved)}
    for line in read(PROC / "net/unix", 2 * 1024 * 1024).decode().splitlines()[1:]:
        parts = line.split(maxsplit=7)
        if len(parts) == 8 and parts[7] in known_names and parts[4:6] == ["0001", "01"]:
            if int(parts[3], 16) & 0x10000:
                rows.append(parts[6])
    need(len(rows) == 1 and rows[0].isdecimal(), "SOCKET_LISTENER_UNPROVEN")
    matches = []
    for fd in (PROC / str(pid) / "fd").iterdir():
        try:
            if os.readlink(fd) == f"socket:[{rows[0]}]":
                matches.append(fd.name)
        except FileNotFoundError:
            continue
    need(len(matches) == 1 and process(pid)[:3] == expected[:3] and
         stamp(resolved.lstat()) == stamp(info), "SOCKET_PEER_FD_UNPROVEN")
    return resolved, stamp(info), hashlib.sha256(main).hexdigest(), rows[0], matches[0], argv_raw


def rpc(pin, method, params=(), *, preflight=None):
    allowed = (method in ("getPID", "getState") and not params) or (
        method == "getProcessInfo" and len(params) == 1 and params[0] in (*TARGETS, MODEL[0])) or (
        method == "stopProcess" and STOP_TARGET in TARGETS and params == (STOP_TARGET, True)
        and preflight is not None)
    need(allowed, "RPC_METHOD_OUT_OF_SCOPE")
    http = http.client.HTTPConnection("localhost", timeout=25)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel, contextlib.closing(http):
        channel.settimeout(25)
        channel.connect(str(pin[0]))
        creds = struct.unpack("3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        need(creds == (SUPERVISOR[0], 0, 0), "SOCKET_PEERCRED")
        pidfd = os.pidfd_open(creds[0])
        try:
            poll = select.poll()
            poll.register(pidfd, select.POLLIN)
            need(not poll.poll(0) and endpoint() == pin, "SUPERVISOR_CHANGED")
            if preflight:
                preflight()
                need(not poll.poll(0) and endpoint() == pin, "SUPERVISOR_CHANGED_BEFORE_STOP")
            http.sock = channel
            body = xmlrpc.client.dumps(params, methodname=f"supervisor.{method}").encode()
            if method == "stopProcess":
                issues["stop_request_attempted"] = True
            http.request("POST", "/RPC2", body,
                         {"Content-Type": "text/xml", "Connection": "close"})
            reply = http.getresponse()
            need(reply.status == 200 and not reply.chunked and
                 reply.length is not None and 0 < reply.length <= HTTP_LIMIT, "RPC_HTTP_REPLY")
            payload = reply.read()
            need(b"<!DOCTYPE" not in payload.upper() and b"<!ENTITY" not in payload.upper(),
                 "RPC_XML_DECLARATION")
            (value,), _ = xmlrpc.client.loads(payload)
            need(not poll.poll(0) and endpoint() == pin, "SUPERVISOR_CHANGED_AFTER_RPC")
            return value
        finally:
            os.close(pidfd)


def membership(name, pid, start_ticks):
    parent = SUPERVISOR[0]
    start, ppid, pgrp, state = process(pid)
    need((start, ppid, pgrp) == (start_ticks, parent, pid) and state != b"Z" and
         cgroup(pid) == cgroup("self"), "TARGET_PROCESS_GENERATION")
    env = read(PROC / str(pid) / "environ", 256 * 1024).split(b"\0")
    names = [x for x in env if x.startswith(b"SUPERVISOR_PROCESS_NAME=")]
    need(names == [f"SUPERVISOR_PROCESS_NAME={name}".encode()] and
         b"SUPERVISOR_ENABLED=1" in env, "TARGET_OWNER_TAG")
    peers = [path for path in PROC.iterdir() if path.name.isascii() and path.name.isdecimal()]
    need(len(peers) <= 512, "PROCESS_GROUP_CENSUS_LIMIT")
    for path in peers:
        peer = int(path.name)
        if peer != pid:
            try:
                _, peer_ppid, peer_pgrp, _ = process(peer)
            except FileNotFoundError:
                continue
            need(peer_ppid != pid and peer_pgrp != pid, "TARGET_GROUP_NOT_ISOLATED")
    need(process(pid)[:3] == (start, ppid, pgrp), "TARGET_CHANGED_DURING_CENSUS")


def runtime_queue_fence(name, pid):
    # An existing native task owned by another service continues to run.
    tasks = json.loads(read(QUEUE, 16 * 1024 * 1024, rooted=True))["tasks"]
    need(isinstance(tasks, dict), "QUEUE_SCHEMA")
    for row in tasks.values():
        need(isinstance(row, dict) and isinstance(row.get("status"), str), "QUEUE_ROW_SCHEMA")
        if row["status"] in {"done", "completed", "failed", "cancelled"}:
            continue
        fields = [row.get(k) for k in ("worker", "worker_id", "worker_pid", "service",
                                      "claim", "owner_claim", "native_worker_lease")]
        encoded = json.dumps(fields, separators=(",", ":"))
        need(name not in encoded and not re.search(rf"(?<![0-9]){pid}(?![0-9])", encoded),
             "TARGET_HAS_QUEUE_OWNERSHIP")


def config_fence(name, expected_sha):
    entries = sorted(INCLUDES.glob("*.conf"))
    need(0 < len(entries) <= 96, "INCLUDE_CENSUS_LIMIT")
    matched = []
    for path in entries:
        raw = read(path, 256 * 1024, rooted=True)
        parser = config_parse(raw)
        for section in parser.sections():
            kind, _, program = section.partition(":")
            if kind == "group":
                grouped = {p.strip() for p in parser[section]["programs"].split(",")}
                need(name not in grouped, "TARGET_IN_SUPERVISOR_GROUP")
            if program == name:
                need(kind == "program", "TARGET_NOT_STANDALONE_PROGRAM")
                matched.append(hashlib.sha256(raw).hexdigest())
    need(matched == [expected_sha], "TARGET_CONFIG_DRIFT")


def protect_model(pin):
    name, pid, ticks = MODEL
    state = rpc(pin, "getProcessInfo", (name,))
    need((state["name"], state["group"], state["statename"], state["pid"]) ==
         (name, name, "RUNNING", pid) and process(pid)[0] == ticks,
         "MODEL_GENERATION_CHANGED")


def memory():
    need(cgroup("self")[0] == b"0::/\n", "CGROUP_NAMESPACE")
    names = ("anon", "file", "shmem", "inactive_file")
    stats = dict(line.split() for line in read(CGROUP / "memory.stat", 8192).decode().splitlines())
    return {"current": int(read(CGROUP / "memory.current", 128)),
            "limit": int(read(CGROUP / "memory.max", 128)),
            **{name: int(stats[name]) for name in names}}


def run():
    need(os.geteuid() == 0 and re.fullmatch(r"[0-9]{1,20}", os.getenv("NOX_OWNER_REQUEST_ID", ""))
         and re.fullmatch(r"[a-f0-9]{40}", os.getenv("NOX_OWNER_SOURCE_SHA", "")),
         "OWNER_CONTEXT")
    need(read(PROC / "sys/kernel/random/boot_id", 128).decode().strip() == BOOT,
         "BOOT_GENERATION")
    pin = endpoint()
    need(rpc(pin, "getPID") == SUPERVISOR[0] and
         rpc(pin, "getState") == {"statecode": 1, "statename": "RUNNING"},
         "SUPERVISOR_RPC_IDENTITY")
    protect_model(pin)
    issues["endpoint_verified"] = True
    issues["before"] = memory()
    candidates = {}
    for name, (pid, ticks, _) in TARGETS.items():
        row = rpc(pin, "getProcessInfo", (name,))
        if (row["name"], row["group"], row["statename"], row["pid"]) == (name, name, "RUNNING", pid):
            membership(name, pid, ticks)
            counts = dict((key, int(val)) for key, val in re.findall(
                rb"^(Private_Clean|Private_Dirty):\s+(\d+)\s+kB\s*$",
                read(PROC / str(pid) / "smaps_rollup", 16384), re.M))
            candidates[name] = sum(counts.values()) * 1024
    issues["candidate_uss_bytes"] = candidates
    if STOP_TARGET is None:
        return "SUPERVISOR_ENDPOINT_VERIFIED_READ_ONLY"
    need(STOP_TARGET in candidates, "STOP_TARGET_UNVERIFIED")
    pid, ticks, config_hash = TARGETS[STOP_TARGET]
    trusted_parents(LEASE)
    fd = os.open(LEASE, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        meta = os.fstat(fd)
        need(stat.S_ISREG(meta.st_mode) and meta.st_uid == meta.st_gid == 0
             and not meta.st_mode & 0o022 and meta.st_nlink == 1, "OWNER_LEASE_IDENTITY")
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        protect_model(pin)
        row = rpc(pin, "getProcessInfo", (STOP_TARGET,))
        need((row["name"], row["group"], row["statename"], row["pid"]) ==
             (STOP_TARGET, STOP_TARGET, "RUNNING", pid), "TARGET_RPC_GENERATION")

        def preflight():
            need(stamp(os.fstat(fd)) == stamp(LEASE.lstat()), "OWNER_LEASE_CHANGED")
            config_fence(STOP_TARGET, config_hash)
            runtime_queue_fence(STOP_TARGET, pid)
            membership(STOP_TARGET, pid, ticks)

        need(rpc(pin, "stopProcess", (STOP_TARGET, True), preflight=preflight) is True,
             "STOP_RETURNED_FALSE")
        after = rpc(pin, "getProcessInfo", (STOP_TARGET,))
        need((after["name"], after["group"], after["statename"], after["pid"]) ==
             (STOP_TARGET, STOP_TARGET, "STOPPED", 0), "STOP_UNCONFIRMED")
        need(not (PROC / str(pid)).exists(), "STOPPED_PID_STILL_PRESENT")
        protect_model(pin)
        time.sleep(1)
        issues["after"] = memory()
        return "STOP_CONFIRMED_MODEL_RETAINED"
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        result = run()
        rc = 0
    except Hold as error:
        result = "HOLD_" + str(error)
        rc = 2
    except (OSError, ValueError, KeyError, TypeError, IndexError,
            configparser.Error, http.client.HTTPException, xmlrpc.client.Error) as error:
        result = "HOLD_" + type(error).__name__.upper()
        rc = 2
    print("NOX_MAINT_SUPERVISOR_BACKGROUND=" + json.dumps({
        "state": result, "target": STOP_TARGET,
        "request": os.getenv("NOX_OWNER_REQUEST_ID", ""), **issues}), flush=True)
    if rc == 0:
        print("NOX_MAINT_REPAIR_COMPLETE=true", flush=True)
    raise SystemExit(rc)
