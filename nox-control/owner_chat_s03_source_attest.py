#!/usr/bin/env python3
"""Bounded, read-only static attestation of fixed chat and S03 source files.

No target module is imported, compiled, executed, or invoked. This script is
intentionally not wired to an owner action.
"""
from __future__ import annotations

import ast
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat

ROOT = Path('/root/nox')
TARGETS = (('chat_proxy', 'scripts/chat_proxy.py'),
           ('s03_memory', 'scripts/s03_memory.py'))
MAX_SOURCE_BYTES = 1024 * 1024
MAX_AST_NODES = 100_000
MAX_FUNCTIONS = 48
MAX_IMPORTS = 32
MAX_CALL_SITES = 64
MAX_REPORT_BYTES = 48 * 1024
IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,79}$')
WRITER_NAME = re.compile(
    r'(?:write|remember|store|insert|upsert|save|append|persist|record|commit|create|add|put)',
    re.I)
DML = re.compile(r'\b(?:INSERT|REPLACE|UPDATE|DELETE)\b', re.I)
S03_TABLE = re.compile(r'\bs03_items\b', re.I)


class Hold(RuntimeError):
    def __init__(self, code):
        self.code = code if re.fullmatch(r'HOLD_[A-Z0-9_]{1,64}', code) else \
            'HOLD_SOURCE_ATTESTATION_INTERNAL'
        super().__init__(self.code)


def _error(exc, directory=False):
    if exc.errno == errno.ELOOP:
        return Hold('HOLD_SYMLINK')
    if isinstance(exc, FileNotFoundError):
        return Hold('HOLD_PATH_COMPONENT' if directory else 'HOLD_FILE_MISSING')
    if exc.errno == errno.ENOTDIR:
        return Hold('HOLD_PATH_COMPONENT' if directory else 'HOLD_FILE_TYPE')
    return Hold('HOLD_SOURCE_UNREADABLE')


def _fixed_parts(root, relative):
    if not isinstance(root, Path) or not root.is_absolute():
        raise Hold('HOLD_ROOT_NOT_ABSOLUTE')
    if relative not in {path for _, path in TARGETS}:
        raise Hold('HOLD_TARGET_NOT_ALLOWLISTED')
    rel = Path(relative)
    if rel.is_absolute() or any(part in ('', '.', '..') for part in rel.parts):
        raise Hold('HOLD_TARGET_PATH_SHAPE')
    dirs = list(root.parts[1:]) + list(rel.parts[:-1])
    if any(part in ('', '.', '..') for part in dirs):
        raise Hold('HOLD_ROOT_PATH_SHAPE')
    return dirs, rel.name


def _open_dirs(root, relative):
    if not hasattr(os, 'O_NOFOLLOW') or not hasattr(os, 'O_DIRECTORY'):
        raise Hold('HOLD_NOFOLLOW_UNAVAILABLE')
    dirs, leaf = _fixed_parts(root, relative)
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, 'O_CLOEXEC', 0)
    fds, ids = [os.open('/', flags)], []
    try:
        info = os.fstat(fds[0])
        ids.append((info.st_dev, info.st_ino))
        for part in dirs:
            try:
                entry = os.stat(part, dir_fd=fds[-1], follow_symlinks=False)
            except OSError as exc:
                raise _error(exc, directory=True) from exc
            if stat.S_ISLNK(entry.st_mode):
                raise Hold('HOLD_SYMLINK')
            if not stat.S_ISDIR(entry.st_mode):
                raise Hold('HOLD_PATH_COMPONENT')
            try:
                fd = os.open(part, flags | os.O_NOFOLLOW, dir_fd=fds[-1])
            except OSError as exc:
                raise _error(exc, directory=True) from exc
            fds.append(fd)
            info = os.fstat(fd)
            ids.append((info.st_dev, info.st_ino))
        return fds, tuple(ids), leaf
    except Exception:
        _close(fds)
        raise


