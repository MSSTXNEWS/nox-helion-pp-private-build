#!/usr/bin/env python3
"""Pinned read-only queries on the live Supervisor UNIX socket."""

import configparser
import contextlib
import hashlib
import http.client
import json
import os
import re
import select
import socket
import stat
import struct
import xmlrpc.client
from pathlib import Path
from urllib.parse import urlsplit


CONFIG = Path("/etc/supervisor/supervisord.conf")
INCLUDES = CONFIG.parent / "conf.d"
PROC = Path("/proc")
CGROUP = Path("/sys/fs/cgroup")
BOOT = "9c0ecc02-85c1-452b-b8ae-521e9a11fd03"
SUPERVISOR = 114, 167791115
MODEL = "nox-ds41-8098", 3266857, 172046662
TARGETS = ()
STOP_TARGET = None
HTTP_LIMIT = 32 * 1024


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
    need(re.fullmatch(r"0?[0-7]{3}", mode) and int(mode, 8) & 0o200
         and not int(mode, 8) & 0o077 and
         server.get("chown", "root:root") in ("root:root", "0:0"), "SOCKET_MODE_CONFIG")
    path = plain_socket_path(server["file"], here)
    uri = urlsplit(client["serverurl"].replace("%(here)s", str(here)))
    need(uri.scheme == "unix" and not (uri.netloc or uri.query or uri.fragment),
         "CLIENT_ENDPOINT_SCHEME")
    client_path = plain_socket_path(uri.path, here)
    return path, client_path, int(mode, 8)


def endpoint():
    main = read(CONFIG, 256 * 1024, rooted=True)
    main_sha = hashlib.sha256(main).hexdigest()
    need(main_sha == "fcead12b4dcb7f56b31d223f1cfa89792bd6e8008f78708a831b41fab9ece25d",
         "SUPERVISOR_CONFIG_CHANGED")
    server, client, mode = endpoint_config(main, CONFIG.parent)
    resolved = resolve_socket(server)
    need(resolve_socket(client) == resolved, "SERVER_CLIENT_ENDPOINT_DIFFER")
    need(len(os.fsencode(resolved)) <= 103, "SOCKET_PATH_LIMIT")
    info = resolved.lstat()
    need(stat.S_ISSOCK(info.st_mode) and info.st_uid == info.st_gid == 0
         and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == mode, "SOCKET_MODE_LIVE")
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
    return resolved, stamp(info), main_sha, rows[0], matches[0], argv_raw


def rpc(pin, method, params=()):
    allowed = (method in ("getPID", "getState") and not params) or (
        method == "getProcessInfo" and len(params) == 1 and params[0] in (*TARGETS, MODEL[0]))
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
            http.sock = channel
            body = xmlrpc.client.dumps(params, methodname=f"supervisor.{method}").encode()
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
