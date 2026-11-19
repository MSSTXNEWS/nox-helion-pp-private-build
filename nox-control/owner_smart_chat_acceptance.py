#!/usr/bin/env python3
"""One real owner-authenticated NOX model stream and S03 dialog readback.

No browser install, GPU allocation, app reload, credentials export or destructive
change. A uniquely labelled synthetic test dialog is the only persistent write.
"""
from __future__ import annotations
import ast
import fcntl
import hashlib
import http.cookiejar
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path('/root/nox')
SCRIPTS = ROOT / 'scripts'
PINS = {'owner_chat_stream.py': 'a26ec83aadac240d7284959b53cf7e59575e8e487d27c962cec7236892ccc7af',
        'nox_v29_chat_bridge.py': '2d7145293fa5566fee38a61e772780b4b0dd0e2d1bcad71b5ceedf77974a75a7'}
STOPS = tuple(ROOT / name for name in
    ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'state/STOP', 'program/STOP'))
SCHEMA = 'NOX_SMART_CHAT_OWNER_E2E_ACCEPTANCE_V1'



def safe_ast_shape(expr, max_nodes=64, max_depth=12):
    """Return bounded AST node kinds/shape only; omit identifiers and literals."""
    rows = []
    deepest = 0
    truncated = False
    stack = [(expr, 0)]
    while stack and len(rows) < max_nodes:
        node, depth = stack.pop()
        if depth > max_depth:
            truncated = True
            continue
        children = list(ast.iter_child_nodes(node))
        rows.append({'type': type(node).__name__, 'depth': depth, 'children': len(children)})
        deepest = max(deepest, depth)
        for child in reversed(children):
            stack.append((child, depth + 1))
    return {'node_count': len(rows), 'max_depth': deepest,
            'truncated': truncated or bool(stack), 'nodes': rows}


def credential_path_not_static(expr):
    error = RuntimeError('HOLD_SMART_CHAT_QA_CREDENTIAL_PATH_NOT_STATIC')
    error.safe_ast_shape = safe_ast_shape(expr)
    return error

def fail(code):
    raise RuntimeError('HOLD_SMART_CHAT_QA_' + code)


def emit(data):
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'smart_chat_owner_e2e_qa', 'data': data},
        separators=(',', ':'), sort_keys=True, allow_nan=False), flush=True)


def check_stop():
    if any(os.path.lexists(x) for x in STOPS):
        fail('OWNER_STOP')


def local_base():
    for _, name in socket.if_nameindex():
        if name == 'lo':
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                raw = fcntl.ioctl(sock.fileno(), 0x8915,
                    struct.pack('256s', name.encode()[:15]))
            host = socket.inet_ntoa(raw[20:24])
            if ipaddress.ip_address(host).is_private:
                return 'http://' + host + ':8080'
        except (OSError, ValueError):
            continue
    fail('SCOPED_OWNER_ORIGIN_UNAVAILABLE')


def http_request(opener, url, method='GET', payload=None, timeout=9, stream=False):
    data = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode() if payload is not None else None
    headers = {'Accept': 'application/json', 'Connection': 'close'}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    response = opener.open(request, timeout=timeout)
    if stream:
        return response
    with response:
        raw = response.read(262145)
        if len(raw) > 262144:
            fail('HTTP_RESPONSE_OVERSIZE')
        if response.status != 200:
            fail('HTTP_STATUS')
        if urllib.parse.urlsplit(url).path in ('/chat/login', '/chat/session'):
            return {'http_status': response.status}
        return json.loads(raw)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def process_state(service):
    run = subprocess.run(['supervisorctl', 'status', service],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, timeout=6)
    lines = run.stdout.decode('utf-8', 'replace').strip().splitlines()
    # supervisorctl right-pads service names with spaces. Match columns, not
    # a literal single-space prefix, and pin the actual reported PID.
    match = (re.fullmatch(re.escape(service) + r'\s+RUNNING\s+pid\s+([0-9]{1,10}),.*',
                        lines[0]) if len(lines) == 1 else None)
    if run.returncode != 0 or match is None:
        fail('SERVICE_NOT_RUNNING_' + service.upper().replace('-','_'))
    pid = int(match.group(1))
    if not Path('/proc', str(pid), 'stat').is_file():
        fail('SERVICE_PID_NOT_LIVE_' + service.upper().replace('-','_'))
    return True


