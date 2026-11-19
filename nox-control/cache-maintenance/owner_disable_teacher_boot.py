"""Owner-scoped compare-and-swap for both native teacher warm boot hooks."""

import ctypes
import fcntl
import os
import re
import stat
import uuid
from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

from owner_teacher_boot_diff import (
    AUTO, BACKUP_T145U, MAX_BYTES, STARTUP, WARM_CONF, WARM_MANIFEST,
    WARM_MANIFEST_SHA, WARM_SCRIPT, WARM_SCRIPT_SHA, config_projection,
    digest, startup_projection,
)


INSTANCE = 60509551
PHASE2_REQUEST = "7011341488"
PHASE2_SOURCE = "8e5f6ef0bd034c7617edeb6711d4f2aa15f58932"
LEASE = "/root/nox/state/owner_maintenance.lock"
DIR_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY | os.O_CLOEXEC
READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
WRITE_FLAGS = os.O_WRONLY | os.O_NOFOLLOW | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC


class Hold(RuntimeError):
    pass


@dataclass
class Change:
    logical: str
    parent: int
    name: str
    before: bytes
    after: bytes
    original: os.stat_result
    temp: str = ""
    prepared: os.stat_result | None = None
    swapped: bool = False


def need(condition, code):
    if not condition:
        raise Hold("HOLD_TEACHER_BOOT_" + code)


def owner():
    return 0, 0


def inode(info):
    return info.st_dev, info.st_ino


def stamp(info):
    return (inode(info), info.st_mode, info.st_uid, info.st_gid, info.st_nlink,
            info.st_size, info.st_ctime_ns, info.st_mtime_ns)


def trust(info, file_type):
    need(file_type(info.st_mode) and (info.st_uid, info.st_gid) == owner()
         and not info.st_mode & 0o022, "UNTRUSTED_PATH")


def directory(stack, root, logical):
    parent = root
    for part in Path(logical).parent.parts[1:]:
        parent = os.open(part, DIR_FLAGS, dir_fd=parent)
        stack.callback(os.close, parent)
        trust(os.fstat(parent), stat.S_ISDIR)
    return parent, Path(logical).name


def assert_directory(root, change):
    with ExitStack() as stack:
        current, _ = directory(stack, root, change.logical)
        need(inode(os.fstat(current)) == inode(os.fstat(change.parent)), "DESTINATION_DIRECTORY_CHANGED")


def read(parent, name):
    fd = os.open(name, READ_FLAGS, dir_fd=parent)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(fd)
        trust(before, stat.S_ISREG)
        need(before.st_nlink == 1 and 0 < before.st_size <= MAX_BYTES, "PREIMAGE_SCOPE")
        raw = stream.read(before.st_size + 1)
        after = os.fstat(fd)
    current = os.stat(name, dir_fd=parent, follow_symlinks=False)
    need(stamp(before) == stamp(after) == stamp(current) and len(raw) == before.st_size,
         "PREIMAGE_CHANGED")
    return raw, before


def exact(parent, name, expected, expected_bytes):
    raw, current = read(parent, name)
    need(inode(current) == inode(expected) and current.st_mode == expected.st_mode
         and raw == expected_bytes, "FILE_COMPARE")


def pid1_start():
    with open("/proc/1/stat", "rb") as stream:
        entry = stream.read(8192)
    return int(entry.rpartition(b") ")[2].split()[19])


def exchange(left_fd, left, right_fd, right):
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, "renameat2", None)
    need(rename is not None, "ATOMIC_EXCHANGE_UNAVAILABLE")
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(left_fd, os.fsencode(left), right_fd, os.fsencode(right), 2) != 0:
        raise OSError(ctypes.get_errno(), "teacher boot atomic exchange")


def checked_lease(parent, name, fd, expected):
    open_info = os.fstat(fd)
    current = os.stat(name, dir_fd=parent, follow_symlinks=False)
    need(stamp(open_info) == stamp(current) == stamp(expected), "OWNER_LEASE_CHANGED")


def verify_phase2(phase2, instance_id, phase2_request, phase2_source):
    need(instance_id == INSTANCE and phase2_request == PHASE2_REQUEST and phase2_source == PHASE2_SOURCE
         and isinstance(phase2, Mapping) and phase2.get("container_pid1_start_ticks") == pid1_start()
         and phase2.get("has_vast_environment") is True, "PHASE2_CONTEXT")
    hooks = phase2.get("warm_hooks")
    need(isinstance(hooks, Mapping) and hooks.get("warm_script_pin_matches") is True
         and hooks.get("warm_manifest_pin_matches") is True, "WARM_SOURCE_NOT_ATTESTED")
    startup, config = hooks.get("startup"), hooks.get("warm_service")
    need(isinstance(startup, Mapping) and isinstance(config, Mapping)
         and startup.get("preimage_matches_current_pin") is True
         and startup.get("single_teacher_line_matches_backup") is True
         and startup.get("startup_may_write_supervisor_config") is False
         and config.get("exact_warm_service") is True and config.get("autostart_enabled") is True,
         "WARM_HOOK_NOT_ATTESTED")
    for row, labels in ((startup, ("sha256", "backup_sha256", "teacher_line_sha256")),
                        (config, ("sha256", "autostart_false_candidate_sha256"))):
        need(all(isinstance(row.get(label), str) and re.fullmatch("[0-9a-f]{64}", row[label])
                 for label in labels), "PHASE2_PINS")
    return startup, config


