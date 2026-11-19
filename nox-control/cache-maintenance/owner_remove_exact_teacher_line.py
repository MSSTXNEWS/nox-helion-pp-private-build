"""Remove only the exact attested synchronous teacher-warm startup command."""

import fcntl
import os
import re
import shlex
import stat
import subprocess
import uuid
from contextlib import ExitStack
from pathlib import Path

from owner_disable_teacher_boot import (
    Change, DIR_FLAGS, INSTANCE, LEASE, PHASE2_REQUEST, PHASE2_SOURCE, READ_FLAGS,
    WRITE_FLAGS, assert_directory, checked_lease, directory, exact, exchange,
    inode, need, owner, pid1_start, prepare, read, rollback, trust, unlink_prepared,
)
from owner_teacher_boot_diff import STARTUP, STARTUP_SHA, WARM_CONF, config_projection, digest


STARTUP_LENGTH = 1621
TEACHER_LINE = b"/bin/bash /root/nox/ops/nox_teachers_warm.sh\n"
TEACHER_LINE_INDEX = 8
TEACHER_LINE_PIN = "e838155b55afc6f445ab345ddd057b60b04e440615ab1f60ce91b4aaa642bce5"
DISABLED_CONF_SHA = "b380979ad50928c6504d945caf5287f616f9914ecb3d0ba50ffb6c0fb25e5d85"
STARTUP_BACKUP = ".nox-onstart-before-teacher-disable-01d1310a50048d6c"
PID1_START_TICKS = 167790899


def bash_syntax(raw):
    result = subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-n", "-s"], input=raw,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=4,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, check=False,
    )
    # Bash can return success with an unterminated here-document warning.
    return result.returncode == 0 and not result.stdout and not result.stderr


def supervisor_path(word):
    return word in ("/etc/supervisor", "conf.d") or word.startswith(("/etc/supervisor/", "conf.d/"))


def supervisor_effects(raw):
    """Classify literal references only. Dynamic shell behavior remains unknown."""
    readonly = writes = unknown = 0
    for line in raw.decode("utf-8", errors="strict").splitlines():
        if line.lstrip().startswith("#") or not re.search(r"/etc/supervisor\b|\bconf\.d/", line):
            continue
        try:
            scanner = shlex.shlex(line, posix=True, punctuation_chars="();<>|&")
            scanner.whitespace_split = True
            tokens = list(scanner)
        except ValueError:
            unknown += 1
            continue
        targets = [i for i, word in enumerate(tokens) if supervisor_path(word)]
        if not targets:
            unknown += 1
            continue
        output = any(i and tokens[i - 1] in (">", ">>", ">|", "&>", "&>>", "<>") for i in targets)
        command = Path(tokens[0]).name if tokens else ""
        if (output or command in {"cp", "install", "ln", "mv", "rm", "tee", "truncate",
                                  "touch", "mkdir", "chmod", "chown"}
                or (command == "sed" and any(word == "-i" or word.startswith("-i") for word in tokens[1:]))):
            writes += 1
        elif (command in {"supervisord", "supervisorctl"} and len(targets) == 1
              and targets[0] > 1 and tokens[targets[0] - 1] in ("-c", "--configuration")
              and not any(word in (";", "|", "||", "&&") for word in tokens)):
            readonly += 1
        else:
            unknown += 1
    return {"configuration_read_reference_count": readonly, "configuration_write_risk_count": writes,
            "configuration_unclassified_reference_count": unknown,
            "runtime_configuration_persistence_verified": False}


def candidate(raw):
    need(len(raw) == STARTUP_LENGTH and digest(raw) == STARTUP_SHA, "EXACT_CURRENT_STARTUP")
    lines = raw.splitlines(keepends=True)
    need(len(lines) > TEACHER_LINE_INDEX and lines[TEACHER_LINE_INDEX] == TEACHER_LINE
         and digest(TEACHER_LINE) == TEACHER_LINE_PIN and lines.count(TEACHER_LINE) == 1, "EXACT_TEACHER_LINE")
    prefix = b"".join(lines[:TEACHER_LINE_INDEX])
    need(not lines[TEACHER_LINE_INDEX - 1].rstrip().endswith(b"\\")
         and bash_syntax(prefix) and bash_syntax(raw), "TEACHER_COMMAND_CONTEXT")
    updated = prefix + b"".join(lines[TEACHER_LINE_INDEX + 1:])
    need(b"/root/nox/ops/nox_teachers_warm.sh" not in updated and bash_syntax(updated), "STARTUP_CANDIDATE")
    return updated


