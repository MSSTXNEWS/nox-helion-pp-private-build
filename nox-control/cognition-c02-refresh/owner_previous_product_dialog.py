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
        'nox_v29_chat_bridge.py': '29121089891a27a0ae28795d1240788421320743a17370858c4d53aca1789e8b'}
STOPS = tuple(ROOT / name for name in
    ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'state/STOP', 'program/STOP'))
SCHEMA = 'NOX_V38_OWNER_DIALOG_RECEIPT_V1'


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
    if hashlib.sha256(raw).hexdigest() != '9fedaefbe39f4cac8a47d77bb0dada2ccf09c43ec38a5624869d3a00c0fbe5a3':
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
        fail('CREDENTIAL_PATH_NOT_STATIC')

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



def accept_turn(base, opener, status, dialog_id, question):
    check_stop()
    status['actual_generation_requests'] += 1
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
            if not line.strip():
                continue
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
    return final, done


def resume_product_dialog():
    check_stop()
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(jar), NoRedirect())
    base = local_base()
    http_request(opener, base + '/chat/login', 'POST',
                 {'password': owner_password_without_proxy_import()}, timeout=9)
    listed = http_request(opener, base + '/api/ui/memory/dialogs?limit=100', timeout=9)
    matches = [row['dialog_id'] for row in listed.get('dialogs', [])
               if row.get('title') == 'NOX V38 — приёмка 7013673520']
    if len(matches) != 1 or not re.fullmatch(r'[a-f0-9]{32}', matches[0]):
        fail('ORIGINAL_PRODUCT_DIALOG_SCOPE')
    dialog_id = matches[0]
    status = {'actual_generation_requests': 0, 'no_private_text_exported': True}
    log = ROOT / 'logs' / 'proxy.log'
    before = log.stat()
    prompt = 'Я снова тревожусь. Напомни одним словом название штабного проекта, записанное в начале этого диалога.'
    answer, done = accept_turn(base, opener, status, dialog_id, prompt)
    history = http_request(opener, base + '/api/ui/memory/dialogs/history?dialog_id=' + dialog_id + '&limit=10', timeout=9)
    messages = history.get('messages', [])
    status['context_answered'] = 'маяксевер' in answer.casefold()
    status['canonical_pair'] = (len(messages) >= 2 and messages[-2].get('role') == 'user'
        and messages[-2].get('content') == prompt and messages[-1].get('role') == 'assistant'
        and messages[-1].get('content') == answer and messages[-1].get('exchange_id') == done.get('exchange_id'))
    status['core_binding'] = 'UNOBSERVED'
    after = log.stat()
    if before.st_ino == after.st_ino and 0 <= after.st_size - before.st_size <= 262144:
        with log.open('rb') as stream:
            stream.seek(before.st_size)
            fresh = stream.read(after.st_size - before.st_size).decode('utf-8', 'replace')
        markers = re.findall(r'nox_v38_context state=([A-Z_]+) hits=(\d+) affect=(True|False) persona=([A-Z_]+|None) cores=(\{[^\r\n]*\})', fresh)
        if len(markers) == 1:
            state, hits, affect, persona, core = markers[0]
            status.update(core_binding=state, scoped_memory_hits=int(hits), behavioral_affect=affect == 'True',
                persona=persona, cores={k: v for k, v in ast.literal_eval(core).items()
                    if re.fullmatch(r'C0[1-8]', k) and re.fullmatch(r'[A-Z_]+', v)})
    return status
