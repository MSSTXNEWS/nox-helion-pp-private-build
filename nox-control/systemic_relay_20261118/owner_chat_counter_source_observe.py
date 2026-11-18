#!/usr/bin/env python3
"""Read-only exact pinned chat counter lifecycle symbols; no serving imports."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import time


ROOT = Path('/root/nox')
TARGETS = (
    ('common.py', 'mark_chat', '618b2b24ffdf780e64a5d09955438dec5a9b6b8b04b3346b29c57fc750403167'),
    ('chat_proxy.py', '_ChatActivityStream', '1b468ebda8cdae0dce3fd1b9df4f7def64c56d708796b05e5bd7f88fbc76af62'),
)
EXPECTED = {
    'proxy': {'pid': 3703386, 'start_ticks': 175609570, 'ppid': 114, 'pgrp': 3703386},
    'model_8098': {'pid': 3266857, 'start_ticks': 172046662, 'ppid': 114, 'pgrp': 3266857},
    'director': {'pid': 106058, 'start_ticks': 181620214, 'ppid': 114, 'pgrp': 106058},
    'worker_runtime': {'pid': 106174, 'start_ticks': 181621423, 'ppid': 106058, 'pgrp': 106058},
    'worker_memory': {'pid': 106175, 'start_ticks': 181621423, 'ppid': 106058, 'pgrp': 106058},
    'worker_weights': {'pid': 106176, 'start_ticks': 181621423, 'ppid': 106058, 'pgrp': 106058},
}
SECRET_PATTERNS = (
    re.compile(r'-----BEGIN [^-\n]*PRIVATE KEY-----'),
    re.compile(r'\b(?:hf_|ghp_|github_pat_)[A-Za-z0-9_]{12,}'),
    re.compile(r'(?i)\bBearer\s+[A-Za-z0-9_.~+/=-]{12,}'),
    re.compile(r'(?i)https?://[^/\s@]+:[^/\s@]+@'),
    re.compile(r'''(?i)(?:password|secret|api_key|access_key|authorization|token)\s*[:=]\s*["'][^"'\n]{12,}["']'''),
    re.compile(r'''(?i)[?&](?:token|key|password|signature|secret)=[^\s&"']+'''),
)
MAX_SYMBOL = 32 * 1024
MAX_TOTAL = 96 * 1024


class Hold(RuntimeError):
    pass


class Deadline(BaseException):
    pass


def require(value, reason):
    if not value:
        raise Hold(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def metadata(info):
    return {'device': info.st_dev, 'inode': info.st_ino, 'uid': info.st_uid,
            'gid': info.st_gid, 'mode': info.st_mode & 0o7777, 'nlink': info.st_nlink,
            'size': info.st_size, 'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}


def safe_error(error):
    value = str(error)
    return value if isinstance(error, Hold) and re.fullmatch('[A-Z0-9_]{1,80}', value) else type(error).__name__


def read_regular(path):
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    fd = None
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
        info = os.fstat(fd)
        before = metadata(info)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and info.st_nlink == 1 and not info.st_mode & 0o022
                and 0 < info.st_size <= 262144, 'SOURCE_METADATA')
        chunks, total = [], 0
        while True:
            chunk = os.read(fd, min(65536, info.st_size - total + 1))
            if not chunk:
                break
            total += len(chunk)
            require(total <= info.st_size, 'SOURCE_CHANGED')
            chunks.append(chunk)
        require(total == info.st_size and before == metadata(os.fstat(fd))
                and before == metadata(os.stat(path.name, dir_fd=parent, follow_symlinks=False)), 'SOURCE_CHANGED')
        return b''.join(chunks), before
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def process_once(pid):
    fd = os.open('/proc/%d/stat' % pid, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'PROCESS_STAT_TYPE')
        raw = os.read(fd, 8193)
        require(len(raw) <= 8192, 'PROCESS_STAT_BOUND')
    finally:
        os.close(fd)
    fields = raw.decode('ascii').rsplit(') ', 1)[1].split()
    return {'pid': pid, 'state': fields[0], 'ppid': int(fields[1]),
            'pgrp': int(fields[2]), 'start_ticks': int(fields[19])}


def protected():
    rows = {}
    for name, expected in EXPECTED.items():
        row = {'expected': expected, 'matches': False}
        try:
            before, after = process_once(expected['pid']), process_once(expected['pid'])
            require(all(before[key] == after[key] for key in ('pid', 'start_ticks', 'ppid', 'pgrp')),
                    'PROCESS_CHANGED')
            row['observed'] = after
            row['matches'] = (after['state'] in ('R', 'S', 'D', 'I')
                              and all(after[key] == value for key, value in expected.items()))
        except (OSError, ValueError, IndexError, Hold) as error:
            row['error'] = safe_error(error)
        rows[name] = row
    return rows


def symbol(name, wanted, expected, remaining):
    raw, info = read_regular(ROOT / 'scripts' / name)
    require(sha(raw) == expected, 'SOURCE_PIN')
    source = raw.decode('utf-8')
    tree = ast.parse(source)
    found = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
             and node.name == wanted]
    require(len(found) == 1, 'SYMBOL_COUNT')
    segment = ast.get_source_segment(source, found[0])
    require(segment is not None, 'SYMBOL_SOURCE')
    payload = (segment + '\n').encode('utf-8')
    row = {'name': name, 'path': str(ROOT / 'scripts' / name), 'file_sha256': expected,
           'metadata': info, 'symbol': wanted, 'line': found[0].lineno, 'end_line': found[0].end_lineno,
           'symbol_sha256': sha(payload), 'symbol_bytes': len(payload),
           'format': 'EXACT_AST_SEGMENT_WITH_TRAILING_LF', 'source_redacted': False}
    if len(payload) > MAX_SYMBOL or len(payload) > remaining:
        row['state'] = 'BLOCKED_SYMBOL_SIZE'
        return row, 0
    if any(pattern.search(segment) for pattern in SECRET_PATTERNS):
        row['state'] = 'BLOCKED_SECRET_PATTERN'
        return row, 0
    row.update(state='EXACT_SOURCE_EXPORTED', encoding='base64-utf8',
               base64=base64.b64encode(payload).decode('ascii'))
    return row, len(payload)


def main():
    previous = signal.getsignal(signal.SIGALRM)
    def expire(signum, frame):
        raise Deadline()
    signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, 20)
    record = {'schema': 'NOX_CHAT_LIFECYCLE_SOURCE_OBSERVE_V1', 'started_at': time.time(),
              'read_only': True, 'source_writes': 0, 'counter_resets': 0, 'service_restarts': 0,
              'model_calls': 0, 'authentication_calls': 0, 'serving_imports': 0,
              'max_symbol_bytes': MAX_SYMBOL, 'max_total_source_bytes': MAX_TOTAL, 'files': []}
    complete = False
    try:
        before = protected()
        record['protected_before'] = before
        total = 0
        for name, wanted, expected in TARGETS:
            row, count = symbol(name, wanted, expected, MAX_TOTAL - total)
            record['files'].append(row)
            total += count
        record['source_bytes_exported'] = total
        unchanged = True
        for row in record['files']:
            raw, info = read_regular(Path(row['path']))
            unchanged = unchanged and sha(raw) == row['file_sha256'] and info == row['metadata']
        record['sources_unchanged'] = unchanged
        after = protected()
        record['protected_after'] = after
        record['protected_stable'] = all(before[name]['matches'] and after[name]['matches'] for name in EXPECTED)
        complete = (unchanged and record['protected_stable']
                    and len(record['files']) == len(TARGETS)
                    and all(row['state'] == 'EXACT_SOURCE_EXPORTED' for row in record['files']))
        record['state'] = 'EXACT_LIFECYCLE_SOURCES_OBSERVED' if complete else 'INCOMPLETE_LIFECYCLE_SOURCE_OBSERVATION'
    except BaseException as error:
        record.update(state='HOLD_LIFECYCLE_SOURCE_OBSERVATION', reason=safe_error(error))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    record['finished_at'] = time.time()
    raw = json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)
    output = ('NOX_MAINT_CHAT_LIFECYCLE_SOURCE_OBSERVE=' + raw + '\n'
              + 'NOX_MAINT_INSPECT_COMPLETE=' + str(bool(complete)).lower() + '\n')
    require(len(output.encode()) < 180000, 'OUTPUT_BOUND')
    print(output, end='', flush=True)
    return 0 if complete else 2


if __name__ == '__main__':
    raise SystemExit(main())
