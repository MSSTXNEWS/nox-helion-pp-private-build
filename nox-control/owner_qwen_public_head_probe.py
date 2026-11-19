#!/usr/bin/env python3
"""Two bounded public HEAD requests using the frozen loader's redirect policy.

No weight/body read, proxy-policy override, credentials/log export or mutation.
Successful HEAD does not verify a complete download or identify trainer cause.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import time
import urllib.error
import urllib.request

SCRIPTS = Path('/root/nox/scripts')
MANIFEST_SHA = '2275fc88370ca8ba409a791819e13c8ab7d4e38cce4576a13170b05bcb8b839b'
MEMFD_SHA = '938335009efe691a9cef7b41daa7c55f3c8d3d8618a10a5eb5db125fd45afa82'
REVISION = 'c202236235762e1c871ad0ccb60c8ee5ba337b9a'
NAMES = ('config.json', 'model.safetensors-00001-of-00004.safetensors')
ERROR_TYPES = {'HTTPError', 'URLError', 'TimeoutError', 'OSError', 'SSLError', 'SSLCertVerificationError',
               'ConnectionResetError', 'ConnectionAbortedError', 'ConnectionRefusedError', 'gaierror',
               'RemoteDisconnected', 'IncompleteRead', 'BadStatusLine', 'Hold'}


class Hold(RuntimeError):
    pass


class ProbeDeadline(BaseException):
    pass


def require(ok, code):
    if not ok:
        raise Hold('HOLD_QWEN_PUBLIC_HEAD_' + code)


def pinned(name, expected):
    path = SCRIPTS / name
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'SOURCE_PATH')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC), 'rb') as stream:
        first = os.fstat(stream.fileno())
        require(stat.S_ISREG(first.st_mode) and first.st_uid == os.geteuid()
                and not first.st_mode & 0o022 and 0 < first.st_size <= 131072, 'SOURCE_FILE')
        raw = stream.read(131073)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(len(raw) == first.st_size and identity(first) == identity(os.fstat(stream.fileno()))
                == identity(path.stat(follow_symlinks=False))
                and hashlib.sha256(raw).hexdigest() == expected, 'SOURCE_PIN')
    return raw


def preparation():
    raw = pinned('owner_qwen_memfd.py', MEMFD_SHA)
    tree = ast.parse(raw)
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))
             and n.name in ('allowed_public_url', 'PublicHFRedirect')]
    require([n.name for n in nodes] == ['allowed_public_url', 'PublicHFRedirect'], 'REDIRECT_DEFINITIONS')
    ns = {'urllib': urllib, 'Hold': Hold}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<pinned-public-redirect-policy>', 'exec'), ns)
    manifest = json.loads(pinned('qwen35_9b_manifest.json', MANIFEST_SHA))
    files = manifest.get('files')
    require(manifest.get('model_id') == 'Qwen/Qwen3.5-9B' and manifest.get('revision') == REVISION
            and isinstance(files, list) and len(files) == 16, 'MANIFEST_IDENTITY')
    chosen = []
    for name in NAMES:
        rows = [r for r in files if isinstance(r, dict) and r.get('path') == name]
        require(len(rows) == 1, 'PUBLIC_MEMBER')
        row = rows[0]
        require(type(row.get('bytes')) is int and 0 < row['bytes'] <= 8 * 1024 ** 3
                and row.get('immutable_url') == 'https://huggingface.co/Qwen/Qwen3.5-9B/resolve/'
                    + REVISION + '/' + name, 'IMMUTABLE_PUBLIC_URL')
        ns['allowed_public_url'](row['immutable_url']); chosen.append(row)
    return ns, chosen


def head(ns, row, label):
    started = time.monotonic()
    result = {'file_kind': label, 'method': 'HEAD', 'expected_bytes': row['bytes'], 'http_status': None,
              'public_host_allowed': None, 'content_length': None, 'exception_type': None, 'errno': None,
              'response_body_bytes_read': 0}
    response = None
    try:
        class HeadOnlyRedirect(ns['PublicHFRedirect']):
            def redirect_request(self, request, *args):
                require(request.get_method() == 'HEAD', 'NON_HEAD_REQUEST')
                following = super().redirect_request(request, *args)
                if following is not None:
                    following.method = 'HEAD'  # stdlib otherwise converts HEAD to GET.
                return following
        opener = urllib.request.build_opener(HeadOnlyRedirect())
        request = urllib.request.Request(row['immutable_url'], method='HEAD',
            headers={'Accept-Encoding': 'identity', 'User-Agent': 'NOX-owner-pinned-student/1'})
        try:
            response = opener.open(request, timeout=10)
        except urllib.error.HTTPError as exc:
            response = exc
            result['exception_type'] = 'HTTPError'
        result['http_status'] = int(response.code)
        ns['allowed_public_url'](response.geturl()); result['public_host_allowed'] = True
        length = response.headers.get('Content-Length', '')
        if re.fullmatch('[0-9]{1,12}', length) and int(length) <= 64 * 1024 ** 3:
            result['content_length'] = int(length)
    except Exception as exc:
        name = type(exc).__name__; result['exception_type'] = name if name in ERROR_TYPES else 'OTHER_EXCEPTION'
        value = getattr(exc, 'errno', None)
        if type(value) is not int:
            value = getattr(getattr(exc, 'reason', None), 'errno', None)
        result['errno'] = value if type(value) is int and -65535 <= value <= 65535 else None
    finally:
        if response is not None:
            response.close()
    result.update(elapsed_seconds=round(time.monotonic() - started, 3),
                  http_response_observed=result['http_status'] is not None,
                  content_length_matches_manifest=(result['content_length'] == row['bytes'])
                      if result['content_length'] is not None else None)
    return result


def main():
    previous = signal.getsignal(signal.SIGALRM); timer = signal.getitimer(signal.ITIMER_REAL); started = time.monotonic()
    def expired(_signal, _frame):
        raise ProbeDeadline('HOLD_QWEN_PUBLIC_HEAD_DEADLINE')
    signal.signal(signal.SIGALRM, expired); signal.setitimer(signal.ITIMER_REAL, min(30, timer[0]) if timer[0] else 30)
    result = {'schema': 'NOX_QWEN_PUBLIC_HEAD_PROBE_V1', 'state': 'PUBLIC_HEAD_OBSERVATION_COMPLETE',
              'read_only': True, 'manifest_sha256': MANIFEST_SHA, 'redirect_source_sha256': MEMFD_SHA,
              'default_proxy_policy_preserved': True, 'redirected_head_method_preserved': True,
              'weight_payload_bytes_read': 0, 'files_written': 0,
              'service_actions': 0, 'full_download_verified': False, 'trainer_failure_cause_established': False, 'rows': []}
    try:
        ns, rows = preparation()
        for row, label in zip(rows, ('config', 'first_weight_shard')):
            result['rows'].append(head(ns, row, label))
        rc = 0  # Completed diagnosis, including an observed HTTP/network failure.
    except (Exception, ProbeDeadline) as exc:
        name = str(exc)
        result.update(state='HOLD', reason=name if re.fullmatch('HOLD_[A-Z0-9_]{1,150}', name)
                      else 'HOLD_QWEN_PUBLIC_HEAD_' + type(exc).__name__.upper()); rc = 2
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)
        signal.setitimer(signal.ITIMER_REAL, max(.001, timer[0] - (time.monotonic() - started)) if timer[0] else 0, timer[1])
    result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_public_head_probe', 'data': result},
          sort_keys=True, separators=(',', ':'), allow_nan=False), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(rc == 0).lower(), flush=True)
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