def snapshots():
    maximum = (Path('/sys/fs/cgroup/memory.max')).read_text().strip()
    current = (Path('/sys/fs/cgroup/memory.current')).read_text().strip()
    events = {}
    for line in Path('/sys/fs/cgroup/memory.events').read_text().splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in ('oom','oom_kill') and parts[1].isdigit():
            events[parts[0]] = int(parts[1])
    if not maximum.isdigit() or not current.isdigit() or events.get('oom', -1) < 0:
        fail('CGROUP_UNKNOWN')
    return {'raw_margin_bytes': int(maximum)-int(current), 'oom': events['oom'],
            'oom_kill': events.get('oom_kill', -1)}



def owner_password_without_proxy_import():
    """Read only the literal owner password path in the pinned native source.

    Never execute chat_proxy.py and never log or export the password bytes.
    """
    proxy = SCRIPTS / 'chat_proxy.py'
    meta = proxy.lstat()
    if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1 or
            meta.st_uid != os.geteuid() or meta.st_size > 1048576):
        fail('PROXY_SOURCE_SCOPE')
    raw = proxy.read_bytes()
    if hashlib.sha256(raw).hexdigest() != 'cc1437ce8c3bfbbc4259ffdbe299bf3b8721d4b1bb09c88565ccb6cb9fdb95eb':
        fail('PROXY_SOURCE_CAS')
    tree = ast.parse(raw)
    definitions = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            definitions[node.targets[0].id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            definitions[node.target.id] = node.value

    # The owner path is `SECRETS / <filename>`; SECRETS is imported from
    # common.py. Resolve just its pinned static AST, never import common.
    common = SCRIPTS / 'common.py'
    common_meta = common.lstat()
    if (not stat.S_ISREG(common_meta.st_mode) or common_meta.st_nlink != 1 or
            common_meta.st_uid != os.geteuid() or common_meta.st_size > 1048576):
        fail('COMMON_SOURCE_SCOPE')
    common_raw = common.read_bytes()
    if hashlib.sha256(common_raw).hexdigest() != '177fbe5df042ba75a94cf9b7c03c8ffe58bde99f12599193db0cf383cc1305dd':
        fail('COMMON_SOURCE_CAS')
    common_defs = {}
    for node in ast.parse(common_raw).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ('ROOT', 'SECRETS'):
                common_defs[node.targets[0].id] = node.value
    if set(common_defs) != {'ROOT', 'SECRETS'}:
        fail('COMMON_SECRET_BINDING_SCOPE')

    def literal_path(expr, seen=(), scope='proxy'):

        if len(seen) >= 8:
            fail('CREDENTIAL_PATH_DEPTH')
        defs = definitions if scope == 'proxy' else common_defs
        if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
            return Path(expr.value)
        if (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name)
                and expr.func.id == 'Path' and len(expr.args) == 1 and not expr.keywords):
            return literal_path(expr.args[0], seen, scope)
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
            left, right = literal_path(expr.left, seen, scope), literal_path(expr.right, seen, scope)
            if right.is_absolute():
                fail('CREDENTIAL_PATH_ESCAPE')
            return left / right
        if isinstance(expr, ast.Name) and expr.id not in seen and expr.id in defs:
            return literal_path(defs[expr.id], seen + (expr.id,), scope)
        if isinstance(expr, ast.Name) and expr.id == 'SECRETS' and 'SECRETS' not in seen and scope == 'proxy':
            return literal_path(common_defs['SECRETS'], seen + ('SECRETS',), 'common')
        raise credential_path_not_static(expr)

    if 'CHAT_PASSWORD_PATH' not in definitions:
        fail('CREDENTIAL_PATH_NOT_DECLARED')
    path = literal_path(definitions['CHAT_PASSWORD_PATH'])
    if not path.is_absolute() or '..' in path.parts or path.parts[:3] != ('/', 'root', 'nox'):
        fail('CREDENTIAL_PATH_NOT_OWNER_SCOPED')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        meta = os.fstat(descriptor)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.geteuid() or
                meta.st_nlink != 1 or (meta.st_mode & 0o077) != 0 or
                not 1 <= meta.st_size <= 4096):
            fail('CREDENTIAL_FILE_SCOPE')
        raw_password = os.read(descriptor, 4097)
        if len(raw_password) != meta.st_size:
            fail('CREDENTIAL_FILE_CHANGED')
        return raw_password.decode('utf-8').strip()
    finally:
        os.close(descriptor)