def prepare(change):
    change.temp = ".nox-teacher-boot-" + uuid.uuid4().hex
    fd = os.open(change.temp, WRITE_FLAGS, 0o600, dir_fd=change.parent)
    with os.fdopen(fd, "wb") as out:
        change.prepared = os.fstat(out.fileno())
        need(out.write(change.after) == len(change.after), "TEMP_SHORT_WRITE")
        out.flush()
        os.fchmod(out.fileno(), stat.S_IMODE(change.original.st_mode))
        os.fsync(out.fileno())
        change.prepared = os.fstat(out.fileno())
    exact(change.parent, change.temp, change.prepared, change.after)


def unlink_prepared(change, expected):
    try:
        info = os.stat(change.temp, dir_fd=change.parent, follow_symlinks=False)
    except FileNotFoundError:
        return
    need(stat.S_ISREG(info.st_mode) and inode(info) == inode(expected), "TEMP_COMPARE")
    os.unlink(change.temp, dir_fd=change.parent)
    os.fsync(change.parent)


def rollback(changes):
    failed = False
    for change in reversed(changes):
        if not change.swapped:
            continue
        try:
            # Roll back only if both sides are exactly the exchanged bytes.
            exact(change.parent, change.name, change.prepared, change.after)
            exact(change.parent, change.temp, change.original, change.before)
            exchange(change.parent, change.name, change.parent, change.temp)
            change.swapped = False
            os.fsync(change.parent)
            exact(change.parent, change.name, change.original, change.before)
        except (Hold, OSError):
            failed = True
    return failed


def current_changes(stack, root, startup_pin, config_pin):
    paths = {path: directory(stack, root, path) for path in
             (STARTUP, BACKUP_T145U, WARM_CONF, WARM_SCRIPT, WARM_MANIFEST)}
    startup, startup_st = read(*paths[STARTUP])
    backup, _ = read(*paths[BACKUP_T145U])
    conf, conf_st = read(*paths[WARM_CONF])
    started = startup_projection(startup, backup)
    projected_conf = config_projection(conf)
    need(started.get("single_teacher_line_matches_backup") is True
         and started.get("startup_may_write_supervisor_config") is False
         and all(startup_pin[key] == started.get(key) for key in
                 ("sha256", "backup_sha256", "teacher_line_sha256"))
         and all(config_pin[key] == projected_conf.get(key) for key in
                 ("sha256", "autostart_false_candidate_sha256")), "PREIMAGE_PINS_CHANGED")
    need(digest(read(*paths[WARM_SCRIPT])[0]) == WARM_SCRIPT_SHA
         and digest(read(*paths[WARM_MANIFEST])[0]) == WARM_MANIFEST_SHA, "WARM_SOURCE_CHANGED")
    new_config, count = AUTO.subn(rb"\g<1>false\g<3>", conf)
    after = config_projection(new_config)
    need(count == 1 and digest(new_config) == config_pin["autostart_false_candidate_sha256"]
         and after["exact_warm_service"] and not after["autostart_enabled"], "CANDIDATE_SCOPE")
    return [Change(WARM_CONF, *paths[WARM_CONF], conf, new_config, conf_st),
            Change(STARTUP, *paths[STARTUP], startup, backup, startup_st)]


def disable_teacher_boot(*, phase2, instance_id, phase2_request, phase2_source, root=Path("/")):
    """Apply only the two reviewed on-disk modifications. No Supervisor RPC."""
    need((os.geteuid(), os.getegid()) == owner(), "ROOT_REQUIRED")
    startup_pin, config_pin = verify_phase2(phase2, instance_id, phase2_request, phase2_source)
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
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise Hold("HOLD_TEACHER_BOOT_OWNER_LEASE_BUSY") from error
        checked_lease(lease_parent, lease_name, lease, lease_info)
        changes = current_changes(stack, root_fd, startup_pin, config_pin)
        try:
            for change in changes:
                prepare(change)
            for change in changes:
                checked_lease(lease_parent, lease_name, lease, lease_info)
                need(pid1_start() == phase2["container_pid1_start_ticks"], "BOOT_GENERATION_CHANGED")
                assert_directory(root_fd, change)
                exact(change.parent, change.name, change.original, change.before)
                exchange(change.parent, change.name, change.parent, change.temp)
                change.swapped = True
                os.fsync(change.parent)
                exact(change.parent, change.temp, change.original, change.before)
                exact(change.parent, change.name, change.prepared, change.after)
            for change in changes:
                assert_directory(root_fd, change)
                exact(change.parent, change.name, change.prepared, change.after)
        except (Hold, OSError) as error:
            if rollback(changes):
                raise Hold("HOLD_TEACHER_BOOT_ROLLBACK_RECONCILIATION") from error
            try:
                for change in changes:
                    if change.prepared is not None:
                        unlink_prepared(change, change.prepared)
            except (Hold, OSError) as cleanup:
                raise Hold("HOLD_TEACHER_BOOT_ROLLBACK_TEMP_RECONCILIATION") from cleanup
            raise Hold("HOLD_TEACHER_BOOT_TRANSACTION_RESTORED") from error
        try:
            for change in changes:
                unlink_prepared(change, change.original)
        except (Hold, OSError) as error:
            raise Hold("HOLD_TEACHER_BOOT_COMMITTED_CLEANUP_RECONCILIATION") from error
    return {"teacher_supervisor_autostart_disabled": True, "onstart_teacher_hook_disabled": True,
            "autostart_false_sha256": digest(changes[0].after), "onstart_sha256": digest(changes[1].after),
            "supervisor_reloaded": False, "server_rebooted": False}
