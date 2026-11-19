"""Exact-epoch NOX Supervisor adapter. The external owner RPC grants each action.

No CLI and no built-in authorizer. A trusted owner runner supplies a verified
readback context and its own live authorization callback. Missing or stale host
proof results in HOLD before dispatching a mutation.
"""
from __future__ import annotations

import configparser
from contextlib import ExitStack
from dataclasses import dataclass
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import select
import shlex
import socket
import stat
import struct
import time
import xmlrpc.client

import owner_runtime_cutover as transaction
import systemic_transaction_helpers as files

ROOT = Path('/root/nox')
PROC = Path('/proc')
MAIN = Path('/etc/supervisor/supervisord.conf')
INCLUDES = MAIN.parent / 'conf.d'
DIRECTOR = files.SERVICE
LAUNCHER = ROOT / 'scripts/nox_dispatcher_t855u.py'
SERVICES = {'model': 'nox-ds41-8098', 'proxy': 'nox-proxy', 'web': 'nox-web29-18775'}
KEEPERS = {ROOT / 'engram_ram/engram_memfd_holder.py', ROOT / 'ops/engram_cold_holder.py'}
BOOT_ID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
SOCKET_PATH = re.compile(r'/(?:[A-Za-z0-9_-][A-Za-z0-9_.-]*/)*[A-Za-z0-9_-][A-Za-z0-9_.-]*')
CONF_NAME = re.compile(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*\.conf')
SOURCE_SHA = re.compile(r'[a-f0-9]{40}')
RUNNABLE = {b'R', b'S', b'D', b'I'}
SAFE_PYTHON = re.compile(r'/(?:[A-Za-z0-9_.-]+/)*python(?:3(?:\.[0-9]+)?)?')
MAX_RPC = 32 * 1024
MAX_PROC = 1024
MAX_CONTEXT_AGE = 180
WAIT_STOP_SECONDS = 8
WAIT_START_SECONDS = 8
ROOT_PEER_IDS = (0, 0)


def need(value, code):
    transaction.require(value, 'NATIVE_' + code)


@dataclass(frozen=True)
class Context:
    request_id: str
    source_commit: str
    bundle_sha256: str
    observed_at: float
    expires_at: float
    boot_id: str
    supervisor: transaction.Process
    socket_path: Path
    main_config_sha256: str
    include: str
    include_sha256: str
    launcher_sha256: str
    director_cmdline_sha256: str
    director: transaction.Process
    children: tuple[transaction.Process, ...]
    protected: tuple[tuple[str, transaction.Process], ...]
    holder_path: Path
    holder_sha256: str
    holder_cmdline_sha256: str

    def validate(self):
        need(self.request_id != '0' and re.fullmatch(r'[0-9]{1,24}', self.request_id)
             and SOURCE_SHA.fullmatch(self.source_commit) and self.source_commit != '0'*40
             and BOOT_ID.fullmatch(self.boot_id) and self.boot_id != '00000000-0000-0000-0000-000000000000'
             and CONF_NAME.fullmatch(self.include) and self.holder_path in KEEPERS
             and SOCKET_PATH.fullmatch(str(self.socket_path)) and len(os.fsencode(self.socket_path)) <= 103,
             'EXACT_CONTEXT_SCOPE')
        pins = (self.bundle_sha256, self.main_config_sha256, self.include_sha256, self.launcher_sha256,
                self.director_cmdline_sha256, self.holder_sha256, self.holder_cmdline_sha256)
        need(all(transaction.SHA.fullmatch(pin) and pin != '0'*64 for pin in pins), 'EXACT_CONTEXT_PINS')
        need(type(self.observed_at) in (int, float) and type(self.expires_at) in (int, float)
             and self.observed_at <= time.time() < self.expires_at <= self.observed_at + MAX_CONTEXT_AGE,
             'CONTEXT_EXPIRED')
        protected = dict(self.protected)
        processes = (self.supervisor, self.director, *self.children, *protected.values())
        need(len(protected) == len(self.protected) == len(transaction.PROTECTED)
             and set(protected) == transaction.PROTECTED and len(self.children) < 64
             and all(isinstance(item, transaction.Process) and item.valid() for item in processes)
             and len({item.pid for item in processes}) == len(processes), 'EXACT_CONTEXT_PROCESSES')


@dataclass(frozen=True)
class Proc:
    generation: transaction.Process
    ppid: int
    pgrp: int
    state: bytes


def stamp(info):
    return info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode, info.st_nlink, info.st_ctime_ns


def trusted_parents(path):
    for parent in path.parents:
        info = parent.lstat()
        need(stat.S_ISDIR(info.st_mode) and info.st_uid == info.st_gid == 0
             and (bool(info.st_mode & stat.S_ISVTX) if parent == Path('/tmp') else not info.st_mode & 0o022),
             'TRUSTED_PARENT')


def read(path, max_bytes, *, rooted=False):
    if rooted:
        trusted_parents(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        need(stat.S_ISREG(info.st_mode) and (not rooted or
             (info.st_uid == info.st_gid == 0 and info.st_nlink == 1 and not info.st_mode & 0o022)), 'FILE')
        raw = stream.read(max_bytes + 1)
        after = os.fstat(stream.fileno())
    need(len(raw) <= max_bytes and stamp(info) == stamp(after) == stamp(path.lstat()), 'FILE_DRIFT')
    return raw


def parse_config(raw):
    config = configparser.ConfigParser(interpolation=None, strict=True, inline_comment_prefixes=(';',))
    config.read_string(raw.decode('utf-8'))
    need(not config.defaults(), 'CONFIG_DEFAULTS')
    return config


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def socket_path(raw, here=MAIN.parent):
    path = Path(raw.replace('%(here)s', str(here)))
    if path.is_relative_to('/var/run') and Path('/var/run').is_symlink():
        alias = Path('/var/run')
        trusted_parents(alias)
        link = alias.lstat()
        need(link.st_uid == link.st_gid == 0 and os.readlink(alias) in ('/run', '../run'), 'SOCKET_ALIAS')
        path = Path('/run') / path.relative_to(alias)
    trusted_parents(path)
    return path


class SupervisorHost:
    """Local-only socket and /proc transport, deliberately missing a generic RPC method."""

    def __init__(self, context):
        self.context = context

    def boot_id(self):
        return read(PROC/'sys/kernel/random/boot_id', 128).decode('ascii').strip()

    def process(self, pid):
        try:
            raw = read(PROC/str(pid)/'stat', 8192)
        except FileNotFoundError:
            return None
        prefix, separator, tail = raw.rpartition(b') ')
        fields = tail.split()
        need(separator and prefix.startswith(f'{pid} ('.encode()) and len(fields) >= 20, 'PROC_STAT')
        return Proc(transaction.Process(pid, int(fields[19])), int(fields[1]), int(fields[2]), fields[0])

    def same_cgroup(self, pid):
        scoped = PROC/str(pid)
        return (read(scoped/'cgroup', 8192) == read(PROC/'self/cgroup', 8192)
                and os.readlink(scoped/'ns/cgroup') == os.readlink(PROC/'self/ns/cgroup'))

    def argv(self, pid):
        raw = read(PROC/str(pid)/'cmdline', 16 * 1024)
        need(raw.endswith(b'\0') and b'\0\0' not in raw, 'PROC_CMDLINE')
        return raw, raw[:-1].split(b'\0')

    def tagged(self, pid, name):
        env = read(PROC/str(pid)/'environ', 256 * 1024).split(b'\0')
        return ([item for item in env if item.startswith(b'SUPERVISOR_PROCESS_NAME=')]
                == [f'SUPERVISOR_PROCESS_NAME={name}'.encode()] and b'SUPERVISOR_ENABLED=1' in env
                and self.same_cgroup(pid))

    def table(self):
        pids = sorted(int(entry.name) for entry in PROC.iterdir() if entry.name.isascii() and entry.name.isdecimal())
        need(len(pids) <= MAX_PROC, 'PROCESS_CENSUS_BOUNDS')
        rows = (self.process(pid) for pid in pids)
        return {row.generation.pid: row for row in rows if row is not None}

    def _endpoint(self):
        ctx = self.context
        need(os.geteuid() == 0 and self.boot_id() == ctx.boot_id, 'BOOT_EPOCH')
        main = read(MAIN, 256 * 1024, rooted=True)
        need(digest(main) == ctx.main_config_sha256, 'MAIN_CONFIG_PIN')
        cfg = parse_config(main)
        server, client = cfg['unix_http_server'], cfg['supervisorctl']
        need(set(server) <= {'file', 'chmod', 'chown'} and set(client) == {'serverurl'}
             and int(server.get('chmod', '0700'), 8) == 0o700
             and server.get('chown', 'root:root') in ('root:root', '0:0')
             and client['serverurl'].startswith('unix:///')
             and not cfg.has_section('inet_http_server')
             and cfg['include']['files'] == str(INCLUDES/'*.conf')
             and cfg['rpcinterface:supervisor']['supervisor.rpcinterface_factory'] ==
                 'supervisor.rpcinterface:make_main_rpcinterface', 'ENDPOINT_CONFIG')
        path = socket_path(server['file'])
        need(path == ctx.socket_path == socket_path(client['serverurl'][7:]), 'SOCKET_PATH')
        info = path.lstat()
        need(stat.S_ISSOCK(info.st_mode) and info.st_uid == info.st_gid == 0
             and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o700, 'SOCKET_METADATA')
        row = self.process(ctx.supervisor.pid)
        need(row and row.generation == ctx.supervisor and row.ppid == 1 and row.state in RUNNABLE
             and self.same_cgroup(ctx.supervisor.pid), 'SUPERVISOR_GENERATION')
        _, argv = self.argv(ctx.supervisor.pid)
        daemon = [index for index, arg in enumerate(argv) if arg.startswith(b'/') and arg.endswith(b'/supervisord')]
        need(len(daemon) == 1 and argv[daemon[0]+1:] in ([b'-c', os.fsencode(MAIN)],
             [b'--configuration', os.fsencode(MAIN)]), 'SUPERVISOR_COMMAND')
        exe = (PROC/str(ctx.supervisor.pid)/'exe').stat()
        need(stat.S_ISREG(exe.st_mode) and exe.st_uid == exe.st_gid == 0 and not exe.st_mode & 0o022,
             'SUPERVISOR_EXECUTABLE')
        return stamp(info)

    def verify_service(self):
        self._endpoint()
        ctx = self.context
        configs = [MAIN, *sorted(INCLUDES.glob('*.conf'))]
        need(1 < len(configs) <= 97, 'INCLUDE_CENSUS')
        matches = []
        for path in configs:
            raw = read(path, 256 * 1024, rooted=True)
            config = parse_config(raw)
            for section in config.sections():
                kind, _, name = section.partition(':')
                if kind == 'group':
                    programs = {item.strip() for item in config[section]['programs'].split(',')}
                    need(DIRECTOR not in programs, 'DIRECTOR_GROUP')
                if name == DIRECTOR:
                    need(kind == 'program', 'DIRECTOR_SECTION')
                    matches.append((path, raw, config[section]))
        need(len(matches) == 1, 'DIRECTOR_SECTION_COUNT')
        path, raw, program = matches[0]
        need(path == INCLUDES/ctx.include and digest(raw) == ctx.include_sha256, 'DIRECTOR_CONFIG_PIN')
        # Named Supervisor stop has no generation-CAS. Exclude automatic replacement and
        # any unfenced lifecycle actor using the external exact owner authorization.
        need(program.get('autorestart', 'unexpected').lower() == 'false'
             and program.get('process_name', '%(program_name)s') == '%(program_name)s'
             and program.getint('numprocs', 1) == 1
             and program.get('stopsignal', 'TERM').upper() == 'TERM'
             and program.getboolean('stopasgroup', False) and program.getboolean('killasgroup', False)
             and 1 <= program.getint('stopwaitsecs', 10) <= 25, 'DIRECTOR_STOP_POLICY_UNPROVEN')
        argv = shlex.split(program['command'])
        need(len(argv) >= 2 and SAFE_PYTHON.fullmatch(argv[0]) and os.fspath(LAUNCHER) in argv
             and '%' not in program['command'] and digest(read(LAUNCHER, 2*1024*1024, rooted=True)) == ctx.launcher_sha256,
             'DIRECTOR_LAUNCHER')
        return tuple(os.fsencode(arg) for arg in argv)

    def verify_holder(self):
        ctx = self.context
        need(digest(read(ctx.holder_path, 2*1024*1024, rooted=True)) == ctx.holder_sha256,
             'HOLDER_SOURCE_PIN')

    def _rpc(self, method, params, preflight=None):
        ctx = self.context
        pin = self._endpoint()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel, ExitStack() as resources:
            channel.settimeout(30)
            channel.connect(os.fspath(ctx.socket_path))
            credentials = struct.unpack('3i', channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            need(credentials == (ctx.supervisor.pid, *ROOT_PEER_IDS), 'SUPERVISOR_PEER')
            peer = os.pidfd_open(ctx.supervisor.pid)
            resources.callback(os.close, peer)
            poll = select.poll()
            poll.register(peer, select.POLLIN)
            if preflight is not None:
                preflight()
            need(not poll.poll(0) and self._endpoint() == pin, 'SUPERVISOR_PEER_DRIFT')
            connection = http.client.HTTPConnection('localhost', timeout=30)
            resources.callback(connection.close)
            connection.sock = channel
            body = xmlrpc.client.dumps(params, methodname='supervisor.' + method).encode()
            connection.request('POST', '/RPC2', body, {'Content-Type': 'text/xml', 'Connection': 'close'})
            reply = connection.getresponse()
            need(reply.status == 200 and not reply.chunked and type(reply.length) is int
                 and 0 < reply.length <= MAX_RPC, 'RPC_REPLY')
            raw = reply.read()
            need(b'<!DOCTYPE' not in raw.upper() and b'<!ENTITY' not in raw.upper(), 'RPC_XML')
            values, _ = xmlrpc.client.loads(raw)
            need(len(values) == 1 and not poll.poll(0) and self._endpoint() == pin, 'RPC_PEER_DRIFT')
            return values[0]

    def program(self, name):
        need(name in {DIRECTOR, *SERVICES.values()}, 'RPC_PROGRAM_SCOPE')
        row = self._rpc('getProcessInfo', (name,))
        need(isinstance(row, dict) and (row.get('name'), row.get('group')) == (name, name)
             and type(row.get('pid')) is int, 'RPC_PROGRAM_IDENTITY')
        return row['statename'], row['pid']

    def control(self, operation, preflight):
        need(operation in ('stopProcess', 'startProcess') and callable(preflight), 'RPC_ACTION_SCOPE')
        return self._rpc(operation, (DIRECTOR, True), preflight)

    def model_healthy(self, process):
        # Require the exact model generation to own the actual IPv4 listen socket.
        lines = read(PROC/'net/tcp', 256*1024).decode('ascii').splitlines()[1:]
        port = f'{8098:04X}'
        listeners = [row[9] for line in lines if len(row := line.split()) >= 10 and row[3] == '0A'
                     and row[1] in (f'0100007F:{port}', f'00000000:{port}')]
        need(len(listeners) == 1 and listeners[0].isdecimal(), 'MODEL_LISTENER_SCOPE')
        entries = list((PROC/str(process.pid)/'fd').iterdir())
        need(len(entries) <= 2048, 'MODEL_FD_BOUNDS')
        tagged = False
        for entry in entries:
            try:
                tagged = tagged or os.readlink(entry) == f'socket:[{listeners[0]}]'
            except FileNotFoundError:
                continue
        need(tagged, 'MODEL_LISTENER_IDENTITY')
        with ExitStack() as resources:
            conn = http.client.HTTPConnection('127.0.0.1', 8098, timeout=3)
            resources.callback(conn.close)
            try:
                conn.request('GET', '/health', headers={'Connection': 'close'})
                response = conn.getresponse()
                raw = response.read(4097)
                health = len(raw) <= 4096 and response.status == 200 and json.loads(raw).get('status') == 'ok'
            except (OSError, ValueError, AttributeError, http.client.HTTPException):
                return False
        row = self.process(process.pid)
        return bool(health and row and row.generation == process and row.state in RUNNABLE)


class NativeSupervisorDriver:
    """One authenticated epoch for the dispatcher transaction and its rollback."""

    def __init__(self, context, authorize, *, host=None):
        need(isinstance(context, Context) and callable(authorize), 'EXTERNAL_AUTH_REQUIRED')
        context.validate()
        self.context = context
        self.authorize = authorize
        self.host = SupervisorHost(context) if host is None else host
        self._phase = 'PRESTOP'
        self._owned = None
        self._retiring = None
        self._used = {context.director}

    def _allow(self, action):
        self.context.validate()
        need(self.authorize(self.context, action) is True, 'EXTERNAL_AUTH_REQUIRED')
        need(self.host.boot_id() == self.context.boot_id, 'BOOT_EPOCH')

    def validate_transaction(self, root, spec, boot_id, request_id):
        self._allow('transaction')
        need(root == ROOT and boot_id == self.context.boot_id and request_id == self.context.request_id
             and files.digest(files.encoded(spec)) == self.context.bundle_sha256, 'TRANSACTION_BINDING')

    def _by_name(self, name, expected=None):
        state, pid = self.host.program(name)
        if state == 'STOPPED':
            need(pid == 0 and expected is None, 'NAMED_STOPPED_IDENTITY')
            return state, None
        if state in ('STARTING', 'STOPPING') and expected is None and name == DIRECTOR:
            return state, None
        need(state == 'RUNNING' and pid > 1, 'NAMED_STATE_UNCERTAIN')
        row = self.host.process(pid)
        need(row and row.state in RUNNABLE and row.ppid == self.context.supervisor.pid
             and row.pgrp == pid and (expected is None or row.generation == expected)
             and self.host.tagged(pid, name), 'NAMED_GENERATION')
        return state, row.generation

    def _command(self, director):
        configured = self.host.verify_service()
        raw, argv = self.host.argv(director.pid)
        need(digest(raw) == self.context.director_cmdline_sha256 and tuple(argv) == configured
             and os.fsencode(LAUNCHER) in argv, 'COMMAND_GENERATION')

    def _protected(self, *, probe=True):
        expected = dict(self.context.protected)
        for label, service in SERVICES.items():
            self._by_name(service, expected[label])
        holder = expected['engram_holder']
        row = self.host.process(holder.pid)
        need(row and row.generation == holder and row.state in RUNNABLE
             and self.host.same_cgroup(holder.pid), 'HOLDER_GENERATION')
        raw, argv = self.host.argv(holder.pid)
        need(digest(raw) == self.context.holder_cmdline_sha256
             and os.fsencode(self.context.holder_path) in argv, 'HOLDER_COMMAND')
        self.host.verify_holder()
        health = self.host.model_healthy(expected['model']) if probe else False
        return expected, health

    def _children(self, director):
        rows = self.host.table()
        root = rows.get(director.pid)
        need(root and root.generation == director and root.state in RUNNABLE, 'CHILD_ANCESTOR')
        descendants = {director.pid}
        while True:
            expanded = descendants | {pid for pid, row in rows.items() if row.ppid in descendants}
            need(len(expanded) <= 64, 'CHILD_SCOPE_BOUND')
            if expanded == descendants:
                break
            descendants = expanded
        members = {pid for pid, row in rows.items() if row.pgrp == director.pid}
        need(members == descendants, 'CHILD_GROUP_SCOPE')
        children = frozenset(rows[pid].generation for pid in descendants - {director.pid})
        if director == self.context.director:
            need(children == frozenset(self.context.children), 'ORIGINAL_CHILDREN_UNPROVEN')
        protected = {item.pid for _, item in self.context.protected}
        need(not protected & members and self.context.supervisor.pid not in members, 'CHILD_PROTECTED_PROCESS')
        for child in children:
            row = self.host.process(child.pid)
            need(row == rows[child.pid] and row.state in RUNNABLE and self.host.tagged(child.pid, DIRECTOR),
                 'CHILD_GENERATION')
        return children

    def verify_worker_generations(self, director, expected):
        self._allow('observe')
        need(len(expected) == 6 and len(set(expected)) == 6, 'FORSAZH_WORKER_COUNT')
        need(set(expected) <= self._children(director), 'FORSAZH_CHILD_SCOPE')
        for generation in expected:
            row = self.host.process(generation.pid)
            need(row and row.generation == generation and row.ppid == director.pid
                 and row.state in RUNNABLE, 'FORSAZH_WORKER_GENERATION')
        return True

    def _retired(self):
        if self._retiring is None:
            return True
        director, children = self._retiring
        rows = self.host.table()
        former = children | {director}
        # Even a reparented process blocks progress until its exact generation disappears.
        released = all(row.generation not in former and row.pgrp != director.pid for row in rows.values())
        if released:
            self._retiring = None
        return released

    def observe(self):
        self._allow('observe')
        self.host.verify_service()
        state, director = self._by_name(DIRECTOR)
        if state == 'RUNNING':
            expected = self.context.director if self._phase == 'PRESTOP' else self._owned
            need(director == expected and self._retiring is None, 'DIRECTOR_GENERATION_UNBOUND')
            self._command(director)
        elif state == 'STOPPED':
            need(self._retired(), 'OLD_CHILDREN_EXIT_UNPROVEN')
        protected, health = self._protected()
        return transaction.Observation(True, self.context.boot_id, time.time(), state, director, protected, health)

    def stop(self, expected, *, check, rollback=False):
        action = 'rollback_stop' if rollback else 'stop'
        need(self._phase == ('ACTIVE' if rollback else 'PRESTOP')
             and expected == (self._owned if rollback else self.context.director), 'STOP_GENERATION_SCOPE')
        captured = None

        def before_rpc():
            nonlocal captured
            check(stop_clear=not rollback)
            self._allow(action)
            self._by_name(DIRECTOR, expected)
            self._command(expected)
            captured = self._children(expected)
            _, health = self._protected(probe=not rollback)
            need(rollback or health, 'STOP_MODEL_HEALTH')
            check(stop_clear=not rollback)
            need(self._children(expected) == captured and self._by_name(DIRECTOR, expected)[1] == expected,
                 'STOP_PREFLIGHT_PROCESS_DRIFT')
            self._allow(action)
            check(stop_clear=not rollback)
            self._retiring = expected, captured

        # An uncertain send/result licenses readback only. No second named stop.
        response = self.host.control('stopProcess', before_rpc)
        need(response is True and captured is not None, 'STOP_RPC_UNVERIFIED')
        deadline = time.monotonic() + WAIT_STOP_SECONDS
        while True:
            state, director = self._by_name(DIRECTOR)
            if state == 'STOPPED' and self._retired():
                self._phase = 'STOPPED'
                self._owned = None
                return
            need(director in (expected, None) and time.monotonic() < deadline, 'OLD_CHILDREN_EXIT_UNPROVEN')
            time.sleep(0.25)

    def start(self, *, check, rollback=False):
        action = 'rollback_start' if rollback else 'start'
        need(self._phase == 'STOPPED' and self._retired(), 'START_PRIOR_EXIT_UNPROVEN')
        entered = False

        def before_rpc():
            nonlocal entered
            check()
            self._allow(action)
            self.host.verify_service()
            _, health = self._protected()
            need(health, 'START_MODEL_HEALTH')
            check()
            need(self._by_name(DIRECTOR) == ('STOPPED', None) and self._retired(), 'START_PREFLIGHT_DRIFT')
            self._allow(action)
            check()
            self._phase = 'UNVERIFIED_START'
            entered = True

        response = self.host.control('startProcess', before_rpc)
        need(response is True and entered, 'START_RPC_UNVERIFIED')
        deadline = time.monotonic() + WAIT_START_SECONDS
        while True:
            state, director = self._by_name(DIRECTOR)
            if state == 'RUNNING':
                need(director not in self._used and director.start_ticks > self.context.director.start_ticks
                     and director.pid not in {item.pid for _, item in self.context.protected}, 'START_GENERATION_REUSED')
                self._command(director)
                need(self._by_name(DIRECTOR, director)[1] == director, 'START_GENERATION_CHANGED')
                self._used.add(director)
                self._owned = director
                self._phase = 'ACTIVE'
                return director
            need(state == 'STARTING' and time.monotonic() < deadline, 'START_GENERATION_UNPROVEN')
            time.sleep(0.25)
