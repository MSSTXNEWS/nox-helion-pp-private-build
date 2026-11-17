#!/usr/bin/env python3
"""Pinned source-only diagnosis of CHAT_PASSWORD_PATH -> SECRETS bindings.

Reads one fixed Python source file. Never reads a credential, imports native
code, executes the password reader, evaluates an expression or contacts HTTP.
All literal values are withheld; only syntax, names, origins and locations exit.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat

SOURCE = Path('/root/nox/scripts/chat_proxy.py')
SOURCE_SHA = 'a03119817d695b1dc7ca2681a60bc564a0aa891468582bbf11b70592e2b4dfd6'
MAX_SOURCE = 250000
MAX_OUTPUT = 24000
IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,95}')
MODULE = re.compile(r'[A-Za-z_][A-Za-z0-9_.]{0,191}')

def name(value):
    return value if isinstance(value, str) and IDENT.fullmatch(value) else '[IDENTIFIER_WITHHELD]'

def shape(node, depth=0, budget=None):
    """Explicit nonvalue projection; never ast.dump/unparse native source."""
    if budget is None: budget = [120]
    budget[0] -= 1
    if node is None: return {'node': 'ABSENT'}
    out = {'node': type(node).__name__}
    if depth >= 9 or budget[0] <= 0:
        out['truncated'] = True
        return out
    sub = lambda n: shape(n, depth + 1, budget)
    if isinstance(node, ast.Constant):
        out['literal_type'] = type(node.value).__name__
        out['value_withheld'] = True
    elif isinstance(node, ast.Name): out['identifier'] = name(node.id)
    elif isinstance(node, ast.Attribute): out.update(owner=sub(node.value), attribute=name(node.attr))
    elif isinstance(node, ast.Call):
        out.update(function=sub(node.func), args=[sub(n) for n in node.args[:8]],
                   keywords=[{'name': name(n.arg) if n.arg else '**', 'value_shape': sub(n.value)} for n in node.keywords[:8]])
    elif isinstance(node, ast.BinOp): out.update(operator=type(node.op).__name__, left=sub(node.left), right=sub(node.right))
    elif isinstance(node, ast.Subscript): out.update(owner=sub(node.value), index=sub(node.slice))
    elif isinstance(node, (ast.Tuple, ast.List, ast.Set)): out.update(count=len(node.elts), elements=[sub(n) for n in node.elts[:16]])
    elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        out.update(targets=[sub(n) for n in targets[:8]], value_shape=sub(node.value))
    elif isinstance(node, ast.Return): out['value_shape'] = sub(node.value)
    elif isinstance(node, ast.Try):
        out.update(body=[sub(n) for n in node.body[:8]],
                   handlers=[{'type_shape': sub(h.type), 'body': [sub(n) for n in h.body[:8]]} for h in node.handlers[:4]],
                   else_count=len(node.orelse), finally_count=len(node.finalbody))
    elif isinstance(node, ast.If):
        out.update(test_shape=sub(node.test), body_node_types=[type(n).__name__ for n in node.body[:16]],
                   else_node_types=[type(n).__name__ for n in node.orelse[:16]])
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        out.update(function_name=name(node.name), parameters=[name(a.arg) for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs][:32],
                   body=[sub(n) for n in node.body[:12]])
    else:
        out['child_node_types'] = [type(n).__name__ for n in ast.iter_child_nodes(node)][:16]
    return out

def target_names(node):
    if isinstance(node, ast.Name): return {node.id}
    if isinstance(node, (ast.Tuple, ast.List)):
        return set().union(*(target_names(n) for n in node.elts)) if node.elts else set()
    if isinstance(node, ast.Starred): return target_names(node.value)
    return set()

def describe_source(source):
    tree = ast.parse(source)
    bindings = {}; wildcards = []; readers = []; visits = 0
    def add(identifier, row, dependencies=()):
        if IDENT.fullmatch(identifier):
            bindings.setdefault(identifier, []).append((row, set(dependencies)))
    def walk(node, scope, context):
        nonlocal visits
        visits += 1
        if visits > 50000: raise ValueError('AST_LIMIT')
        location = {'line': getattr(node, 'lineno', None), 'scope': scope[:8], 'context': context[:8]}
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            ids = set().union(*(target_names(n) for n in targets))
            deps = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)} if node.value else set()
            for identifier in ids:
                add(identifier, {**location, 'binding_kind': type(node).__name__, 'statement_shape': shape(node)}, deps)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            module = node.module if isinstance(node, ast.ImportFrom) else None
            module = module if module is None or MODULE.fullmatch(module) else '[MODULE_WITHHELD]'
            for alias in node.names:
                row = {**location, 'binding_kind': type(node).__name__, 'module': module,
                       'level': node.level if isinstance(node, ast.ImportFrom) else 0,
                       'import_name': alias.name if MODULE.fullmatch(alias.name) or alias.name == '*' else '[NAME_WITHHELD]',
                       'alias': name(alias.asname) if alias.asname else None}
                if alias.name == '*': wildcards.append(row)
                else: add(alias.asname or alias.name.split('.')[0], row)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add(node.name, {**location, 'binding_kind': 'FunctionDef', 'function_name': name(node.name)})
            if node.name == '_read_chat_password': readers.append({**location, 'reader_shape': shape(node)})
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            scope = scope + [name(node.name)]
        for field, value in ast.iter_fields(node):
            children = value if isinstance(value, list) else [value]
            for child in children:
                if not isinstance(child, ast.AST): continue
                nested = context
                if isinstance(node, (ast.If, ast.Try, ast.With, ast.For, ast.While, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.ExceptHandler)):
                    nested = context + [type(node).__name__ + '.' + field]
                walk(child, scope, nested)
    walk(tree, [], [])
    pending = ['CHAT_PASSWORD_PATH', 'SECRETS']; seen = set(); output = []; unresolved = []
    while pending and len(seen) < 24:
        identifier = pending.pop(0)
        if identifier in seen or not IDENT.fullmatch(identifier): continue
        seen.add(identifier)
        rows = bindings.get(identifier, [])
        if not rows: unresolved.append(identifier)
        for row, deps in rows[:8]:
            output.append({'identifier': identifier, **row})
            pending.extend(sorted(n for n in deps if n not in ('Path', '__file__') and n not in seen))
    return {'bindings': output, 'dependency_identifiers': sorted(seen), 'unresolved_identifiers': sorted(unresolved),
            'wildcard_imports': wildcards[:8], 'password_readers': readers[:2],
            'dependency_limit_reached': bool(pending)}

def run():
    report = {'schema': 'NOX_CHAT_PASSWORD_PATH_AST_DIAGNOSTIC_V1', 'source_path': str(SOURCE),
              'expected_source_sha256': SOURCE_SHA, 'credential_file_read': False,
              'native_app_imported': False, 'password_reader_executed': False,
              'literal_values_exported': False, 'http_requests': 0, 'native_mutations': 0}
    if SOURCE.resolve() != SOURCE: raise ValueError('SOURCE_SYMLINK')
    fd = os.open(SOURCE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SOURCE: raise ValueError('SOURCE_TYPE_OR_SIZE')
        raw = os.pread(fd, MAX_SOURCE + 1, 0)
        after = os.fstat(fd)
        if len(raw) != info.st_size or (info.st_ino, info.st_dev, info.st_mtime_ns, info.st_ctime_ns) != (after.st_ino, after.st_dev, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('SOURCE_CHANGED')
    finally:
        os.close(fd)
    report['observed_source_sha256'] = hashlib.sha256(raw).hexdigest()
    if report['observed_source_sha256'] != SOURCE_SHA:
        return {**report, 'status': 'HOLD_SOURCE_SHA_CHANGED'}
    report.update(describe_source(raw.decode('utf-8')))
    report['status'] = 'AST_BINDING_DIAGNOSTIC_ONLY'
    if len(json.dumps(report, ensure_ascii=False).encode()) > MAX_OUTPUT:
        for row in report['bindings']: row.pop('statement_shape', None)
        report['password_readers'] = [{k: v for k, v in r.items() if k != 'reader_shape'} for r in report['password_readers']]
        report['shapes_omitted'] = 'TOTAL_OUTPUT_BUDGET'
    return report

if __name__ == '__main__':
    try:
        result = run(); complete = result.get('status') == 'AST_BINDING_DIAGNOSTIC_ONLY'
    except Exception:
        result = {'schema': 'NOX_CHAT_PASSWORD_PATH_AST_DIAGNOSTIC_V1', 'status': 'HOLD_BOUNDED_SOURCE_DIAGNOSTIC', 'credential_file_read': False, 'http_requests': 0}; complete = False
    print('NOX_MAINT_AUDIT=' + json.dumps(result, ensure_ascii=False, separators=(',', ':')))
    print('NOX_MAINT_AUDIT_COMPLETE=' + str(complete).lower())
