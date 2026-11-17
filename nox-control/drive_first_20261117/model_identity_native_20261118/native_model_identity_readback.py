"""Bounded, generation-free identity readback for the existing owner audit.

Call observe() while holding the already-existing maintenance lease. No module
executes on import. Exactly five reviewed sources, two fixed JSON snapshots,
one fixed model process and its IPv4 listener may be read. The sole HTTP route
is the source-established GET /health at the already observed port 8098.

The result proves only a current process's model-file reference. It does not
identify weight contents, architecture, training history, context capacity or
the backend used by a previous chat request. No /props route is assumed.
"""
from __future__ import annotations

import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import stat
import time

import model_identity_projection as projection

ROOT = Path('/root/nox')
PROC = Path('/proc')
OWNER_UID = 0
PINNED_PID = 3266857
PINNED_PORT = 8098
PROCESS_PIN = {
    'start_ticks': 172046662, 'ppid': 114,
    'argv_sha256': '88bc6d7a0ed91c5363a7129514e354983e7285f8c13bcd00e84c3649192b56e4',
    'exe_path_sha256': '4b67e9230f074d14e7f16587f6f9adbb2c7f094a0556d313b55ee320c0091815',
    'cwd_sha256': '5ac55c8ee49f44fbeb36ae4536b880b5db18275d00d087bf23c7e6e7a81a143b',
}
LOCK_PIN = {'dev': 36, 'ino': 59886214}
MAX_READ = 2 * 1024 * 1024
MAX_SECONDS = 15.0
MAX_FDS = 512
MAX_TCP_SCAN = 262144
MAX_TCP_ROWS = 4096
MAX_TCP_LINE = 1024
MAX_OUTPUT = 32768


class Hold(Exception):
    pass


def require(condition, code):
    if not condition:
        raise Hold(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf8')


def ident(value):
    return (value.st_dev, value.st_ino, value.st_uid, value.st_gid,
            value.st_mode, value.st_nlink, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def dir_ident(value):
    return (value.st_dev, value.st_ino, value.st_uid, value.st_gid, value.st_mode)


def metadata(value, raw):
    return {'dev': value.st_dev, 'ino': value.st_ino, 'uid': value.st_uid,
            'gid': value.st_gid, 'mode': oct(stat.S_IMODE(value.st_mode)),
            'bytes': len(raw), 'mtime_ns': value.st_mtime_ns, 'sha256': sha(raw)}


class Reader:
    def __init__(self):
        self.total = 0
        self.attempts = 0
        self.deadline = time.monotonic() + MAX_SECONDS

    def check(self):
        require(time.monotonic() <= self.deadline, 'HOLD_COOPERATIVE_DEADLINE')
        require(self.total <= MAX_READ and self.attempts <= 250, 'HOLD_READ_BUDGET')

    def read_fd(self, fd, maximum):
        self.check()
        self.attempts += 1
        parts, size = [], 0
        while True:
            self.check()
            remaining = MAX_READ - self.total
            require(remaining > 0, 'HOLD_READ_BUDGET')
            chunk = os.read(fd, min(16384, maximum + 1 - size, remaining))
            if not chunk:
                break
            self.total += len(chunk)
            size += len(chunk)
            require(size <= maximum, 'HOLD_FILE_BYTES')
            parts.append(chunk)
        self.check()
        return b''.join(parts)

    def directory(self, path):
        """Return opened chain; retain and verify every named parent identity."""
        require(path.is_absolute() and '..' not in path.parts, 'HOLD_PATH_SCOPE')
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        opened = []
        try:
            fd = os.open('/', flags)
            opened.append((fd, None, None, os.fstat(fd)))
            for part in path.parts[1:]:
                self.check()
                require(part not in {'', '.', '..'}, 'HOLD_PATH_COMPONENT')
                parent = fd
                fd = os.open(part, flags, dir_fd=parent)
                opened.append((fd, parent, part, os.fstat(fd)))
            for _, _, _, value in opened:
                require(stat.S_ISDIR(value.st_mode) and value.st_uid in {0, OWNER_UID},
                        'HOLD_ROOT_DIRECTORY_OWNER_OR_TYPE')
            self.verify_dirs(opened)
            return opened
        except BaseException:
            self.close_dirs(opened)
            raise

    @staticmethod
    def close_dirs(opened):
        for fd, _, _, _ in reversed(opened):
            os.close(fd)

    @staticmethod
    def verify_dirs(opened):
        for fd, parent, name, before in opened:
            require(dir_ident(os.fstat(fd)) == dir_ident(before), 'HOLD_DIRECTORY_IDENTITY_DRIFT')
            if parent is not None:
                named = os.stat(name, dir_fd=parent, follow_symlinks=False)
                require(dir_ident(named) == dir_ident(before), 'HOLD_DIRECTORY_NAMED_DRIFT')

    def file(self, path, maximum):
        require(path.is_absolute() and '..' not in path.parts, 'HOLD_PATH_SCOPE')
        opened = self.directory(path.parent)
        fd = None
        try:
            parent = opened[-1][0]
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                         dir_fd=parent)
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid == OWNER_UID
                    and before.st_nlink == 1 and before.st_size <= maximum,
                    'HOLD_FILE_OWNER_TYPE_OR_BOUND')
            require(ident(before) == ident(os.stat(path.name, dir_fd=parent, follow_symlinks=False)),
                    'HOLD_FILE_NAMED_DRIFT')
            raw = self.read_fd(fd, maximum)
            require(len(raw) == before.st_size and ident(os.fstat(fd)) == ident(before)
                    and ident(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) == ident(before),
                    'HOLD_FILE_CHANGED')
            self.verify_dirs(opened)
            return raw, metadata(before, raw)
        finally:
            if fd is not None:
                os.close(fd)
            self.close_dirs(opened)


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'HOLD_IDENTITY_JSON_DUPLICATE')
            result[key] = value
        return result
    def nonfinite(_):
        raise Hold('HOLD_IDENTITY_JSON_NONFINITE')
    value = json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)
    require(type(value) is dict, 'HOLD_IDENTITY_JSON_OBJECT')
    return value