def _close(fds):
    for fd in reversed(fds):
        try:
            os.close(fd)
        except OSError:
            pass


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _safe_read(root, relative):
    """Read one allowlisted regular file through a stable no-follow descriptor."""
    fds, dir_ids, leaf = _open_dirs(root, relative)
    file_fd = None
    try:
        try:
            entry = os.stat(leaf, dir_fd=fds[-1], follow_symlinks=False)
            if stat.S_ISLNK(entry.st_mode):
                raise Hold('HOLD_SYMLINK')
            if not stat.S_ISREG(entry.st_mode):
                raise Hold('HOLD_FILE_TYPE')
            file_fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                              getattr(os, 'O_CLOEXEC', 0), dir_fd=fds[-1])
        except OSError as exc:
            raise _error(exc) from exc
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode):
            raise Hold('HOLD_FILE_TYPE')
        if before.st_size < 0 or before.st_size > MAX_SOURCE_BYTES:
            raise Hold('HOLD_SOURCE_OVERSIZED')
        if before.st_nlink != 1:
            raise Hold('HOLD_SOURCE_LINK_COUNT')
        chunks, total = [], 0
        while total <= MAX_SOURCE_BYTES:
            try:
                block = os.read(file_fd, min(65536, MAX_SOURCE_BYTES + 1 - total))
            except OSError as exc:
                raise Hold('HOLD_SOURCE_READ_FAILED') from exc
            if not block:
                break
            chunks.append(block)
            total += len(block)
        after = os.fstat(file_fd)
        if total > MAX_SOURCE_BYTES:
            raise Hold('HOLD_SOURCE_OVERSIZED')
        if _identity(before) != _identity(after) or total != after.st_size:
            raise Hold('HOLD_SOURCE_CHANGED_DURING_READ')

        try:
            current = os.stat(leaf, dir_fd=fds[-1], follow_symlinks=False)
            check_fds, check_ids, check_leaf = _open_dirs(root, relative)
        except OSError as exc:
            raise Hold('HOLD_SOURCE_PATH_CHANGED') from exc
        try:
            if (stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(current.st_mode)
                    or (current.st_dev, current.st_ino) != (after.st_dev, after.st_ino)
                    or check_ids != dir_ids or check_leaf != leaf):
                raise Hold('HOLD_SOURCE_PATH_CHANGED')
            check = os.stat(check_leaf, dir_fd=check_fds[-1], follow_symlinks=False)
            if (not stat.S_ISREG(check.st_mode)
                    or (check.st_dev, check.st_ino) != (after.st_dev, after.st_ino)):
                raise Hold('HOLD_SOURCE_PATH_CHANGED')
        except OSError as exc:
            raise Hold('HOLD_SOURCE_PATH_CHANGED') from exc
        finally:
            _close(check_fds)

        identity_sha = hashlib.sha256(
            ':'.join(str(value) for value in _identity(after)).encode('ascii')).hexdigest()
        metadata = {'bytes': total, 'uid': after.st_uid, 'gid': after.st_gid,
                    'mode': format(stat.S_IMODE(after.st_mode), '04o'),
                    'mtime_ns': after.st_mtime_ns, 'ctime_ns': after.st_ctime_ns,
                    'file_identity_sha256': identity_sha}
        return b''.join(chunks), metadata
    finally:
        if file_fd is not None:
            try:
                os.close(file_fd)
            except OSError:
                pass
        _close(fds)


def _ident(value):
    return value if isinstance(value, str) and IDENT.fullmatch(value) else None


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        name = _ident(node.attr)
        if name is None:
            return None
        parts.append(name)
        node = node.value
    if not isinstance(node, ast.Name) or _ident(node.id) is None:
        return None
    parts.append(node.id)
    parts.reverse()
    value = '.'.join(parts)
    return value if len(value) <= 200 else None


