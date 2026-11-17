#!/usr/bin/env python3
"""One bounded owner-authorized loopback canary. Never imports the native app.

Default: offline readiness only. --canary requires the existing authenticated
owner repair runner (which validates actor/repository/issue) and its source pin.
No external network, other dialogs, model reload, daemon, or credential output.
"""
from __future__ import annotations
import argparse
import ast
import contextlib
import fcntl
import hashlib
from html.parser import HTMLParser
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import signal
import stat
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = Path('/root/nox')
PROXY = ROOT / 'scripts/chat_proxy.py'
COMMON = PROXY.with_name('common.py')
PROXY_SHA = 'a03119817d695b1dc7ca2681a60bc564a0aa891468582bbf11b70592e2b4dfd6'
BRIDGE = ROOT / 'scripts/nox_v29_chat_bridge.py'
BRIDGE_SHA = '0cff2e7aee068571b2895ec476255e97ef3b85bd93104a27a822acfb8408632b'
WRAPPER = ROOT / 'scripts/nox_web29_onehost_18775.py'
WRAPPER_SHA = '0a0165e5b061f88ec60009c49a3c12e9823a45b89044604186e307c81fb701e6'
OWNER_UI = ROOT / 'scripts/owner_chat_ui.py'
OWNER_UI_SHA = 'da2cea21d21d3c1129bcb6621cd5293469a085ad861924a8c5cc63981577a866'
OWNER_DECORATED_HTML_SHA = 'e736c54022439cc2cddfaba17aeebf9844e2f6cf35a3b07c3837a8c0531b70cc'
RECONCILE_DIALOG_ID = '5ce69137da0a4c42a0387917c8567d52'
RECONCILE_ORIGIN = {'run_id': '44147786817', 'job_id': '134267516216', 'owner_request_id': '6957085526',
                    'owner_source_sha': '9699fd3ec4cfaaaa6c7df1ed37250663a8f4e553',
                    'canary_sha256': '2e319aaa381ebecae73de00772397d5d4b640810728be37f78606e3a62372dbf'}
SITE = ROOT / 'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site'
BASE = 'http://127.0.0.1:18775'
MODEL_BASE = 'http://127.0.0.1:8098'
PAGE = '/nox-web-v29/pc/resonance.html'
LOCK = ROOT / 'state/owner_maintenance.lock'
EXPECTED = {
    'resonance.html': '597ede7cf68e7606fc6b761f7d366e14737f86ffa50d648b637857b2275d070b',
    'nox-resonance-native-fix-v1.css': '717aec370c76857c7f932d3d0973921d3440d882d55a252b65edac35a9a37c29',
    'nox-resonance-native-fix-v1.js': '323f9153db7101e85280f9302738d078f0504fa7db4ba77d98ce794eef9455c9',
}
OWNER_HTML_INJECTION = b'<head><script src="/nox-web-v29/native-owner.js"></script>'

class Hold(Exception):
    """Only fixed public error codes; never raw HTTP/source/OS exceptions."""

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def served_asset_matches(name, raw, *, owner_ui_verified=False):
    expected = EXPECTED[name]
    if digest(raw) == expected:
        return True
    # Independently reproduced from exact owner_chat_ui.py da2cea... and then
    # observed byte-for-byte in native run44147786817. No generic HTML removal.
    if name == 'resonance.html' and owner_ui_verified and len(raw) == 14519 and digest(raw) == OWNER_DECORATED_HTML_SHA:
        return True
    # Exact existing _OwnerStatic HTML transform only. No generic stripping.
    if name == 'resonance.html' and raw.count(OWNER_HTML_INJECTION) == 1:
        return digest(raw.replace(OWNER_HTML_INJECTION, b'<head>', 1)) == expected
    return False

def _identifier(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9.]{0,159}', value) else '[WITHHELD]'

def _call_name(node):
    if isinstance(node, ast.Name):
        return _identifier(node.id)
    if isinstance(node, ast.Attribute):
        return _identifier(_call_name(node.value) + '.' + node.attr)
    return '[COMPUTED]'

def _literal_fingerprint(value):
    raw = value.encode('utf-8') if isinstance(value, str) else value
    return {'bytes': len(raw), 'sha256': digest(raw)}

