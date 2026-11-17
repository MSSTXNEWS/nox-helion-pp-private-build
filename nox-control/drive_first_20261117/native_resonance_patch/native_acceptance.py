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
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import signal
import stat
import threading
import time
import urllib.error
import urllib.request

ROOT = Path('/root/nox')
PROXY = ROOT / 'scripts/chat_proxy.py'
PROXY_SHA = 'a03119817d695b1dc7ca2681a60bc564a0aa891468582bbf11b70592e2b4dfd6'
BRIDGE = ROOT / 'scripts/nox_v29_chat_bridge.py'
BRIDGE_SHA = '0cff2e7aee068571b2895ec476255e97ef3b85bd93104a27a822acfb8408632b'
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

def served_asset_matches(name, raw):
    expected = EXPECTED[name]
    if digest(raw) == expected:
        return True
    # Exact existing _OwnerStatic HTML transform only. No generic stripping.
    if name == 'resonance.html' and raw.count(OWNER_HTML_INJECTION) == 1:
        return digest(raw.replace(OWNER_HTML_INJECTION, b'<head>', 1)) == expected
    return False

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

def resolve_password_path(source, source_path=PROXY, allowed_root=ROOT):
    """Interpret a tiny path AST grammar; no eval/exec/import or env expansion."""
    tree = ast.parse(source)
    assigned = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned.setdefault(target.id, []).append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assigned.setdefault(node.target.id, []).append(node.value)
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
    def evaluate(node):
        if isinstance(node, ast.Name):
            dependencies.add(node.id)
            if len(dependencies) > 64:
                raise Hold('HOLD_PATH_CHAIN_LIMIT')
            if node.id in resolving:
                raise Hold('HOLD_PATH_CYCLE')
            if node.id not in assigned:
                raise Hold('HOLD_PATH_NAME')
            if len(assigned[node.id]) != 1:
                raise Hold('HOLD_DUPLICATE_PATH_BINDING')
            resolving.add(node.id)
            result = evaluate(assigned[node.id][0])
            resolving.remove(node.id)
            return result
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'Path' and len(node.args) == 1 and not node.keywords:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return Path(arg.value)
            if isinstance(arg, ast.Name) and arg.id == '__file__':
                return Path(source_path)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            rhs = node.right
            if isinstance(rhs, ast.Constant) and isinstance(rhs.value, str) and rhs.value and not Path(rhs.value).is_absolute() and '..' not in Path(rhs.value).parts:
                return evaluate(node.left) / rhs.value
        # Exact Path(__file__).resolve().parents[1], interpreted statically.
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == 'parents':
            idx = node.slice
            call = node.value.value
            if isinstance(idx, ast.Constant) and idx.value == 1 and isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == 'resolve' and not call.args and not call.keywords:
                inner = call.func.value
                if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) and inner.func.id == 'Path' and len(inner.args) == 1 and isinstance(inner.args[0], ast.Name) and inner.args[0].id == '__file__' and not inner.keywords):
                    return Path(source_path).absolute().parents[1]
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
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPCookieProcessor(self.jar))
    def request(self, path, data=None, *, model=False, timeout=5):
        # Caller uses fixed paths only; reject any route/network injection.
        allowed = {'/chat/login', '/api/nox/chat/stream', '/api/nox/stop', '/api/ui/memory/dialogs/create'}
        allowed.update('/nox-web-v29/pc/' + name for name in EXPECTED)
        valid_history = re.fullmatch(r'/api/ui/memory/dialogs/history\?dialog_id=[a-f0-9]{32}&limit=2', path)
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