def ensure_backup(parent, raw):
    """Publish one private, no-clobber exact source backup before activation."""
    try:
        previous, saved = read(parent, STARTUP_BACKUP)
    except FileNotFoundError:
        temp = ".nox-teacher-source-" + uuid.uuid4().hex
        descriptor = os.open(temp, WRITE_FLAGS, 0o600, dir_fd=parent)
        with os.fdopen(descriptor, "wb") as out:
            try:
                need(out.write(raw) == len(raw), "BACKUP_SHORT_WRITE")
                out.flush()
                os.fchmod(out.fileno(), 0o600)
                os.fsync(out.fileno())
                prepared = os.fstat(out.fileno())
                os.link(temp, STARTUP_BACKUP, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
            finally:
                item = os.stat(temp, dir_fd=parent, follow_symlinks=False)
                need(inode(item) == inode(os.fstat(out.fileno())), "BACKUP_TEMP_CHANGED")
                os.unlink(temp, dir_fd=parent)
                os.fsync(parent)
        previous, saved = read(parent, STARTUP_BACKUP)
        need(inode(saved) == inode(prepared), "BACKUP_INODE_CHANGED")
    need(previous == raw and stat.S_IMODE(saved.st_mode) == 0o600, "BACKUP_SOURCE_SCOPE")
    return saved


def remove_exact_teacher_line(*, instance_id, phase2_request, phase2_source, apply=False, root=Path("/")):
    need((os.geteuid(), os.getegid()) == owner() and instance_id == INSTANCE
         and phase2_request == PHASE2_REQUEST and phase2_source == PHASE2_SOURCE
         and pid1_start() == PID1_START_TICKS and type(apply) is bool, "OWNER_CONTEXT")
    with ExitStack() as stack:
        root_fd = os.open(root, DIR_FLAGS)
        stack.callback(os.close, root_fd)
        trust(os.fstat(root_fd), stat.S_ISDIR)
        lease_parent, lease_name = directory(stack, root_fd, LEASE)
        lease = os.open(lease_name, READ_FLAGS, dir_fd=lease_parent)
        stack.callback(os.close, lease)
        lease_info = os.fstat(lease)
        trust(lease_info, stat.S_ISREG)
        need(lease_info.st_nlink == 1, "OWNER_LEASE_SCOPE")
        fcntl.flock(lease, (fcntl.LOCK_EX if apply else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        checked_lease(lease_parent, lease_name, lease, lease_info)
        startup_parent, name = directory(stack, root_fd, STARTUP)
        conf_parent, conf_name = directory(stack, root_fd, WARM_CONF)
        raw, original = read(startup_parent, name)
        conf, conf_info = read(conf_parent, conf_name)
        observed = config_projection(conf)
        need(digest(conf) == DISABLED_CONF_SHA and observed["exact_warm_service"]
             and not observed["autostart_enabled"], "TEACHER_SUPERVISOR_UNIT_CHANGED")
        updated = candidate(raw)
        effects = supervisor_effects(updated)
        result = {"startup_before_sha256": digest(raw), "startup_candidate_sha256": digest(updated),
                  "teacher_line_sha256": TEACHER_LINE_PIN, "teacher_line_number": TEACHER_LINE_INDEX + 1,
                  "teacher_supervisor_file_verified_disabled": True, "teacher_supervisor_file_modified": False,
                  "supervisor_effects": effects, "supervisor_reloaded": False, "server_rebooted": False,
                  "startup_line_removed": False, "root_backup_retained": False}
        if not apply:
            return result
        backup = ensure_backup(startup_parent, raw)
        change = Change(STARTUP, startup_parent, name, raw, updated, original)
        try:
            prepare(change)
            assert_directory(root_fd, change)
            exact(startup_parent, name, original, raw)
            exact(startup_parent, STARTUP_BACKUP, backup, raw)
            exact(conf_parent, conf_name, conf_info, conf)
            checked_lease(lease_parent, lease_name, lease, lease_info)
            need(pid1_start() == PID1_START_TICKS, "BOOT_GENERATION_CHANGED")
            exchange(startup_parent, name, startup_parent, change.temp)
            change.swapped = True
            os.fsync(startup_parent)
            assert_directory(root_fd, change)
            exact(startup_parent, name, change.prepared, updated)
            exact(startup_parent, change.temp, original, raw)
            exact(startup_parent, STARTUP_BACKUP, backup, raw)
            exact(conf_parent, conf_name, conf_info, conf)
        except (RuntimeError, OSError) as error:
            if rollback([change]):
                raise RuntimeError("HOLD_TEACHER_BOOT_ROLLBACK_RECONCILIATION") from error
            if change.prepared is not None:
                unlink_prepared(change, change.prepared)
            raise RuntimeError("HOLD_TEACHER_BOOT_STARTUP_PREIMAGE_RESTORED") from error
        unlink_prepared(change, original)
        result.update(startup_line_removed=True, root_backup_retained=True)
        return result
