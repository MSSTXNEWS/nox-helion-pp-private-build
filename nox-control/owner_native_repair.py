"""Bounded, non-mutating proof for the exact T145u teacher cold-start hooks."""

import configparser
import hashlib
import re
import shlex


STARTUP = "/root/onstart.sh"
BACKUP_T145U = "/root/onstart.sh.bak_t145u"
STARTUP_SHA = "01d1310a50048d6c8e5a972cafcea8bf5d943d598a11334a237c3b46961f18be"
WARM_SCRIPT = "/root/nox/ops/nox_teachers_warm.sh"
WARM_SCRIPT_SHA = "437739550dbdff28380a95302c1cc1e98ceab3f147de898b40dd8ec82ef80389"
WARM_MANIFEST = "/root/nox/ops/teachers_manifest.json"
WARM_MANIFEST_SHA = "237deb2a93c53de9d73501bc572f62af2565c45b8a895382a183685434199093"
WARM_CONF = "/etc/supervisor/conf.d/nox-teachers-warm.conf"
WARM_SECTION = "program:nox-teachers-warm"
MAX_BYTES = 256 << 10
MAX_LINE = 4096
SSH_START = re.compile(rb"^[ \t]*(?:/usr/sbin/)?service[ \t]+ssh[ \t]+start\b")
DAEMON = re.compile(rb"(?:^|[\s/])supervisord(?=[\s;&|]|$)")
SUP_PATH = re.compile(rb"/etc/supervisor(?:/|\b)|\bconf\.d/")
WRITE = re.compile(rb"(?:^|[ \t;&|])(?:cp|install|ln|mv|rm|tee|truncate|touch)(?:[ \t]|$)"
                   rb"|\bsed\b[^\n;]*\s-i\b|(?<![0-9&>])(?:>>|>)(?!=)")
AUTO = re.compile(rb"(^[\t ]*autostart[\t ]*=[\t ]*)(true|yes|on|1)"
                  rb"([\t ]*(?:;[^\r\n]*)?(?:\r?\n|$))", re.I | re.M)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def bounded(raw):
    return (type(raw) is bytes and 0 < len(raw) <= MAX_BYTES and b"\0" not in raw
            and all(len(line) <= MAX_LINE for line in raw.splitlines()))


def active(lines):
    return [index for index, line in enumerate(lines) if not line.lstrip().startswith(b"#")]


def startup_projection(current, backup):
    result = {"preimage_matches_current_pin": False, "single_teacher_line_matches_backup": False,
              "startup_mentions_supervisor_config": False, "startup_may_write_supervisor_config": False}
    if not bounded(current):
        return result
    result.update(sha256=digest(current), size_bytes=len(current))
    result["preimage_matches_current_pin"] = result["sha256"] == STARTUP_SHA
    lines = current.splitlines(keepends=True)
    commands = active(lines)
    teacher = [i for i in commands if WARM_SCRIPT.encode() in lines[i]]
    ssh_start = [i for i in commands if SSH_START.match(lines[i])]
    supervisor = [i for i in commands if DAEMON.search(lines[i])]
    cfg = [i for i in commands if SUP_PATH.search(lines[i])]
    result.update(teacher_hook_count=len(teacher), ssh_start_present=bool(ssh_start),
                  supervisord_launch_reference=bool(supervisor), startup_mentions_supervisor_config=bool(cfg),
                  startup_may_write_supervisor_config=any(WRITE.search(lines[i]) for i in cfg))
    if bounded(backup):
        result.update(backup_sha256=digest(backup), backup_size_bytes=len(backup))
    if not (result["preimage_matches_current_pin"] and bounded(backup)
            and len(teacher) == 1 and ssh_start and supervisor):
        return result
    index = teacher[0]
    line = lines[index]
    anchored = ssh_start[0] + 1 == index and index < supervisor[0]
    without_teacher = b"".join(lines[:index] + lines[index + 1:])
    result.update(teacher_line_number=index + 1, teacher_line_sha256=digest(line),
                  teacher_line_size_bytes=len(line), after_first_ssh_before_supervisor=anchored,
                  single_teacher_line_matches_backup=anchored and without_teacher == backup)
    return result


def config_projection(raw):
    out = {"exact_warm_service": False, "autostart_enabled": False}
    if not bounded(raw):
        return out
    out.update(sha256=digest(raw), size_bytes=len(raw))
    try:
        parser = configparser.ConfigParser(strict=True, interpolation=None, inline_comment_prefixes=(";",))
        parser.read_string(raw.decode("utf-8"))
        if parser.sections() != [WARM_SECTION] or parser.defaults():
            return out
        section = parser[WARM_SECTION]
        command = shlex.split(section.get("command", ""))
        exact = (bool(command) and command in ([WARM_SCRIPT], ["/bin/bash", WARM_SCRIPT],
                                               ["/bin/sh", WARM_SCRIPT], ["bash", WARM_SCRIPT])
                 and section.get("priority", "") == "4" and section.get("startsecs", "") == "0"
                 and section.get("autorestart", "") == "false")
        autostart = section.getboolean("autostart", fallback=True)
    except (UnicodeError, ValueError, configparser.Error):
        return out
    out.update(exact_warm_service=exact, autostart_enabled=autostart)
    if exact and autostart:
        updated, count = AUTO.subn(rb"\g<1>false\g<3>", raw)
        if count == 1:
            out["autostart_false_candidate_sha256"] = digest(updated)
    return out