def _parse(raw, relative):
    try:
        source = raw.decode('utf-8', errors='strict')
    except UnicodeDecodeError as exc:
        raise Hold('HOLD_SOURCE_INVALID_UTF8') from exc
    try:
        tree = ast.parse(source, filename=relative, mode='exec', type_comments=True)
        count = 0
        for _ in ast.walk(tree):
            count += 1
            if count > MAX_AST_NODES:
                raise Hold('HOLD_AST_LIMIT')
    except Hold:
        raise
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        raise Hold('HOLD_AST_INVALID') from exc
    return tree, count


def _chat_edges(tree):
    module_aliases, imported_symbols, imports = set(), {}, []
    dynamic = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name == 's03_memory':
                    alias = _ident(item.asname or 's03_memory')
                    if alias:
                        module_aliases.add(alias)
                        imports.append({'kind': 'module', 'alias': alias})
        elif isinstance(node, ast.ImportFrom) and node.module == 's03_memory':
            for item in node.names:
                if item.name == '*':
                    dynamic = True
                    continue
                symbol, alias = _ident(item.name), _ident(item.asname or item.name)
                if symbol and alias:
                    imported_symbols[alias] = symbol
                    imports.append({'kind': 'symbol', 'symbol': symbol, 'alias': alias})
    # Scan calls after collecting imports. A generic getattr(config, "x")
    # is not a dynamic S03 writer link; all actual S03 aliases remain fenced.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        dotted = _dotted(node.func)
        call_name = dotted.rsplit('.', 1)[-1] if dotted else None
        dynamic_target = any(
            isinstance(part, ast.Constant) and part.value == 's03_memory'
            for arg in node.args for part in ast.walk(arg)
        )
        first = _dotted(node.args[0]) if node.args else None
        attr = node.args[1].value if (len(node.args) > 1 and
            isinstance(node.args[1], ast.Constant) and
            type(node.args[1].value) is str) else None
        dynamic_s03_getattr = (call_name == 'getattr' and (
            (first is not None and first.split('.')[0] in module_aliases)
            or first in imported_symbols
            or attr in ('remember', 'persist_turn', 'ledger_append')
        ))
        dynamic = (dynamic or dynamic_target or dynamic_s03_getattr
                   or call_name in ('__import__', 'import_module', 'eval', 'exec'))
    if len(imports) > MAX_IMPORTS:
        return {'imports': imports[:MAX_IMPORTS], 'imports_truncated': True,
                'call_sites': [], 'call_sites_truncated': False,
                'dynamic_access_detected': dynamic, 'static_scope_complete': False}

    calls, scope = [], []

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            scope.append(_ident(node.name) or 'UNSAFE_FUNCTION')
            for child in node.body:
                self.visit(child)
            scope.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node):
            scope.append(_ident(node.name) or 'UNSAFE_CLASS')
            for child in node.body:
                self.visit(child)
            scope.pop()

        def visit_Call(self, node):
            if isinstance(node.func, ast.Attribute):
                dotted = _dotted(node.func)
                if dotted and dotted.split('.')[0] in module_aliases:
                    calls.append({'caller': '.'.join(scope) or '<module>',
                                  'symbol': dotted.split('.')[-1], 'kind': 'module_attribute'})
            elif isinstance(node.func, ast.Name) and node.func.id in imported_symbols:
                calls.append({'caller': '.'.join(scope) or '<module>',
                              'symbol': imported_symbols[node.func.id], 'kind': 'imported_symbol'})
            self.generic_visit(node)

    Visitor().visit(tree)
    truncated = len(calls) >= MAX_CALL_SITES
    return {'imports': sorted(imports, key=lambda row: (row['kind'], row.get('symbol', ''),
                                                        row.get('alias', ''))),
            'imports_truncated': False, 'call_sites': calls[:MAX_CALL_SITES],
            'call_sites_truncated': truncated, 'dynamic_access_detected': dynamic,
            'static_scope_complete': not dynamic and not truncated}


