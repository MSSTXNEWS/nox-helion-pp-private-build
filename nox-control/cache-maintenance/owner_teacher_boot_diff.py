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
