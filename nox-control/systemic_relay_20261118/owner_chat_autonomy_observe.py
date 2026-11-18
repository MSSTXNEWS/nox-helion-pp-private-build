#!/usr/bin/env python3
"""Fixed read-only chat source observation; never imports serving modules."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import ast
import hashlib
import io
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import time
import tokenize

ROOT = Path('/root/nox')
SCRIPTS = ROOT / 'scripts'
SOURCE_NAMES = ('slim_chat_t885u.py', 'owner_chat_stream.py', 'agent_loop.py',
                'chat_proxy.py', 'nox_v29_chat_bridge.py', 'owner_chat_evidence.py')
PUBLIC_ASSET = ROOT / 'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/pc/v24/nox-v24-chat.js'
SERVICES = ('nox-ds41-8098', 'nox-proxy', 'nox-web29-18775', 'nox-dispatcher-t855u')
STREAM_CONSTANTS = frozenset(('EXECUTOR_STATUS', 'CONNECT_TIMEOUT', 'READ_TIMEOUT',
    'MODEL_TIMEOUT', 'STREAM_TIMEOUT', 'MAX_STREAM_BYTES', 'MAX_CHUNK_BYTES', 'MAX_OUTPUT_TOKENS'))
MAX_FILE = 2 * 1024 * 1024
MAX_EXPORT = 64 * 1024
MAX_EXPORT_TOTAL = 128 * 1024
SAFE_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_.]{0,159}')
SECRET_PATTERNS = (
    re.compile(r'-----BEGIN [^-\n]*PRIVATE KEY-----'),
    re.compile(r'\b(?:hf_|ghp_|github_pat_)[A-Za-z0-9_]{12,}'),
    re.compile(r'(?i)\bBearer\s+[A-Za-z0-9_.~+/=-]{12,}'),
    re.compile(r'(?i)https?://[^/\s@]+:[^/\s@]+@'),
    re.compile(r'''(?i)(?:password|secret|api_key|access_key|authorization|token)\s*[:=]\s*["'][^"'\n]{12,}["']'''),
)


class Hold(RuntimeError):
    pass


def require(value, reason):
    if not value:
        raise Hold(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def file_identity(info):
    return {'device': info.st_dev, 'inode': info.st_ino, 'uid': info.st_uid, 'gid': info.st_gid,
            'mode': stat.S_IMODE(info.st_mode), 'nlink': info.st_nlink, 'size': info.st_size,
            'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}


def read_regular(path, maximum=MAX_FILE):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'PATH_SCOPE')
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= maximum, 'FILE_BOUND')
            chunks, size = [], 0
            while True:
                chunk = os.read(fd, min(65536, before.st_size - size + 1))
                if not chunk:
                    break
                size += len(chunk)
                require(size <= before.st_size, 'FILE_CHANGED')
                chunks.append(chunk)
            require(size == before.st_size and file_identity(before) == file_identity(os.fstat(fd))
                    and file_identity(before) == file_identity(os.stat(path.name, dir_fd=directory, follow_symlinks=False)),
                    'FILE_CHANGED')
            return b''.join(chunks), file_identity(before)
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def process_identity(pid):
    path = Path('/proc') / str(pid) / 'stat'
    def one():
        # procfs reports st_size=0 although its virtual stat record is nonempty.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            require(stat.S_ISREG(os.fstat(fd).st_mode), 'PROCESS_STAT_TYPE')
            raw = os.read(fd, 8193)
            require(len(raw) <= 8192, 'PROCESS_STAT_BOUND')
        finally:
            os.close(fd)
        fields = raw.decode('ascii').rsplit(') ', 1)[1].split()
        require(fields[0] in ('R', 'S', 'D', 'I'), 'PROCESS_NOT_LIVE')
        return {'pid': pid, 'ppid': int(fields[1]), 'pgrp': int(fields[2]),
                'start_ticks': int(fields[19])}
    first = one()
    require(first == one(), 'PROCESS_CHANGED')
    return first


def protected_snapshot():
    result = subprocess.run(['supervisorctl', 'status', *SERVICES], capture_output=True,
                            timeout=10, check=False)
    require(len(result.stdout) <= 16384 and len(result.stderr) <= 16384, 'SUPERVISOR_OUTPUT_BOUND')
    found = {}
    for line in result.stdout.decode('utf-8', 'replace').splitlines():
        match = re.fullmatch(r'([A-Za-z0-9_.:-]+)\s+([A-Z]+)(?:\s+pid\s+(\d+))?.*', line)
        if not match or match[1] not in SERVICES:
            continue
        require(match[1] not in found, 'SUPERVISOR_DUPLICATE')
        row = {'service': match[1], 'state': match[2], 'identity': None}
        if match[3]:
            try:
                row['identity'] = process_identity(int(match[3]))
            except (OSError, ValueError, IndexError, Hold) as exc:
                if isinstance(exc, Hold) and str(exc) == 'PROBE_TIME_BUDGET':
                    raise
                row['identity_state'] = str(exc) if isinstance(exc, Hold) else type(exc).__name__
        found[match[1]] = row
    return {'returncode': result.returncode,
            'services': [found.get(name, {'service': name, 'state': 'UNAVAILABLE'}) for name in SERVICES]}


def qualified(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = qualified(node.value)
        return parent + '.' + node.attr if parent else None
    return None


def ast_structure(tree):
    definitions, imports, hooks = [], [], []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and SAFE_NAME.fullmatch(node.name):
            definitions.append({'name': node.name, 'kind': type(node).__name__,
                                'start_line': node.lineno, 'end_line': node.end_lineno})
        elif isinstance(node, ast.Import):
            imports.extend({'module': item.name, 'alias': item.asname, 'line': node.lineno}
                           for item in node.names if SAFE_NAME.fullmatch(item.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module and SAFE_NAME.fullmatch(node.module):
                imports.append({'module': node.module, 'level': node.level,
                                'names': [item.name for item in node.names if SAFE_NAME.fullmatch(item.name)][:64],
                                'line': node.lineno})
        elif isinstance(node, ast.Call):
            name = qualified(node.func)
            if name and SAFE_NAME.fullmatch(name) and name.rsplit('.', 1)[-1] in ('install', 'apply_system'):
                hooks.append({'callee': name, 'line': node.lineno})
    return {'definitions': definitions[:128], 'definition_count': len(definitions),
            'imports': imports[:128], 'import_count': len(imports),
            'hooks': hooks[:128], 'hook_count': len(hooks),
            'metadata_bounded': any(len(rows) > 128 for rows in (definitions, imports, hooks))}


def assignment_names(node):
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    else:
        return set()
    return {part.id for target in targets for part in ast.walk(target) if isinstance(part, ast.Name)}


def export_exact(label, raw, encoding, budget, *, start_line=None, end_line=None):
    item = {'symbol': label, 'sha256': sha(raw), 'bytes': len(raw), 'encoding': encoding}
    if start_line is not None:
        item.update(start_line=start_line, end_line=end_line)
    if len(raw) > MAX_EXPORT:
        return {**item, 'state': 'BLOCKED_SYMBOL_EXPORT_SIZE'}
    text = raw.decode(encoding)
    size = len(text.encode('utf-8'))
    if size > MAX_EXPORT or budget[0] + size > MAX_EXPORT_TOTAL:
        return {**item, 'state': 'BLOCKED_TOTAL_EXPORT_SIZE'}
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        return {**item, 'state': 'BLOCKED_SENSITIVE_LITERAL', 'text_redacted': False}
    budget[0] += size
    return {**item, 'state': 'EXACT_SOURCE_EXPORTED', 'text': text}


def selected_exports(name, raw, tree, budget):
    encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
    lines = re.findall(rb'[^\r\n]*(?:\r\n|\r|\n|$)', raw)
    if lines and not lines[-1]:
        lines.pop()
    requested = {'slim_chat_t885u.py': ('SLIM_RULES', 'apply_system'),
                 'owner_chat_stream.py': ('_model_events', 'install', *sorted(STREAM_CONSTANTS))}.get(name, ())
    output = []
    for symbol in requested:
        nodes = [node for node in ast.walk(tree)
                 if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol)
                 or symbol in assignment_names(node)]
        if len(nodes) != 1:
            output.append({'symbol': symbol, 'state': 'SYMBOL_ABSENT' if not nodes else 'BLOCKED_AMBIGUOUS_SYMBOL',
                           'matches': len(nodes)})
            continue
        node = nodes[0]
        # Multi-target assignments could contain unrelated credentials or constants.
        require(not assignment_names(node) or assignment_names(node) == {symbol}, 'SYMBOL_ASSIGNMENT_SCOPE')
        decorators = getattr(node, 'decorator_list', [])
        start = min([node.lineno, *(item.lineno for item in decorators)])
        segment = b''.join(lines[start - 1:node.end_lineno])
        output.append(export_exact(symbol, segment, encoding, budget,
                                   start_line=start, end_line=node.end_lineno))
    return output


def main():
    started = time.time()
    signal.signal(signal.SIGALRM, lambda *_: require(False, 'PROBE_TIME_BUDGET'))
    signal.setitimer(signal.ITIMER_REAL, 35)
    result = {'schema': 'NOX_CHAT_AUTONOMY_OBSERVE_V1', 'read_only': True,
              'source_writes': 0, 'service_restarts': 0, 'model_calls': 0,
              'source_imports': 0, 'started_at': started, 'files': [],
              'source_export_limit_each': MAX_EXPORT, 'source_export_limit_total': MAX_EXPORT_TOTAL}
    budget = [0]
    try:
        result['protected_before'] = protected_snapshot()
        paths = [PUBLIC_ASSET, *(SCRIPTS / name for name in SOURCE_NAMES)]
        for path in paths:
            row = {'path': str(path), 'name': path.name}
            try:
                raw, info = read_regular(path)
                row.update(**info, sha256=sha(raw), state='SOURCE_PINNED')
                if path == PUBLIC_ASSET:
                    row['exports'] = [export_exact('PUBLIC_V24_CHAT_ASSET', raw, 'utf-8', budget)]
                else:
                    tree = ast.parse(raw, filename=path.name)
                    row['ast'] = ast_structure(tree)
                    row['exports'] = selected_exports(path.name, raw, tree, budget)
            except (OSError, ValueError, TypeError, SyntaxError, Hold) as exc:
                if isinstance(exc, Hold) and str(exc) == 'PROBE_TIME_BUDGET':
                    raise
                row.update(state='BLOCKED_SOURCE_OBSERVATION', reason=str(exc) if isinstance(exc, Hold) else type(exc).__name__)
            result['files'].append(row)
        result['protected_after'] = protected_snapshot()
        result['protected_stable'] = result['protected_before'] == result['protected_after']
        result['protected_all_running_verified'] = all(row.get('state') == 'RUNNING' and row.get('identity')
            for row in result['protected_after']['services'])
        result['state'] = 'READ_ONLY_SOURCE_OBSERVED'
    except (OSError, ValueError, TypeError, Hold, subprocess.TimeoutExpired) as exc:
        result.update(state='BLOCKED_OBSERVATION', reason=str(exc) if isinstance(exc, Hold) else type(exc).__name__)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    result.update(source_export_utf8_bytes=budget[0], finished_at=time.time())
    raw = encoded(result)
    if len(raw) > 512 * 1024:
        raw = encoded({'schema': result['schema'], 'read_only': True, 'state': 'BLOCKED_OUTPUT_BOUND'})
    print('NOX_MAINT_CHAT_AUTONOMY_OBSERVE=' + raw.decode(), flush=True)
    return 0 if result.get('state') == 'READ_ONLY_SOURCE_OBSERVED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