def main():
    request_id = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    sha = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch(r'[0-9]{1,24}', request_id) or not re.fullmatch(r'[0-9a-f]{40}', sha):
        fail('OWNER_CONTEXT')
    status = {'schema': SCHEMA, 'request': request_id, 'source_sha': sha,
        'actual_generation_requests': 0, 'chat_behavior_verified': False,
        's03_dialog_readback_verified': False, 'private_bodies_exported': False,
        'credentials_exported': False, 'services_modified': False,
        'stop_flags_changed': False}
    success = False
    try:
        check_stop()
        for name, pin in PINS.items():
            path = SCRIPTS / name
            meta = path.lstat()
            if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:
                fail('SOURCE_SCOPE')
            if hashlib.sha256(path.read_bytes()).hexdigest() != pin:
                fail('SOURCE_IDENTITY')
        for name in ('nox-proxy','nox-ds41-8098','nox-web29-18775'):
            process_state(name)
        before = snapshots()
        status['resource_before'] = before
        if before['oom'] != 0 or before['oom_kill'] != 0 or before['raw_margin_bytes'] < 8*1024*1024:
            fail('RESOURCE_ADMISSION')
        # Separate cookies from the owner's real browser. No user dialog read.
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(jar), NoRedirect())
        base = local_base()
        try:
            http_request(opener, base + '/api/ui/executors', timeout=6)
            fail('ANONYMOUS_SCOPE_LEAK')
        except urllib.error.HTTPError as error:
            if error.code != 401:
                fail('ANONYMOUS_SCOPE_UNVERIFIED')
        password = owner_password_without_proxy_import()
        if not isinstance(password, str) or not 6 <= len(password) <= 4096:
            fail('NATIVE_OWNER_CREDENTIAL')
        login = http_request(opener, base + '/chat/login', 'POST', {'password': password}, timeout=9)
        password = None
        status['owner_login_verified'] = isinstance(login, dict)
        session = http_request(opener, base + '/chat/session', timeout=9)
        status['owner_session_verified'] = isinstance(session, dict)
        if not status['owner_login_verified'] or not status['owner_session_verified']:
            fail('OWNER_SESSION')
        title = 'NOX E2E ' + request_id
        created = http_request(opener, base + '/api/ui/memory/dialogs/create',
            'POST', {'title': title, 'confirmed': True}, timeout=9)
        dialog_id = created.get('dialog_id') if isinstance(created, dict) else None
        if not isinstance(dialog_id, str) or not re.fullmatch(r'[0-9a-f]{32}', dialog_id):
            fail('QA_DIALOG_NOT_CREATED')
        status['synthetic_dialog_created'] = True
        question = 'Проверка NOX. Ответь только словом ГОТОВО.'
        check_stop()
        status['actual_generation_requests'] = 1
        response = http_request(opener, base + '/api/nox/chat/stream', 'POST',
            {'message': question, 'dialog_id': dialog_id}, timeout=150, stream=True)
        seen = []; answer = []; error = None; done = None; total = 0
        with response:
            if response.status != 200:
                fail('CHAT_STREAM_HTTP')
            while True:
                line = response.readline(65537)
                if not line:
                    break
                total += len(line)
                if len(line) > 65536 or total > 262144:
                    fail('CHAT_STREAM_SIZE')
                frame = json.loads(line)
                if not isinstance(frame, dict):
                    fail('CHAT_FRAME_SHAPE')
                kind = frame.get('type')
                if kind == 'delta' and isinstance(frame.get('text'), str):
                    answer.append(frame['text'])
                    if sum(len(x) for x in answer) > 4000:
                        fail('CHAT_OUTPUT_SCOPE')
                if kind == 'error':
                    error = frame.get('error')
                    break
                if kind == 'done':
                    done = frame
                    break
                if kind in ('preparing','start','delta'):
                    seen.append(kind)
        final = ''.join(answer)
        status['stream_types_seen'] = sorted(set(seen))
        status['answer_characters'] = len(final)
        status['answer_sha256'] = hashlib.sha256(final.encode()).hexdigest() if final else None
        status['done_received'] = bool(done)
        status['upstream_error_code'] = error if isinstance(error, str) and re.fullmatch(
            r'[A-Z0-9_]{3,100}', error) else type(error).__name__ if error else None
        if error or not done or not final.strip() or final.strip() in ('—','-','...'):
            fail('MODEL_STREAM_INCOMPLETE')
        if done.get('saved') is not True or done.get('s03_integrated') is not True:
            fail('S03_TERMINAL_RECEIPT')
        if done.get('dialog_id') != dialog_id:
            fail('DIALOG_SCOPE_CHANGED')
        history = http_request(opener, base + '/api/ui/memory/dialogs/history?dialog_id=' + dialog_id + '&limit=10', timeout=9)
        messages = history.get('messages', []) if isinstance(history, dict) else []
        matched = (len(messages) >= 2 and messages[-2].get('role') == 'user' and
            messages[-2].get('content') == question and
            messages[-1].get('role') == 'assistant' and messages[-1].get('content') == final and
            messages[-1].get('exchange_id') == done.get('exchange_id'))
        if not matched:
            fail('S03_DIALOG_READBACK_MISMATCH')
        # Same owner-authenticated, same-dialog continuation. Exactly one more
        # model request: never repeat the first turn or any external tools.
        second_question = 'Какое одно слово ты ответил в предыдущем сообщении? Повтори его.'
        check_stop()
        status['actual_generation_requests'] = 2
        second = http_request(opener, base + '/api/nox/chat/stream', 'POST',
            {'message': second_question, 'dialog_id': dialog_id}, timeout=150, stream=True)
        second_answer = []; second_done = None; second_error = None; second_bytes = 0; second_types = []
        with second:
            if second.status != 200:
                fail('CONTINUATION_HTTP')
            while True:
                line = second.readline(65537)
                if not line:
                    break
                second_bytes += len(line)
                if len(line) > 65536 or second_bytes > 262144:
                    fail('CONTINUATION_STREAM_BUDGET')
                frame = json.loads(line)
                if not isinstance(frame, dict):
                    fail('CONTINUATION_FRAME')
                if isinstance(frame.get('type'), str) and len(second_types) < 32:
                    second_types.append(frame['type'])
                if frame.get('type') == 'delta' and isinstance(frame.get('text'), str):
                    second_answer.append(frame['text'])
                    if sum(len(x) for x in second_answer) > 4000:
                        fail('CONTINUATION_OUTPUT_BUDGET')
                elif frame.get('type') == 'error':
                    second_error = frame.get('error')
                    break
                elif frame.get('type') == 'done':
                    second_done = frame
                    break
        resumed = ''.join(second_answer)
        status['continuation_characters'] = len(resumed)
        status['continuation_sha256'] = hashlib.sha256(resumed.encode()).hexdigest() if resumed else None
        status['continuation_done'] = bool(second_done)
        status['continuation_frame_types'] = sorted(set(second_types))
        errcode = (second_error.get('code') if isinstance(second_error, dict) else second_error)
        status['continuation_error_code'] = (errcode if isinstance(errcode, str) and re.fullmatch(r'[A-Z0-9_]{3,100}', errcode) else 'UNCLASSIFIED' if second_error else None)
        if second_error or not second_done or not resumed.strip() or resumed.strip() in ('—','-','...'):
            fail('CONTINUATION_INCOMPLETE')
        if (second_done.get('saved') is not True or second_done.get('s03_integrated') is not True
                or second_done.get('dialog_id') != dialog_id):
            fail('CONTINUATION_S03_RECEIPT')
        new_history = http_request(opener,
            base + '/api/ui/memory/dialogs/history?dialog_id=' + dialog_id + '&limit=10', timeout=9)
        pairs = new_history.get('messages', []) if isinstance(new_history, dict) else []
        expected_pairs = [('user', question), ('assistant', final),
                          ('user', second_question), ('assistant', resumed)]
        if len(pairs) < 4 or [(row.get('role'), row.get('content'))
                               for row in pairs[-4:]] != expected_pairs:
            fail('CONTINUATION_S03_HISTORY')
        if pairs[-1].get('exchange_id') != second_done.get('exchange_id'):
            fail('CONTINUATION_S03_EXCHANGE_ID')
        status['continuation_semantic_recall_observed'] = 'готово' in resumed.casefold()
        status['same_dialog_continuation_and_s03_verified'] = True
        check_stop()
        after = snapshots()
        status['resource_after'] = after
        if after['oom_kill'] != before['oom_kill']:
            fail('OOM_KILL_AFTER_GENERATION')
        status.update(chat_behavior_verified=True, s03_dialog_readback_verified=True,
            outcome='NATIVE_OWNER_TWO_TURNS_AND_S03_READBACK_PASS')
        success = True
    except Exception as error:
        shape = getattr(error, 'safe_ast_shape', None)
        if isinstance(shape, dict):
            status['credential_path_ast_shape'] = shape
        code = str(error)
        status['outcome'] = code if re.fullmatch(r'HOLD_SMART_CHAT_QA_[A-Z0-9_]{1,100}', code) else 'HOLD_SMART_CHAT_QA_' + type(error).__name__.upper()
    emit(status)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    raise SystemExit(main())
