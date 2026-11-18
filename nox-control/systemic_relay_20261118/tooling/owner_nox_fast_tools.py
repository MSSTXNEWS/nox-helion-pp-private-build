#!/usr/bin/env python3
"""Small, pinned, read-only source tools for NOX operators and task producers.

The installed nox-fast shim supplies the exact manifest and its SHA256.
Examples after installation:
  nox-fast context --file forge_split_guard.py --symbol bounded_split_lines
  nox-fast search --pattern time.monotonic --file nox_runpod/teacher_mesh/v38/durable_runtime.py
  nox-fast check --file forge_split_guard.py
  nox-fast status

Results describe bounded source snapshots, never execution or task acceptance.
No dependency installation, shell command, autofix, cache, or network is used.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import time
import tokenize

ROOT = Path('/root/nox/projects/owner_executor/source_workspace')
CONFIG = Path('/root/nox/config/owner_native_subagents.json')
RELEASE = Path('/root/nox/tools/acceleration/releases/20261118-v1')
VERSIONS = {'uv': '0.13.9', 'uvx': '0.13.9', 'ruff': '0.17.5', 'rg': '15.2.0'}
MAX_SOURCE = 512 * 1024
MAX_TOTAL = 16 * 1024 * 1024
MAX_FILES = MAX_MATCHES = 100
MAX_OUTPUT = 64 * 1024
WALL_SECONDS = 10
SHA = re.compile(r'[a-f0-9]{64}')


class Hold(RuntimeError):
    pass


def require(value, reason):
    if not value:
        raise Hold(reason)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def relative(value):
    require(isinstance(value, str) and 0 < len(value) <= 240
            and not value.startswith('/') and '\\' not in value and '\x00' not in value
            and all(part and not part.startswith('.') for part in value.split('/')), 'SOURCE_PATH')
    return value


def identity(info):
    return (info.st_dev, info.st_ino, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def open_regular(path):
    """Walk anchored directory descriptors; no component may be a symlink."""
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'ABSOLUTE_PATH')
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory)
    finally:
        os.close(directory)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'REGULAR_FILE_REQUIRED')
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_exact(path, limit):
    fd = open_regular(path)
    try:
        before = os.fstat(fd)
        require(0 <= before.st_size <= limit, 'FILE_SIZE')
        chunks, size = [], 0
        while True:
            raw = os.read(fd, min(65536, before.st_size - size + 1))
            if not raw:
                break
            size += len(raw)
            require(size <= before.st_size, 'FILE_CHANGED')
            chunks.append(raw)
        require(size == before.st_size and identity(before) == identity(os.fstat(fd)), 'FILE_CHANGED')
        return b''.join(chunks)
    finally:
        os.close(fd)


def strict_json(raw):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: require(False, 'NONFINITE_JSON'))


def load_scope(args):
    path = Path(args.manifest)
    require(path.is_absolute() and path.is_relative_to(RELEASE)
            and SHA.fullmatch(args.manifest_sha256), 'MANIFEST_REFERENCE')
    raw = read_exact(path, 65536)
    require(sha(raw) == args.manifest_sha256, 'MANIFEST_PIN')
    manifest = strict_json(raw)
    require(manifest.get('schema') == 'NOX_ACCELERATION_INSTALLED_V1'
            and isinstance(manifest.get('tools'), dict)
            and set(manifest['tools']) == set(VERSIONS), 'MANIFEST_SCHEMA')
    for name, version in VERSIONS.items():
        entry = manifest['tools'][name]
        folder = 'uv' if name == 'uvx' else name
        require(isinstance(entry, dict) and entry.get('version') == version
                and entry.get('path') == str(RELEASE / folder / version / name)
                and isinstance(entry.get('sha256'), str) and SHA.fullmatch(entry['sha256']), 'TOOL_MANIFEST')
    config_raw = read_exact(CONFIG, 2 * 1024 * 1024)
    config = strict_json(config_raw)
    require(config.get('schema') == 'NOX_NATIVE_SUBAGENT_BINDING_V1'
            and config.get('owner_authorized') is True and config.get('instance_id') == 60509551,
            'OWNER_SCOPE')
    scope = config['project_executor']['roots']['NOX_PROJECT_SOURCE']
    require(scope.get('path') == str(ROOT) and scope.get('integration_kind') == 'SOURCE_WORKSPACE'
            and isinstance(scope.get('allowed_paths'), list) and 1 <= len(scope['allowed_paths']) <= 256,
            'PROJECT_SCOPE')
    for item in [*scope['allowed_paths'], *scope.get('deny_paths', [])]:
        relative(item[:-1] if item.endswith('/') else item)
    return manifest, scope, sha(config_raw)


def source_snapshots(scope, files):
    def allowed(path, patterns):
        return any(path == item or (item.endswith('/') and path.startswith(item)) for item in patterns)
    files = files or scope['allowed_paths']
    require(1 <= len(files) <= MAX_FILES and len(set(files)) == len(files), 'SOURCE_COUNT')
    result, total = {}, 0
    for path in sorted(files):
        relative(path)
        require(allowed(path, scope['allowed_paths'])
                and not allowed(path, scope.get('deny_paths', [])), 'SOURCE_NOT_ALLOWED')
        raw = read_exact(ROOT / path, MAX_SOURCE)
        total += len(raw)
        require(total <= MAX_TOTAL, 'SOURCE_TOTAL_SIZE')
        result[path] = raw
    return result


def tool_fd(manifest, name):
    entry = manifest['tools'][name]
    fd = open_regular(entry['path'])
    try:
        before = os.fstat(fd)
        require(before.st_uid == os.geteuid() and before.st_nlink == 1
                and not before.st_mode & 0o022 and before.st_mode & 0o111
                and 0 < before.st_size <= 128 * 1024 * 1024, 'BINARY_SCOPE')
        digest, size = hashlib.sha256(), 0
        while True:
            raw = os.read(fd, 65536)
            if not raw:
                break
            size += len(raw)
            require(size <= before.st_size, 'BINARY_CHANGED')
            digest.update(raw)
        require(size == before.st_size and digest.hexdigest() == entry['sha256']
                and identity(before) == identity(os.fstat(fd)), 'BINARY_PIN')
        return fd
    except BaseException:
        os.close(fd)
        raise


def run_tool(fd, argv, raw, deadline):
    """Execute the verified open inode, with bounded simultaneous pipe I/O."""
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
           'RAYON_NUM_THREADS': '1', 'NO_COLOR': '1', 'PYTHONDONTWRITEBYTECODE': '1',
           'UV_PYTHON_DOWNLOADS': 'never', 'UV_NO_PROGRESS': '1'}
    proc = subprocess.Popen(argv, executable='/proc/self/fd/' + str(fd), pass_fds=(fd,),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=str(ROOT), env=env, shell=False, start_new_session=True, bufsize=0)
    output, error, offset = bytearray(), bytearray(), 0
    try:
        with selectors.DefaultSelector() as selector:
            for stream, event in ((proc.stdin, selectors.EVENT_WRITE),
                                  (proc.stdout, selectors.EVENT_READ), (proc.stderr, selectors.EVENT_READ)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, event)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                require(remaining > 0, 'TIME_BUDGET')
                for key, _ in selector.select(min(.1, remaining)):
                    stream = key.fileobj
                    if stream is proc.stdin:
                        try:
                            offset += os.write(stream.fileno(), raw[offset:offset + 65536]) if offset < len(raw) else 0
                        except BrokenPipeError:
                            offset = len(raw)
                        if offset == len(raw):
                            selector.unregister(stream)
                            stream.close()
                    else:
                        chunk = os.read(stream.fileno(), 65536)
                        if not chunk:
                            selector.unregister(stream)
                            stream.close()
                            continue
                        (output if stream is proc.stdout else error).extend(chunk)
                        require(len(output) + len(error) <= MAX_OUTPUT, 'TOOL_OUTPUT_BOUND')
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'TIME_BUDGET')
            proc.wait(timeout=remaining)
        require(proc.returncode in (0, 1), 'TOOL_EXIT_' + str(proc.returncode))
        return proc.returncode, bytes(output), bytes(error)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=1)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if not stream.closed:
                stream.close()


def symbols(tree):
    result = []
    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = '.'.join((*prefix, child.name))
                start = min([child.lineno, *(item.lineno for item in child.decorator_list)])
                result.append({'symbol': name, 'kind': type(child).__name__,
                               'start_line': start, 'end_line': child.end_lineno})
                visit(child, (*prefix, child.name))
            else:
                visit(child, prefix)
    visit(tree, ())
    return result


def context(args, snapshots):
    raw = snapshots[args.file]
    if args.expected_sha256:
        require(SHA.fullmatch(args.expected_sha256) and sha(raw) == args.expected_sha256, 'SOURCE_PIN')
    entries = symbols(ast.parse(raw, filename=args.file))
    result = {'file': args.file, 'source_sha256': sha(raw), 'source_bytes': len(raw)}
    if not args.symbol:
        return {**result, 'symbols': entries[:100], 'symbol_count': len(entries), 'truncated': len(entries) > 100}
    matching = [row for row in entries if row['symbol'] == args.symbol]
    require(len(matching) == 1, 'SYMBOL_MISSING_OR_AMBIGUOUS')
    selected = matching[0]
    # Python source line numbers use LF/CR/CRLF, not form-feed or vertical-tab.
    lines = re.findall(rb'[^\r\n]*(?:\r\n|\r|\n|$)', raw)
    if lines and not lines[-1]:
        lines.pop()
    start, end = selected['start_line'] - 1, selected['end_line']
    require(0 <= args.offset < end - start and 1 <= args.lines <= 100, 'CONTEXT_RANGE')
    first, last = start + args.offset, min(start + args.offset + args.lines, end)
    encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
    segment = b''.join(lines[first:last])
    return {**result, **selected, 'symbol_sha256': sha(b''.join(lines[start:end])),
            'context_start_line': first + 1, 'context_end_line': last,
            'context_sha256': sha(segment), 'text': segment.decode(encoding),
            'complete_symbol': first == start and last == end,
            'next_offset': last - start if last < end else None}


def search(args, snapshots, manifest, deadline):
    require(0 < len(args.pattern.encode()) <= 256 and '\n' not in args.pattern and '\x00' not in args.pattern,
            'SEARCH_PATTERN')
    result = {'matches': [], 'searched_files': [], 'truncated': False}
    fd = tool_fd(manifest, 'rg')
    try:
        for path, raw in snapshots.items():
            _, output, error = run_tool(fd, ['rg', '--no-config', '--fixed-strings', '--json',
                '--threads', '1', '--max-count', str(MAX_MATCHES - len(result['matches'])),
                '--color', 'never', '--', args.pattern, '-'], raw, deadline)
            require(not error, 'SEARCH_DIAGNOSTIC')
            result['searched_files'].append({'path': path, 'sha256': sha(raw), 'bytes': len(raw)})
            for line in output.splitlines():
                event = strict_json(line)
                if event.get('type') != 'match':
                    continue
                row = event['data']
                text = row['lines'].get('text')
                require(isinstance(text, str), 'SEARCH_NON_TEXT_MATCH')
                match = {'file': path, 'source_sha256': sha(raw), 'line': row['line_number'],
                         'line_sha256': sha(text.encode()), 'text': text[:1024],
                         'text_truncated': len(text) > 1024,
                         'submatches': [{'start_byte': item['start'], 'end_byte': item['end']}
                                        for item in row['submatches'][:100]]}
                result['matches'].append(match)
                require(len(encoded(result)) <= MAX_OUTPUT - 4096, 'SEARCH_RESULT_BOUND')
            if len(result['matches']) >= MAX_MATCHES:
                result['truncated'] = True
                break
    finally:
        os.close(fd)
    return result


def check(snapshots, manifest, deadline):
    checks = []
    fd = tool_fd(manifest, 'ruff')
    try:
        for path, raw in snapshots.items():
            require(path.endswith(('.py', '.pyi')), 'PYTHON_FILE_REQUIRED')
            code, output, error = run_tool(fd, ['ruff', 'check', '--isolated', '--no-cache', '--no-fix',
                '--select', 'E9', '--output-format', 'json', '--stdin-filename', path, '-'], raw, deadline)
            require(not error, 'CHECK_DIAGNOSTIC')
            findings = strict_json(output)
            require(isinstance(findings, list), 'CHECK_OUTPUT')
            checks.append({'file': path, 'source_sha256': sha(raw), 'exit_code': code,
                           'syntax_ok': code == 0, 'findings': findings})
            require(len(encoded(checks)) <= MAX_OUTPUT - 4096, 'CHECK_OUTPUT_BOUND')
    finally:
        os.close(fd)
    return {'checks': checks, 'syntax_ok': all(row['syntax_ok'] for row in checks),
            'semantic_validity_verified': False, 'tests_executed': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--manifest-sha256', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status')
    one = commands.add_parser('context')
    one.add_argument('--file', required=True)
    one.add_argument('--symbol')
    one.add_argument('--expected-sha256')
    one.add_argument('--offset', type=int, default=0)
    one.add_argument('--lines', type=int, default=100)
    lookup = commands.add_parser('search')
    lookup.add_argument('--file', action='append')
    lookup.add_argument('--pattern', required=True)
    lint = commands.add_parser('check')
    lint.add_argument('--file', action='append', required=True)
    args = parser.parse_args()
    started = time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: require(False, 'TIME_BUDGET'))
    signal.setitimer(signal.ITIMER_REAL, WALL_SECONDS)
    base = {'schema': 'NOX_FAST_TOOLS_RESULT_V1', 'command': args.command, 'read_only': True,
            'original_task_accepted': False,
            'manifest_sha256': args.manifest_sha256 if SHA.fullmatch(args.manifest_sha256) else None}
    status = 0
    try:
        manifest, scope, config_sha = load_scope(args)
        base['config_sha256'] = config_sha
        if args.command == 'status':
            for name in VERSIONS:
                os.close(tool_fd(manifest, name))
            result = {'tools': manifest['tools'], 'binary_pins_verified': True,
                      'commands': ['context', 'search', 'check', 'status'], 'project_root': str(ROOT),
                      'uv_execution_enabled': False, 'network_enabled': False,
                      'limits': {'source_bytes': MAX_SOURCE, 'source_total_bytes': MAX_TOTAL,
                                 'files': MAX_FILES, 'output_bytes': MAX_OUTPUT, 'wall_seconds': WALL_SECONDS}}
        else:
            files = [args.file] if args.command == 'context' else args.file
            snapshots = source_snapshots(scope, files)
            if args.command == 'context':
                result = context(args, snapshots)
            elif args.command == 'search':
                result = search(args, snapshots, manifest, started + WALL_SECONDS)
            else:
                result = check(snapshots, manifest, started + WALL_SECONDS)
                status = 0 if result['syntax_ok'] else 1
        response = {**base, 'state': 'READ_ONLY_RESULT', **result}
    except (Hold, OSError, ValueError, KeyError, TypeError, RecursionError, subprocess.TimeoutExpired) as exc:
        response = {**base, 'state': 'HOLD', 'reason': str(exc) if isinstance(exc, Hold) else type(exc).__name__}
        status = 2
    except SyntaxError as exc:
        response = {**base, 'state': 'SYNTAX_ERROR', 'line': exc.lineno, 'column': exc.offset,
                    'message': exc.msg, 'semantic_validity_verified': False}
        status = 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    response['elapsed_ms'] = int((time.monotonic() - started) * 1000)
    raw = encoded(response)
    if len(raw) + 1 > MAX_OUTPUT:
        raw = encoded({**base, 'state': 'HOLD', 'reason': 'OUTPUT_BOUND'})
        status = 2
    sys.stdout.buffer.write(raw + b'\n')
    return status


if __name__ == '__main__':
    raise SystemExit(main())
