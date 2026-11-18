#!/usr/bin/env python3
"""Fixed, bounded chat metadata inspection. No native imports or mutations.

Sources are hashed and parsed as AST only. No source body, chat message,
environment value, credential, model prompt or raw log line leaves this probe.
"""
from __future__ import annotations

import ast
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import time

ROOT = Path('/root/nox')
SCRIPTS = ROOT / 'scripts'
SITE = ROOT / 'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site'
SOURCES = ('nox_tools.py', 'agent_loop.py', 'chat_proxy.py', 'owner_chat_stream.py',
           'nox_v29_chat_bridge.py', 'owner_chat_evidence.py')
ASSETS = (('V24_CHAT', SITE / 'pc/v24/nox-v24-chat.js'),
          ('OWNER_BRIDGE', SITE / 'nox-v135-resonance-owner-bridge.js'))
LOGS = (('PROXY', ROOT / 'logs/proxy.log'),
        ('LLAMA_8081', ROOT / 'logs/llama-chat-8081.log'),
        ('DS41_8098', ROOT / 'logs/ds41-8098.log'))
SERVICES = ('nox-proxy', 'nox-ds41-8098', 'nox-chat-8081', 'nox-web29-18775')
STATES = frozenset(('RUNNING', 'STOPPED', 'STARTING', 'STOPPING', 'BACKOFF', 'FATAL', 'EXITED', 'UNKNOWN'))
NUMERIC_FLAGS = {'-t': 'threads', '--threads': 'threads', '-tb': 'threads_batch',
    '--threads-batch': 'threads_batch', '--threads-http': 'threads_http',
    '-np': 'parallel', '--parallel': 'parallel', '-c': 'context', '--ctx-size': 'context',
    '--n-cpu-moe': 'cpu_moe', '-ngl': 'gpu_layers', '--n-gpu-layers': 'gpu_layers',
    '--port': 'port', '-p': 'port'}
ERRORS = frozenset(('TypeError', 'ValueError', 'KeyError', 'RuntimeError', 'AttributeError',
    'TimeoutError', 'JSONDecodeError', 'ConnectionError', 'ReadTimeout', 'ConnectTimeout',
    'HTTPStatusError', 'CancelledError', 'ModuleNotFoundError', 'ImportError',
    'HOLD_MODEL_HTTP', 'HOLD_MODEL_SSE_FRAME', 'HOLD_MODEL_SSE_SIZE', 'HOLD_MODEL_INCOMPLETE',
    'HOLD_MODEL_OUTPUT_SIZE', 'HOLD_MODEL_SSE_INVALID', 'HOLD_MODEL_STREAM_INCOMPLETE',
    'HOLD_TOOL_CALL_TERMINAL', 'HOLD_TOOL_CALL_ID', 'HOLD_MODEL_EMPTY', 'HOLD_TOOL_CALL_SIZE',
    'HOLD_TOOL_CALL_COUNT', 'HOLD_TOOL_CALL_SHAPE'))
IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,79}')
INTEREST = re.compile(r'chat|completion|dispatch|heuristic|parse_tool|history|messages|model_events|'
    r'owner_request|action_request|^install$|^_run$|normal_calls|assistant_tools|meaningful|'
    r'trim_ctx|build_messages|prepare_payload|dialog_context|native_v29_stream')
PROTOCOL = frozenset(('messages', 'history', 'role', 'content', 'reasoning_content', 'reasoning',
    'tool_calls', 'tool_call_id', 'finish_reason', 'tools', 'tool_choice', 'delta', 'stream',
    'max_tokens', 'max_completion_tokens', 'n_predict', 'temperature', 'dialog_id', 'confirmed',
    'reasoning_budget', 'chat_template_kwargs', 'enable_thinking', 'thinking_mode'))
LIMIT_KEYS = frozenset(('max_tokens', 'max_completion_tokens', 'n_predict', 'reasoning_budget',
    'max_chars', 'max_turns', 'turns', 'limit', 'n_ctx', 'ctx_size', 'budget', 'token_budget',
    'max_messages', 'history_limit', 'enable_thinking', 'thinking_mode'))
MAX_SOURCE = 1024 * 1024
SCHEMA = 'NOX_OWNER_SMART_CHAT_INSPECTION_V1'


class Hold(Exception):
    pass


class Deadline(BaseException):
    pass