def serving_source_projection(raw, kind):
    """Pinned-source syntax only. No native code, literal values or URLs returned."""
    tree = ast.parse(raw.decode('utf-8'))
    functions = []
    def collect(nodes, prefix=''):
        for node in nodes:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                name = prefix + node.name
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append((name, node))
                collect(node.body, name + '.')
    collect(tree.body)
    def relevant(name, node):
        if kind == 'bridge':
            return name == '_OwnerStatic.get_response' or 'overlay' in name.lower()
        return (any(x in name.lower() for x in ('proxy', 'response', 'forward', 'handle'))
                or name.rsplit('.', 1)[-1] in ('do_GET', 'do_POST', 'do_HEAD')
                or any(isinstance(n, ast.Call) and _call_name(n.func).rsplit('.', 1)[-1] in
                       ('replace', 'HTMLResponse', 'StreamingResponse', 'Response') for n in ast.walk(node)))
    selected = [(name, node) for name, node in functions if relevant(name, node)]
    selected.sort(key=lambda item: (item[0] != '_OwnerStatic.get_response', item[1].lineno))
    helper_names = {n.func.id for _, node in selected for n in ast.walk(node)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    selected += [(name, node) for name, node in functions if name in helper_names and (name, node) not in selected]
    lines = raw.splitlines(keepends=True)
    rows = []
    dependencies = set()
    for name, node in selected[:20]:
        calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
        literals = [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, (str, bytes))]
        dependencies.update(n.id for n in ast.walk(node) if isinstance(n, ast.Name))
        replacements = []
        for call in calls:
            if _call_name(call.func).endswith('.replace'):
                args = []
                for arg in call.args[:3]:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, (str, bytes)):
                        args.append({'kind': 'literal', **_literal_fingerprint(arg.value)})
                    elif isinstance(arg, ast.Name):
                        args.append({'kind': 'name', 'identifier': _identifier(arg.id)})
                    else:
                        args.append({'kind': type(arg).__name__})
                replacements.append({'line': call.lineno, 'target': _call_name(call.func), 'args': args})
        rows.append({'function': _identifier(name), 'line': node.lineno,
                     'source_sha256': digest(b''.join(lines[node.lineno - 1:node.end_lineno])),
                     'calls': sorted({_call_name(n.func) for n in calls})[:40],
                     'replacements': replacements[:16],
                     'literal_fingerprints': [_literal_fingerprint(v) for v in literals[:48]],
                     'literal_count': len(literals)})
    constants = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in dependencies and isinstance(node.value, ast.Constant) and isinstance(node.value.value, (str, bytes)):
                constants.append({'identifier': _identifier(node.targets[0].id), **_literal_fingerprint(node.value.value)})
    result = {'source_sha256': digest(raw), 'source_bytes': len(raw), 'source_executed': False,
              'selected_function_count': len(selected), 'functions': rows,
              'referenced_literal_bindings': constants[:24], 'literal_values_exported': False}
    while len(json.dumps(result)) > 16000 and result['functions']:
        result['functions'].pop()
    result['emitted_function_count'] = len(result['functions'])
    return result

def served_asset_diagnostic(name, raw, expected_raw, *, status=200, content_type='', content_encoding='', truncated=False, owner_ui_verified=False):
    mime = content_type.split(';', 1)[0].strip().lower()
    mime = mime if mime in ('text/html', 'text/css', 'text/javascript', 'application/javascript', 'application/json', 'text/plain', 'application/octet-stream') else '[OTHER_OR_MISSING]'
    encoding = content_encoding.strip().lower()
    encoding = encoding if encoding in ('', 'identity', 'gzip', 'br', 'deflate') else '[OTHER]'
    result = {'status': status, 'content_type': mime, 'content_encoding': encoding,
              'bytes_read': len(raw), 'truncated': truncated, 'sha256': digest(raw),
              'sha256_scope': 'PREFIX_ONLY' if truncated else 'ENTIRE_RESPONSE',
              'expected_disk_bytes': len(expected_raw), 'expected_disk_sha256': digest(expected_raw),
              'matches_pinned_asset': status == 200 and not truncated and served_asset_matches(name, raw, owner_ui_verified=owner_ui_verified)}
    if name != 'resonance.html':
        return result
    normalized = raw
    count = raw.count(OWNER_HTML_INJECTION)
    if count == 1:
        normalized = raw.replace(OWNER_HTML_INJECTION, b'<head>', 1)
    result['known_owner_head_injection_count'] = count
    result['accepted_transform'] = ('RAW' if digest(raw) == EXPECTED[name] else
                                    'PINNED_OWNER_HEAD_AND_OWNER_UI_COMPOSITION' if owner_ui_verified and len(raw) == 14519 and digest(raw) == OWNER_DECORATED_HTML_SHA else
                                    'SINGLE_KNOWN_OWNER_HEAD_INJECTION' if result['matches_pinned_asset'] else 'NONE')
    markers = {'html_head': b'<head>', 'html_body': b'<body', 'chat_form': b'chatForm',
               'native_css': b'nox-resonance-native-fix-v1.css', 'native_js': b'nox-resonance-native-fix-v1.js',
               'owner_script': b'/nox-web-v29/native-owner.js', 'password_input': b'type="password"'}
    result['fixed_marker_counts'] = {key: raw.count(value) for key, value in markers.items()}
    class Refs(HTMLParser):
        def __init__(self):
            super().__init__(); self.rows = []; self.total = 0
        def handle_starttag(self, tag, attrs):
            if tag not in ('script', 'link', 'img'):
                return
            for key, value in attrs:
                if key in ('src', 'href') and isinstance(value, str):
                    self.total += 1
                    if len(self.rows) < 64:
                        self.rows.append({'tag': tag, 'attribute': key, **_literal_fingerprint(value)})
    observed, expected = Refs(), Refs()
    observed.feed(raw.decode('utf-8', errors='replace')); expected.feed(expected_raw.decode('utf-8', errors='replace'))
    expected_hashes = {row['sha256'] for row in expected.rows}
    result['static_reference_fingerprints'] = [row | {'present_in_expected_disk': row['sha256'] in expected_hashes} for row in observed.rows]
    result['static_reference_count'] = observed.total
    prefix = 0
    common = min(len(normalized), len(expected_raw))
    while prefix < common and normalized[prefix] == expected_raw[prefix]:
        prefix += 1
    suffix = 0
    while suffix < common - prefix and normalized[len(normalized) - suffix - 1] == expected_raw[len(expected_raw) - suffix - 1]:
        suffix += 1
    expected_middle = expected_raw[prefix:len(expected_raw) - suffix if suffix else len(expected_raw)]
    served_middle = normalized[prefix:len(normalized) - suffix if suffix else len(normalized)]
    result['difference_after_known_injection_normalization'] = {
        'common_prefix_bytes': prefix, 'common_suffix_bytes': suffix,
        'expected_middle': _literal_fingerprint(expected_middle), 'served_middle': _literal_fingerprint(served_middle)}
    return result