def run(canary=False, *, expected_source_sha=None, maintenance_lock_fd=None):
    started = time.monotonic()
    report = {'schema': 'NOX_NATIVE_RESONANCE_ACCEPTANCE_V1', 'mode': 'canary' if canary else 'readiness',
              'native_canary_pass': False, 'external_http_requests': 0, 'credentials_exported': False,
              'model_reloads': 0, 'dialogs_created': 0, 'model_requests': 0,
              'scope': 'LOOPBACK_18775_TO_8080_EXISTING_CHAT_AND_MODEL_8098',
              'public_tunnel_verified': False, 'actor_authorization': 'EXISTING_OWNER_REPAIR_RUNNER_REQUIRED'}
    source = regular_read(PROXY, 250000)
    if digest(source) != PROXY_SHA:
        raise Hold('HOLD_PROXY_SHA_CHANGED')
    password_path = resolve_password_path(source.decode())
    bridge_source = regular_read(BRIDGE, 250000)
    if digest(bridge_source) != BRIDGE_SHA:
        raise Hold('HOLD_BRIDGE_SHA_CHANGED')
    stop_scoped = scoped_stop_supported(bridge_source.decode())
    report['proxy_sha256'] = PROXY_SHA
    report['bridge_sha256'] = BRIDGE_SHA
    report['auth_path_resolved'] = True
    report['scoped_stop_verified'] = stop_scoped
    report['assets_on_disk'] = {name: digest(regular_read(SITE / 'pc' / name, 200000)) == expected for name, expected in EXPECTED.items()}
    report['priority'] = priority_snapshot()
    if not canary:
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
    client = LoopbackClient(); response = None; stream_started = False; stream_terminal = False
    previous_handler = signal.getsignal(signal.SIGALRM)
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise Hold('HOLD_EXISTING_ALARM')
    def expired(signum, frame):
        raise Hold('HOLD_CANARY_DEADLINE')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, max(0.01, 56 - (time.monotonic() - started)))
    try:
        with maintenance_lease(maintenance_lock_fd):
            priority_snapshot()
            report['free_model_slots'] = slots_free(client)
            info = password_path.stat()
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise Hold('HOLD_CREDENTIAL_FILE_PERMISSIONS')
            password = regular_read(password_path, 4096).decode('utf-8').strip()
            if not 6 <= len(password) <= 4096:
                raise Hold('HOLD_CREDENTIAL_UNAVAILABLE')
            try:
                client.raw('/chat/login', {'password': password}, limit=32768)
            finally:
                password = None
            if not any(True for _ in client.jar):
                raise Hold('HOLD_OFFICIAL_LOGIN_NO_SESSION')
            report['authenticated_login'] = True
            report['authenticated_assets'] = {}
            for name, expected in EXPECTED.items():
                raw = client.raw('/nox-web-v29/pc/' + name)
                report['authenticated_assets'][name] = served_asset_matches(name, raw)
            if not all(report['authenticated_assets'].values()):
                raise Hold('HOLD_SERVED_ASSET_HASH')
            marker = secrets.token_hex(6)
            question = '[QA ' + marker + '] Сколько будет 17 + 25? Ответь только числом.'
            priority_snapshot(); slots_free(client)
            created = client.json('/api/ui/memory/dialogs/create', {'confirmed': True, 'title': 'Проверка связки NOX ' + marker})
            did = created.get('dialog_id') if isinstance(created, dict) else None
            if not isinstance(did, str) or not re.fullmatch(r'[a-f0-9]{32}', did):
                raise Hold('HOLD_DIALOG_CREATE_SCHEMA')
            report['dialogs_created'] = 1
            report['own_dialog_id'] = did
            priority_snapshot(); slots_free(client)
            stream_started = True; report['model_requests'] = 1
            turn_start = time.monotonic()
            response = client.request('/api/nox/chat/stream', {'message': question, 'history': [], 'task': 'general', 'dialog_id': did}, timeout=45)
            if response.status != 200:
                raise Hold('HOLD_STREAM_HTTP')
            turn = read_stream(response, turn_start, started + 56)
            stream_terminal = True
            response.close(); response = None
            history = client.json('/api/ui/memory/dialogs/history?dialog_id=' + did + '&limit=2')
            report.update(public_turn(turn, history, question))
            report['native_canary_pass'] = report['useful_chat_pass']
            report['status'] = 'PASS' if report['native_canary_pass'] else 'HOLD_USEFUL_CHAT'
    except (Exception, KeyboardInterrupt) as exc:
        report['status'] = str(exc) if isinstance(exc, Hold) else 'HOLD_BOUNDED_CANARY_FAILURE'
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
    parser.add_argument('--canary', action='store_true')
    parser.add_argument('--expected-source-sha')
    parser.add_argument('--maintenance-lock-fd', type=int)
    args = parser.parse_args()
    try:
        result = run(args.canary, expected_source_sha=args.expected_source_sha, maintenance_lock_fd=args.maintenance_lock_fd)
    except Exception as exc:
        result = {'schema': 'NOX_NATIVE_RESONANCE_ACCEPTANCE_V1', 'status': str(exc) if isinstance(exc, Hold) else 'HOLD_READINESS_FAILURE', 'native_canary_pass': False, 'credentials_exported': False}
        if isinstance(exc, Hold) and hasattr(exc, 'dependency_identifiers'):
            result['dependency_identifiers'] = exc.dependency_identifiers
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'native_resonance_acceptance', 'data': result}, ensure_ascii=False, separators=(',', ':')), flush=True)
    return 0 if result.get('native_canary_pass') or result.get('status') == 'READY_FOR_EXPLICIT_CANARY' else 2

if __name__ == '__main__':
    raise SystemExit(main())