def proc_read(reader, relative, maximum):
    allowed = {'stat': 8192, 'cmdline': 32768, 'status': 16384}
    require(relative in allowed and maximum == allowed[relative], 'HOLD_IDENTITY_PROC_SCOPE')
    path = PROC / str(PINNED_PID) / relative
    opened = reader.directory(path.parent)
    fd = None
    try:
        parent = opened[-1][0]
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                     dir_fd=parent)
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == OWNER_UID,
                'HOLD_IDENTITY_PROC_FILE')
        raw = reader.read_fd(fd, maximum)
        # proc files often have size zero. Their content is validated separately.
        require(dir_ident(os.fstat(fd)) == dir_ident(before), 'HOLD_IDENTITY_PROC_DRIFT')
        reader.verify_dirs(opened)
        return raw
    finally:
        if fd is not None:
            os.close(fd)
        reader.close_dirs(opened)


def bounded_link(path):
    value = os.readlink(path)
    require(len(value.encode('utf8')) <= 4096 and not value.endswith(' (deleted)'),
            'HOLD_IDENTITY_LINK_BOUND')
    return value


def lifetime(raw):
    fields = raw.decode('ascii').rsplit(') ', 1)[1].split()
    return {'state': fields[0], 'ppid': int(fields[1]), 'start_ticks': int(fields[19])}


def model_process(reader):
    before = lifetime(proc_read(reader, 'stat', 8192))
    require(before['state'] not in {'Z', 'X'}
            and before['ppid'] == PROCESS_PIN['ppid']
            and before['start_ticks'] == PROCESS_PIN['start_ticks'],
            'HOLD_IDENTITY_PROCESS_LIFETIME')
    raw = proc_read(reader, 'cmdline', 32768)
    require(raw.endswith(b'\0') and sha(raw) == PROCESS_PIN['argv_sha256'],
            'HOLD_IDENTITY_PROCESS_ARGV')
    argv = raw[:-1].decode('utf8', 'strict').split('\0')
    require(0 < len(argv) <= 96 and all(argv), 'HOLD_IDENTITY_PROCESS_ARGV_SHAPE')
    exe = bounded_link(PROC / str(PINNED_PID) / 'exe')
    cwd = bounded_link(PROC / str(PINNED_PID) / 'cwd')
    require(sha(exe.encode()) == PROCESS_PIN['exe_path_sha256']
            and sha(cwd.encode()) == PROCESS_PIN['cwd_sha256'], 'HOLD_IDENTITY_PROCESS_EXE_CWD')
    uid = re.findall(rb'^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$',
                     proc_read(reader, 'status', 16384), re.M)
    require(len(uid) == 1 and all(int(value) == OWNER_UID for value in uid[0]),
            'HOLD_IDENTITY_PROCESS_UID')
    after = lifetime(proc_read(reader, 'stat', 8192))
    require(after['state'] not in {'Z', 'X'} and after['start_ticks'] == before['start_ticks']
            and after['ppid'] == before['ppid']
            and sha(proc_read(reader, 'cmdline', 32768)) == PROCESS_PIN['argv_sha256']
            and bounded_link(PROC / str(PINNED_PID) / 'exe') == exe
            and bounded_link(PROC / str(PINNED_PID) / 'cwd') == cwd,
            'HOLD_IDENTITY_PROCESS_CHANGED')
    return {'pid': PINNED_PID, **PROCESS_PIN, 'uid': OWNER_UID,
            'argv_exported': False, 'environment_read': False}, argv