def _signature(node, qualname):
    args = node.args
    posonly, positional = list(args.posonlyargs), list(args.args)
    all_defaults = ([False] * max(0, len(posonly) + len(positional) - len(args.defaults))
                    + [True] * len(args.defaults))
    row = {'qualname': qualname, 'async': isinstance(node, ast.AsyncFunctionDef),
           'posonly': [_ident(arg.arg) or 'UNSAFE_IDENTIFIER' for arg in posonly],
           'posonly_has_default': all_defaults[:len(posonly)],
           'positional': [_ident(arg.arg) or 'UNSAFE_IDENTIFIER' for arg in positional],
           'positional_has_default': all_defaults[len(posonly):],
           'vararg': _ident(args.vararg.arg) if args.vararg else None,
           'kwonly': [_ident(arg.arg) or 'UNSAFE_IDENTIFIER' for arg in args.kwonlyargs],
           'kwonly_required': [value is None for value in args.kw_defaults],
           'kwarg': _ident(args.kwarg.arg) if args.kwarg else None,
           'argument_annotations_present': any(arg.annotation is not None for arg in
               posonly + positional + list(args.kwonlyargs) +
               ([args.vararg] if args.vararg else []) + ([args.kwarg] if args.kwarg else [])),
           'return_annotation_present': node.returns is not None,
           'positional_default_count': len(args.defaults),
           'kwonly_default_count': sum(value is not None for value in args.kw_defaults)}
    body_nodes, return_none, return_value = [], 0, 0
    stack = list(node.body)
    while stack:
        child = stack.pop()
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body_nodes.append(child)
        if isinstance(child, ast.Return):
            if child.value is None or isinstance(child.value, ast.Constant) and child.value.value is None:
                return_none += 1
            else:
                return_value += 1
        stack.extend(ast.iter_child_nodes(child))
    literals = [item.value for item in body_nodes
                if isinstance(item, ast.Constant) and isinstance(item.value, str)]
    dml_s03 = any(DML.search(value) and S03_TABLE.search(value) for value in literals)
    name_candidate = bool(WRITER_NAME.search(node.name))
    if not (name_candidate or dml_s03):
        return None
    try:
        row.update({'candidate_reasons': [name for name, matched in
                    (('writer_name', name_candidate), ('s03_table_dml', dml_s03)) if matched],
                    'return_none_count': return_none, 'return_value_count': return_value,
                    'commit_call': any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                                       and n.func.attr == 'commit' for item in body_nodes
                                       for n in ast.walk(item)),
                    'rollback_call': any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                                         and n.func.attr == 'rollback' for item in body_nodes
                                         for n in ast.walk(item)),
                    'context_manager_count': sum(isinstance(n, (ast.With, ast.AsyncWith))
                                                 for item in body_nodes for n in ast.walk(item)),
                    'function_ast_sha256': hashlib.sha256(ast.dump(
                        node, annotate_fields=True, include_attributes=False).encode('utf-8')).hexdigest()})
    except (ValueError, RecursionError, MemoryError) as exc:
        raise Hold('HOLD_WRITER_AST_LIMIT') from exc
    return row


def _writers(tree):
    rows = []

    def visit_scope(node, prefix):
        for child in getattr(node, 'body', ()):
            if isinstance(child, ast.ClassDef):
                name = _ident(child.name)
                if name:
                    visit_scope(child, prefix + [name])
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = _ident(child.name)
                if name is None:
                    raise Hold('HOLD_WRITER_SIGNATURE_SHAPE')
                row = _signature(child, '.'.join(prefix + [name]))
                if row:
                    rows.append(row)
                visit_scope(child, prefix + [name])

    try:
        visit_scope(tree, [])
    except (RecursionError, MemoryError) as exc:
        raise Hold('HOLD_AST_LIMIT') from exc
    if len(rows) > MAX_FUNCTIONS:
        raise Hold('HOLD_WRITER_SIGNATURE_LIMIT')
    return rows


