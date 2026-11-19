"""Read the active NOX cache worker and its exact cycle receipt."""

import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import stat
import time


CACHE = Path('/root/nox/logs/nox-cache-maintenance.log')
UNIT = Path('/etc/supervisor/conf.d/nox-cache-maintenance.conf')
UNIT_SHA = '9c3eb4d108fa640936a05e178c3ec4f63cc3083c3c4aa7d0a1ac8074d79c09ad'
START = Path('/root/onstart.sh')
WORKER = b'/root/nox/ops/cache-maintenance/nox_cache_maintenance.py'
MARKER = Path('/root/nox/state/chat_active')


def protected_tail(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError('HOLD_CACHE_OBSERVER_FILE')
        stream.seek(max(0, info.st_size - 64 * 1024))
        return info, stream.read(64 * 1024)


def worker():
    pid = 747159
    proc = Path(f'/proc/{pid}')
    state = (proc/'stat').read_text().rpartition(') ')[2].split()
    return (state[19] == '189183257' and state[1] == '114' and state[0] not in ('Z', 'X')
            and WORKER in (proc/'cmdline').read_bytes().split(b'\0'))


def chat_gate():
    result = {}
    try:
        info = MARKER.lstat()
    except FileNotFoundError:
        result['marker_absent'] = True
    else:
        result.update(marker_mode=oct(stat.S_IMODE(info.st_mode)),
                      marker_owner_regular=stat.S_ISREG(info.st_mode) and info.st_uid == 0,
                      marker_recent_or_future=time.time() - info.st_mtime < 3)
    connection = http.client.HTTPConnection('127.0.0.1', 8098, timeout=3)
    try:
        connection.request('GET', '/slots', headers={'Connection': 'close'})
        response = connection.getresponse()
        data = response.read(100001)
        result['slots_http'] = response.status
        if response.status == 200 and len(data) <= 100000:
            rows = json.loads(data)
            flags = [[row[key] for key in ('is_processing', 'processing') if key in row]
                     for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
            if isinstance(rows, list) and 1 <= len(flags) == len(rows) <= 64 and all(
                row and all(type(value) is bool and value == row[0] for value in row) for row in flags
            ):
                result.update(slots=len(flags), busy_slots=sum(row[0] for row in flags))
    except (OSError, ValueError, http.client.HTTPException):
        result['slots_unknown'] = True
    finally:
        connection.close()
    return result


def latest():
    observed_running = worker()
    if hashlib.sha256(protected_tail(UNIT)[1]).hexdigest() != UNIT_SHA:
        raise RuntimeError('HOLD_CACHE_OBSERVER_UNIT_PIN')
    info, data = protected_tail(CACHE)
    prefix = b'NOX_CACHE_MAINTENANCE='
    result = {'worker_generation_running': observed_running and worker(), 'log_updated_unix': info.st_mtime}
    allowed = ('state', 'verified_candidate_count', 'page_cache_residency_reduction_bytes',
               'observed_cgroup_headroom_delta_bytes', 'attempted_range_bytes', 'before', 'after')
    for line in reversed(data.splitlines()):
        if line.startswith(prefix) and len(line) < 16000:
            row = json.loads(line[len(prefix):])
            if isinstance(row, dict):
                result.update({key: row[key] for key in allowed if key in row})
                break
    root = Path('/sys/fs/cgroup')
    result['current_cgroup_headroom_bytes'] = int((root/'memory.max').read_text()) - int((root/'memory.current').read_text())
    result['chat_gate'] = chat_gate()
    return result


def startup_references():
    _, raw = protected_tail(START)
    refs = []
    for index, line in enumerate(raw.decode('utf-8').splitlines(), 1):
        clean = line.strip()
        if clean.startswith('#') or not re.search(r'conf\.d|supervisord|/etc/supervisor', clean):
            continue
        refs.append({'line': index, 'has_supervisor_command': bool(re.search(r'\bsupervisor(?:d|ctl)\b', clean)),
                     'refers_to_cache_or_holder': any(name in clean for name in ('nox-cache-maintenance', 'nox-engram-cold-holder')),
                     'writes_directly_to_supervisor_path': bool(re.search(r'>+\s*[\"\']?/(?:etc/)?supervisor/', clean)),
                     'may_change_supervisor_conf_dir': bool(re.search(r'\b(?:rm|cp|mv|install|rsync|tee)\s.*conf\.d', clean)),
                     'refers_to_teacher_warm_command': 'nox_teachers_warm.sh' in clean})
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'references': refs}


def main():
    if (os.geteuid() != 0 or not re.fullmatch(r'[1-9][0-9]{0,19}', os.environ.get('NOX_OWNER_REQUEST_ID', ''))
            or not re.fullmatch(r'[a-f0-9]{40}', os.environ.get('NOX_OWNER_SOURCE_SHA', ''))):
        raise RuntimeError('HOLD_CACHE_OBSERVER_CONTEXT')
    print('NOX_MAINT_CACHE_OBSERVATION=' + json.dumps(latest(), separators=(',', ':')), flush=True)
    print('NOX_MAINT_BOOT_CONFIG_REFERENCES=' + json.dumps(startup_references(), separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    main()
