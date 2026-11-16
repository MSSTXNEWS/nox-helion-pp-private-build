#!/usr/bin/env python3
"""Static projection of the exact admin delegated handler; never import it.

Read only nox_admin.py and the one local module named by its pinned import.
No config, log, queue, credentials, network, tool or service is accessed.
"""
from __future__ import annotations
import ast
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import time

ROOT = Path('/root/nox/scripts')
ADMIN_NAME = 'nox_admin.py'
ADMIN_SHA = '916a77ad87f034295bff8e23e622536f922b8c930d31c52343684b741796cbfe'
ALIAS = '_ctl_handle_t878u'
SCHEMA = 'NOX_ADMIN_DELEGATED_CONTROL_STRUCTURE_V1'
MAX_FILE = 1024 * 1024
MAX_OUTPUT = 128 * 1024
IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,79}')
PROTOCOL = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,95}')
SENSITIVE = re.compile(r'password|secret|token|credential|bearer|private_key|api_key|^sk_|^ghp_|^github_pat_', re.I)
TABLES = {'aliases', '_aliases', 'ALIASES', 'ACTIONS', 'ACTION_MAP', 'ALLOWED_ACTIONS',
          'READONLY_ACTIONS', 'MUTATING_ACTIONS', 'HANDLERS', 'DIRECT_ADMIN'}
INTEREST = re.compile(r'handle|dispatch|action|queue|enqueue|submit|owner_order|upsert|admit|confirm')


class Hold(RuntimeError):
    pass


class Deadline(BaseException):
    pass


def require(value, code):
    if not value:
        raise Hold('HOLD_ADMIN_CONTROL_' + code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ident(value):
    return isinstance(value, str) and IDENT.fullmatch(value) is not None


def protocol(value):
    return isinstance(value, str) and PROTOCOL.fullmatch(value) is not None and not SENSITIVE.search(value)


def symbol(node):
    if isinstance(node, ast.Name) and ident(node.id):
        return node.id
    if isinstance(node, ast.Attribute) and ident(node.attr):
        base = symbol(node.value)
        if base and base.count('.') < 3:
            return base + '.' + node.attr
    return None


def identity(value):
    return tuple(getattr(value, key) for key in ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode',
                 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def root_fd():
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for name in ROOT.parts[1:]:
            nxt = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd); fd = nxt
        return fd
    except BaseException:
        os.close(fd); raise


def read_source(name, allowed):
    require(name in allowed and name.endswith('.py') and ident(name[:-3]), 'FIXED_SOURCE')
    parent = current = fd = None
    try:
        parent = root_fd()
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid() and before.st_nlink == 1
                and 0 < before.st_size <= MAX_FILE, 'SOURCE_METADATA')
        parts = []; left = before.st_size
        while left:
            block = os.read(fd, min(left, 65536)); require(bool(block), 'SOURCE_TRUNCATED')
            parts.append(block); left -= len(block)
        require(not os.read(fd, 1), 'SOURCE_GREW')
        current = root_fd()
        require(identity(before) == identity(os.fstat(fd))
                == identity(os.stat(name, dir_fd=parent, follow_symlinks=False))
                == identity(os.stat(name, dir_fd=current, follow_symlinks=False)), 'SOURCE_CHANGED')
        return b''.join(parts), {'bytes': before.st_size, 'uid': before.st_uid,
            'mode_octal': format(stat.S_IMODE(before.st_mode), '04o'), 'same_file_identity_verified': True}
    finally:
        for item in (fd, current, parent):
            if item is not None:
                os.close(item)


def tree_for(raw):
    text = raw.decode('utf-8'); tree = ast.parse(text)
    require(sum(1 for _ in ast.walk(tree)) <= 60000, 'AST_BOUND')
    return text, tree