def require(ok, code):
    if not ok:
        raise Hold(code)


def safe(exc):
    return str(exc) if isinstance(exc, Hold) else type(exc).__name__


def identity(value):
    return tuple(getattr(value, 'st_' + key) for key in
                 ('dev', 'ino', 'uid', 'gid', 'mode', 'nlink', 'size', 'mtime_ns', 'ctime_ns'))


def regular(path, maximum=MAX_SOURCE, tail=False, metadata_only=False):
    """No symlink parent traversal. Stable sources; growing logs stay marked tails."""
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'FIXED_PATH_REQUIRED')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    fd = None
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            os.close(parent); parent = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode), 'REGULAR_FILE_REQUIRED')
        meta = {'bytes': before.st_size, 'uid': before.st_uid, 'gid': before.st_gid,
                'mode_octal': format(stat.S_IMODE(before.st_mode), '04o'),
                'device': before.st_dev, 'inode': before.st_ino, 'nlink': before.st_nlink,
                'mtime_ns': before.st_mtime_ns, 'ctime_ns': before.st_ctime_ns}
        if metadata_only:
            return b'', dict(meta, content_bytes_read=0, contents_exported=False)
        if tail:
            os.lseek(fd, max(0, before.st_size - maximum), os.SEEK_SET)
        else:
            require(before.st_size <= maximum, 'SOURCE_SIZE_BOUND')
        chunks = []; count = 0
        while count <= maximum:
            part = os.read(fd, min(65536, maximum + 1 - count))
            if not part:
                break
            chunks.append(part); count += len(part)
        require(count <= maximum, 'SOURCE_READ_BOUND')
        after = os.fstat(fd); named = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if not tail:
            require(identity(before) == identity(after) == identity(named) and count == before.st_size,
                    'SOURCE_CHANGED')
        else:
            require((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
                    == (named.st_dev, named.st_ino), 'LOG_ROTATED')
        return b''.join(chunks), dict(meta, content_bytes_read=count, stable_complete_file=not tail)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def symbol(node):
    if isinstance(node, ast.Name) and IDENT.fullmatch(node.id):
        return node.id
    if isinstance(node, ast.Attribute) and IDENT.fullmatch(node.attr):
        base = symbol(node.value)
        if base and base.count('.') < 4:
            return base + '.' + node.attr
    return None


def tool_projection(node):
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, RecursionError, MemoryError):
        return {'state': 'DYNAMIC_UNRESOLVED', 'names': []}
    if not isinstance(value, list) or len(value) > 128:
        return {'state': 'SCHEMA_UNRECOGNIZED', 'names': []}
    tools = []
    for item in value:
        fn = item.get('function') if isinstance(item, dict) else None
        if not isinstance(fn, dict) or not isinstance(fn.get('name'), str) or not IDENT.fullmatch(fn['name']):
            return {'state': 'SCHEMA_UNRECOGNIZED', 'names': []}
        params = fn.get('parameters') or {}; props = params.get('properties') or {}
        if not isinstance(props, dict) or len(props) > 64:
            return {'state': 'SCHEMA_UNRECOGNIZED', 'names': []}
        tools.append({'name': fn['name'], 'parameter_names': sorted(k for k in props
            if isinstance(k, str) and IDENT.fullmatch(k)), 'required': [k for k in params.get('required', [])
            if isinstance(k, str) and IDENT.fullmatch(k)][:64]})
    return {'state': 'LITERAL_NAMES_ONLY', 'names': [v['name'] for v in tools], 'tools': tools}


