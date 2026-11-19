#!/usr/bin/env python3
"""Read only fixed advisor key-presence booleans via the owner native inspector."""
import json
import os
from pathlib import Path
import re
import stat
import subprocess


KEYS = {'openrouter': b'OPENROUTER_API_KEY', 'groq': b'GROQ_API_KEY',
        'gemini': b'GEMINI_API_KEY'}
SERVICES = ('nox-proxy', 'nox-dispatcher-t855u')
CONTROL = (Path('/usr/bin/supervisorctl'), Path('/usr/local/bin/supervisorctl'))
SUPERVISOR_CONFIG = Path('/etc/supervisor/supervisord.conf')


def present(value):
    return isinstance(value, bytes) and bool(value.strip()) and b'\r' not in value and b'\n' not in value


def project_environment(data):
    result = dict.fromkeys(KEYS, False)
    reverse = {name: provider for provider, name in KEYS.items()}
    for entry in data.split(b'\0'):
        name, separator, value = entry.partition(b'=')
        if separator and name in reverse:
            result[reverse[name]] = result[reverse[name]] or present(value)
    return result


def is_trusted_regular(path, *, executable=False):
    try:
        info = path.lstat()
    except OSError:
        return False
    return (stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022
            and (not executable or bool(info.st_mode & 0o111)))


def read_proc(pid, name, limit):
    path = Path('/proc') / str(pid) / name
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError('PROC_FIELD_SIZE')
    return data


def process_identity(pid):
    data = read_proc(pid, 'stat', 4096)
    fields = data.rsplit(b')', 1)[1].split()
    return fields[19]


def supervisor_pid(command, name):
    if command is None or not is_trusted_regular(SUPERVISOR_CONFIG):
        return None
    try:
        result = subprocess.run([str(command), '-c', str(SUPERVISOR_CONFIG), 'pid', name],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'},
                                stdin=subprocess.DEVNULL, timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    if result.returncode or re.fullmatch(rb'[1-9][0-9]{0,8}', value) is None:
        return None
    return int(value)


def service_projection(command, name):
    scope = {'program': name, 'trusted_config_present': is_trusted_regular(
        SUPERVISOR_CONFIG.parent / 'conf.d' / (name + '.conf')), 'state': 'UNOBSERVED',
        'keys_present': dict.fromkeys(KEYS, None)}
    pid = supervisor_pid(command, name)
    if pid is None:
        return scope
    try:
        before = process_identity(pid)
        keys = project_environment(read_proc(pid, 'environ', 131072))
        if process_identity(pid) != before or supervisor_pid(command, name) != pid:
            return dict(scope, state='PROCESS_REPLACED_DURING_READ')
    except (OSError, ValueError, IndexError):
        return dict(scope, state='ENV_READ_UNAVAILABLE')
    return dict(scope, state='PRESENCE_ONLY', keys_present=keys)


def main():
    control = next((path for path in CONTROL if is_trusted_regular(path, executable=True)), None)
    row = {'schema': 'NOX_ADVISOR_PROVIDER_READINESS_V1',
           'probe_keys_present': {provider: present(os.environb.get(key)) for provider, key in KEYS.items()},
           'services': [service_projection(control, name) for name in SERVICES],
           'key_values_reported': False, 'provider_contacted': False,
           'account_or_quota_verified': False}
    print('NOX_MAINT_SCOPE_ADVISOR_PROVIDER_READINESS=' + json.dumps(row, separators=(',', ':')), flush=True)
    print('NOX_MAINT_INSPECT_COMPLETE=true', flush=True)


if __name__ == '__main__':
    main()
