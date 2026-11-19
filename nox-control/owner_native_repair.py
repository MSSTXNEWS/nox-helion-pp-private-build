"""Read-only cold-start and locally configured Drive facts for the owner."""

import hashlib
import json
import os
from pathlib import Path
import re
import stat


def file_fact(name, *, digest=False, keep=False):
    path = Path(name)
    try:
        mode = path.lstat()
    except FileNotFoundError:
        return {'presence': 'absent'}, b''
    trusted = (stat.S_ISREG(mode.st_mode) and mode.st_uid == 0 and mode.st_nlink == 1
               and not mode.st_mode & 0o022)
    public = {'presence': 'present', 'root_regular': trusted,
              'private_mode': trusted and not mode.st_mode & 0o077}
    if not trusted or not digest or mode.st_size > 256 * 1024:
        return public, b''
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        actual = os.fstat(stream.fileno())
        if (actual.st_dev, actual.st_ino, actual.st_size) != (mode.st_dev, mode.st_ino, mode.st_size):
            return {'presence': 'changed'}, b''
        raw = stream.read(256 * 1024 + 1)
    after = path.lstat()
    if len(raw) != mode.st_size or after.st_mtime_ns != mode.st_mtime_ns or after.st_ino != mode.st_ino:
        return {'presence': 'changed'}, b''
    public['sha256'] = hashlib.sha256(raw).hexdigest()
    return public, raw if keep else b''


def start_ticks(pid):
    raw = Path(f'/proc/{pid}/stat').read_text()
    return int(raw.rpartition(') ')[2].split()[19])


def clean_shell(raw):
    return b'\n'.join(line for line in raw.splitlines() if not line.lstrip().startswith(b'#'))


def directory_fact(name):
    path = Path(name)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {'presence': 'absent'}
    return {'presence': 'present', 'root_directory': stat.S_ISDIR(info.st_mode) and info.st_uid == 0,
            'shm_device': info.st_dev == Path('/dev/shm').stat().st_dev}


def main():
    if (os.geteuid() != 0 or not re.fullmatch(r'[a-f0-9]{40}', os.environ.get('NOX_OWNER_SOURCE_SHA', ''))
            or not re.fullmatch(r'[0-9]{1,20}', os.environ.get('NOX_OWNER_REQUEST_ID', ''))):
        raise RuntimeError('HOLD_OWNER_CONTEXT')
    startup, script = file_fact('/root/onstart.sh', digest=True, keep=True)
    active = clean_shell(script)
    startup.update(teacher_warm_reference=bool(re.search(rb'teacher.{0,60}warm|warm.{0,60}teacher', active, re.I)),
                   supervisor_reference=b'supervisor' in active.lower(),
                   supervisor_conf_reference=b'/etc/supervisor' in active,
                   drive_reference=bool(re.search(rb'rclone|cold_drive|drive-auth', active, re.I)))
    launcher, script = file_fact('/root/nox/ops/nox_boot_ds41_8098.sh', digest=True, keep=True)
    launcher.update(engram_reference=b'engram' in clean_shell(script).lower(),
                    poll_loop_present=bool(re.search(rb'\b(while|until)\b', clean_shell(script))),
                    time_limit_reference=bool(re.search(rb'\b(timeout|deadline|attempts)\b', clean_shell(script), re.I)))
    configs = {}
    prefix = '/etc/supervisor/conf.d/'
    for tag, filename in {'model': 'nox-ds41-8098.conf', 'dispatcher': 'nox-dispatcher-t855u.conf',
                          'cold_holder': 'nox-engram-cold-holder.conf'}.items():
        fact, raw = file_fact(prefix + filename, digest=True, keep=True)
        for key in (b'autostart', b'autorestart', b'startsecs', b'startretries', b'stopasgroup', b'killasgroup'):
            match = re.search(rb'(?m)^\s*' + key + rb'\s*=\s*(true|false|unexpected|[0-9]{1,6})\s*$', raw)
            fact[key.decode()] = match.group(1).decode() if match else None
        configs[tag] = fact
    profiles = {}
    for tag, filename in {'legacy': '/root/nox/state/cold_drive.conf',
                          'default': '/root/.config/rclone/rclone.conf',
                          'new': '/root/nox/state/drive-auth/rclone.conf'}.items():
        profiles[tag] = file_fact(filename)[0]
    result = {
        'container_pid1_start_ticks': start_ticks(1),
        'startup': startup, 'launcher': launcher, 'services': configs,
        'supervisor': file_fact('/etc/supervisor/supervisord.conf', digest=True)[0],
        'ops_directory': directory_fact('/root/nox/ops'),
        'supervisor_directory': directory_fact('/etc/supervisor/conf.d'),
        'active_maintenance_file': file_fact('/root/nox/state/owner_maintenance.lock')[0],
        'drive_profiles': profiles,
        'rclone_available': Path('/usr/bin/rclone').is_file() or Path('/usr/local/bin/rclone').is_file(),
    }
    print('NOX_MAINT_COLD_OWNER_FACTS=' + json.dumps(result, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    main()