def owned_ipv4_listener_row(raw, owned_inodes):
    fields = raw.decode('ascii', 'strict').split()
    require(len(fields) >= 10 and re.fullmatch(r'[0-9A-Fa-f]{8}:[0-9A-Fa-f]{4}', fields[1])
            and re.fullmatch(r'[0-9A-Fa-f]{2}', fields[3])
            and fields[7].isdigit() and fields[9].isdigit(), 'HOLD_IDENTITY_TCP_ROW')
    address, raw_port = fields[1].upper().split(':')
    inode = int(fields[9])
    if (inode in owned_inodes and inode > 0 and fields[3].upper() == '0A'
            and int(raw_port, 16) == PINNED_PORT and address in {'0100007F', '00000000'}):
        require(int(fields[7]) == OWNER_UID, 'HOLD_IDENTITY_SOCKET_UID')
        return {'socket_inode': inode, 'uid': int(fields[7]), 'port': PINNED_PORT,
                'address': '127.0.0.1' if address == '0100007F' else '0.0.0.0'}
    return None


def owned_tcp_listener(reader, owned_inodes):
    """Stop at a matching owned row; never require an unrelated table's EOF."""
    opened = reader.directory(PROC / str(PINNED_PID) / 'net')
    fd = None
    try:
        fd = os.open('tcp', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                     dir_fd=opened[-1][0])
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == OWNER_UID,
                'HOLD_IDENTITY_PROC_FILE')
        reader.attempts += 1
        scanned = rows = 0
        pending = b''
        header = False
        while scanned < MAX_TCP_SCAN and rows < MAX_TCP_ROWS:
            reader.check()
            remaining = min(MAX_TCP_SCAN - scanned, MAX_READ - reader.total)
            require(remaining > 0, 'HOLD_READ_BUDGET')
            chunk = os.read(fd, min(4096, remaining))
            scanned += len(chunk); reader.total += len(chunk)
            if not chunk:
                require(not pending, 'HOLD_IDENTITY_TCP_PARTIAL_LINE')
                break
            pending += chunk
            while b'\n' in pending:
                line, pending = pending.split(b'\n', 1)
                require(len(line) <= MAX_TCP_LINE, 'HOLD_IDENTITY_TCP_LINE_BOUND')
                if not header:
                    require(b'local_address' in line, 'HOLD_IDENTITY_TCP_SCHEMA')
                    header = True
                    continue
                rows += 1
                require(rows <= MAX_TCP_ROWS, 'HOLD_IDENTITY_TCP_ROW_BOUND')
                row = owned_ipv4_listener_row(line, owned_inodes)
                if row is not None:
                    require(dir_ident(os.fstat(fd)) == dir_ident(before), 'HOLD_IDENTITY_PROC_DRIFT')
                    reader.verify_dirs(opened)
                    reader.check()
                    return {**row, 'table_scan': {'bytes_read': scanned, 'rows_checked': rows,
                            'stopped_at_owned_listener': True, 'table_eof_required': False,
                            'maximum_bytes': MAX_TCP_SCAN, 'maximum_rows': MAX_TCP_ROWS}}
            require(len(pending) <= MAX_TCP_LINE, 'HOLD_IDENTITY_TCP_LINE_BOUND')
        raise Hold('HOLD_IDENTITY_OWNED_LISTENER_NOT_OBSERVED_WITHIN_BOUND')
    finally:
        if fd is not None:
            os.close(fd)
        reader.close_dirs(opened)