def project(read):
    """Use the owner's trusted bounded file reader. Emit neither scripts nor argv."""
    def get(path):
        try:
            return read(path)
        except (OSError, ValueError):
            return b""

    warmup = get(WARM_SCRIPT)
    manifest = get(WARM_MANIFEST)
    return {
        "startup": startup_projection(get(STARTUP), get(BACKUP_T145U)),
        "warm_service": config_projection(get(WARM_CONF)),
        "warm_script_pin_matches": bounded(warmup) and digest(warmup) == WARM_SCRIPT_SHA,
        "warm_manifest_pin_matches": bounded(manifest) and digest(manifest) == WARM_MANIFEST_SHA,
        "runtime_mutated": False,
    }

"""Read-only cold-start and locally configured Drive facts for the owner."""

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import urllib.parse
import urllib.request


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


def fixed_payload(name, magic, size=None):
    path = Path(name)
    try:
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        with os.fdopen(os.open(path, flags), 'rb') as stream:
            info = os.fstat(stream.fileno())
            match = (stat.S_ISREG(info.st_mode) and info.st_uid == 0
                     and info.st_size > 0 and (size is None or size == info.st_size)
                     and info.st_dev != Path('/dev/shm').stat().st_dev and stream.read(len(magic)) == magic)
        return {'matching_file_metadata': match, 'bytes': info.st_size}
    except OSError:
        return {'matching_file_metadata': False}


def safe_hf(url):
    url = urllib.parse.urlsplit(url)
    hostname = url.hostname or ''
    if (url.scheme != 'https' or url.username is not None or url.password is not None
            or url.port not in (None, 443)
            or not (hostname == 'huggingface.co' or hostname.endswith(('.huggingface.co', '.hf.co')))):
        raise ValueError('HOLD_MODEL_ENDPOINT_SCOPE')


class ScopedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        safe_hf(url)
        return super().redirect_request(request, fp, code, message, headers, url)


def egress():
    url = ('https://huggingface.co/kerem266/DeepSeek-V4.1-Flash-Engram-IQ3_XXS/resolve/'
           '81fd6e0a6f063344001bdecc6119ac53c80c8e63/')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), ScopedRedirect())
    verified = []
    for idx, size in enumerate((21_474_836_480, 21_474_836_480, 21_474_836_480, 10_841_730_276)):
        request = urllib.request.Request(url + f'engram.part{idx:02}',
                                         headers={'Range': 'bytes=0-3', 'Accept-Encoding': 'identity'})
        try:
            with opener.open(request, timeout=12) as response:
                safe_hf(response.geturl())
                valid = (response.status == 206 and response.headers.get('Content-Range') == f'bytes 0-3/{size}'
                         and response.headers.get('Content-Encoding', 'identity') == 'identity')
                sample = response.read(5) if valid else b''
                verified.append(valid and len(sample) == 4 and (idx > 0 or sample == b'GGUF'))
        except (OSError, ValueError):
            verified.append(False)
    return {'parts': verified, 'all_reachable': all(verified), 'payload_downloaded': False}


def main():
    if (os.geteuid() != 0 or not re.fullmatch(r'[a-f0-9]{40}', os.environ.get('NOX_OWNER_SOURCE_SHA', ''))
            or not re.fullmatch(r'[0-9]{1,20}', os.environ.get('NOX_OWNER_REQUEST_ID', ''))):
        raise RuntimeError('HOLD_OWNER_CONTEXT')
    startup, script = file_fact('/root/onstart.sh', digest=True, keep=True)
    active = clean_shell(script)
    hooks = project(lambda path: file_fact(path, digest=True, keep=True)[1])
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
    for tag, filename in {'model': 'nox-ds41-8098.conf', 'dispatcher': 'nox-t855u.conf',
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
    result['warm_hooks'] = hooks
    result['cold_egress'] = egress()
    result['has_vast_environment'] = os.environ.get('VAST_CONTAINERLABEL') in ('60509551', 'C.60509551') or os.environ.get('CONTAINER_ID') == '60509551'
    result['candidate_model_launcher'] = file_fact('/root/nox/models/deepseek_v41_flash_iq2xxs/launch_ds41_8098_t119u.sh', digest=True)[0]
    base = ('/root/nox/models/deepseek_v41_flash_iq2xxs/'
            'DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-')
    result['persistent_model_parts'] = [fixed_payload(base + f'{idx:05}-of-00006.gguf', b'GGUF', size)
                                        for idx, size in enumerate((5780704, 39535781184, 39736712000,
                                                                   39036908384, 19923784832), 1)]
    result['persistent_s03'] = fixed_payload('/root/nox/kb/knowledge.sqlite', b'SQLite format 3\x00')
    result['persistent_queue'] = fixed_payload('/root/nox/state/dispatcher/state.json', b'{')
    print('NOX_MAINT_COLD_OWNER_FACTS=' + json.dumps(result, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    main()