def finalize_acceptance(report):
    report['native_chat_canary_pass'] = report.get('useful_chat_pass') is True
    report['native_canary_pass'] = report['native_chat_canary_pass'] and report.get('ui_asset_acceptance_pass') is True
    report['status'] = ('PASS' if report['native_canary_pass'] else
                        'HOLD_USEFUL_CHAT' if not report['native_chat_canary_pass'] else 'HOLD_SERVED_ASSET_HASH')

def regular_read(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise Hold('HOLD_FILE_TYPE_OR_LIMIT')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            value = stream.read(limit + 1)
        if len(value) > limit:
            raise Hold('HOLD_FILE_LIMIT')
        return value
    finally:
        os.close(fd)

def stable_common_read(path=COMMON):
    """Read existing sibling source as data, with a stable owner-controlled pin."""
    if path.resolve() != path:
        raise Hold('HOLD_COMMON_SOURCE_SYMLINK')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() or before.st_mode & 0o022 or before.st_size > 250000:
            raise Hold('HOLD_COMMON_SOURCE_TYPE_OWNER_OR_SIZE')
        raw = os.pread(fd, 250001, 0)
        after, current = os.fstat(fd), path.lstat()
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if len(raw) != before.st_size or any(getattr(before, k) != getattr(after, k) or getattr(before, k) != getattr(current, k) for k in fields):
            raise Hold('HOLD_COMMON_SOURCE_CHANGED')
        return raw, {'sha256': digest(raw), 'bytes': len(raw), 'stable_file_identity_verified': True,
                     'binding': 'PINNED_PROXY_FROM_COMMON_IMPORT_SECRETS_FIXED_SIBLING',
                     'code_executed': False, 'loaded_module_memory_identity_verified': False}
    finally:
        os.close(fd)

def exact_common_import(tree):
    rows = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.asname == 'SECRETS' or alias.name == 'SECRETS' and alias.asname is None:
                    rows.append((node, alias))
    if not rows:
        return False
    if len(rows) != 1 or rows[0][0].module != 'common' or rows[0][0].level != 0 or rows[0][1].name != 'SECRETS' or rows[0][1].asname is not None:
        raise Hold('HOLD_SECRETS_IMPORT_UNSUPPORTED')
    return True

def resolve_password_path(source, source_path=PROXY, allowed_root=ROOT, *, common_source=None):
    """Interpret a tiny path AST grammar; no eval/exec/import or env expansion."""
    tree = ast.parse(source)
    def assignments(unit):
        result = {}
        for node in unit.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        result.setdefault(target.id, []).append(node.value)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                result.setdefault(node.target.id, []).append(node.value)
        return result
    assigned = {'proxy': assignments(tree)}
    common_import = exact_common_import(tree)
    if common_import and 'SECRETS' in assigned['proxy']:
        raise Hold('HOLD_DUPLICATE_SECRETS_BINDING')
    if common_source is not None:
        if not common_import:
            raise Hold('HOLD_UNREQUESTED_COMMON_SOURCE')
        assigned['common'] = assignments(ast.parse(common_source))
    readers = [x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == '_read_chat_password']
    if len(readers) != 1:
        raise Hold('HOLD_AUTH_READER_MISSING')
    body = [n for n in readers[0].body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))]
    # Actual native helper has precisely an OSError -> empty-string fallback.
    if len(body) == 1 and isinstance(body[0], ast.Try):
        attempt = body[0]
        valid = (len(attempt.handlers) == 1 and not attempt.orelse and not attempt.finalbody)
        handler = attempt.handlers[0] if valid else None
        valid = (valid and isinstance(handler.type, ast.Name) and handler.type.id == 'OSError'
                 and handler.name is None and len(handler.body) == 1
                 and isinstance(handler.body[0], ast.Return) and isinstance(handler.body[0].value, ast.Constant)
                 and handler.body[0].value.value == '')
        if not valid:
            raise Hold('HOLD_AUTH_READER_UNSUPPORTED')
        body = attempt.body
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        raise Hold('HOLD_AUTH_READER_UNSUPPORTED')
    value = body[0].value
    if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and value.func.attr == 'strip' and not value.args and not value.keywords):
        raise Hold('HOLD_AUTH_READER_UNSUPPORTED')
    read = value.func.value
    if not (isinstance(read, ast.Call) and isinstance(read.func, ast.Attribute) and read.func.attr == 'read_text' and isinstance(read.func.value, ast.Name) and read.func.value.id == 'CHAT_PASSWORD_PATH' and not read.args):
        raise Hold('HOLD_AUTH_READER_UNSUPPORTED')
    for kw in read.keywords:
        if kw.arg != 'encoding' or not isinstance(kw.value, ast.Constant) or kw.value.value not in ('utf-8', 'utf8'):
            raise Hold('HOLD_AUTH_READER_ENCODING')
    resolving = set()
    dependencies = set()
    def evaluate(node, unit='proxy'):
        if isinstance(node, ast.Name):
            dependencies.add(node.id)
            if len(dependencies) > 64:
                raise Hold('HOLD_PATH_CHAIN_LIMIT')
            identity = (unit, node.id)
            if identity in resolving:
                raise Hold('HOLD_PATH_CYCLE')
            resolving.add(identity)
            if unit == 'proxy' and node.id == 'SECRETS' and common_import:
                if 'common' not in assigned:
                    raise Hold('HOLD_COMMON_SOURCE_REQUIRED')
                result = evaluate(ast.Name(id='SECRETS'), 'common')
                resolving.remove(identity)
                return result
            local = assigned[unit]
            if node.id not in local:
                raise Hold('HOLD_PATH_NAME')
            if len(local[node.id]) != 1:
                raise Hold('HOLD_DUPLICATE_PATH_BINDING')
            result = evaluate(local[node.id][0], unit)
            resolving.remove(identity)
            return result
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'Path' and len(node.args) == 1 and not node.keywords:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return Path(arg.value)
            if isinstance(arg, ast.Name) and arg.id == '__file__':
                return Path(source_path) if unit == 'proxy' else Path(source_path).with_name('common.py')
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            rhs = node.right
            if isinstance(rhs, ast.Constant) and isinstance(rhs.value, str) and rhs.value and not Path(rhs.value).is_absolute() and '..' not in Path(rhs.value).parts:
                return evaluate(node.left, unit) / rhs.value
        # Exact Path(__file__).resolve().parents[1], interpreted statically.
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == 'parents':
            idx = node.slice
            call = node.value.value
            if isinstance(idx, ast.Constant) and idx.value == 1 and isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == 'resolve' and not call.args and not call.keywords:
                inner = call.func.value
                if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) and inner.func.id == 'Path' and len(inner.args) == 1 and isinstance(inner.args[0], ast.Name) and inner.args[0].id == '__file__' and not inner.keywords):
                    unit_path = Path(source_path) if unit == 'proxy' else Path(source_path).with_name('common.py')
                    return unit_path.absolute().parents[1]
        raise Hold('HOLD_PATH_EXPRESSION')
    try:
        result = evaluate(ast.Name(id='CHAT_PASSWORD_PATH'))
        root = Path(allowed_root).absolute()
        if not result.is_absolute() or '..' in result.parts or result == root or root not in result.parents or result.resolve() != result:
            raise Hold('HOLD_AUTH_PATH_OUTSIDE_ROOT_OR_SYMLINK')
    except Hold as exc:
        # Identifiers only. Never source, evaluated values, paths or secret text.
        exc.dependency_identifiers = sorted(name for name in dependencies if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,95}', name))[:32]
        raise
    return result

