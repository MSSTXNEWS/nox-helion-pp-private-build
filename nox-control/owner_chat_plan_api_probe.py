#!/usr/bin/env python3
"""Bounded static API projection of six known native modules; execute none."""
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
TARGETS = (
    ('TOOLS', ROOT / 'nox_tools.py', '2c17b7684275b532d4cc710322588ce178c9b23866630b11c778d1863bc448aa'),
    ('ADMIN', ROOT / 'nox_admin.py', '916a77ad87f034295bff8e23e622536f922b8c930d31c52343684b741796cbfe'),
    ('DISPATCHER', ROOT / 'nox_dispatcher_t855u.py', '75fe4346b28c74dd20ebda135e9382d09e4767a403ffe575035cbd139927ad2b'),
    ('PRIORITY', ROOT / 'nox_priority_scheduler.py', None),
    ('PLANNER', ROOT / 'owner_task_plans.py', '7eb207b361086d3c34299b44fb36d96758cf824a7bf68a05e7868408d646f773'),
    ('PROXY', ROOT / 'chat_proxy.py', 'a427aa68ed7760380880c5d1c9ddb0714bef367ee5162a20602dbe43b6722d90'),
)
SCHEMA = 'NOX_CHAT_PLAN_API_STRUCTURE_V1'
MAX_FILE = 1024 ** 2
MAX_OUTPUT = 256 * 1024
IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,79}')
ACTION = re.compile(r'[a-z][a-z0-9_]{0,63}')
SENSITIVE = re.compile(r'(?:password|secret|token|credential|bearer|private_key|api_key|^sk_|^ghp_|^github_pat_)', re.I)
INTEREST = re.compile(r'dispatch|run_action|heuristic|parse_tool|queue|enqueue|submit|owner_order|'
                      r'load_state|save_state|upsert|requested_plan|admitted|bind_dispatcher|'
                      r'^Planner\.(?:install|step|owner_order|worker_configuration)$|proxy_completion')
ACTION_TABLES = {'ACTIONS', 'ACTION_MAP', 'ALLOWED_ACTIONS', 'READONLY_ACTIONS', 'MUTATING_ACTIONS', 'DIRECT_ADMIN'}


class Hold(RuntimeError):
    pass


class Deadline(BaseException):
    pass


def require(ok, code):
    if not ok:
        raise Hold('HOLD_CHAT_PLAN_API_' + code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def identity(value):
    return tuple(getattr(value, key) for key in ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode',
                    'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def parent(path):
    require(path in {row[1] for row in TARGETS} and path.is_absolute() and '..' not in path.parts, 'FIXED_PATH')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for name in path.parts[1:-1]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd); fd = child
        return fd
    except BaseException:
        os.close(fd); raise


def source(path):
    directory = current_directory = fd = None
    try:
        directory = parent(path)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid() and before.st_nlink == 1
                and 0 < before.st_size <= MAX_FILE, 'SOURCE_SCOPE')
        parts = []; remaining = before.st_size
        while remaining:
            block = os.read(fd, min(remaining, 65536)); require(bool(block), 'TRUNCATED_SOURCE')
            parts.append(block); remaining -= len(block)
        require(not os.read(fd, 1), 'SOURCE_GREW')
        current_directory = parent(path)
        require(identity(before) == identity(os.fstat(fd))
                == identity(os.stat(path.name, dir_fd=directory, follow_symlinks=False))
                == identity(os.stat(path.name, dir_fd=current_directory, follow_symlinks=False)), 'SOURCE_CHANGED')
        return b''.join(parts), {'uid': before.st_uid, 'mode_octal': format(stat.S_IMODE(before.st_mode), '04o'),
                               'bytes': before.st_size, 'same_file_identity_verified': True}
    finally:
        for item in (fd, current_directory, directory):
            if item is not None:
                os.close(item)


def identifier(value):
    return isinstance(value, str) and IDENT.fullmatch(value) is not None


def symbols(node):
    if isinstance(node, ast.Name) and identifier(node.id):
        return node.id
    if isinstance(node, ast.Attribute) and identifier(node.attr):
        base = symbols(node.value)
        if base and base.count('.') < 3:
            return base + '.' + node.attr
    return None


