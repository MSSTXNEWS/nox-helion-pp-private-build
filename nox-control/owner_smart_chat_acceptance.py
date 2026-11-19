#!/usr/bin/env python3
"""One real owner-authenticated NOX model stream and S03 dialog readback.

No browser install, GPU allocation, app reload, credentials export or destructive
change. A uniquely labelled synthetic test dialog is the only persistent write.
"""
from __future__ import annotations
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
        sys.path.insert(0, str(SCRIPTS))
        import chat_proxy
        password = chat_proxy._read_chat_password()
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
        check_stop()
        after = snapshots()
        status['resource_after'] = after
        if after['oom_kill'] != before['oom_kill']:
            fail('OOM_KILL_AFTER_GENERATION')
        status.update(chat_behavior_verified=True, s03_dialog_readback_verified=True,
            outcome='NATIVE_OWNER_STREAM_AND_S03_READBACK_PASS')
        success = True
    except Exception as error:
        code = str(error)
        status['outcome'] = code if re.fullmatch(r'HOLD_SMART_CHAT_QA_[A-Z0-9_]{1,100}', code) else 'HOLD_SMART_CHAT_QA_' + type(error).__name__.upper()
    emit(status)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    raise SystemExit(main())