def structure(raw):
    text = raw.decode('utf-8'); tree = ast.parse(text)
    require(sum(1 for _ in ast.walk(tree)) <= 100000, 'AST_SIZE_BOUND')
    functions = []; imports = set(); registry = {'state': 'NOT_DECLARED', 'names': []}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and INTEREST.search(node.name):
            require(len(functions) < 80, 'FUNCTION_COUNT_BOUND')
            calls = sorted({v for child in ast.walk(node) if isinstance(child, ast.Call)
                            and (v := symbol(child.func)) is not None})
            keys = sorted({child.value for child in ast.walk(node) if isinstance(child, ast.Constant)
                           and isinstance(child.value, str) and child.value in PROTOCOL})
            branches = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Compare) and isinstance(child.left, ast.Name) and child.left.id in ('name', 'action'):
                    for other in child.comparators:
                        values = other.elts if isinstance(other, (ast.List, ast.Tuple, ast.Set)) else [other]
                        branches.update(v.value for v in values if isinstance(v, ast.Constant)
                            and isinstance(v.value, str) and IDENT.fullmatch(v.value))
            defaults = {}
            positions = (*node.args.posonlyargs, *node.args.args)
            paired = list(zip(positions[-len(node.args.defaults):], node.args.defaults)) if node.args.defaults else []
            paired += list(zip(node.args.kwonlyargs, node.args.kw_defaults))
            for argument, default in paired:
                if isinstance(default, ast.Constant) and type(default.value) in (int, float, bool) and abs(default.value) <= 10**9:
                    defaults[argument.arg] = default.value
            limits = []
            for child in ast.walk(node):
                pairs = []
                if isinstance(child, ast.Dict):
                    pairs = [(key.value, val) for key, val in zip(child.keys, child.values)
                             if isinstance(key, ast.Constant) and isinstance(key.value, str)]
                elif isinstance(child, ast.Call):
                    pairs = [(key.arg, key.value) for key in child.keywords]
                    if isinstance(child.func, ast.Attribute) and child.func.attr == 'get' and len(child.args) == 2:
                        key = child.args[0]
                        if isinstance(key, ast.Constant) and isinstance(key.value, str):
                            pairs.append((key.value, child.args[1]))
                for key, val in pairs:
                    if key in LIMIT_KEYS and isinstance(val, ast.Constant) and type(val.value) in (int, float, bool) and abs(val.value) <= 10**9:
                        limits.append({'key': key, 'value': val.value})
            body = ast.get_source_segment(text, node) or ''
            functions.append({'name': node.name, 'line': node.lineno, 'async': isinstance(node, ast.AsyncFunctionDef),
                'parameters': [a.arg for a in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)],
                'sha256': hashlib.sha256(body.encode()).hexdigest(), 'calls': calls[:96],
                'calls_truncated': len(calls) > 96, 'protocol_keys': keys, 'numeric_defaults': defaults,
                'declared_limits': limits[:64], 'dialog_context_call_count': sum(1 for child in ast.walk(node)
                    if isinstance(child, ast.Call) and (symbol(child.func) or '').rsplit('.', 1)[-1] == '_dialog_context'),
                'action_or_tool_branches': sorted(branches)[:128]})
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(v, ast.Name) and v.id == 'TOOLS' for v in targets):
                registry = tool_projection(node.value)
    return {'state': 'STATIC_AST_OBSERVED', 'imports': sorted(imports)[:160],
            'functions': functions, 'tool_registry': registry, 'source_body_exported': False,
            'native_module_imported': False, 'running_module_binding_proven': False}


def source_row(label, path, python=False):
    try:
        raw, meta = regular(path)
        row = {'label': label, 'path': str(path), 'state': 'STABLE_SOURCE_HASH', **meta,
               'sha256': hashlib.sha256(raw).hexdigest()}
        if python:
            row['interface'] = structure(raw)
        return row
    except Exception as exc:
        return {'label': label, 'path': str(path), 'state': 'UNAVAILABLE', 'reason': safe(exc)}


def proc_bytes(path, maximum):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'PROC_REGULAR_REQUIRED')
        raw = os.read(fd, maximum + 1)
        require(len(raw) <= maximum, 'PROC_BOUND')
        return raw
    finally:
        os.close(fd)


def proc_identity(pid):
    raw = proc_bytes('/proc/' + str(pid) + '/stat', 8192)
    fields = raw[raw.rindex(b')') + 2:].split()
    require(int(raw.split(b' ', 1)[0]) == pid, 'PROC_PID_CHANGED')
    return {'pid': pid, 'ppid': int(fields[1]), 'pgrp': int(fields[2]),
            'start_ticks': int(fields[19]), 'threads': int(fields[17])}


