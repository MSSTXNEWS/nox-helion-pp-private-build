"""Bounded read-only evidence for the existing llama process; no generation."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import urllib.request

PID, START_TICKS = 7637, 149189867
PROC = Path('/proc') / str(PID)
CGROUP = Path('/sys/fs/cgroup')
LAUNCH = Path('/root/nox/scripts/start_chat_8081.sh')
LAUNCH_SHA = '98038f370163740e41d3738b1a349e8a0e2eac8ceb76a742ba67f426efa58ba4'
LOG = Path('/root/nox/logs/llama-chat-8081.log')
BINARY = Path('/root/nox/bin/llama-server')
FLAGS = {'-t': 'threads', '--threads': 'threads', '-tb': 'threads_batch', '--threads-batch': 'threads_batch', '--threads-http': 'threads_http', '--poll': 'poll', '--poll-batch': 'poll_batch', '-np': 'parallel', '--parallel': 'parallel', '-c': 'context', '--ctx-size': 'context', '--n-cpu-moe': 'cpu_moe'}
ENV_KEYS = ('LLAMA_ARG_THREADS', 'LLAMA_ARG_THREADS_BATCH', 'LLAMA_ARG_THREADS_HTTP', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')


def read(path, limit):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return None
            value = stream.read(limit + 1)
        return value if len(value) <= limit else None
    except OSError:
        return None


def process():
    raw = read(PROC / 'stat', 4096)
    try:
        fields = raw[raw.rindex(b')') + 2:].split()
        if int(raw.split(b' ', 1)[0]) != PID:
            return None
        return dict(pid=PID, start_ticks=int(fields[19]), ppid=int(fields[1]),
                    threads=int(fields[17]), user_ticks=int(fields[11]), system_ticks=int(fields[12]))
    except (AttributeError, TypeError, ValueError, IndexError):
        return None


def number(value):
    return int(value) if re.fullmatch(rb'-?[0-9]{1,7}', value) else 'UNKNOWN'


def arguments():
    raw = read(PROC / 'cmdline', 32768)
    if not raw:
        return {'executable_verified': None, 'numeric_flags': {}}
    parts = raw.rstrip(b'\0').split(b'\0')
    result = {}
    for index, item in enumerate(parts[1:], 1):
        key, separator, value = item.partition(b'=')
        name = FLAGS.get(key.decode('ascii', errors='replace'))
        if name:
            result[name] = number(value if separator else (parts[index + 1] if index + 1 < len(parts) else b''))
    return {'executable_verified': parts[0].rsplit(b'/', 1)[-1] == b'llama-server', 'numeric_flags': result}


def environment():
    raw = read(PROC / 'environ', 65536)
    if raw is None:
        return {'state': 'UNKNOWN'}
    allowed = {key.encode(): key for key in ENV_KEYS}
    return {allowed[key]: number(value) for item in raw.split(b'\0')
            for key, sep, value in [item.partition(b'=')] if sep and key in allowed}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def properties():
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open('http://127.0.0.1:8081/props', timeout=2) as response:
            raw = response.read(131073)
        if len(raw) > 131072:
            return {'state': 'UNKNOWN_RESPONSE_LIMIT'}
        data = json.loads(raw)
        settings = data.get('default_generation_settings', {})
        result = {'state': 'OBSERVED', 'build_info': 'UNKNOWN'}
        build = data.get('build_info')
        if isinstance(build, str) and re.fullmatch(r'b[0-9]{1,10}-[a-fA-F0-9]{7,64}(?:-dirty)?', build):
            result['build_info'] = build
        for key, value in [('total_slots', data.get('total_slots')), ('context_per_slot', settings.get('n_ctx'))] + [(key, data.get(key, settings.get(key))) for key in ('n_threads', 'n_threads_batch', 'n_threads_http')]:
            if type(value) is int and -1 <= value <= 1048576:
                result[key] = value
        return result
    except Exception:
        return {'state': 'UNKNOWN_HTTP_OR_METADATA'}


def startup_log():
    source = read(LAUNCH, 65536)
    if source is None or hashlib.sha256(source).hexdigest() != LAUNCH_SHA or b'LOG=/root/nox/logs/llama-chat-8081.log' not in source:
        return {'state': 'UNKNOWN_LAUNCH_SOURCE'}
    try:
        fd = os.open(LOG, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            size = os.fstat(stream.fileno()).st_size
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return {'state': 'UNKNOWN_LOG_TYPE'}
            raw = stream.read(65536)
            if size > 65536:
                stream.seek(max(65536, size - 65536))
                raw += b'\n' + stream.read(65536)
        values = {}
        for name in (b'n_threads', b'n_threads_batch', b'n_threads_http'):
            matches = re.findall(rb'(?<![A-Za-z0-9_])' + name + rb'\s*=\s*([0-9]{1,7})(?![0-9])', raw)
            values[name.decode()] = [int(item) for item in matches[-8:]]
        return {'state': 'LOG_ONLY_NOT_PID_PROVEN', 'thread_values': values}
    except OSError:
        return {'state': 'UNKNOWN_LOG'}


def executable():
    try:
        fd = os.open(PROC / 'exe', os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                return {'state': 'UNKNOWN_EXECUTABLE_TYPE'}
            result = {'device': before.st_dev, 'inode': before.st_ino, 'bytes': before.st_size}
            try:
                configured = BINARY.stat()
                result['configured_inode_matches'] = (configured.st_dev, configured.st_ino) == (before.st_dev, before.st_ino)
            except OSError:
                result['configured_inode_matches'] = None
            if before.st_size > 64 * 1024 * 1024:
                return dict(result, state='HASH_NOT_READ_SIZE_LIMIT')
            digest, deadline, remaining = hashlib.sha256(), time.monotonic() + 2, before.st_size
            while remaining:
                block = stream.read(min(1024 * 1024, remaining))
                if not block:
                    return dict(result, state='EXECUTABLE_CHANGED')
                digest.update(block)
                remaining -= len(block)
                if time.monotonic() > deadline:
                    return dict(result, state='HASH_NOT_READ_TIME_LIMIT')
            after, named = os.fstat(stream.fileno()), (PROC / 'exe').stat()
            identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
            if identity(before) != identity(after) or identity(before) != identity(named):
                return dict(result, state='EXECUTABLE_CHANGED')
            return dict(result, state='HASH_VERIFIED', sha256=digest.hexdigest())
    except OSError:
        return {'state': 'UNKNOWN_EXECUTABLE'}


def cpu():
    result = {}
    raw = read(CGROUP / 'cpu.max', 128)
    if raw and re.fullmatch(rb'(?:max|[0-9]{1,15}) [0-9]{1,15}\n?', raw):
        result['cpu_max'] = raw.decode().strip()
    raw = read(CGROUP / 'cpu.stat', 4096) or b''
    for key, value in re.findall(rb'(?m)^(usage_usec|user_usec|system_usec|nr_periods|nr_throttled|throttled_usec) ([0-9]{1,20})$', raw):
        result[key.decode()] = int(value)
    return result


def snapshot():
    result = {'schema': 'NOX_OWNER_CHAT_RUNTIME_SNAPSHOT_V1', 'recorded_unix': round(time.time(), 3), 'cpu': cpu()}
    before = process()
    if before is None:
        return dict(result, state='UNKNOWN_PROCESS', process_identity_verified=False)
    if before['start_ticks'] != START_TICKS:
        return dict(result, state='PROCESS_IDENTITY_CHANGED', process_identity_verified=False)
    argv = arguments()
    if argv['executable_verified'] is False:
        return dict(result, state='PROCESS_IDENTITY_CHANGED', process_identity_verified=False)
    result.update(process_before=before, arguments=argv, environment=environment(), props=properties(), startup_log=startup_log(), executable=executable())
    after = process()
    if after is None or after['start_ticks'] != START_TICKS:
        return {'schema': result['schema'], 'recorded_unix': result['recorded_unix'], 'cpu': result['cpu'], 'state': 'PROCESS_IDENTITY_CHANGED', 'process_identity_verified': False}
    result.update(process_after=after, state='OBSERVED' if argv['executable_verified'] else 'PARTIAL_UNKNOWN_EXECUTABLE', process_identity_verified=argv['executable_verified'] is True)
    return result


def main():
    print(json.dumps(snapshot(), sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