def listener(reader):
    process_ns = bounded_link(PROC / str(PINNED_PID) / 'ns/net')
    self_ns = bounded_link(PROC / 'self/ns/net')
    require(re.fullmatch(r'net:\[[0-9]{1,24}\]', process_ns) and process_ns == self_ns,
            'HOLD_IDENTITY_NETWORK_NAMESPACE')
    opened = reader.directory(PROC / str(PINNED_PID) / 'fd')
    owned = {}
    try:
        fd = opened[-1][0]
        with os.scandir(fd) as entries:
            for count, entry in enumerate(entries, 1):
                reader.check()
                require(count <= MAX_FDS and re.fullmatch(r'[0-9]{1,8}', entry.name),
                        'HOLD_IDENTITY_FD_BOUND')
                try:
                    value = os.readlink(entry.name, dir_fd=fd)
                except FileNotFoundError:
                    continue  # Unrelated descriptor churn is not listener evidence.
                require(len(value.encode()) <= 4096, 'HOLD_IDENTITY_FD_LINK_BOUND')
                matched = re.fullmatch(r'socket:\[([0-9]{1,24})\]', value)
                if matched:
                    owned.setdefault(int(matched[1]), []).append(int(entry.name))
        require(bool(owned), 'HOLD_IDENTITY_NO_OWNED_SOCKETS')
        row = owned_tcp_listener(reader, set(owned))
        found = owned[row['socket_inode']]
        for number in found:
            require(os.readlink(str(number), dir_fd=fd) == 'socket:[' + str(row['socket_inode']) + ']',
                    'HOLD_IDENTITY_SOCKET_CHANGED')
        reader.verify_dirs(opened)
    finally:
        reader.close_dirs(opened)
    require(bounded_link(PROC / str(PINNED_PID) / 'ns/net') == process_ns
            and bounded_link(PROC / 'self/ns/net') == self_ns,
            'HOLD_IDENTITY_NETWORK_NAMESPACE_CHANGED')
    return {**row, 'pid': PINNED_PID, 'start_ticks': PROCESS_PIN['start_ticks'],
            'file_descriptors': sorted(found), 'same_network_namespace': True,
            'network_namespace_sha256': sha(process_ns.encode()),
            'table_scope': 'BOUNDED_PREFIX_UNTIL_FIXED_PID_OWNED_IPV4_LISTENER',
            'global_listener_uniqueness_proven': False,
            'atomic_binding': False}


def lease(reader, fd):
    require(type(fd) is int and fd >= 0 and os.geteuid() == OWNER_UID, 'HOLD_IDENTITY_LEASE_REQUIRED')
    opened = reader.directory(ROOT / 'state')
    try:
        bound = os.fstat(fd)
        named = os.stat('owner_maintenance.lock', dir_fd=opened[-1][0], follow_symlinks=False)
        require(stat.S_ISREG(bound.st_mode) and bound.st_uid == OWNER_UID
                and not bound.st_mode & 0o022 and dir_ident(bound) == dir_ident(named)
                and {'dev': bound.st_dev, 'ino': bound.st_ino} == LOCK_PIN,
                'HOLD_IDENTITY_LEASE_PIN')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        reader.verify_dirs(opened)
    finally:
        reader.close_dirs(opened)


def health(reader):
    reader.check()
    connection = http.client.HTTPConnection('127.0.0.1', PINNED_PORT,
        timeout=min(0.8, max(0.001, reader.deadline - time.monotonic())))
    try:
        connection.request('GET', '/health', headers={'Accept': 'application/json', 'Accept-Encoding': 'identity'})
        response = connection.getresponse()
        raw = response.read(65537)
        identity = response.getheader('Content-Encoding', 'identity').lower() in {'', 'identity'}
        if len(raw) > 65536 or not identity:
            return {'complete': False, 'healthy_by_source_rule': None,
                    'reason': 'BOUNDED_RESPONSE_OR_ENCODING', 'response_body_exported': False}
        return {**projection.health_projection(response.status, raw), 'response_body_exported': False}
    except (OSError, http.client.HTTPException):
        return {'complete': False, 'healthy_by_source_rule': None,
                'reason': 'NETWORK_UNAVAILABLE', 'response_body_exported': False}
    finally:
        connection.close()