def action_values(values):
    """Only protocol identifiers, never descriptions, commands or credentials."""
    if not isinstance(values, (list, tuple, set, frozenset)) or len(values) > 128:
        return {'state': 'NONSTATIC_OR_BOUNDED_OUT', 'values': []}
    accepted = []; hidden = 0
    for value in values:
        if isinstance(value, str) and ACTION.fullmatch(value) and not SENSITIVE.search(value):
            accepted.append(value)
        else:
            hidden += 1
    return {'state': 'LITERAL_PROTOCOL_IDENTIFIERS', 'values': sorted(set(accepted)), 'omitted_values': hidden}


def tool_projection(node):
    require(sum(1 for _ in ast.walk(node)) <= 12000, 'TOOLS_AST_BOUND')
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return {'state': 'DYNAMIC_UNRESOLVED', 'tools': []}
    if not isinstance(value, list) or not 0 <= len(value) <= 128:
        return {'state': 'UNRECOGNIZED_SCHEMA', 'tools': []}
    result = []
    for item in value:
        function = item.get('function') if isinstance(item, dict) else None
        if not isinstance(function, dict) or not identifier(function.get('name')):
            return {'state': 'UNRECOGNIZED_SCHEMA', 'tools': []}
        params = function.get('parameters') or {}; props = params.get('properties') or {}
        require(isinstance(props, dict) and len(props) <= 64, 'TOOL_PARAMETER_BOUND')
        properties = {key: val.get('type') if isinstance(val, dict) and val.get('type') in
                      ('string', 'integer', 'number', 'boolean', 'object', 'array', 'null') else None
                      for key, val in props.items() if identifier(key)}
        row = {'name': function['name'], 'parameter_types': properties,
               'required': [key for key in params.get('required', []) if identifier(key)][:64],
               'additional_properties_false': params.get('additionalProperties') is False}
        # Other enums can contain private file IDs; only the admin action enum
        # is a public protocol vocabulary needed for this investigation.
        if function['name'] == 'run_admin':
            action = props.get('action') or {}
            row['action_enum'] = action_values(action.get('enum')) if isinstance(action, dict) else action_values(None)
        result.append(row)
    return {'state': 'LITERAL_SCHEMA_PROJECTED', 'tools': result}


def projection(raw):
    text = raw.decode('utf-8'); tree = ast.parse(text)
    require(sum(1 for _ in ast.walk(tree)) <= 100000, 'SOURCE_AST_BOUND')
    definitions = []; functions = []; routes = []; tables = {}; registry = {'state': 'NOT_DECLARED', 'tools': []}
    def inspect_function(node, prefix=''):
        name = prefix + node.name
        require(identifier(node.name), 'FUNCTION_NAME')
        definitions.append(name)
        if INTEREST.search(name):
            calls = sorted({call_name for child in ast.walk(node) if isinstance(child, ast.Call)
                            and (call_name := symbols(child.func)) is not None})
            arguments = [arg.arg for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)]
            if node.args.vararg: arguments.append(node.args.vararg.arg)
            if node.args.kwarg: arguments.append(node.args.kwarg.arg)
            branch_values = []; confirmation = []
            for child in ast.walk(node):
                if isinstance(child, ast.Compare) and isinstance(child.left, ast.Name) and child.left.id in ('action', 'name'):
                    for other in child.comparators:
                        if isinstance(other, ast.Constant): branch_values.append(other.value)
                        elif isinstance(other, (ast.List, ast.Tuple, ast.Set)):
                            branch_values.extend(part.value for part in other.elts if isinstance(part, ast.Constant))
                if isinstance(child, ast.Call) and symbols(child.func) in ('run_action', 'nox_admin.run_action'):
                    value = next((k.value for k in child.keywords if k.arg == 'confirmed'), None)
                    confirmation.append(value.value if isinstance(value, ast.Constant) and type(value.value) is bool else 'DYNAMIC_OR_ABSENT')
            snippet = ast.get_source_segment(text, node).encode()
            functions.append({'name': name, 'line': node.lineno, 'sha256': sha(snippet),
                'parameters': arguments, 'calls': calls[:128], 'calls_truncated': len(calls) > 128,
                'action_or_tool_branches': action_values(branch_values), 'run_action_confirmed_arguments': confirmation[:32]})
        for decorator in node.decorator_list:
            call = symbols(decorator.func) if isinstance(decorator, ast.Call) else None
            if call and call.rsplit('.', 1)[-1] in ('get', 'post', 'put', 'patch', 'delete') and decorator.args:
                arg = decorator.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and re.fullmatch(r'/(?:api|nox)/[A-Za-z0-9_/{.}\-]{1,150}', arg.value):
                    routes.append({'method': call.rsplit('.', 1)[-1].upper(), 'path': arg.value, 'function': name})
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            inspect_function(node)
        elif isinstance(node, ast.ClassDef) and identifier(node.name):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    inspect_function(child, node.name + '.')
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [target.id for target in targets if isinstance(target, ast.Name)]
            if 'TOOLS' in names:
                require(registry['state'] == 'NOT_DECLARED', 'MULTIPLE_TOOL_REGISTRIES')
                registry = tool_projection(node.value)
            for name in set(names) & ACTION_TABLES:
                if isinstance(node.value, ast.Dict):
                    tables[name] = action_values([k.value for k in node.value.keys if isinstance(k, ast.Constant)])
                elif isinstance(node.value, (ast.Set, ast.List, ast.Tuple)):
                    tables[name] = action_values([k.value for k in node.value.elts if isinstance(k, ast.Constant)])
                else:
                    tables[name] = action_values(None)
    require(len(definitions) <= 400 and len(functions) <= 96 and len(routes) <= 128, 'STRUCTURE_BOUND')
    return {'definitions': definitions, 'selected_functions': functions, 'tool_registry': registry,
            'literal_action_tables': tables, 'literal_routes': routes,
            'source_body_or_literal_arguments_exported': False, 'code_executed': False,
            'enqueue_safety_or_authorization_verified': False}


