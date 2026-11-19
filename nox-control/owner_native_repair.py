"""Accept the deployed Resonance route with two owner-scoped synthetic turns."""
from contextlib import contextmanager
import fcntl
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time
import urllib.error
import urllib.request


ROOT = Path('/root/nox')
BASE = 'http://127.0.0.1:8080'
PROXY = ROOT / 'scripts/chat_proxy.py'
PROXY_SHA = 'd19027e3d12980baa619474e633c5cd452d1570d8c5549b1421fc8041e2c4064'
STOP_MARKS = tuple(ROOT / marker for marker in (
    'STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP',
    'state/STOP.flag', 'state/OWNER_MAINTENANCE.flag',
)) + (Path('/workspace/NOX_STOP'),)
GIB = 1024 ** 3
MIB = 1024 ** 2
READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


class Hold(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Hold('HOLD_CONTEXT_REDIRECT')


def require(ok, code):
    if not ok:
        raise Hold('HOLD_CONTEXT_' + code)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def same_file(a, b):
    return (a.st_dev, a.st_ino, a.st_size, a.st_mtime_ns, a.st_ctime_ns) == (
        b.st_dev, b.st_ino, b.st_size, b.st_mtime_ns, b.st_ctime_ns)


def scoped_file(path, cap, *, private=False):
    require(not any(parent.is_symlink() for parent in path.parents), 'PARENT_SCOPE')
    with os.fdopen(os.open(path, READ), 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1
                and not before.st_mode & (0o077 if private else 0o022)
                and 0 < before.st_size <= cap, 'FILE_SCOPE')
        raw = stream.read(cap + 1)
        require(len(raw) == before.st_size and same_file(before, os.fstat(stream.fileno()))
                and same_file(before, path.lstat()), 'FILE_CHANGED')
    return raw


@contextmanager
def owner_lease():
    path = ROOT / 'state/owner_maintenance.lock'
    fd = os.open(path, READ)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
                and not info.st_mode & 0o022 and same_file(info, path.lstat()), 'LEASE_SCOPE')
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Hold('HOLD_CONTEXT_MAINTENANCE_ACTIVE') from None
        yield
    finally:
        os.close(fd)


def active_proxy():
    identities = []
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            command = (process / 'cmdline').read_bytes()
            if str(PROXY).encode() not in command.split(b'\0'):
                continue
            fields = (process / 'stat').read_bytes().rsplit(b') ', 1)[1].split()
            if fields[0] not in (b'Z', b'X'):
                identities.append((int(process.name), int(fields[19])))
        except (FileNotFoundError, ProcessLookupError, PermissionError, IndexError):
            continue
    require(len(identities) == 1, 'PROXY_PROCESS')
    return identities[0]


def guard(receipt, identity, *, require_idle):
    require(not any(os.path.lexists(path) for path in STOP_MARKS), 'STOP')
    require(digest(scoped_file(PROXY, 256 * 1024)) == PROXY_SHA and active_proxy() == identity, 'PROXY_CHANGED')
    cg = Path('/sys/fs/cgroup')
    max_raw = (cg / 'memory.max').read_text().strip()
    require(max_raw.isdigit(), 'MEMORY_LIMIT_UNKNOWN')
    free = int(max_raw) - int((cg / 'memory.current').read_text())
    counters = dict((name, int(value)) for name, value in
                    (line.split() for line in (cg / 'memory.stat').read_text().splitlines()))
    cold = max(0, min(counters['inactive_file'], max(0, counters['file'] - counters['shmem']))
               - counters['shmem'])
    receipt['memory_raw_headroom_bytes'] = free
    receipt['memory_cold_lower_bound_bytes'] = cold
    events = dict(line.split() for line in (cg / 'memory.events').read_text().splitlines())
    pressure = (cg / 'memory.pressure').read_text().splitlines()
    require(events.get('oom') == events.get('oom_kill') == '0' and len(pressure) == 2 and
            all(re.search(r'\bavg10=0\.00\b', row) for row in pressure), 'MEMORY_PRESSURE')
    require((free >= 512 * MIB and cold >= 4 * GIB) or (free >= 256 * MIB and cold >= 12 * GIB),
            'MODEL_MEMORY')
    if require_idle:
        probe = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        slots = None
        for port in (8081, 8098):
            try:
                with probe.open(f'http://127.0.0.1:{port}/slots', timeout=3) as response:
                    raw = response.read(32769)
                candidate = json.loads(raw) if len(raw) <= 32768 else None
            except (OSError, ValueError):
                continue
            if isinstance(candidate, list) and 0 < len(candidate) <= 10 and all(
                    isinstance(row, dict) and ('is_processing' in row or 'processing' in row)
                    for row in candidate):
                slots = candidate
                break
        require(slots is not None, 'MODEL_SLOTS_UNKNOWN')
        require(all(row.get('is_processing', row.get('processing')) is False for row in slots), 'MODEL_BUSY')


def request(client, path, payload=None, *, timeout=12):
    raw = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
    return client.open(urllib.request.Request(BASE + path, data=raw,
                       headers={'Content-Type': 'application/json'}), timeout=timeout)


def reply_json(client, path, payload=None):
    with request(client, path, payload) as result:
        raw = result.read(65537)
        require(result.status == 200 and len(raw) <= 65536, 'RESPONSE')
    value = json.loads(raw)
    require(isinstance(value, dict), 'JSON_SCHEMA')
    return value