def resolve_handler(tree):
    bindings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for item in node.names:
                if (item.asname or item.name) == ALIAS:
                    bindings.append((node, item))
    if len(bindings) != 1:
        return {'state': 'DYNAMIC_OR_AMBIGUOUS_IMPORT', 'matching_import_count': len(bindings)}
    node, item = bindings[0]
    if node.level != 0 or not ident(node.module) or not ident(item.name) or node.module == 'nox_admin':
        return {'state': 'NONLOCAL_OR_UNSUPPORTED_IMPORT', 'matching_import_count': 1}
    # A conventional import-failure None fallback is observable, not a claim
    # that this helper is bound in the running interpreter.
    null_fallbacks = set()
    for child in ast.walk(tree):
        if isinstance(child, (ast.Assign, ast.AnnAssign)) and isinstance(child.value, ast.Constant) and child.value.value is None:
            targets = child.targets if isinstance(child, ast.Assign) else [child.target]
            null_fallbacks.update(id(target) for target in targets if isinstance(target, ast.Name) and target.id == ALIAS)
    for child in ast.walk(tree):
        if isinstance(child, ast.Name) and child.id == ALIAS and isinstance(child.ctx, (ast.Store, ast.Del)):
            if id(child) not in null_fallbacks:
                return {'state': 'DYNAMIC_REBINDING', 'matching_import_count': 1}
    return {'state': 'ONE_LOCAL_STATIC_IMPORT', 'module': node.module,
            'handler': item.name, 'alias': ALIAS, 'line': node.lineno,
            'null_import_fallback_count': len(null_fallbacks), 'runtime_binding_verified': False}


def literal_protocols(node):
    values = ([node.value] if isinstance(node, ast.Constant) else
              [x.value for x in node.elts if isinstance(x, ast.Constant)]
              if isinstance(node, (ast.List, ast.Tuple, ast.Set)) else [])
    return sorted({value for value in values if protocol(value)})[:128]


def return_shape(value):
    if value is None or isinstance(value, ast.Constant) and value.value is None:
        return {'kind': 'NONE'}
    if isinstance(value, ast.Dict):
        fields = []
        for key, val in zip(value.keys, value.values):
            if isinstance(key, ast.Constant) and ident(key.value):
                item = {'key': key.value, 'value_shape': type(val).__name__}
                if isinstance(val, ast.Constant) and type(val.value) is bool:
                    item['boolean'] = val.value
                elif key.value in ('state', 'status', 'reason') and isinstance(val, ast.Constant) and protocol(val.value):
                    item['protocol_value'] = val.value
                fields.append(item)
        return {'kind': 'DICT', 'fields': fields[:64], 'fields_truncated': len(fields) > 64}
    if isinstance(value, ast.Call):
        return {'kind': 'CALL', 'callee': symbol(value.func)}
    if isinstance(value, ast.Name):
        return {'kind': 'VARIABLE', 'symbol': value.id if ident(value.id) else None}
    if isinstance(value, ast.Constant) and type(value.value) is bool:
        return {'kind': 'BOOLEAN', 'value': value.value}
    return {'kind': type(value).__name__}


def action_tables(tree):
    rows = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [x.id for x in targets if isinstance(x, ast.Name) and x.id in TABLES]
        for name in names:
            pairs = []; values = []
            if isinstance(node.value, ast.Dict):
                for key, value in zip(node.value.keys, node.value.values):
                    if isinstance(key, ast.Constant) and protocol(key.value):
                        row = {'action': key.value, 'target_symbol': symbol(value)}
                        if isinstance(value, ast.Constant) and protocol(value.value):
                            row['alias_target'] = value.value
                        pairs.append(row)
            else:
                values = literal_protocols(node.value)
            rows.append({'name': name, 'line': node.lineno, 'pairs': pairs[:128],
                         'values': values, 'dynamic_or_nonprotocol_values_omitted': True})
    require(len(rows) <= 64, 'ACTION_TABLE_BOUND')
    return rows