def observe(label, path, historical_pin):
    row = {'label': label, 'state': 'STRUCTURE_UNAVAILABLE', 'historical_source_sha256': historical_pin}
    try:
        raw, meta = source(path)
        row.update(meta, sha256=sha(raw), historical_source_matches=sha(raw) == historical_pin if historical_pin else None)
        row.update(projection(raw), state='STATIC_API_STRUCTURE_OBSERVED')
    except Exception as exc:
        row['reason'] = str(exc) if isinstance(exc, Hold) else errno.errorcode.get(exc.errno, 'OS_ERROR') if isinstance(exc, OSError) else type(exc).__name__.upper()
    return row


def main():
    request, source_sha = (os.environ.get(key, '') for key in ('NOX_OWNER_REQUEST_ID', 'NOX_OWNER_SOURCE_SHA'))
    require(re.fullmatch(r'[0-9]{1,24}', request) and re.fullmatch(r'[a-f0-9]{40}', source_sha), 'OWNER_CONTEXT')
    def expired(_signum, _frame):
        raise Deadline()
    previous = signal.signal(signal.SIGALRM, expired); signal.alarm(20); started = time.monotonic()
    rows = []; state = 'STATIC_API_STRUCTURE_OBSERVED'
    try:
        for target in TARGETS:
            rows.append(observe(*target))
    except Deadline:
        state = 'HOLD_CHAT_PLAN_API_DEADLINE'
    finally:
        signal.alarm(0); signal.signal(signal.SIGALRM, previous)
    complete = len(rows) == len(TARGETS) and all(row['state'] == 'STATIC_API_STRUCTURE_OBSERVED' for row in rows)
    result = {'schema': SCHEMA, 'state': state if complete or state.endswith('DEADLINE') else 'STATIC_API_STRUCTURE_PARTIAL',
        'request': request, 'source_sha': source_sha, 'rows': rows, 'observation_complete': complete,
        'elapsed_seconds': round(time.monotonic() - started, 3), 'read_only': True, 'files_written': 0,
        'service_actions': 0, 'tool_execution_performed': False, 'task_enqueued': False,
        'private_contents_exported': False, 'enqueue_safety_or_authorization_verified': False}
    raw = encode({'kind': 'chat_plan_api_structure', 'data': result})
    if len(raw) > MAX_OUTPUT:
        raw = encode({'kind': 'chat_plan_api_structure', 'data': {'schema': SCHEMA,
            'state': 'HOLD_CHAT_PLAN_API_OUTPUT_BOUND', 'observation_complete': False,
            'read_only': True, 'files_written': 0, 'tool_execution_performed': False}})
        complete = False
    print('NOX_MAINT_REPAIR=' + raw.decode(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(complete).lower(), flush=True)
    return 0 if complete else 2


if __name__ == '__main__':
    raise SystemExit(main())