def scoped_stop_supported(source):
    """Prove the pinned handler only sets the event selected by scope(request)."""
    tree = ast.parse(source)
    registrations = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'register_native_v29_chat']
    if len(registrations) != 1:
        return False
    handlers = [n for n in ast.walk(registrations[0]) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'stream_stop']
    if len(handlers) != 1:
        return False
    nodes = list(ast.walk(handlers[0]))
    key_names = set()
    event_names = set()
    for node in nodes:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
            fn = call.func.id if isinstance(call.func, ast.Name) else ''
            if 'scope' in fn.lower() and len(call.args) == 1 and isinstance(call.args[0], ast.Name) and call.args[0].id == 'request':
                key_names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    def keyed_event(node):
        if isinstance(node, ast.Subscript):
            return isinstance(node.value, ast.Name) and 'active' in node.value.id.lower() and isinstance(node.slice, ast.Name) and node.slice.id in key_names
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'get' and isinstance(node.func.value, ast.Name) and 'active' in node.func.value.id.lower() and node.args:
            return isinstance(node.args[0], ast.Name) and node.args[0].id in key_names
        return False
    for node in nodes:
        if isinstance(node, ast.Assign) and keyed_event(node.value):
            event_names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    setters = [node for node in nodes if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'set']
    return bool(key_names and setters and all(not n.args and not n.keywords and (keyed_event(n.func.value) or isinstance(n.func.value, ast.Name) and n.func.value.id in event_names) for n in setters))

def priority_snapshot():
    result = {}
    for name in ('CHAT_ACTIVE', 'MODE'):
        value = regular_read(ROOT / 'state/priority' / name, 64).decode('ascii').strip()
        result[name] = value
    if result != {'CHAT_ACTIVE': '0', 'MODE': 'IDLE'}:
        raise Hold('HOLD_OWNER_PRIORITY_BUSY')
    return result