def observe(owner_request, source_sha, *, maintenance_lock_fd):
    reader = Reader()
    report = {'schema': 'NOX_BOUND_MODEL_REFERENCE_READBACK_V1', 'owner_request': owner_request,
              'source_sha': source_sha, 'observed_at': int(time.time()), 'status': 'HOLD_NOT_COMPLETED',
              'model_requests': 0, 'http_gets': 0, 'http_posts': 0, 'external_requests': 0,
              'application_imports': 0, 'file_writes': 0, 'env_reads': 0, 'key_reads': 0,
              'service_mutations': 0, 'full_argv_exported': False, 'raw_config_exported': False,
              'listener_model_reference_verified': False, 'weight_content_identity_verified': False,
              'architecture_or_training_identity_verified': False, 'last_chat_backend_identified': False,
              'atomic_snapshot': False, 'fallback_8085_observed': False, 'props_endpoint_assumed': False}
    try:
        require(type(owner_request) is str and re.fullmatch('[0-9]{1,24}', owner_request)
                and type(source_sha) is str and re.fullmatch('[a-f0-9]{40}', source_sha),
                'HOLD_IDENTITY_OWNER_CONTEXT')
        lease(reader, maintenance_lock_fd)
        sources, source_meta = {}, {}
        for name in projection.SOURCE_PINS:
            raw, info = reader.file(ROOT / 'scripts' / name, 262144)
            sources[name] = raw; source_meta[name] = info
        report['source_contract'] = projection.source_contract(sources)
        report['source_readback'] = source_meta
        status_raw, status_meta = reader.file(ROOT / 'status/status.json', 131072)
        backend_raw, backend_meta = reader.file(ROOT / 'config/backend.json', 65536)
        report['disk_status'] = {'projection': projection.status_projection(strict_json(status_raw)),
                                'readback': status_meta, 'origin': 'FIXED_DISK_SNAPSHOT',
                                'age_seconds': round(time.time() - status_meta['mtime_ns'] / 1e9, 3),
                                'api_status_sampled': False}
        plan = projection.backend_probe_plan(strict_json(backend_raw))
        report['backend'] = {'projection': plan, 'readback': backend_meta}
        process_before, argv = model_process(reader)
        report['process'] = process_before
        # Useful current process-reference evidence survives a later listener
        # HOLD. Its separate listener binding flag stays false until final proof.
        report['argv_projection'] = projection.model_argv_projection(argv)
        argv = None
        binding = listener(reader)
        report['listener'] = binding
        require(plan['port'] == PINNED_PORT, 'HOLD_IDENTITY_CONFIGURED_PORT_NOT_PINNED_LISTENER')
        require(plan['host'] == '127.0.0.1', 'HOLD_IDENTITY_LOCALHOST_RESOLUTION_NOT_OBSERVED')
        report['http_gets'] = 1
        report['health'] = health(reader)
        process_after, _ = model_process(reader)
        binding_after = listener(reader)
        identity_fields = ('socket_inode', 'uid', 'port', 'address', 'pid', 'start_ticks',
                           'file_descriptors', 'network_namespace_sha256', 'same_network_namespace')
        require(process_before == process_after
                and all(binding_after[key] == binding[key] for key in identity_fields),
                'HOLD_IDENTITY_BINDING_CHANGED')
        report['listener']['table_scan_after'] = binding_after['table_scan']
        for name, before in source_meta.items():
            _, info = reader.file(ROOT / 'scripts' / name, 262144)
            require(info == before, 'HOLD_IDENTITY_SOURCE_CHANGED')
        # The status file is an independently timed disk snapshot; periodic
        # status updates do not invalidate this exact read's provenance.
        _, backend_after = reader.file(ROOT / 'config/backend.json', 65536)
        require(backend_after == backend_meta, 'HOLD_IDENTITY_BACKEND_CHANGED')
        lease(reader, maintenance_lock_fd)
        reader.check()
        report['argv_projection']['listener_process_binding_verified'] = True
        report['listener_model_reference_verified'] = 'model_basename' in report['argv_projection']['model_argument']
        report['configured_primary_healthy_by_source_rule'] = report['health'].get('healthy_by_source_rule')
        report['status'] = 'BOUNDED_LISTENER_MODEL_REFERENCE_SNAPSHOT'
        report['evidence_scope'] = 'CURRENT_PINNED_PRIMARY_LISTENER_ARGV_REFERENCE_ONLY'
    except (Hold, ValueError) as exc:
        text = str(exc)
        report['status'] = text if re.fullmatch(r'HOLD_[A-Z0-9_]{1,100}(?::[A-Za-z0-9_.]{1,80})?', text) else 'HOLD_IDENTITY_VALUE'
    except (OSError, UnicodeError, TypeError, KeyError, IndexError, RecursionError, http.client.HTTPException):
        report['status'] = 'HOLD_IDENTITY_READ_OR_SCHEMA'
    report['bytes_read'] = reader.total
    report['read_attempts'] = reader.attempts
    report['elapsed_seconds'] = round(MAX_SECONDS - (reader.deadline - time.monotonic()), 3)
    if len(canonical(report)) > MAX_OUTPUT:
        return {'schema': report['schema'], 'status': 'HOLD_IDENTITY_OUTPUT_BOUND',
                'listener_model_reference_verified': False, 'model_requests': 0, 'file_writes': 0}
    return report