def _record(label, relative, root):
    try:
        raw, meta = _safe_read(root, relative)
    except Hold as exc:
        return {'target': label, 'relative_path': relative, 'status': exc.code}
    record = {'target': label, 'relative_path': relative, **meta,
              'sha256': hashlib.sha256(raw).hexdigest()}
    try:
        tree, count = _parse(raw, relative)
    except Hold as exc:
        record['status'] = exc.code
        return record
    record.update({'status': 'AST_PARSED', 'ast_node_count': count,
                   'source_text_emitted': False, 'source_literals_emitted': False})
    if label == 'chat_proxy':
        record.update(_chat_edges(tree))
        return record
    try:
        record['writer_signatures'] = _writers(tree)
    except Hold as exc:
        record['status'] = exc.code
        return record
    record['writer_signature_count'] = len(record['writer_signatures'])
    return record


def attest_sources(root=ROOT):
    """Attest exactly two fixed files, without accepting user-supplied paths."""
    root = Path(root)
    records = [_record(label, relative, root) for label, relative in TARGETS]
    proxy, memory = records
    calls = proxy.get('call_sites', [])
    called = {row.get('symbol') for row in calls if isinstance(row, dict)}
    writers = memory.get('writer_signatures', [])
    exported = {row['qualname'] for row in writers if '.' not in row['qualname']}
    links = [row for row in writers if row['qualname'] in called and '.' not in row['qualname']]
    complete = (all(row.get('status') == 'AST_PARSED' for row in records)
                and bool(links) and proxy.get('static_scope_complete') is True
                and proxy.get('imports_truncated') is False
                and proxy.get('call_sites_truncated') is False
                and bool(called & exported))
    report = {'schema': 'NOX_CHAT_S03_SOURCE_ATTESTATION_V1',
              'status': 'SOURCE_STATIC_ATTESTED' if complete else 'HOLD_STATIC_WRITER_LINK_INCOMPLETE',
              'complete': complete, 'targets': records,
              'chat_to_s03_writer_links': links[:MAX_FUNCTIONS],
              'guarantees': {'target_paths_fixed': True, 'target_modules_imported': False,
                  'target_code_executed': False, 'subprocesses_run': False,
                  'database_opened': False, 'chat_rows_read': False,
                  'source_text_emitted': False, 'source_literals_emitted': False}}
    encoded = json.dumps(report, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
    if len(encoded.encode('ascii')) > MAX_REPORT_BYTES:
        return {'schema': 'NOX_CHAT_S03_SOURCE_ATTESTATION_V1',
                'status': 'HOLD_REPORT_OVERSIZED', 'complete': False, 'targets': [],
                'guarantees': report['guarantees']}
    return report


def main():
    try:
        report = attest_sources()
    except Hold as exc:
        report = {'schema': 'NOX_CHAT_S03_SOURCE_ATTESTATION_V1',
                  'status': exc.code, 'complete': False}
    except Exception:
        report = {'schema': 'NOX_CHAT_S03_SOURCE_ATTESTATION_V1',
                  'status': 'HOLD_SOURCE_ATTESTATION_INTERNAL', 'complete': False}
    encoded = json.dumps(report, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
    if len(encoded.encode('ascii')) >= MAX_REPORT_BYTES:
        report = {'schema': 'NOX_CHAT_S03_SOURCE_ATTESTATION_V1',
                  'status': 'HOLD_REPORT_OVERSIZED', 'complete': False}
        encoded = json.dumps(report, separators=(',', ':'))
    print('NOX_MAINT_SOURCE_ATTESTATION=' + encoded, flush=True)
    complete = report.get('complete') is True
    print('NOX_MAINT_SOURCE_ATTESTATION_COMPLETE=' + str(complete).lower(), flush=True)
    return 0 if complete else 2


if __name__ == '__main__':
    raise SystemExit(main())