def project(raw, handler):
    text, tree = tree_for(raw); definitions = []; selected = []
    for node in tree.body:
        candidates = [(node, '')] if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else (
            [(n, node.name + '.') for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if isinstance(node, ast.ClassDef) and ident(node.name) else [])
        for fn, prefix in candidates:
            require(ident(fn.name), 'FUNCTION_NAME'); name = prefix + fn.name; definitions.append(name)
            if fn.name != handler and not INTEREST.search(name):
                continue
            nodes = list(ast.walk(fn))
            calls = sorted({sym for n in nodes if isinstance(n, ast.Call) and (sym := symbol(n.func))})
            branches = set(); prefixes = set(); confirmations = []
            for n in nodes:
                if isinstance(n, ast.Compare) and symbol(n.left) in ('action', 'act', 'name', 'action_name'):
                    for value in n.comparators: branches.update(literal_protocols(value))
                if isinstance(n, ast.Call):
                    if symbol(n.func) in ('action.startswith', 'act.startswith', 'action_name.startswith'):
                        for value in n.args: prefixes.update(literal_protocols(value))
                    for kw in n.keywords:
                        if kw.arg == 'confirmed':
                            confirmations.append(kw.value.value if isinstance(kw.value, ast.Constant)
                                and type(kw.value.value) is bool else 'DYNAMIC')
            args = [x.arg for x in (*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs)]
            if fn.args.vararg: args.append(fn.args.vararg.arg)
            if fn.args.kwarg: args.append(fn.args.kwarg.arg)
            returns = [return_shape(n.value) for n in sorted(
                (n for n in nodes if isinstance(n, ast.Return)), key=lambda n: n.lineno)]
            selected.append({'name': name, 'line': fn.lineno, 'parameters': args,
                'sha256': sha(ast.get_source_segment(text, fn).encode()), 'calls': calls[:128],
                'calls_truncated': len(calls) > 128, 'action_branches': sorted(branches)[:128],
                'action_prefixes': sorted(prefixes)[:64], 'confirmed_arguments': confirmations[:32],
                'return_shapes': returns[:64], 'returns_truncated': len(returns) > 64})
    require(len(definitions) <= 240 and len(selected) <= 64, 'FUNCTION_BOUND')
    return {'definitions': definitions, 'selected_functions': selected, 'action_tables': action_tables(tree),
            'handler_declared_at_module_scope': any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                                                   and n.name == handler for n in tree.body),
            'source_or_literal_arguments_exported': False, 'code_executed': False}


def observe():
    raw, meta = read_source(ADMIN_NAME, {ADMIN_NAME})
    require(sha(raw) == ADMIN_SHA, 'ADMIN_PIN')
    text, tree = tree_for(raw); binding = resolve_handler(tree)
    result = {'state': 'DELEGATED_CONTROL_UNRESOLVED', 'admin': dict(meta, sha256=sha(raw),
        structure=project(raw, 'run_action')), 'binding': binding, 'helper_observed': False}
    if binding['state'] != 'ONE_LOCAL_STATIC_IMPORT':
        result['observation_complete'] = True
        return result
    name = binding['module'] + '.py'
    try:
        raw, meta = read_source(name, {name})
    except Exception as exc:
        result.update(state='DELEGATED_CONTROL_SOURCE_UNAVAILABLE', reason=safe(exc), observation_complete=False)
        return result
    result.update(helper=dict(meta, sha256=sha(raw), structure=project(raw, binding['handler'])),
                  helper_observed=True, observation_complete=True, state='DELEGATED_CONTROL_STRUCTURE_OBSERVED')
    return result


def safe(exc):
    if isinstance(exc, Hold):
        return str(exc)
    if isinstance(exc, OSError):
        return errno.errorcode.get(exc.errno, 'OS_ERROR')
    return type(exc).__name__.upper()


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', ''); source_sha = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch(r'[0-9]{1,24}', request) and re.fullmatch(r'[a-f0-9]{40}', source_sha), 'OWNER_CONTEXT')
    def expired(_signum, _frame): raise Deadline()
    previous = signal.signal(signal.SIGALRM, expired); signal.alarm(20); started = time.monotonic()
    try:
        result = observe()
    except Deadline:
        result = {'state': 'HOLD_ADMIN_CONTROL_DEADLINE', 'observation_complete': False}
    except Exception as exc:
        result = {'state': 'DELEGATED_CONTROL_SOURCE_UNAVAILABLE', 'reason': safe(exc), 'observation_complete': False}
    finally:
        signal.alarm(0); signal.signal(signal.SIGALRM, previous)
    result.update(schema=SCHEMA, request=request, source_sha=source_sha,
        elapsed_seconds=round(time.monotonic() - started, 3), read_only=True, files_written=0,
        tool_or_service_actions=0, native_code_executed=False, task_enqueued=False,
        enqueue_safety_or_authorization_verified=False, private_contents_exported=False)
    encoded = json.dumps({'kind': 'admin_delegated_control_structure', 'data': result},
                         sort_keys=True, separators=(',', ':'), allow_nan=False)
    if len(encoded.encode()) > MAX_OUTPUT:
        result = {'schema': SCHEMA, 'state': 'HOLD_ADMIN_CONTROL_OUTPUT_BOUND', 'observation_complete': False,
                  'read_only': True, 'files_written': 0, 'native_code_executed': False}
        encoded = json.dumps({'kind': 'admin_delegated_control_structure', 'data': result}, separators=(',', ':'))
    print('NOX_MAINT_REPAIR=' + encoded, flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(result['observation_complete']).lower(), flush=True)
    return 0 if result['observation_complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