def process_row(pid):
    before = proc_identity(pid); base = '/proc/' + str(pid)
    raw = proc_bytes(base + '/cmdline', 65536); parts = raw.rstrip(b'\0').split(b'\0')
    flags = {}
    for index, value in enumerate(parts):
        key, equals, number = value.partition(b'=')
        name = NUMERIC_FLAGS.get(key.decode('ascii', 'replace'))
        if name:
            number = number if equals else parts[index + 1] if index + 1 < len(parts) else b''
            if re.fullmatch(rb'-?[0-9]{1,9}', number):
                flags[name] = int(number)
    executable = os.readlink(base + '/exe')
    require(bool(re.fullmatch(r'/[A-Za-z0-9/_.+\-]{1,260}(?: \(deleted\))?', executable)), 'EXE_PATH_FORMAT')
    info = os.stat(base + '/exe')
    after = proc_identity(pid)
    require(before['start_ticks'] == after['start_ticks'], 'PROCESS_CHANGED')
    return {'state': 'PROCESS_IDENTITY_OBSERVED', **before, 'executable': executable,
            'executable_device': info.st_dev, 'executable_inode': info.st_ino,
            'argv_sha256': hashlib.sha256(raw).hexdigest(), 'numeric_flags': flags,
            'raw_argv_exported': False, 'environment_read': False}


def services():
    exe = shutil.which('supervisorctl', path='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin')
    if not exe:
        return {'state': 'SUPERVISOR_UNAVAILABLE', 'services': []}
    try:
        p = subprocess.run([exe, 'status', *SERVICES], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5,
            env={'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'})
        require(len(p.stdout) <= 32768, 'SUPERVISOR_OUTPUT_BOUND')
        rows = []
        for line in p.stdout.decode('utf-8', 'replace').splitlines():
            fields = line.split()
            if len(fields) < 2 or fields[0] not in SERVICES or fields[1] not in STATES:
                continue
            row = {'service': fields[0], 'state': fields[1]}
            matched = re.search(r'\bpid ([0-9]{1,10}),', line)
            if matched:
                try:
                    row['process'] = process_row(int(matched[1]))
                except Exception as exc:
                    row['process'] = {'state': 'UNAVAILABLE', 'reason': safe(exc)}
            rows.append(row)
        return {'state': 'SUPERVISOR_METADATA_OBSERVED', 'return_code': p.returncode, 'services': rows}
    except Exception as exc:
        return {'state': 'SUPERVISOR_UNAVAILABLE', 'reason': safe(exc), 'services': []}


def model_http(port, path):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
    started = time.monotonic()
    try:
        connection.request('GET', path, headers={'Accept': 'application/json'})
        response = connection.getresponse()
        out = {'port': port, 'path': path, 'http': response.status}
        if path not in ('/props', '/slots') or response.status != 200:
            return out
        raw = response.read(262145); require(len(raw) <= 262144, 'PROPS_RESPONSE_BOUND')
        value = json.loads(raw)
        if path == '/slots':
            require(isinstance(value, list) and len(value) <= 64, 'SLOTS_LIST_BOUND')
            out['slots'] = [{key: row[key] for key in ('id', 'n_ctx', 'is_processing', 'processing')
                if type(row.get(key)) in (bool, int) and abs(row[key]) <= 1048576}
                for row in value if isinstance(row, dict)]
            out['state'] = 'SLOT_SCALARS_OBSERVED'; out['prompt_or_tokens_exported'] = False
            return out
        require(isinstance(value, dict), 'PROPS_OBJECT_REQUIRED')
        settings = value.get('default_generation_settings') or {}
        settings = settings if isinstance(settings, dict) else {}
        out['numeric'] = {k: v for k in ('total_slots', 'n_ctx', 'n_predict', 'n_threads', 'n_threads_batch', 'n_threads_http')
            if type(v := value.get(k, settings.get(k))) is int and -1 <= v <= 1048576}
        template = value.get('chat_template')
        if isinstance(template, str):
            out['chat_template'] = {'present': bool(template), 'sha256': hashlib.sha256(template.encode()).hexdigest(),
                'characters': len(template), 'tool_calls_marker': 'tool_calls' in template,
                'reasoning_marker': 'reasoning' in template, 'enable_thinking_marker': 'enable_thinking' in template,
                'thinking_mode_marker': 'thinking_mode' in template, 'think_tag_marker': '<think>' in template,
                'body_exported': False}
        build = value.get('build_info')
        if isinstance(build, str) and re.fullmatch(r'b[0-9]{1,10}-[a-fA-F0-9]{7,64}(?:-dirty)?', build):
            out['build_info'] = build
        capabilities = value.get('chat_template_caps')
        allowed = ('supports_tools', 'supports_tool_calls', 'supports_parallel_tool_calls', 'supports_tool_call_id',
                   'supports_system_role', 'supports_developer_role', 'supports_reasoning', 'supports_object_arguments')
        if isinstance(capabilities, dict):
            out['chat_template_caps'] = {k: capabilities[k] for k in allowed if type(capabilities.get(k)) is bool}
        out['state'] = 'SELECTED_MODEL_METADATA_OBSERVED'
        return out
    except Exception as exc:
        return {'port': port, 'path': path, 'state': 'UNAVAILABLE', 'reason': safe(exc)}
    finally:
        connection.close()


