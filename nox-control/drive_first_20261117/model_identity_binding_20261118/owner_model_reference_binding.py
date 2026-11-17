"""Small, read-only model-reference binding for a standalone owner question.

The accepted audit is provenance, not a timeless assertion. Every matching turn
rechecks its process lifetime, argv hash, namespaces and owned listening socket.
No network, credentials, environment, model file or application import is read.
The model still writes the answer through the existing owner SSE implementation.
This module bounds prompt bytes; it makes no exact tokenizer/window claim.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

SNAPSHOT = Path('/root/nox/state/verified_model_reference.json')
PROC = Path('/proc')
OWNER_UID = 0
PRIMARY_URL = 'http://127.0.0.1:8098/v1/chat/completions'
FALLBACK_URL = 'http://127.0.0.1:8085/v1/chat/completions'
CONTRACT = 'NOX VERIFIED SELF-MODEL CONTRACT:'
MAX_SNAPSHOT = 8192
MAX_TCP = 262144
MAX_TCP_ROWS = 4096
MAX_TCP_LINE = 1024
MAX_READ_BYTES = 700000
MAX_SECONDS = 0.25  # cooperative bound on fixed, nonblocking local reads
MAX_QUESTION_BYTES = 640
MAX_PREFIX_BYTES = 6144
MAX_FACT_BYTES = 1536
MAX_CONTEXT_BYTES = 8192

# Full matches only. Compound instructions, quotations, examples, comparison
# requests and ordinary conversations remain in the existing owner tool loop.
_RU = (
    r'(?:какая\s+(?:(?:у\s+тебя|твоя|ты)\s+)?(?:(?:базовая|основная|текущая)\s+)?модель'
    r'(?:\s+(?:у\s+тебя|в\s+твоей\s+основе(?:\s+сейчас)?|сейчас\s+(?:отвечает|работает)|ты))?'
    r'|на\s+какой\s+модели\s+ты\s+(?:работаешь|основан|основана)'
    r'|какой\s+(?:gguf|gguf-файл)\s+(?:у\s+тебя|ты\s+используешь)(?:\s+сейчас)?'
    r'|(?:назови|уточни)\s+(?:свою|твою)\s+(?:(?:базовую|текущую)\s+)?модель)'
)
_EN = (
    r'(?:what\s+model\s+are\s+you(?:\s+(?:running|using))?'
    r'|which\s+model\s+are\s+you\s+(?:running|using)'
    r'|what\s+is\s+your\s+(?:(?:base|current|underlying)\s+)?model'
    r'|what\s+model\s+is\s+answering(?:\s+(?:now|right\s+now))?)'
)
_IDENTITY = re.compile(
    r'(?:(?:nox|нокс)\s*[, :]\s*)?(?:(?:скажи|скажи\s+пожалуйста|please\s+tell\s+me)\s*[, :]?\s*)?'
    r'(?:' + _RU + r'|' + _EN + r')(?:\s*[, ]\s*(?:пожалуйста|please))?\s*[?.!]*', re.I)


class ReferenceUnavailable(RuntimeError):
    """A fixed, non-sensitive reason, suitable for a bounded model context."""


def require(value, code):
    if not value:
        raise ReferenceUnavailable(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def model_identity_query(text):
    if not isinstance(text, str) or not 1 <= len(text) <= 240:
        return False
    if len(text.encode('utf8')) > MAX_QUESTION_BYTES or any(c in text for c in '\n\r`"«»;'):
        return False
    return _IDENTITY.fullmatch(text.strip()) is not None


def _json(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'SNAPSHOT_DUPLICATE_KEY')
            value[key] = item
        return value
    def nonfinite(_):
        raise ReferenceUnavailable('SNAPSHOT_NONFINITE')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


def _object(value, keys):
    require(type(value) is dict and set(value) == set(keys.split()), 'SNAPSHOT_SCHEMA')


def _integer(value, minimum=1, maximum=2**63-1):
    require(type(value) is int and minimum <= value <= maximum, 'SNAPSHOT_INTEGER')


def validate_snapshot(value, now):
    _object(value, 'schema evidence route process listener model_reference scope')
    require(value['schema'] == 'NOX_VERIFIED_MODEL_REFERENCE_V1'
            and value['scope'] == 'CURRENT_LISTENER_ARGV_REFERENCE_ONLY', 'SNAPSHOT_SCHEMA')
    evidence, route = value['evidence'], value['route']
    _object(evidence, 'run request source_sha raw_sha256 observed_at')
    require(all(isinstance(evidence[k], str) and re.fullmatch(r'[0-9]{1,20}', evidence[k])
                for k in ('run', 'request')), 'SNAPSHOT_PROVENANCE')
    require(isinstance(evidence['source_sha'], str) and re.fullmatch(r'[0-9a-f]{40}', evidence['source_sha'])
            and isinstance(evidence['raw_sha256'], str) and re.fullmatch(r'[0-9a-f]{64}', evidence['raw_sha256']),
            'SNAPSHOT_PROVENANCE')
    _integer(evidence['observed_at'])
    require(evidence['observed_at'] <= now + 5, 'SNAPSHOT_FUTURE')
    _object(route, 'host port path')
    require(route == {'host': '127.0.0.1', 'port': 8098, 'path': '/v1/chat/completions'}, 'SNAPSHOT_ROUTE')
    process, listener = value['process'], value['listener']
    _object(process, 'pid start_ticks ppid uid argv_sha256 exe_path_sha256 cwd_sha256')
    for key in ('pid', 'start_ticks', 'ppid'):
        _integer(process[key])
    require(process['uid'] == OWNER_UID and type(process['uid']) is int, 'SNAPSHOT_UID')
    _object(listener, 'fd socket_inode network_namespace_sha256 address')
    _integer(listener['fd'], 0, 1048575)
    _integer(listener['socket_inode'])
    require(listener['address'] in ('0.0.0.0', '127.0.0.1'), 'SNAPSHOT_ADDRESS')
    reference = value['model_reference']
    _object(reference, 'basename argument_sha256')
    require(isinstance(reference['basename'], str)
            and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+\-]{0,174}\.gguf', reference['basename']),
            'SNAPSHOT_REFERENCE')
    for digest in [process[k] for k in ('argv_sha256', 'exe_path_sha256', 'cwd_sha256')] + [
            listener['network_namespace_sha256'], reference['argument_sha256']]:
        require(isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest), 'SNAPSHOT_DIGEST')
    return value


def _identity(value):
    return (value.st_dev, value.st_ino, value.st_uid, value.st_gid, value.st_mode,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def _dir_identity(value):
    return (value.st_dev, value.st_ino, value.st_uid, value.st_gid, value.st_mode)


class _Reader:
    def __init__(self):
        self.deadline = time.monotonic() + MAX_SECONDS
        self.bytes = 0

    def check(self):
        require(time.monotonic() <= self.deadline, 'READBACK_DEADLINE')
        require(self.bytes <= MAX_READ_BYTES, 'READBACK_BYTE_BOUND')

    @contextmanager
    def directory(self, path):
        require(path.is_absolute() and '..' not in path.parts, 'READBACK_PATH')
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        opened = []
        try:
            fd = os.open('/', flags)
            opened.append((fd, None, None, os.fstat(fd)))
            for name in path.parts[1:]:
                self.check()
                parent = fd
                fd = os.open(name, flags, dir_fd=parent)
                opened.append((fd, parent, name, os.fstat(fd)))
            require(all(stat.S_ISDIR(meta.st_mode) and meta.st_uid in {0, OWNER_UID}
                        for _, _, _, meta in opened), 'READBACK_DIRECTORY_OWNER')
            yield fd
            for fd, parent, name, before in opened:
                require(_dir_identity(os.fstat(fd)) == _dir_identity(before), 'READBACK_DIRECTORY_CHANGED')
                if parent is not None:
                    require(_dir_identity(os.stat(name, dir_fd=parent, follow_symlinks=False))
                            == _dir_identity(before), 'READBACK_DIRECTORY_CHANGED')
        finally:
            for fd, _, _, _ in reversed(opened):
                os.close(fd)

    def read(self, parent, name, maximum, *, snapshot=False):
        self.check()
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid == OWNER_UID, 'READBACK_FILE_TYPE_OWNER')
            if snapshot:
                require(stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1
                        and 0 < before.st_size <= maximum, 'SNAPSHOT_FILE_METADATA')
            pieces, size = [], 0
            while True:
                self.check()
                part = os.read(fd, min(8192, maximum + 1 - size))
                if not part:
                    break
                size += len(part)
                self.bytes += len(part)
                require(size <= maximum, 'READBACK_FILE_BOUND')
                pieces.append(part)
            named = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if snapshot:
                require(_identity(before) == _identity(os.fstat(fd)) == _identity(named)
                        and size == before.st_size, 'SNAPSHOT_CHANGED')
            else:
                require(_dir_identity(before) == _dir_identity(os.fstat(fd)) == _dir_identity(named),
                        'READBACK_PROC_CHANGED')
            return b''.join(pieces)
        finally:
            os.close(fd)


def _link(parent, name):
    value = os.readlink(name, dir_fd=parent)
    require(0 < len(value.encode('utf8')) <= 4096 and not value.endswith(' (deleted)'), 'READBACK_LINK_BOUND')
    return value


def _process(reader, fd, expected):
    raw = reader.read(fd, 'stat', 8192)
    fields = raw.decode('ascii').rsplit(') ', 1)[1].split()
    require(int(raw.split(b' ', 1)[0]) == expected['pid'] and fields[0] not in {'Z', 'X'}
            and int(fields[1]) == expected['ppid'] and int(fields[19]) == expected['start_ticks'],
            'PROCESS_LIFETIME_CHANGED')
    argv = reader.read(fd, 'cmdline', 32768)
    require(argv.endswith(b'\0') and sha(argv) == expected['argv_sha256'], 'PROCESS_ARGV_CHANGED')
    # argv is only hashed, never decoded, parsed as flags or put in the result.
    require(sha(_link(fd, 'exe').encode()) == expected['exe_path_sha256']
            and sha(_link(fd, 'cwd').encode()) == expected['cwd_sha256'], 'PROCESS_EXE_CWD_CHANGED')
    uids = re.findall(rb'^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$',
                      reader.read(fd, 'status', 16384), re.M)
    require(len(uids) == 1 and all(int(uid) == OWNER_UID for uid in uids[0]), 'PROCESS_UID_CHANGED')


def _socket(reader, process_fd, value):
    expected = value['listener']
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    sockets_fd = os.open('fd', flags, dir_fd=process_fd)
    namespace_fd = None
    try:
        namespace_fd = os.open('ns', flags, dir_fd=process_fd)
        socket_name = str(expected['fd'])
        socket_link = 'socket:[' + str(expected['socket_inode']) + ']'
        require(_link(sockets_fd, socket_name) == socket_link, 'LISTENER_FD_CHANGED')
        network = _link(namespace_fd, 'net')
        require(sha(network.encode()) == expected['network_namespace_sha256']
                and os.readlink(PROC / 'self' / 'ns' / 'net') == network, 'LISTENER_NAMESPACE_CHANGED')
        net_fd = os.open('net', flags, dir_fd=process_fd)
        try:
            tcp_fd = os.open('tcp', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=net_fd)
            try:
                meta = os.fstat(tcp_fd)
                require(stat.S_ISREG(meta.st_mode) and meta.st_uid == OWNER_UID, 'LISTENER_TABLE_METADATA')
                pending, scanned, rows, header, matched = b'', 0, 0, False, False
                while scanned < MAX_TCP and rows < MAX_TCP_ROWS and not matched:
                    reader.check()
                    part = os.read(tcp_fd, min(4096, MAX_TCP - scanned))
                    if not part:
                        break
                    scanned += len(part)
                    reader.bytes += len(part)
                    pending += part
                    while b'\n' in pending:
                        line, pending = pending.split(b'\n', 1)
                        require(len(line) <= MAX_TCP_LINE, 'LISTENER_LINE_BOUND')
                        if not header:
                            require(b'local_address' in line and b'inode' in line, 'LISTENER_TABLE_HEADER')
                            header = True
                            continue
                        rows += 1
                        require(rows <= MAX_TCP_ROWS, 'LISTENER_ROW_BOUND')
                        fields = line.split()
                        if len(fields) < 10:
                            continue
                        if fields[9] != str(expected['socket_inode']).encode():
                            continue
                        address = b'00000000' if expected['address'] == '0.0.0.0' else b'0100007F'
                        matched = (fields[1].upper() == address + b':' + f"{value['route']['port']:04X}".encode()
                                   and fields[3].upper() == b'0A' and fields[7] == str(OWNER_UID).encode())
                        if matched:
                            break
                    require(len(pending) <= MAX_TCP_LINE or matched, 'LISTENER_LINE_BOUND')
                require(matched, 'OWNED_LISTENER_UNOBSERVED_WITHIN_BOUND')
            finally:
                os.close(tcp_fd)
        finally:
            os.close(net_fd)
        # An inode found in the table is not sufficient if its FD changed while scanning.
        require(_link(sockets_fd, socket_name) == socket_link and _link(namespace_fd, 'net') == network
                and os.readlink(PROC / 'self' / 'ns' / 'net') == network, 'LISTENER_CHANGED_DURING_READ')
    finally:
        if namespace_fd is not None:
            os.close(namespace_fd)
        os.close(sockets_fd)


def current_reference(url):
    checked_at = int(time.time())
    route = '127.0.0.1:8098' if url == PRIMARY_URL else '127.0.0.1:8085' if url == FALLBACK_URL else 'unbound'
    unknown = {'state': 'unverified', 'selected_route': route, 'checked_at': checked_at}
    if url != PRIMARY_URL:
        return dict(unknown, reason='SELECTED_ROUTE_HAS_NO_BOUND_REFERENCE')
    try:
        reader = _Reader()
        with reader.directory(SNAPSHOT.parent) as parent:
            value = validate_snapshot(_json(reader.read(parent, SNAPSHOT.name, MAX_SNAPSHOT, snapshot=True)), checked_at)
        with reader.directory(PROC / str(value['process']['pid'])) as process_fd:
            _process(reader, process_fd, value['process'])
            _socket(reader, process_fd, value)
            _process(reader, process_fd, value['process'])
            _socket(reader, process_fd, value)
        reader.check()
        return {'state': 'verified_reference', 'selected_route': route, 'checked_at': checked_at,
                'model_file_reference': value['model_reference']['basename'],
                'audit_observed_at': value['evidence']['observed_at'], 'audit_run': value['evidence']['run'],
                'scope': 'current PID/start + argv hash + owned listening socket; file reference only',
                'weight_contents_verified': False, 'architecture_or_training_verified': False,
                'global_listener_uniqueness_verified': False, 'prior_chat_backend_verified': False,
                'health_rechecked': False, 'atomic_snapshot': False}
    except ReferenceUnavailable as error:
        return dict(unknown, reason=str(error))
    except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError):
        return dict(unknown, reason='LOCAL_REFERENCE_READBACK_UNAVAILABLE')


def prepare_identity_request(url, payload, user_text):
    """Build two bounded messages for a full-match question, not compound work.

    The exact stable prefix through the existing contract is retained. Its
    variable memory/status tail and old turns are unnecessary for this narrow
    question. The new fact block is appended after all trimming and no later
    trimmer runs. Byte limits are not a claim about exact tokenizer output.
    """
    require(model_identity_query(user_text), 'MODEL_REFERENCE_QUESTION_SCOPE')
    messages = payload.get('messages')
    require(isinstance(messages, list) and messages and messages[0].get('role') == 'system'
            and isinstance(messages[0].get('content'), str), 'MODEL_REFERENCE_SYSTEM_PREFIX')
    content = messages[0]['content']
    require(content.count(CONTRACT) == 1, 'MODEL_REFERENCE_CONTRACT')
    end = content.find('\n\n', content.index(CONTRACT) + len(CONTRACT))
    prefix = content if end < 0 else content[:end]
    require(0 < len(prefix.encode('utf8')) <= MAX_PREFIX_BYTES, 'MODEL_REFERENCE_PREFIX_BOUND')
    fact = current_reference(url)
    block = ('\n\nNOX_CURRENT_MODEL_REFERENCE_V1 (runtime data):\n'
             + json.dumps(fact, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
             + '\nОтветь кратко по этим данным. Имя GGUF — ссылка из аргументов процесса, не проверка '
               'содержимого весов или архитектуры. При unverified прямо скажи, что имя текущей модели '
               'не подтверждено. Не подставляй имя из старого статуса или плана.')
    require(len(block.encode('utf8')) <= MAX_FACT_BYTES, 'MODEL_REFERENCE_FACT_BOUND')
    system = prefix + block
    require(len(system.encode('utf8')) + len(user_text.encode('utf8')) <= MAX_CONTEXT_BYTES,
            'MODEL_REFERENCE_CONTEXT_BOUND')
    # Retain existing sampling/routing settings; do not pass optional schemas,
    # tool definitions or previous tool calls into this no-tools answer.
    allowed = ('model', 'id_slot', 'seed', 'temperature', 'min_p', 'top_p', 'top_k',
               'repeat_penalty', 'presence_penalty', 'frequency_penalty', 'reasoning_effort')
    request = {key: payload[key] for key in allowed if key in payload}
    requested = payload.get('max_tokens', 256)
    requested = requested if type(requested) is int and requested > 0 else 256
    request.update(messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user_text}],
                   stream=True, cache_prompt=True, tool_choice='none', n=1, max_tokens=min(requested, 256),
                   chat_template_kwargs={'enable_thinking': False})
    return request