def model_turn(client, dialog_id, user_text):
    chunks = []
    started = time.monotonic()
    terminal = None
    with request(client, '/api/nox/chat/stream', {'message': user_text, 'history': [],
                 'task': 'general', 'dialog_id': dialog_id}, timeout=32) as result:
        require(result.status == 200, 'STREAM_HTTP')
        total = 0
        for index in range(256):
            raw = result.readline(32769)
            if not raw:
                break
            require(index < 255 and len(raw) <= 32768 and time.monotonic() - started <= 65, 'STREAM_BOUNDS')
            line = raw.strip()
            if not line or line.startswith((b':', b'event:', b'id:', b'retry:')):
                continue
            if line.startswith(b'data:'):
                line = line[5:].strip()
            if line == b'[DONE]':
                break
            frame = json.loads(line)
            require(isinstance(frame, dict), 'STREAM_SCHEMA')
            kind = frame.get('type')
            if kind == 'delta':
                text = frame.get('text')
                require(isinstance(text, str), 'STREAM_DELTA')
                chunks.append(text)
                total += len(text)
                require(total <= 6000, 'ANSWER_LENGTH')
            elif kind == 'done':
                terminal = frame
                break
            elif kind == 'error':
                raise Hold('HOLD_CONTEXT_STREAM_ERROR')
    response_text = ''.join(chunks)
    require(isinstance(terminal, dict) and bool(response_text.strip()), 'STREAM_TERMINAL')
    if 'dialog_id' in terminal:
        require(terminal['dialog_id'] == dialog_id, 'STREAM_DIALOG')
    if 'saved' in terminal:
        require(terminal['saved'] is True, 'STREAM_SAVE')
    require(terminal.get('model_called') is not False and not terminal.get('tool'), 'STREAM_TOOL_ONLY')
    return response_text, len(chunks)


def main():
    request_id = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    report = {'kind': 'resonance_context_acceptance_v1', 'posts': 0, 'request_id': request_id,
              'proxy_sha256': PROXY_SHA, 'context_recall': False, 'dialog_readback': False,
              'raw_content_exported': False, 'canonical_s03_receipt_verified': False}
    client = None
    accepted = False
    try:
        labels = {os.environ[k].removeprefix('C.') for k in ('VAST_CONTAINERLABEL', 'CONTAINER_ID')
                  if os.environ.get(k)}
        require(os.geteuid() == 0 and labels == {'60509551'} and re.fullmatch('[1-9][0-9]{0,19}', request_id)
                and re.fullmatch('[a-f0-9]{40}', os.environ.get('NOX_OWNER_SOURCE_SHA', '')), 'OWNER_CONTEXT')
        with owner_lease():
            identity = active_proxy()
            report['proxy_identity'] = identity
            guard(report, identity, require_idle=True)
            jar = http.cookiejar.CookieJar()
            client = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                                 urllib.request.HTTPCookieProcessor(jar))
            password = scoped_file(ROOT / 'secrets/chat_password', 4096, private=True).decode('utf-8').strip()
            with request(client, '/chat/login', {'password': password}) as login:
                require(login.status == 200 and any(jar), 'OWNER_LOGIN')
            del password
            require(reply_json(client, '/chat/session').get('ok') is True, 'OWNER_SESSION')
            report['owner_authenticated'] = True
            canary = 'ORBITA' + secrets.token_hex(6).upper()
            prompts = (f'В нашей игре научная станция называется {canary}. Запомни имя. Ответь только «Принято».',
                       'А как она называется? Ответь только названием.')
            dialog = reply_json(client, '/api/ui/memory/dialogs/create',
                                {'title': 'NOX QA / проверка контекста ' + request_id, 'confirmed': True})
            dialog_id = dialog.get('dialog_id')
            require(isinstance(dialog_id, str) and re.fullmatch('[a-f0-9]{32}', dialog_id), 'DIALOG')
            report['dialog_sha256'] = digest(dialog_id.encode())
            expected = []
            report['turns'] = []
            for prompt in prompts:
                guard(report, identity, require_idle=True)
                report['posts'] += 1
                answer, chunks = model_turn(client, dialog_id, prompt)
                expected.extend([('user', prompt), ('assistant', answer)])
                report['turns'].append({'user_sha256': digest(prompt.encode()),
                                        'answer_sha256': digest(answer.encode()), 'chunks': chunks})
            saved = reply_json(client, '/api/ui/memory/dialogs/history?dialog_id=' + dialog_id + '&limit=6')
            messages = saved.get('messages')
            report['dialog_readback'] = isinstance(messages, list) and len(messages) == 4 and all(
                isinstance(row, dict) and (row.get('role'), row.get('content')) == pair
                for row, pair in zip(messages, expected))
            report['context_recall'] = answer.strip() == canary
            require(report['dialog_readback'] and report['context_recall'], 'RECALL_OR_PERSISTENCE')
            require(active_proxy() == identity, 'PROXY_CHANGED')
            accepted = True
    except Hold as failure:
        report['reason'] = str(failure)
    except urllib.error.HTTPError as failure:
        report['reason'] = f'HOLD_CONTEXT_HTTP_{failure.code}'
    except (OSError, ValueError, KeyError, TypeError, IndexError) as failure:
        report['reason'] = 'HOLD_CONTEXT_' + type(failure).__name__.upper()
    finally:
        if client is not None:
            try:
                with request(client, '/chat/logout', {}, timeout=4) as response:
                    response.read(4096)
            except (OSError, Hold):
                pass
    report['state'] = 'TWO_TURN_CONTEXT_ACCEPTED' if accepted else 'HOLD'
    print('NOX_MAINT_RESONANCE_CONTEXT=' + json.dumps(report, sort_keys=True), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