@contextlib.contextmanager
def maintenance_lease(borrowed_fd=None):
    owned = borrowed_fd is None
    fd = os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW) if owned else borrowed_fd
    try:
        actual, expected = os.fstat(fd), os.lstat(LOCK)
        if not stat.S_ISREG(actual.st_mode) or (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
            raise Hold('HOLD_MAINTENANCE_FD_BINDING')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Hold('HOLD_MAINTENANCE_BUSY') from None
        yield
    finally:
        if owned:
            os.close(fd)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Hold('HOLD_HTTP_REDIRECT')

class LoopbackClient:
    def __init__(self, *, read_only=False, owner_ui_verified=False):
        self.read_only = read_only
        self.owner_ui_verified = owner_ui_verified
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPCookieProcessor(self.jar))
    def request(self, path, data=None, *, model=False, timeout=5):
        # Caller uses fixed paths only; reject any route/network injection.
        allowed = {'/chat/login', '/api/nox/chat/stream', '/api/nox/stop', '/api/ui/memory/dialogs/create'}
        allowed.update('/nox-web-v29/pc/' + name for name in EXPECTED)
        valid_history = re.fullmatch(r'/api/ui/memory/dialogs/history\?dialog_id=[a-f0-9]{32}&limit=2', path)
        if self.read_only:
            if data is not None and path != '/chat/login':
                raise Hold('HOLD_READ_ONLY_POST')
            if path in ('/api/nox/chat/stream', '/api/nox/stop', '/api/ui/memory/dialogs/create'):
                raise Hold('HOLD_READ_ONLY_ROUTE')
            if valid_history and path != '/api/ui/memory/dialogs/history?dialog_id=' + RECONCILE_DIALOG_ID + '&limit=2':
                raise Hold('HOLD_RECONCILE_OWN_DIALOG_ONLY')
        if model:
            if path != '/slots' or data is not None:
                raise Hold('HOLD_MODEL_ROUTE')
        elif path not in allowed and not valid_history:
            raise Hold('HOLD_HTTP_ROUTE')
        payload = None if data is None else json.dumps(data, ensure_ascii=False).encode()
        req = urllib.request.Request((MODEL_BASE if model else BASE) + path, data=payload, headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
        return self.opener.open(req, timeout=timeout)
    def raw(self, path, data=None, *, model=False, limit=200000):
        with self.request(path, data, model=model) as response:
            if response.status != 200:
                raise Hold('HOLD_HTTP_STATUS')
            raw = response.read(limit + 1)
            if len(raw) > limit:
                raise Hold('HOLD_HTTP_SIZE')
            return raw
    def asset(self, name, expected_raw):
        # HTTP errors are UI evidence, not permission to follow redirects or run code.
        if name not in EXPECTED:
            raise Hold('HOLD_ASSET_NAME')
        try:
            response = self.request('/nox-web-v29/pc/' + name)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read(200001)
            truncated = len(raw) > 200000
            return served_asset_diagnostic(name, raw[:200000], expected_raw,
                status=response.status, content_type=response.headers.get('Content-Type', ''),
                content_encoding=response.headers.get('Content-Encoding', ''), truncated=truncated,
                owner_ui_verified=self.owner_ui_verified)
    def history_evidence(self, dialog_id):
        if not isinstance(dialog_id, str) or not re.fullmatch('[a-f0-9]{32}', dialog_id):
            raise Hold('HOLD_HISTORY_DIALOG_SCHEMA')
        try:
            response = self.request('/api/ui/memory/dialogs/history?dialog_id=' + dialog_id + '&limit=2')
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read(200001)
            mime = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
            meta = {'status': response.status, 'bytes_read': min(len(raw), 200000),
                    'truncated': len(raw) > 200000, 'sha256': digest(raw[:200000]),
                    'content_type': mime if mime in ('application/json', 'text/html', 'text/plain') else '[OTHER_OR_MISSING]',
                    'json_decoded': False}
        if meta['truncated']:
            return None, meta
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            meta['error_class'] = type(exc).__name__
            return None, meta
        meta['json_decoded'] = True
        meta['json_type'] = type(value).__name__
        return value, meta
    def json(self, path, data=None, *, model=False):
        return json.loads(self.raw(path, data, model=model))

def slots_free(client):
    slots = client.json('/slots', model=True)
    if not isinstance(slots, list) or not slots or len(slots) > 16:
        raise Hold('HOLD_MODEL_SLOT_SCHEMA')
    for slot in slots:
        if not isinstance(slot, dict) or not any(k in slot for k in ('is_processing', 'processing')):
            raise Hold('HOLD_MODEL_SLOT_SCHEMA')
        if slot.get('is_processing', slot.get('processing')) is not False:
            raise Hold('HOLD_MODEL_BUSY')
    return len(slots)

def read_stream(response, started, deadline):
    answer = ''; first = None; done = None; count = 0; placeholders = 0
    for _ in range(2000):
        if time.monotonic() >= deadline:
            raise Hold('HOLD_CANARY_DEADLINE')
        line = response.readline(65537)
        if not line:
            break
        if len(line) > 65536:
            raise Hold('HOLD_STREAM_FRAME_LIMIT')
        frame = json.loads(line)
        if not isinstance(frame, dict) or frame.get('type') not in ('preparing', 'start', 'started', 'delta', 'done', 'error', 'status', 'meta'):
            raise Hold('HOLD_STREAM_SCHEMA')
        if frame['type'] == 'delta':
            text = frame.get('text')
            if not isinstance(text, str):
                raise Hold('HOLD_STREAM_TEXT_SCHEMA')
            answer += text; count += 1
            if re.search(r'[^\s.…]', text):
                if first is None:
                    first = round((time.monotonic() - started) * 1000)
            else:
                placeholders += 1
            if len(answer) > 10000:
                raise Hold('HOLD_STREAM_TEXT_LIMIT')
        elif frame['type'] == 'done':
            done = frame
            break
        elif frame['type'] == 'error':
            raise Hold('HOLD_STREAM_ERROR')
    if done is None or first is None:
        raise Hold('HOLD_STREAM_INCOMPLETE')
    return {'answer': answer, 'done': done, 'first_meaningful_delta_ms': first,
            'delta_count': count, 'placeholder_delta_count': placeholders,
            'stream_total_ms': round((time.monotonic() - started) * 1000)}

def public_turn(turn, history, question):
    answer = turn['answer']
    messages = history.get('messages') if isinstance(history, dict) else None
    pair_ok = (isinstance(messages, list) and len(messages) == 2 and all(isinstance(m, dict) for m in messages)
               and messages[0].get('role') == 'user' and messages[0].get('content') == question
               and messages[1].get('role') == 'assistant' and messages[1].get('content') == answer)
    done = turn['done']
    saved = done.get('saved') is True and done.get('s03_integrated') is True and pair_ok
    numeric = answer.strip().strip('`*_ .!\n\r\t')
    arithmetic = numeric == '42'
    return {k: turn[k] for k in ('first_meaningful_delta_ms', 'delta_count', 'placeholder_delta_count', 'stream_total_ms')} | {
        'answer_public_synthetic': '42' if arithmetic else '[WITHHELD]', 'answer_sha256': digest(answer.encode()),
        'arithmetic_pass': arithmetic, 'terminal_receipt': True,
        'receipt_saved': done.get('saved') is True, 'receipt_s03_integrated': done.get('s03_integrated') is True,
        'history_persisted': saved, 'useful_chat_pass': arithmetic and saved,
        'performance_target_pass': arithmetic and saved and turn['first_meaningful_delta_ms'] <= 8000 and turn['stream_total_ms'] <= 25000}

def reconcile_history(history):
    messages = history.get('messages') if isinstance(history, dict) else None
    valid = (isinstance(history, dict) and history.get('status') == 'READY'
             and history.get('dialog_id') == RECONCILE_DIALOG_ID and isinstance(messages, list)
             and len(messages) == 2 and all(isinstance(row, dict) for row in messages))
    result = {'own_dialog_id': RECONCILE_DIALOG_ID, 'history_schema_valid': valid,
              'history_reconciliation_pass': False, 'history_content_exported': False,
              'terminal_receipt_fields_recovered': False, 'prior_stream_timings_recovered': False,
              'prior_stream_terminal_evidence': 'INFERRED_FROM_V4_CONTROL_FLOW_NOT_RECORDED_FIELDS'}
    if not valid:
        return result
    question, answer = messages[0].get('content'), messages[1].get('content')
    text_valid = isinstance(question, str) and isinstance(answer, str) and len(question) <= 1000 and len(answer) <= 10000
    if not text_valid:
        return result
    synthetic = bool(re.fullmatch(r'\[QA [a-f0-9]{12}\] Сколько будет 17 \+ 25\? Ответь только числом\.', question))
    roles = messages[0].get('role') == 'user' and messages[1].get('role') == 'assistant'
    numeric = answer.strip().strip('`*_ .!\n\r\t') == '42'
    first_exchange, second_exchange = messages[0].get('exchange_id'), messages[1].get('exchange_id')
    same_exchange = (isinstance(first_exchange, str) and 0 < len(first_exchange) <= 200
                     and first_exchange == second_exchange)
    result.update({'own_synthetic_question_matches': synthetic, 'roles_match': roles,
                   'question_sha256': digest(question.encode()), 'answer_sha256': digest(answer.encode()),
                   'answer_public_synthetic': '42' if numeric and synthetic else '[WITHHELD]',
                   'arithmetic_pass': numeric, 'same_exchange_id': same_exchange,
                   'exchange_id_sha256': digest(first_exchange.encode()) if same_exchange else None,
                   'history_reconciliation_pass': synthetic and roles and numeric and same_exchange})
    return result

def run(canary=False, *, expected_source_sha=None, maintenance_lock_fd=None, reconcile_dialog_id=None, assets_only=False):
    started = time.monotonic()
    reconcile = reconcile_dialog_id is not None
    if sum((bool(canary), bool(assets_only), reconcile)) > 1:
        raise Hold('HOLD_ACCEPTANCE_MODE_CONFLICT')
    if reconcile and reconcile_dialog_id != RECONCILE_DIALOG_ID:
        raise Hold('HOLD_RECONCILE_OWN_DIALOG_ONLY')
    active = canary or assets_only or reconcile
    mode = 'reconcile' if reconcile else 'assets_only' if assets_only else 'canary' if canary else 'readiness'
    report = {'schema': 'NOX_NATIVE_RESONANCE_ACCEPTANCE_V1', 'mode': mode, 'phase': 'SOURCE_IDENTITY',
              'python_version': tuple(sys.version_info[:3]),
              'native_canary_pass': False, 'native_chat_canary_pass': False, 'ui_asset_acceptance_pass': False,
              'external_http_requests': 0, 'credentials_exported': False,
              'model_reloads': 0, 'dialogs_created': 0, 'model_requests': 0,
              'scope': 'LOOPBACK_18775_TO_8080_EXISTING_CHAT_AND_MODEL_8098',
              'public_tunnel_verified': False, 'actor_authorization': 'EXISTING_OWNER_REPAIR_RUNNER_REQUIRED'}
    source = regular_read(PROXY, 250000)
    if digest(source) != PROXY_SHA:
        raise Hold('HOLD_PROXY_SHA_CHANGED')
    common_raw = None
    if exact_common_import(ast.parse(source.decode())):
        common_raw, common_pin = stable_common_read()
        report['common_source_pin'] = common_pin
    try:
        password_path = resolve_password_path(source.decode(), common_source=common_raw.decode() if common_raw is not None else None)
    except Hold as exc:
        if common_raw is not None:
            exc.common_source_pin = report['common_source_pin']
        raise
    bridge_source = regular_read(BRIDGE, 250000)
    if digest(bridge_source) != BRIDGE_SHA:
        raise Hold('HOLD_BRIDGE_SHA_CHANGED')
    stop_scoped = scoped_stop_supported(bridge_source.decode())
    wrapper_source = regular_read(WRAPPER, 250000)
    if digest(wrapper_source) != WRAPPER_SHA:
        raise Hold('HOLD_WRAPPER_SHA_CHANGED')
    owner_ui_source = regular_read(OWNER_UI, 250000)
    if len(owner_ui_source) != 4854 or digest(owner_ui_source) != OWNER_UI_SHA:
        raise Hold('HOLD_OWNER_UI_SHA_CHANGED')
    report['proxy_sha256'] = PROXY_SHA
    report['bridge_sha256'] = BRIDGE_SHA
    report['wrapper_sha256'] = WRAPPER_SHA
    report['owner_ui_sha256'] = OWNER_UI_SHA
    report['auth_path_resolved'] = True
    report['scoped_stop_verified'] = stop_scoped
    disk_assets = {name: regular_read(SITE / 'pc' / name, 200000) for name in EXPECTED}
    report['assets_on_disk'] = {name: digest(raw) == EXPECTED[name] for name, raw in disk_assets.items()}
    report['priority'] = priority_snapshot()
    if not active:
        report['status'] = 'READY_FOR_EXPLICIT_CANARY' if stop_scoped and all(report['assets_on_disk'].values()) else 'HOLD_READINESS'
        return report
    request_id = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source_sha = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch(r'[0-9]{1,24}', request_id) or not re.fullmatch(r'[a-f0-9]{40}', source_sha) or expected_source_sha != source_sha:
        raise Hold('HOLD_OWNER_REQUEST_SOURCE_BINDING')
    if not stop_scoped or not all(report['assets_on_disk'].values()):
        raise Hold('HOLD_CANARY_READINESS')
    if threading.current_thread() is not threading.main_thread():
        raise Hold('HOLD_MAIN_THREAD_DEADLINE_REQUIRED')
    report['owner_request_id'] = request_id
    report['owner_source_sha'] = source_sha
    client = LoopbackClient(read_only=not canary, owner_ui_verified=True)
    response = None; stream_started = False; stream_terminal = False
    previous_handler = signal.getsignal(signal.SIGALRM)
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise Hold('HOLD_EXISTING_ALARM')
    def expired(signum, frame):
        raise Hold('HOLD_CANARY_DEADLINE')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, max(0.01, (56 if canary else 20) - (time.monotonic() - started)))
    try:
        with maintenance_lease(maintenance_lock_fd):
            report['phase'] = 'OWNER_IDLE_AND_SLOTS'
            priority_snapshot()
            report['free_model_slots'] = slots_free(client)
            if common_raw is not None:
                current_common, _ = stable_common_read()
                if digest(current_common) != report['common_source_pin']['sha256']:
                    raise Hold('HOLD_COMMON_SOURCE_CHANGED_BEFORE_LOGIN')
            info = password_path.stat()
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise Hold('HOLD_CREDENTIAL_FILE_PERMISSIONS')
            password = regular_read(password_path, 4096).decode('utf-8').strip()
            if not 6 <= len(password) <= 4096:
                raise Hold('HOLD_CREDENTIAL_UNAVAILABLE')
            try:
                report['phase'] = 'OFFICIAL_LOGIN'
                client.raw('/chat/login', {'password': password}, limit=32768)
            finally:
                password = None
            if not any(True for _ in client.jar):
                raise Hold('HOLD_OFFICIAL_LOGIN_NO_SESSION')
            report['authenticated_login'] = True
            report['phase'] = 'AUTHENTICATED_ASSETS'
            report['authenticated_assets'] = {}
            report['served_asset_diagnostics'] = {}
            for name in EXPECTED:
                diagnostic = client.asset(name, disk_assets[name])
                report['served_asset_diagnostics'][name] = diagnostic
                report['authenticated_assets'][name] = diagnostic['matches_pinned_asset']
            report['ui_asset_acceptance_pass'] = all(report['authenticated_assets'].values())
            if not report['ui_asset_acceptance_pass']:
                report['ui_status'] = 'HOLD_SERVED_ASSET_HASH'
                report['serving_source_projection'] = {
                    'bridge': serving_source_projection(bridge_source, 'bridge'),
                    'wrapper': serving_source_projection(wrapper_source, 'wrapper')}
            else:
                report['ui_status'] = 'PASS'
            if assets_only:
                report['status'] = 'ASSETS_VERIFIED_ONLY' if report['ui_asset_acceptance_pass'] else 'HOLD_SERVED_ASSET_HASH'
                report['phase'] = 'COMPLETE_ASSETS_ONLY'
                return report
            if reconcile:
                report['reconciles_prior_canary'] = RECONCILE_ORIGIN
                report['phase'] = 'OWN_HISTORY_READ_ONLY'
                priority_snapshot(); slots_free(client)
                history, history_meta = client.history_evidence(RECONCILE_DIALOG_ID)
                report['history_http_diagnostic'] = history_meta
                if history_meta['status'] != 200 or not history_meta['json_decoded'] or history_meta['truncated']:
                    raise Hold('HOLD_HISTORY_HTTP_OR_JSON')
                report.update(reconcile_history(history))
                report['reconciliation_pass'] = report['history_reconciliation_pass'] and report['ui_asset_acceptance_pass']
                report['status'] = ('HISTORY_AND_UI_RECONCILED_TERMINAL_RECEIPT_UNAVAILABLE' if report['reconciliation_pass']
                                    else 'HOLD_OWN_HISTORY_RECONCILIATION' if not report['history_reconciliation_pass']
                                    else 'HOLD_SERVED_ASSET_HASH')
                report['phase'] = 'COMPLETE_RECONCILIATION'
                return report
            # HTML is never executed here. Its independent mismatch cannot change
            # pinned auth, own-session scope or chat admission. Overall PASS still
            # requires both UI asset identity and the real own-chat receipt.
            marker = secrets.token_hex(6)
            question = '[QA ' + marker + '] Сколько будет 17 + 25? Ответь только числом.'
            priority_snapshot(); slots_free(client)
            report['phase'] = 'OWN_DIALOG_CREATE'
            created = client.json('/api/ui/memory/dialogs/create', {'confirmed': True, 'title': 'Проверка связки NOX ' + marker})
            did = created.get('dialog_id') if isinstance(created, dict) else None
            if not isinstance(did, str) or not re.fullmatch(r'[a-f0-9]{32}', did):
                raise Hold('HOLD_DIALOG_CREATE_SCHEMA')
            report['dialogs_created'] = 1
            report['own_dialog_id'] = did
            priority_snapshot(); slots_free(client)
            stream_started = True; report['model_requests'] = 1
            report['phase'] = 'OWN_STREAM'
            turn_start = time.monotonic()
            response = client.request('/api/nox/chat/stream', {'message': question, 'history': [], 'task': 'general', 'dialog_id': did}, timeout=45)
            if response.status != 200:
                raise Hold('HOLD_STREAM_HTTP')
            turn = read_stream(response, turn_start, started + 56)
            stream_terminal = True
            report['stream_terminal_received'] = True
            report['phase'] = 'OWN_STREAM_RECEIPT'
            partial_turn = public_turn(turn, {}, question)
            report['stream_receipt'] = {key: partial_turn[key] for key in
                ('answer_public_synthetic', 'answer_sha256', 'arithmetic_pass', 'terminal_receipt',
                 'receipt_saved', 'receipt_s03_integrated', 'first_meaningful_delta_ms', 'stream_total_ms')}
            report['phase'] = 'OWN_STREAM_CLOSE'
            response.close(); response = None
            report['phase'] = 'OWN_HISTORY_READ'
            history, history_meta = client.history_evidence(did)
            report['history_http_diagnostic'] = history_meta
            if history_meta['status'] != 200 or not history_meta['json_decoded'] or history_meta['truncated']:
                raise Hold('HOLD_HISTORY_HTTP_OR_JSON')
            report['phase'] = 'OWN_HISTORY_VALIDATE'
            report.update(public_turn(turn, history, question))
            finalize_acceptance(report)
            report['phase'] = 'COMPLETE_CANARY'
    except (Exception, KeyboardInterrupt) as exc:
        report['status'] = str(exc) if isinstance(exc, Hold) else 'HOLD_BOUNDED_CANARY_FAILURE'
        report['error_class'] = _identifier(type(exc).__name__)
        report['error_phase'] = report['phase']
        # Never print raw exception text, cookies, password, or unexpected answer.
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        if response is not None:
            response.close()
        if stream_started and not stream_terminal:
            report['own_stream_stop_attempted'] = True
            try:
                # Same private CookieJar; AST above proves only this session event.
                signal.setitimer(signal.ITIMER_REAL, 2)
                with client.request('/api/nox/stop', {}, timeout=2) as stopped:
                    report['own_stream_stop_http_ok'] = stopped.status == 200
            except Exception:
                report['own_stream_stop_http_ok'] = False
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        client.jar.clear()
        report['total_ms'] = round((time.monotonic() - started) * 1000)
    return report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--canary', action='store_true')
    modes.add_argument('--assets-only', action='store_true')
    modes.add_argument('--reconcile-owned-dialog', action='store_true')
    parser.add_argument('--expected-source-sha')
    parser.add_argument('--maintenance-lock-fd', type=int)
    args = parser.parse_args()
    try:
        result = run(args.canary, expected_source_sha=args.expected_source_sha, maintenance_lock_fd=args.maintenance_lock_fd,
                     reconcile_dialog_id=RECONCILE_DIALOG_ID if args.reconcile_owned_dialog else None, assets_only=args.assets_only)
    except Exception as exc:
        result = {'schema': 'NOX_NATIVE_RESONANCE_ACCEPTANCE_V1', 'status': str(exc) if isinstance(exc, Hold) else 'HOLD_READINESS_FAILURE', 'native_canary_pass': False, 'credentials_exported': False}
        if isinstance(exc, Hold) and hasattr(exc, 'dependency_identifiers'):
            result['dependency_identifiers'] = exc.dependency_identifiers
        if isinstance(exc, Hold) and hasattr(exc, 'common_source_pin'):
            result['common_source_pin'] = exc.common_source_pin
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'native_resonance_acceptance', 'data': result}, ensure_ascii=False, separators=(',', ':')), flush=True)
    return 0 if result.get('native_canary_pass') or result.get('reconciliation_pass') or result.get('status') in ('READY_FOR_EXPLICIT_CANARY', 'ASSETS_VERIFIED_ONLY') else 2

if __name__ == '__main__':
    raise SystemExit(main())