def log_row(label, path):
    try:
        raw, meta = regular(path, 131072, tail=True)
        tokens = re.findall(rb'(?<![A-Za-z0-9_])(?:' + b'|'.join(v.encode() for v in sorted(ERRORS))
                            + rb')(?![A-Za-z0-9_])', raw)
        counts = {name: tokens.count(name.encode()) for name in sorted(ERRORS) if name.encode() in tokens}
        return {'label': label, 'state': 'BOUNDED_LOG_CODE_COUNTS', 'file_bytes': meta['bytes'],
                'sampled_bytes': len(raw), 'counts': counts, 'raw_lines_exported': False,
                'historical_tail_not_current_request_proof': True}
    except Exception as exc:
        return {'label': label, 'state': 'UNAVAILABLE', 'reason': safe(exc)}


def drive_metadata():
    path = ROOT / 'state/cold_drive.conf'
    try:
        _, meta = regular(path, metadata_only=True)
        return {'path': str(path), 'state': 'METADATA_OBSERVED', **meta,
                'owner_and_mode_valid': meta['uid'] == os.geteuid() and meta['mode_octal'] == '0600',
                'authentication_tested': False}
    except Exception as exc:
        return {'path': str(path), 'state': 'UNAVAILABLE', 'reason': safe(exc), 'contents_read': False}


def emit(kind, data):
    raw = json.dumps({'kind': kind, 'data': data}, sort_keys=True, separators=(',', ':'), allow_nan=False)
    require(len(raw.encode()) < 170000, 'OUTPUT_ROW_BOUND')
    print('NOX_MAINT_INSPECT=' + raw, flush=True)


def main():
    request, source = (os.environ.get(k, '') for k in ('NOX_OWNER_REQUEST_ID', 'NOX_OWNER_SOURCE_SHA'))
    require(re.fullmatch(r'[0-9]{1,24}', request) and re.fullmatch(r'[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    def expired(*_):
        raise Deadline()
    previous = signal.signal(signal.SIGALRM, expired); signal.alarm(40)
    started = time.time()
    try:
        emit('context', {'schema': SCHEMA, 'request': request, 'source_sha': source, 'started_at': started})
        emit('services_before', services())
        for name in SOURCES:
            emit('source', source_row(name, SCRIPTS / name, python=True))
        for label, path in ASSETS:
            emit('asset', source_row(label, path))
        for port in (8080, 8081, 8082, 8098):
            emit('health', model_http(port, '/health'))
        for port in (8081, 8098):
            emit('model_props', model_http(port, '/props'))
            emit('model_slots', model_http(port, '/slots'))
        for label, path in LOGS:
            emit('log_counts', log_row(label, path))
        emit('drive_metadata', drive_metadata())
        emit('services_after', services())
        emit('summary', {'schema': SCHEMA, 'request': request, 'source_sha': source,
            'state': 'BOUNDED_READ_ONLY_INSPECTION_FINISHED', 'elapsed_seconds': round(time.time() - started, 3),
            'files_written': 0, 'services_changed': False, 'native_modules_imported': False,
            'generation_posts': 0, 'private_chat_or_source_bodies_exported': False,
            'loaded_python_module_identity_verified': False})
        print('NOX_MAINT_INSPECT_COMPLETE=true', flush=True)
        return 0
    except Deadline:
        emit('summary', {'schema': SCHEMA, 'state': 'HOLD_INSPECTION_DEADLINE', 'files_written': 0})
        return 2
    finally:
        signal.alarm(0); signal.signal(signal.SIGALRM, previous)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        emit('hold', {'schema': SCHEMA, 'reason': safe(exc), 'files_written': 0})
        raise SystemExit(2)
