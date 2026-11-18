#!/usr/bin/env python3
"""Observe the pinned foreground counter; never reset it or infer request life."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import ast
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import time


ROOT = Path('/root/nox')
SOURCES = {
    'common.py': '618b2b24ffdf780e64a5d09955438dec5a9b6b8b04b3346b29c57fc750403167',
    'chat_proxy.py': '1b468ebda8cdae0dce3fd1b9df4f7def64c56d708796b05e5bd7f88fbc76af62',
}
SYMBOLS = {
    'common.py': ('mark_chat', '156f8727e714a5864a10d34cfbdf6a97f78703c9f81893b49cb4ea21676c49ec'),
    'chat_proxy.py': ('_ChatActivityStream', '12f8ccd256246c68d78caae05d0ce54ad90cc8803515f3ebc2f804b518defc57'),
}
COUNTER = ROOT / 'status/chat_state.json'
EXPECTED = {
    'proxy': {'pid': 3703386, 'start_ticks': 175609570, 'ppid': 114, 'pgrp': 3703386},
    'model_8098': {'pid': 3266857, 'start_ticks': 172046662, 'ppid': 114, 'pgrp': 3266857},
    'director': {'pid': 106058, 'start_ticks': 181620214, 'ppid': 114, 'pgrp': 106058},
    'worker_runtime': {'pid': 106174, 'start_ticks': 181621423, 'ppid': 106058, 'pgrp': 106058},
    'worker_memory': {'pid': 106175, 'start_ticks': 181621423, 'ppid': 106058, 'pgrp': 106058},
    'worker_weights': {'pid': 106176, 'start_ticks': 181621423, 'ppid': 106058, 'pgrp': 106058},
}


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
            'size': info.st_size, 'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns,
            'regular': stat.S_ISREG(info.st_mode)}


def safe_error(error):
    value = str(error)
    return value if isinstance(error, Hold) and re.fullmatch('[A-Z0-9_]{1,80}', value) else type(error).__name__


def read_regular(path, maximum):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'FIXED_ABSOLUTE_PATH')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    fd = None
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
        info = os.fstat(fd)
        first = metadata(info)
        require(first['regular'] and first['uid'] == os.geteuid()
                and first['nlink'] == 1 and 0 <= first['size'] <= maximum, 'FILE_METADATA')
        chunks, total = [], 0
        while True:
            chunk = os.read(fd, min(65536, info.st_size - total + 1))
            if not chunk:
                break
            total += len(chunk)
            require(total <= info.st_size, 'FILE_CHANGED')
            chunks.append(chunk)
        require(total == info.st_size and first == metadata(os.fstat(fd))
                and first == metadata(os.stat(path.name, dir_fd=parent, follow_symlinks=False)), 'FILE_CHANGED')
        return b''.join(chunks), first
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'DUPLICATE_COUNTER_KEY')
            result[key] = value
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                      parse_constant=lambda value: require(False, 'NONFINITE_COUNTER'))


def source_path_proof():
    report, common_tree = {}, None
    for name, expected in SOURCES.items():
        raw, info = read_regular(ROOT / 'scripts' / name, 262144)
        require(sha(raw) == expected and not info['mode'] & 0o022, 'PINNED_SOURCE_CHANGED')
        text = raw.decode('utf-8')
        tree = ast.parse(text)
        symbol, symbol_pin = SYMBOLS[name]
        matches = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                   and node.name == symbol]
        require(len(matches) == 1, 'PINNED_SYMBOL_COUNT')
        segment = ast.get_source_segment(text, matches[0])
        require(segment is not None and sha((segment + '\n').encode()) == symbol_pin, 'PINNED_SYMBOL_CHANGED')
        report[name] = {'sha256': expected, 'metadata': info, 'symbol': symbol,
                        'symbol_sha256': symbol_pin, 'source_exported': False}
        if name == 'common.py':
            common_tree = tree
    assignments = {}
    for node in common_tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            assignments.setdefault(node.targets[0].id, []).append(node.value)
    referenced = set()
    def resolve(node, seen=()):
        require(len(seen) <= 6, 'COMMON_PATH_DEPTH')
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            require(node.id not in seen and len(assignments.get(node.id, [])) == 1, 'COMMON_PATH_NAME')
            referenced.add(node.id)
            return resolve(assignments[node.id][0], (*seen, node.id))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'Path':
            require(len(node.args) == 1 and not node.keywords, 'COMMON_PATH_CALL')
            return Path(resolve(node.args[0], seen))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return Path(resolve(node.left, seen)) / resolve(node.right, seen)
        raise Hold('COMMON_PATH_EXPRESSION')
    require(len(assignments.get('CHAT_STATE', [])) == 1, 'COMMON_CHAT_STATE')
    resolved = Path(resolve(assignments['CHAT_STATE'][0], ('CHAT_STATE',)))
    require(resolved == COUNTER, 'COMMON_COUNTER_PATH')
    return report, {'path': str(resolved), 'resolved_from': 'common.py:CHAT_STATE',
                    'referenced_names': sorted(referenced), 'serving_modules_imported': False}


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
            keys = ('pid', 'start_ticks', 'ppid', 'pgrp')
            require(all(before[key] == after[key] for key in keys), 'PROCESS_CHANGED')
            row['observed'] = after
            row['matches'] = (after['state'] in ('R', 'S', 'D', 'I')
                              and all(after[key] == value for key, value in expected.items()))
        except (OSError, ValueError, IndexError, Hold) as error:
            row['error'] = safe_error(error)
        rows[name] = row
    return rows



def proxy_tcp_counts():
    """Bounded counts only, never peer addresses or session contents.

    Observing zero sockets does not grant a write or prove an atomic idle fence.
    """
    pid = EXPECTED['proxy']['pid']
    before = process_once(pid)
    require(before['start_ticks'] == EXPECTED['proxy']['start_ticks'], 'PROXY_IDENTITY')
    found = set()
    entries = list((Path('/proc') / str(pid) / 'fd').iterdir())
    require(len(entries) <= 4096, 'PROXY_FD_COUNT')
    for entry in entries:
        try:
            target = os.readlink(entry)
        except FileNotFoundError:
            continue
        found_inode = re.fullmatch(r'socket:\[(\d+)\]', target)
        if found_inode:
            found.add(found_inode.group(1))
    count = {'LISTEN': 0, 'ESTABLISHED': 0, 'CLOSE_WAIT': 0,
             'SYN_RECV': 0, 'OTHER_OWNED': 0}
    matched = 0
    for name in ('tcp', 'tcp6'):
        with open('/proc/net/' + name, 'rb', buffering=0) as stream:
            data = stream.read(2 * 1024 * 1024 + 1)
        require(len(data) <= 2 * 1024 * 1024, 'TCP_TABLE_BOUND')
        for row in data.decode('ascii').splitlines()[1:]:
            fields = row.split()
            if len(fields) < 10 or fields[9] not in found:
                continue
            try:
                local_port = int(fields[1].rsplit(':', 1)[1], 16)
            except (IndexError, ValueError):
                raise Hold('TCP_PORT_SCHEMA')
            if local_port != 8080:
                continue
            matched += 1
            category = {'0A': 'LISTEN', '01': 'ESTABLISHED',
                        '08': 'CLOSE_WAIT', '03': 'SYN_RECV'}.get(fields[3], 'OTHER_OWNED')
            count[category] += 1
    after = process_once(pid)
    require(before == after and before['state'] not in ('Z', 'X'), 'PROXY_IDENTITY_CHANGED')
    require(count['LISTEN'] >= 1, 'PROXY_LISTENER_MISSING')
    return {'port': 8080, 'owned_connections': matched, 'state_counts': count,
            'nonlistener_connections': matched - count['LISTEN'],
            'identity_stable': True, 'peer_addresses_exported': False,
            'idle_permission': False}


def sample(index):
    result = {'sample': index, 'observed_at': time.time(), 'path': str(COUNTER),
              'state': 'UNAVAILABLE', 'raw_content_exported': False}
    try:
        raw, info = read_regular(COUNTER, 8192)
        result.update(metadata=info, sha256=sha(raw))
        data = strict_json(raw)
        require(isinstance(data, dict), 'COUNTER_OBJECT')
        inflight = data.get('inflight')
        require(type(inflight) is int and 0 <= inflight <= 1000000, 'COUNTER_INFLIGHT_SCHEMA')
        result['inflight'] = inflight
        for key in ('last_start', 'last_end', 'last_ts'):
            value = data.get(key)
            require(type(value) in (int, float) and math.isfinite(value) and value >= 0, 'COUNTER_TIME_SCHEMA')
            result[key] = value
        result['observed_at'] = time.time()
        result['age_seconds'] = {key: round(result['observed_at'] - result[key], 3)
                                 for key in ('last_start', 'last_end', 'last_ts')}
        result['last_end_at_or_after_start'] = result['last_end'] >= result['last_start']
        result['state'] = 'OBSERVED'
    except (OSError, ValueError, UnicodeError, Hold) as error:
        result['error'] = safe_error(error)
    try:
        result['proxy_tcp'] = proxy_tcp_counts()
    except (OSError, ValueError, UnicodeError, Hold) as error:
        result['proxy_tcp_error'] = safe_error(error)
    return result


def main():
    previous = signal.getsignal(signal.SIGALRM)
    def expire(signum, frame):
        raise Deadline()
    signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, 20)
    record = {'schema': 'NOX_CHAT_FOREGROUND_COUNTER_OBSERVE_V1', 'started_at': time.time(),
              'read_only': True, 'source_writes': 0, 'counter_resets': 0, 'service_restarts': 0,
              'model_calls': 0, 'authentication_calls': 0, 'request_liveness_inferred': False,
              'atomic_admission_fence': False, 'sample_interval_seconds': 1}
    complete = False
    try:
        before = protected()
        record['protected_before'] = before
        record['sources'], record['counter_path_proof'] = source_path_proof()
        record['samples'] = [sample(1)]
        time.sleep(1)
        record['samples'].append(sample(2))
        after = protected()
        record['protected_after'] = after
        record['protected_stable'] = all(before[name]['matches'] and after[name]['matches'] for name in EXPECTED)
        end_sources, end_path = source_path_proof()
        record['sources_unchanged'] = end_sources == record['sources'] and end_path == record['counter_path_proof']
        first, second = record['samples']
        observed = first['state'] == second['state'] == 'OBSERVED'
        record['counter_unchanged_between_samples'] = observed and first['sha256'] == second['sha256']
        record['both_observed_zero'] = observed and first['inflight'] == second['inflight'] == 0
        record['proxy_tcp_stable'] = (first.get('proxy_tcp') == second.get('proxy_tcp') and
                                     isinstance(first.get('proxy_tcp'), dict))
        record['reconciliation_authorized'] = False
        complete = observed and record['protected_stable'] and record['sources_unchanged']
        record['state'] = 'READ_ONLY_COUNTER_OBSERVED' if complete else 'INCOMPLETE_COUNTER_OBSERVATION'
    except BaseException as error:
        record.update(state='HOLD_COUNTER_OBSERVATION', reason=safe_error(error))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    record['finished_at'] = time.time()
    raw = json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)
    require(len(raw.encode()) <= 32768, 'OUTPUT_BOUND')
    print('NOX_MAINT_CHAT_FOREGROUND_COUNTER_OBSERVE=' + raw, flush=True)
    print('NOX_MAINT_INSPECT_COMPLETE=' + str(bool(complete)).lower(), flush=True)
    return 0 if complete else 2


if __name__ == '__main__':
    raise SystemExit(main())
