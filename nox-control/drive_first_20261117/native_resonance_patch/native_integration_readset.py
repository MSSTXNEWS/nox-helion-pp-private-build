#!/usr/bin/env python3
"""Fixed-path, bounded OneHost binding inventory. No imports from native code.

Only file identity, AST identifiers/imports, selected mapping keys and shapes
are emitted. No function bodies, string values, defaults, secret files or HTTP.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat

ROOT = Path('/root/nox')
MAX_REPORT_BYTES = 65536
PYTHON_FILES = (
    'scripts/nox_dispatcher_t855u.py',
    'scripts/owner_component_tasks.py',
    'scripts/owner_dispatcher_mentor.py',
    'scripts/owner_task_lifecycle.py',
    'scripts/owner_event_outbox.py',
    'scripts/owner_subagent_dispatcher.py',
    'scripts/owner_subagent_dispatcher_fresh.py',
    'scripts/owner_subagent_processes.py',
    'scripts/owner_autonomy_pool.py',
    'scripts/nox_priority_arbiter.py',
    'scripts/owner_s03_gateway.py',
    'scripts/owner_drive_ram_bridge.py',
    'scripts/owner_drive_storage_bridge.py',
    'scripts/owner_drive_ram_prepare.py',
    'scripts/owner_builder_cold_location.py',
    'scripts/owner_hermes_hydrate.py',
)
JSON_FILES = ('config/owner_native_subagents.json', 'scripts/owner_drive_ram_assets.json')
METADATA_ONLY = ('ops/nox_teachers_warm.sh',)
KNOWN_PINS = {
    'scripts/owner_component_tasks.py': '190bf9948dbe821b5fe3512e3edbc0a7a9348b14aa2a154274e78f058d5d6d5d',
    'scripts/owner_dispatcher_mentor.py': '12211a29f77de8e5181d4dd78c35d5da2ed5de0dc6ea529149d32f0896809292',
}
IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,95}')
KEY = re.compile(r'[A-Za-z_][A-Za-z0-9_.:-]{0,119}')
MAPS = frozenset(('HANDLERS', 'LOCKS', 'CAPABILITIES', 'handlers', 'source_pins', 'module_pins', 'trusted', 'namespace'))

def identifier(value):
    return value if isinstance(value, str) and IDENT.fullmatch(value) else None

def mapping_key(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) and KEY.fullmatch(node.value) else None

def dotted(node):
    if isinstance(node, ast.Name):
        return identifier(node.id)
    if isinstance(node, ast.Attribute):
        left = dotted(node.value)
        return left + '.' + node.attr if left and identifier(node.attr) else None
    return None

def python_shape(source):
    tree = ast.parse(source)
    imports = set(); functions = []; mapping = {}; assigned = set(); bindings = set()
    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.scope = []
        def visit_Import(self, node):
            for alias in node.names:
                if all(identifier(p) for p in alias.name.split('.')):
                    imports.add(alias.name)
        def visit_ImportFrom(self, node):
            if node.module and all(identifier(p) for p in node.module.split('.')):
                imports.add('.' * node.level + node.module)
        def visit_ClassDef(self, node):
            if identifier(node.name):
                self.scope.append(node.name); self.generic_visit(node); self.scope.pop()
        def visit_FunctionDef(self, node):
            if not identifier(node.name):
                return
            args = node.args
            names = [a.arg for a in args.posonlyargs + args.args + args.kwonlyargs]
            if args.vararg: names.append(args.vararg.arg)
            if args.kwarg: names.append(args.kwarg.arg)
            qualified = '.'.join(self.scope + [node.name])
            if len(qualified) <= 256:
                functions.append({'name': qualified, 'parameters': [n for n in names if identifier(n)][:32], 'async': isinstance(node, ast.AsyncFunctionDef)})
            self.scope.append(node.name); self.generic_visit(node); self.scope.pop()
        visit_AsyncFunctionDef = visit_FunctionDef
        def visit_Assign(self, node):
            for target in node.targets:
                if isinstance(target, ast.Name) and not self.scope and identifier(target.id):
                    assigned.add(target.id)
                if isinstance(target, ast.Name) and target.id in MAPS and isinstance(node.value, ast.Dict):
                    mapping.setdefault(target.id, set()).update(k for x in node.value.keys if (k := mapping_key(x)))
            self.generic_visit(node)
        def visit_Subscript(self, node):
            if isinstance(node.value, ast.Name) and node.value.id in MAPS:
                key = mapping_key(node.slice)
                if key: mapping.setdefault(node.value.id, set()).add(key)
            self.generic_visit(node)
        def visit_Call(self, node):
            fn = dotted(node.func)
            if fn and fn.rsplit('.', 1)[-1] in ('bind_dispatcher', 'register_native_v29_chat', 'verify_success', 'record_experience', 'remember', 'journal', 'save_state', '_nox_owner_task_admitted', 'run_one', 's03_readback'):
                bindings.add(fn)
            # Literal map keys only; never the provided default or value.
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id in MAPS and node.func.attr in ('get', 'setdefault') and node.args:
                key = mapping_key(node.args[0])
                if key: mapping.setdefault(node.func.value.id, set()).add(key)
            self.generic_visit(node)
    Visitor().visit(tree)
    return {'imports': sorted(imports)[:128], 'functions': functions[:256],
            'top_level_identifiers': sorted(assigned)[:256],
            'mapping_keys': {key: sorted(values)[:128] for key, values in sorted(mapping.items())},
            'binding_call_names': sorted(bindings)[:128], 'source_exported': False}

def json_shape(raw):
    value = json.loads(raw)
    if not isinstance(value, dict):
        return {'json_type': type(value).__name__}
    selected = ('module_pins', 'source_pins', 'catalog', 'assets')
    result = {'top_level_keys': sorted(k for k in value if isinstance(k, str) and KEY.fullmatch(k))[:128]}
    for name in selected:
        child = value.get(name)
        if isinstance(child, dict):
            result[name] = {'type': 'object', 'keys': sorted(k for k in child if isinstance(k, str) and KEY.fullmatch(k))[:128]}
        elif isinstance(child, list):
            keys = set()
            for row in child[:64]:
                if isinstance(row, dict): keys.update(k for k in row if isinstance(k, str) and KEY.fullmatch(k))
            result[name] = {'type': 'array', 'count': len(child), 'item_keys': sorted(keys)[:128]}
    return result

def inspect_file(relative):
    path = ROOT / relative
    row = {'path': str(path), 'exists': path.exists()}
    if not row['exists']:
        return row
    if any(part.is_symlink() for part in (path, *path.parents)):
        return {**row, 'status': 'HOLD_SYMLINK'}
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1048576:
            return {**row, 'status': 'HOLD_TYPE_OR_SIZE'}
        raw = os.pread(fd, 1048577, 0)
        after = os.fstat(fd)
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if len(raw) != info.st_size or any(getattr(info, k) != getattr(after, k) or getattr(info, k) != getattr(path.lstat(), k) for k in fields):
            return {**row, 'status': 'HOLD_CHANGED_DURING_READ'}
        row.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), status='READ_ONLY_METADATA')
        if relative in KNOWN_PINS:
            row['matches_reported_native_pin'] = row['sha256'] == KNOWN_PINS[relative]
        if relative in PYTHON_FILES:
            row['ast'] = python_shape(raw.decode('utf-8'))
        elif relative in JSON_FILES:
            row['json_shape'] = json_shape(raw)
        return row
    finally:
        os.close(fd)

def run():
    rows = []
    for relative in PYTHON_FILES + JSON_FILES + METADATA_ONLY:
        try:
            rows.append(inspect_file(relative))
        except Exception:
            rows.append({'path': str(ROOT / relative), 'status': 'HOLD_READ_OR_PARSE', 'source_exported': False})
    report = {'schema': 'NOX_ONEHOST_INTEGRATION_BINDING_READSET_V1', 'files': rows,
            'http_requests': 0, 'native_mutations': 0, 'native_code_imported': False,
            'source_exported': False, 'secret_values_exported': False,
            'integration_handlers_enabled': False}
    if len(json.dumps(report, ensure_ascii=False).encode()) > MAX_REPORT_BYTES:
        # Preserve every identity/pin, dropping detailed shapes rather than
        # emitting a partial JSON document or unbounded audit output.
        for row in rows:
            if 'ast' in row or 'json_shape' in row:
                row.pop('ast', None); row.pop('json_shape', None)
                row['shape_omitted'] = 'TOTAL_OUTPUT_BUDGET'
        report['details_omitted'] = True
    return report

if __name__ == '__main__':
    print('NOX_MAINT_AUDIT=' + json.dumps(run(), ensure_ascii=False, separators=(',', ':')))
    print('NOX_MAINT_AUDIT_COMPLETE=true')
