#!/usr/bin/env python3
"""NOX owner-only one-shot deploy of bounded native Supervisor lifeline.

Run solely by the existing pinned GitHub -> authenticated Vast #60509551
SSH owner-maintenance transport. No weight/S03/chat/trainer mutations.
"""
from __future__ import annotations
import base64
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import signal
import subprocess
import sys
import tempfile
import time

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path("/root/nox")
SCRIPT = ROOT / "scripts/nox_native_lifeline.py"
POLICY = Path("/etc/nox/lifeline.json")
CONFIG = Path("/etc/supervisor/conf.d/nox-lifeline-guard.conf")
GUARD = "nox-lifeline-guard"
OWNER_STOP = ROOT / "STOP"
OWNER_MAINTENANCE = ROOT / "state/OWNER_MAINTENANCE.flag"
OWNER_MAINTENANCE_LOCK = ROOT / "state/owner_maintenance.lock"
OWNER_LOCK_FD = None
REQUIRED = ("nox-dispatcher-t855u", "nox-priority-scheduler",
            "nox-selfheal", "nox-gpu-watchdog-t865u")
AUDIT_SHA = re.compile(r"^[0-9a-f]{40}$")
EXACT_FILES = {"nox_native_lifeline.py": 32_768,
               "lifeline.example.json": 8_192,
               "nox-lifeline-guard.conf": 8_192}
SUPERVISOR_OUTPUT = re.compile(r"^([a-zA-Z0-9_.:-]+)\s+([A-Z]+)(?:\s+pid\s+([0-9]+))?")
AUDIT_SCRIPT_OLD_SHA256 = "a2503c1463738c215bf3cd4eb5cdcb29f5ff65a85128160728033a80e9af1f66"
AUDIT_SCRIPT_NEW_SHA256 = "d10b12461cdf08a309ea7ac08c81a6d465d254f95b78b1d3b441e7f59f01e69f"
AUDIT_POLICY_SHA256 = "e06d45654fd664f9d15a057fbb5290dd862c4087dba383764283dbaab51edc5b"
AUDIT_CONFIG_SHA256 = "266d75d12cb3203dd8200a6b382231105a0fd3fd9ea37379531d86c413ddfba6"
AUDIT_GUARD_PID = 3355691
AUDIT_GUARD_START_TICKS = 172312630
REVIEWED_COMMAND = ("/usr/bin/python3 -u /root/nox/scripts/nox_native_lifeline.py "
                    "--policy /etc/nox/lifeline.json "
                    "--state /root/nox/state/lifeline/state.json")
REVIEWED_EXECUTABLE = "/usr/bin/python3"
REVIEWED_ARGV = ("/usr/bin/python3", "-u", "/root/nox/scripts/nox_native_lifeline.py",
                 "--policy", "/etc/nox/lifeline.json",
                 "--state", "/root/nox/state/lifeline/state.json")
AUDIT_CONFIG_RECONCILED = False
AUDIT_GUARD_IDENTITY = None
AUDIT_SYSTEMD_STATE = None
AUDIT_GUARD_PREIMAGE = None
AUDIT_SCRIPT_BACKUP = None
AUDIT_CONFIG_BACKUP = None
AUDIT_SCRIPT_NEW_SHA = None
AUDIT_CONFIG_NEW_SHA = None
AUDIT_SCRIPT_RECONCILED = False
AUDIT_MEMORY_REPORT = None
AUDIT_MEMORY_TIMESTAMP = None
AUDIT_SYSTEMD_PREIMAGE = None

def fail(label):
    raise RuntimeError("HOLD_LIFELINE_" + label)

def call(args, timeout=15):
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              shell=False, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        fail("COMMAND_UNAVAILABLE")

def info(name):
    # A nonzero supervisorctl rc invalidates stdout even when it resembles a
    # plausible RUNNING/STOPPED row. Never admit a service from a failed probe.
    p = call(["supervisorctl", "status", name])
    # Supervisorctl uses rc=3 for an explicitly stopped process on this host.
    # Admit rc=3 ONLY with a single exact STOPPED/EXITED row and no PID.
    if p.returncode not in (0, 3) or not isinstance(p.stdout, str):
        return {"state": "UNKNOWN", "pid": None}
    lines = p.stdout.strip().splitlines()
    m = SUPERVISOR_OUTPUT.match(lines[0]) if len(lines) == 1 else None
    if m is None or m[1] != name:
        return {"state": "UNKNOWN", "pid": None}
    state, pid = m[2], int(m[3]) if m[3] else None
    if p.returncode == 3 and state not in ("STOPPED", "EXITED"):
        return {"state": "UNKNOWN", "pid": None}
    # A stray or malformed PID token after the matched prefix is contradictory.
    if pid is None and re.search(r"\bpid\b", lines[0][m.end():], re.IGNORECASE):
        return {"state": "UNKNOWN", "pid": None}
    if not ((state == "RUNNING" and pid is not None and pid > 0) or
            (state in ("STOPPED", "EXITED") and pid is None)):
        return {"state": "UNKNOWN", "pid": None}
    return {"state": state, "pid": pid}


def process_identity(pid):
    """Read a bounded PID start-time and argv identity from procfs."""
    if type(pid) is not int or pid <= 0:
        fail("GUARD_PROCESS_IDENTITY")
    base = Path("/proc") / str(pid)
    def stat_identity():
        try:
            stat_fd = os.open(base / "stat", os.O_RDONLY | os.O_NOFOLLOW |
                              os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
            try:
                stat_raw = os.read(stat_fd, 4097)
            finally:
                os.close(stat_fd)
        except OSError:
            fail("GUARD_PROCESS_IDENTITY")
        if len(stat_raw) > 4096:
            fail("GUARD_PROCESS_IDENTITY")
        try:
            pid_raw, rest = stat_raw.split(b" ", 1)
            close = rest.rfind(b")")
            if int(pid_raw) != pid or close < 0 or not rest.startswith(b"("):
                raise ValueError
            fields = rest[close + 1:].split()
            if len(fields) < 20:
                raise ValueError
            return {"ppid": int(fields[1]), "pgrp": int(fields[2]),
                    "start_ticks": int(fields[19])}
        except (IndexError, ValueError):
            fail("GUARD_PROCESS_IDENTITY")
    def cmdline():
        try:
            cmd_fd = os.open(base / "cmdline", os.O_RDONLY | os.O_NOFOLLOW |
                             os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
            try:
                return os.read(cmd_fd, 4097)
            finally:
                os.close(cmd_fd)
        except OSError:
            fail("GUARD_PROCESS_IDENTITY")
    before = stat_identity()
    try:
        exe_before = os.readlink(base / "exe")
    except OSError:
        fail("GUARD_PROCESS_IDENTITY")
    cmd_raw = cmdline()
    try:
        exe_after = os.readlink(base / "exe")
        expected_exe = os.path.realpath(REVIEWED_EXECUTABLE)
    except OSError:
        fail("GUARD_PROCESS_IDENTITY")
    cmd_raw_after = cmdline()
    after = stat_identity()
    if (before != after or exe_before != exe_after or cmd_raw != cmd_raw_after or
        len(cmd_raw) > 4096 or not cmd_raw.endswith(b"\0") or
        exe_before != expected_exe):
        fail("GUARD_PROCESS_IDENTITY")
    try:
        argv = tuple(part.decode("utf-8") for part in cmd_raw[:-1].split(b"\0"))
    except (ValueError, UnicodeError):
        fail("GUARD_PROCESS_IDENTITY")
    if not argv or any(not part for part in argv):
        fail("GUARD_PROCESS_IDENTITY")
    return {"pid": pid, **before, "argv": argv, "exe": exe_before}


def _path_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid,
            info.st_gid, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_bounded_root_file(path, limit):
    """Read one root-owned, single-link regular file with a strict byte bound."""
    path = Path(path)
    protect_path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                     getattr(os, "O_CLOEXEC", 0))
    except OSError:
        fail("AUDIT_FILE_UNAVAILABLE")
    try:
        metadata = os.fstat(fd)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or
            metadata.st_uid != 0 or metadata.st_mode & 0o022 or metadata.st_size > limit):
            fail("AUDIT_FILE_UNSAFE")
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, min(1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(fd)
        if (len(raw) > limit or len(raw) != metadata.st_size or
            _path_identity(after) != _path_identity(metadata)):
            fail("AUDIT_FILE_SIZE")
        return raw, _path_identity(metadata)
    finally:
        os.close(fd)


def _config_assignment(raw, key):
    matches = []
    for index, line in enumerate(raw.splitlines(keepends=True)):
        body = line.rstrip(b"\r\n")
        if body.startswith(key + b"="):
            value = body[len(key) + 1:]
            ending = line[len(body):]
            matches.append((index, value, ending))
    if len(matches) != 1:
        fail("AUDIT_CONFIG_FIELDS")
    return matches[0]


def _set_config_assignment(raw, key, expected, replacement):
    lines = raw.splitlines(keepends=True)
    index, actual, ending = _config_assignment(raw, key)
    if expected is not None and actual != expected:
        fail("AUDIT_CONFIG_PREIMAGE")
    if expected is None and actual == replacement:
        fail("AUDIT_CONFIG_PREIMAGE")
    lines[index] = key + b"=" + replacement + ending
    return b"".join(lines)


def atomic_replace_exact_file(path, old_raw, old_identity, expected_sha256, new_raw, limit):
    """Atomically replace a bounded file only while its pinned preimage stays in place."""
    path = Path(path)
    protect_path(path)
    current, identity = read_bounded_root_file(path, limit)
    if (identity != old_identity or current != old_raw or
        hashlib.sha256(current).hexdigest() != expected_sha256):
        fail("AUDIT_FILE_RACE")
    fd, temp = tempfile.mkstemp(prefix=".nox-lifeline-audit-", dir=str(path.parent))
    try:
        os.fchmod(fd, stat.S_IMODE(old_identity[2]))
        with os.fdopen(fd, "wb") as writer:
            writer.write(new_raw)
            writer.flush()
            os.fsync(writer.fileno())
        current_after, identity_after = read_bounded_root_file(path, limit)
        if identity_after != old_identity or current_after != old_raw:
            fail("AUDIT_FILE_RACE")
        os.replace(temp, path)
        dir_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    result, _ = read_bounded_root_file(path, limit)
    if result != new_raw:
        fail("AUDIT_FILE_READBACK")


def supervisor_systemd_state():
    active = call(["systemctl", "is-active", "supervisor.service"], timeout=10)
    enabled = call(["systemctl", "is-enabled", "supervisor.service"], timeout=10)
    return {"active": active.stdout.strip() if isinstance(active.stdout, str) else "unknown",
            "active_rc": active.returncode,
            "enabled": enabled.stdout.strip() if isinstance(enabled.stdout, str) else "unknown",
            "enabled_rc": enabled.returncode}


def _fresh_memory_report(after):
    global AUDIT_MEMORY_REPORT, AUDIT_MEMORY_TIMESTAMP
    state_path = ROOT / "state/lifeline/state.json"
    AUDIT_MEMORY_REPORT = {"memory.current": None, "memory.max": None,
                           "raw_headroom_bytes": None, "below_2GiB": True,
                           "status": "UNKNOWN"}
    for _ in range(10):
        try:
            raw, _ = read_bounded_root_file(state_path, 262_144)
            state = json.loads(raw)
            if not isinstance(state, dict):
                raise ValueError
            report = state.get("last_report")
            if not isinstance(report, dict) or not isinstance(report.get("at"), str):
                raise ValueError
            if report.get("observer_only") is not True:
                raise ValueError
            report_time = dt.datetime.fromisoformat(
                report["at"].replace("Z", "+00:00")).timestamp()
            if report_time > time.time() + 5:
                raise ValueError
            memory = report.get("cgroup_memory")
            if (type(state.get("at")) in (int, float) and state["at"] >= after and
                report_time >= after and isinstance(memory, dict)):
                current = memory.get("memory.current")
                maximum = memory.get("memory.max")
                headroom = memory.get("raw_headroom_bytes")
                below = memory.get("below_2GiB")
                if type(below) is not bool:
                    raise ValueError
                if type(current) is int and type(maximum) is int:
                    expected = maximum - current
                    if (headroom != expected or below != (expected < 2 * 1024 ** 3) or
                        memory.get("status") != ("OK" if expected >= 0 else "INCONSISTENT")):
                        raise ValueError
                elif (headroom is not None or below is not True or
                      memory.get("status") != "UNKNOWN"):
                    raise ValueError
                AUDIT_MEMORY_REPORT = memory
                AUDIT_MEMORY_TIMESTAMP = report["at"]
                return memory
        except (OSError, ValueError, TypeError, RuntimeError):
            pass
        time.sleep(2)
    fail("AUDIT_MEMORY_REPORT_READBACK")


def reconcile_audited_config(script, policy, reviewed_config, request):
    """Upgrade only the exact audited files and running guard; all other preimages HOLD."""
    global AUDIT_CONFIG_RECONCILED, AUDIT_GUARD_IDENTITY, AUDIT_SYSTEMD_STATE
    global AUDIT_GUARD_PREIMAGE, AUDIT_SCRIPT_BACKUP, AUDIT_CONFIG_BACKUP
    global AUDIT_SCRIPT_NEW_SHA, AUDIT_CONFIG_NEW_SHA, AUDIT_SCRIPT_RECONCILED
    global AUDIT_MEMORY_REPORT, AUDIT_MEMORY_TIMESTAMP, AUDIT_SYSTEMD_PREIMAGE
    protect_path(CONFIG)
    try:
        CONFIG.lstat()
    except FileNotFoundError:
        return reviewed_config, False
    config_raw, config_identity = read_bounded_root_file(
        CONFIG, EXACT_FILES["nox-lifeline-guard.conf"])
    if hashlib.sha256(config_raw).hexdigest() != AUDIT_CONFIG_SHA256:
        return reviewed_config, False

    script_raw, script_identity = read_bounded_root_file(
        SCRIPT, EXACT_FILES["nox_native_lifeline.py"])
    policy_raw, _ = read_bounded_root_file(POLICY, EXACT_FILES["lifeline.example.json"])
    if (hashlib.sha256(script_raw).hexdigest() != AUDIT_SCRIPT_OLD_SHA256 or
        hashlib.sha256(policy_raw).hexdigest() != AUDIT_POLICY_SHA256 or
        hashlib.sha256(script).hexdigest() != AUDIT_SCRIPT_NEW_SHA256 or
        hashlib.sha256(policy).hexdigest() != AUDIT_POLICY_SHA256 or
        stat.S_IMODE(script_identity[2]) != 0o644):
        fail("AUDIT_SOURCE_PREIMAGE")
    try:
        live_policy = json.loads(policy_raw)
    except (ValueError, UnicodeError, TypeError):
        fail("AUDIT_POLICY_PREIMAGE")
    if (live_policy.get("enabled") is not False or
        not isinstance(live_policy.get("services"), list) or
        any(not isinstance(item, dict) or item.get("restart") is not False
            for item in live_policy["services"])):
        fail("AUDIT_POLICY_NOT_DISABLED")

    guard = info(GUARD)
    if guard.get("state") != "RUNNING" or guard.get("pid") != AUDIT_GUARD_PID:
        fail("AUDIT_GUARD_STATUS_PREIMAGE")
    old_identity = process_identity(AUDIT_GUARD_PID)
    if (old_identity["start_ticks"] != AUDIT_GUARD_START_TICKS or
        old_identity["argv"] != REVIEWED_ARGV):
        fail("AUDIT_GUARD_PROCESS_PREIMAGE")

    current_systemd = supervisor_systemd_state()
    if (current_systemd["active"] != "active" or current_systemd["active_rc"] != 0 or
        current_systemd["enabled"] not in ("enabled", "disabled")):
        fail("SUPERVISOR_SYSTEMD_NOT_ACTIVE")
    if ((current_systemd["enabled"] == "enabled" and current_systemd["enabled_rc"] != 0) or
        (current_systemd["enabled"] == "disabled" and current_systemd["enabled_rc"] != 1)):
        fail("SUPERVISOR_SYSTEMD_ENABLE_STATE")
    AUDIT_SYSTEMD_PREIMAGE = current_systemd.copy()

    reviewed_command = _config_assignment(reviewed_config, b"command")[1]
    if reviewed_command.decode("utf-8") != REVIEWED_COMMAND:
        fail("REVIEWED_COMMAND_MISMATCH")
    if (_config_assignment(reviewed_config, b"autostart")[1] != b"true" or
        _config_assignment(reviewed_config, b"autorestart")[1] != b"true"):
        fail("REVIEWED_CONFIG_POLICY")

    new_raw = _set_config_assignment(config_raw, b"command", None, reviewed_command)
    new_raw = _set_config_assignment(new_raw, b"autostart", b"false", b"true")
    if (_config_assignment(config_raw, b"autorestart")[1] != b"true" or
        new_raw != reviewed_config):
        fail("AUDIT_CONFIG_DIFF_SCOPE")

    backup_dir = ROOT / "backup/owner_maintenance" / request
    script_backup = backup_dir / ("nox-native-lifeline-preimage-" + AUDIT_SCRIPT_OLD_SHA256 + ".py")
    config_backup = backup_dir / ("nox-lifeline-guard-preimage-" + AUDIT_CONFIG_SHA256 + ".conf")
    for backup, original, limit, label in (
        (script_backup, script_raw, EXACT_FILES["nox_native_lifeline.py"], "SCRIPT"),
        (config_backup, config_raw, EXACT_FILES["nox-lifeline-guard.conf"], "CONFIG")):
        if backup.exists() or backup.is_symlink():
            existing_backup, _ = read_bounded_root_file(backup, limit)
            if existing_backup != original:
                fail("AUDIT_" + label + "_BACKUP_CONFLICT")
        else:
            preserve_or_write(backup, original, 0o600)
        checked_backup, _ = read_bounded_root_file(backup, limit)
        if checked_backup != original:
            fail("AUDIT_" + label + "_BACKUP_READBACK")

    AUDIT_SCRIPT_BACKUP, AUDIT_CONFIG_BACKUP = script_backup, config_backup
    AUDIT_SCRIPT_NEW_SHA = AUDIT_SCRIPT_NEW_SHA256
    AUDIT_CONFIG_NEW_SHA = hashlib.sha256(new_raw).hexdigest()
    AUDIT_GUARD_PREIMAGE = old_identity
    replace_script_exact(SCRIPT, script_raw, script)
    AUDIT_SCRIPT_RECONCILED = True
    installed_script, _ = read_bounded_root_file(
        SCRIPT, EXACT_FILES["nox_native_lifeline.py"])
    if hashlib.sha256(installed_script).hexdigest() != AUDIT_SCRIPT_NEW_SHA256:
        fail("AUDIT_SCRIPT_READBACK")
    atomic_replace_exact_file(CONFIG, config_raw, config_identity,
                              AUDIT_CONFIG_SHA256, new_raw,
                              EXACT_FILES["nox-lifeline-guard.conf"])

    reread = call(["supervisorctl", "reread"], timeout=15)
    if (reread.returncode or
        "nox-lifeline-guard: changed" not in reread.stdout.splitlines()):
        fail("SUPERVISOR_CONFIG_REREAD")
    update_started = time.time()
    update = call(["supervisorctl", "update", GUARD], timeout=25)
    if update.returncode:
        fail("GUARD_UPDATE")
    fresh_guard = {"state": "UNKNOWN", "pid": None}
    fresh_identity = None
    for _ in range(10):
        fresh_guard = info(GUARD)
        if fresh_guard["state"] == "RUNNING" and fresh_guard.get("pid"):
            fresh_identity = process_identity(fresh_guard["pid"])
            if (fresh_identity["argv"] == REVIEWED_ARGV and
                (fresh_identity["pid"] != old_identity["pid"] or
                 fresh_identity["start_ticks"] != old_identity["start_ticks"])):
                break
        time.sleep(2)
    else:
        fail("GUARD_RESTART_READBACK")
    AUDIT_MEMORY_REPORT = _fresh_memory_report(update_started)
    if (AUDIT_MEMORY_REPORT.get("status") != "OK" or
        type(AUDIT_MEMORY_REPORT.get("memory.current")) is not int or
        type(AUDIT_MEMORY_REPORT.get("memory.max")) is not int or
        type(AUDIT_MEMORY_REPORT.get("raw_headroom_bytes")) is not int):
        fail("AUDIT_MEMORY_UNKNOWN")

    if current_systemd["enabled"] == "disabled":
        # Never enable global Supervisor here: that could boot-start unrelated
        # NOX workloads. Use the independent lifeline-observer systemd action.
        fail("SUPERVISOR_BOOT_DISABLED_GLOBAL_ENABLE_FORBIDDEN")
    elif current_systemd["enabled_rc"] != 0:
        fail("SUPERVISOR_SYSTEMD_ENABLE_STATE")

    AUDIT_CONFIG_RECONCILED = True
    AUDIT_GUARD_IDENTITY = fresh_identity
    AUDIT_SYSTEMD_STATE = current_systemd
    return new_raw, True


def recover_audited_preimage():
    """Restore only the two exact audited preimages; never overwrite unknown files."""
    global AUDIT_SCRIPT_BACKUP, AUDIT_CONFIG_BACKUP
    if AUDIT_SCRIPT_BACKUP is None and AUDIT_CONFIG_BACKUP is None:
        return
    script_backup = AUDIT_SCRIPT_BACKUP
    config_backup = AUDIT_CONFIG_BACKUP
    script_restored = False
    config_restored = False
    if script_backup is not None:
        old_script, _ = read_bounded_root_file(
            script_backup, EXACT_FILES["nox_native_lifeline.py"])
        if hashlib.sha256(old_script).hexdigest() != AUDIT_SCRIPT_OLD_SHA256:
            fail("AUDIT_ROLLBACK_SCRIPT_BACKUP")
        current_script, _ = read_bounded_root_file(
            SCRIPT, EXACT_FILES["nox_native_lifeline.py"])
        current_sha = hashlib.sha256(current_script).hexdigest()
        if current_sha == AUDIT_SCRIPT_NEW_SHA:
            replace_script_exact(SCRIPT, current_script, old_script)
            script_restored = True
        elif current_sha != AUDIT_SCRIPT_OLD_SHA256:
            fail("AUDIT_ROLLBACK_SCRIPT_UNKNOWN")
    if config_backup is not None:
        old_config, _ = read_bounded_root_file(
            config_backup, EXACT_FILES["nox-lifeline-guard.conf"])
        if hashlib.sha256(old_config).hexdigest() != AUDIT_CONFIG_SHA256:
            fail("AUDIT_ROLLBACK_CONFIG_BACKUP")
        current_config, current_identity = read_bounded_root_file(
            CONFIG, EXACT_FILES["nox-lifeline-guard.conf"])
        current_sha = hashlib.sha256(current_config).hexdigest()
        if current_sha == AUDIT_CONFIG_NEW_SHA:
            atomic_replace_exact_file(CONFIG, current_config, current_identity,
                                      current_sha, old_config,
                                      EXACT_FILES["nox-lifeline-guard.conf"])
            config_restored = True
        elif current_sha != AUDIT_CONFIG_SHA256:
            fail("AUDIT_ROLLBACK_CONFIG_UNKNOWN")

    if config_restored:
        reread = call(["supervisorctl", "reread"], timeout=15)
        if reread.returncode:
            fail("AUDIT_ROLLBACK_REREAD")

    current = info(GUARD)
    if current.get("state") == "RUNNING" and current.get("pid"):
        current_identity = process_identity(current["pid"])
    elif current.get("state") in ("STOPPED", "EXITED") and current.get("pid") is None:
        current_identity = None
    else:
        fail("AUDIT_ROLLBACK_GUARD_UNKNOWN")
    if (current_identity is None or
        (AUDIT_GUARD_PREIMAGE and current_identity != AUDIT_GUARD_PREIMAGE)):
        action = ("update" if config_restored else
                  "start" if current_identity is None else "restart")
        recovered = call(["supervisorctl", action, GUARD], timeout=25)
        if recovered.returncode:
            fail("AUDIT_ROLLBACK_GUARD_ACTION")
        current_identity = None
        start_attempted = action == "start"
        for _ in range(10):
            current = info(GUARD)
            if current.get("state") == "RUNNING" and current.get("pid"):
                current_identity = process_identity(current["pid"])
                if (current_identity["argv"] == REVIEWED_ARGV and
                    (AUDIT_GUARD_PREIMAGE is None or
                     current_identity != AUDIT_GUARD_PREIMAGE)):
                    break
            elif (current.get("state") in ("STOPPED", "EXITED") and
                  current.get("pid") is None and not start_attempted):
                started = call(["supervisorctl", "start", GUARD], timeout=20)
                if started.returncode:
                    fail("AUDIT_ROLLBACK_GUARD_START")
                start_attempted = True
            time.sleep(2)
        else:
            fail("AUDIT_ROLLBACK_GUARD_READBACK")
    if current_identity is None or current_identity["argv"] != REVIEWED_ARGV:
        fail("AUDIT_ROLLBACK_GUARD_ARGV")
    restored_script, _ = read_bounded_root_file(
        SCRIPT, EXACT_FILES["nox_native_lifeline.py"])
    restored_config, _ = read_bounded_root_file(
        CONFIG, EXACT_FILES["nox-lifeline-guard.conf"])
    if (hashlib.sha256(restored_script).hexdigest() != AUDIT_SCRIPT_OLD_SHA256 or
        hashlib.sha256(restored_config).hexdigest() != AUDIT_CONFIG_SHA256):
        fail("AUDIT_ROLLBACK_FILE_READBACK")

    if AUDIT_SYSTEMD_PREIMAGE is not None:
        systemd = supervisor_systemd_state()
        if systemd["active"] != "active" or systemd["active_rc"] != 0:
            fail("AUDIT_ROLLBACK_SYSTEMD_ACTIVE")
        original_enabled = AUDIT_SYSTEMD_PREIMAGE.get("enabled")
        if original_enabled not in ("enabled", "disabled"):
            fail("AUDIT_ROLLBACK_SYSTEMD_PREIMAGE")
        if original_enabled == "disabled" and systemd["enabled"] == "enabled":
            # Never repair the global Supervisor unit from this legacy lifeline
            # transaction; preserve evidence and require a separate owner action.
            fail("AUDIT_ROLLBACK_GLOBAL_SUPERVISOR_ENABLE_CHANGED")
        systemd = supervisor_systemd_state()
        if (systemd["active"] != "active" or systemd["active_rc"] != 0 or
            systemd["enabled"] != original_enabled or
            systemd["enabled_rc"] != (0 if original_enabled == "enabled" else 1)):
            fail("AUDIT_ROLLBACK_SYSTEMD_READBACK")

    AUDIT_SCRIPT_BACKUP = None
    AUDIT_CONFIG_BACKUP = None
    emit({"state": "AUDIT_PREIMAGE_RESTORED",
          "script_sha256": AUDIT_SCRIPT_OLD_SHA256,
          "config_sha256": AUDIT_CONFIG_SHA256,
          "guard_pid": current_identity["pid"],
          "guard_start_ticks": current_identity["start_ticks"],
          "supervisor_systemd_enabled": ("disabled" if AUDIT_SYSTEMD_PREIMAGE and
                                          AUDIT_SYSTEMD_PREIMAGE.get("enabled") == "disabled"
                                          else "enabled"),
          "no_original_services_changed": True})

def protect_path(path):
    # Existing directories may not be replaced by symlink attacks.
    for p in (path, *path.parents):
        if p.is_symlink():
            fail("PATH_SYMLINK")

def require_owner_fence():
    # This installation is only for a deliberately fenced handoff. Never
    # create, remove, rename, or rewrite either owner flag.
    for label, path in (("STOP", OWNER_STOP), ("MAINTENANCE", OWNER_MAINTENANCE)):
        protect_path(path)
        try:
            mode = path.lstat().st_mode
        except OSError:
            fail("OWNER_" + label + "_NOT_PRESENT")
        if not stat.S_ISREG(mode):
            fail("OWNER_" + label + "_UNSAFE")


def acquire_owner_maintenance_lock(path=None):
    # Match the existing native operator flock contract; file existence alone
    # is not a lease. Hold EX|NB from admission through the whole installation.
    path = OWNER_MAINTENANCE_LOCK if path is None else Path(path)
    protect_path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                     getattr(os, "O_CLOEXEC", 0))
    except FileNotFoundError:
        fail("OWNER_MAINTENANCE_LOCK_MISSING")
    except OSError:
        fail("OWNER_MAINTENANCE_LOCK_UNSAFE")
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            fail("OWNER_MAINTENANCE_LOCK_UNSAFE")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("OWNER_MAINTENANCE_BUSY")
        return fd
    except BaseException:
        os.close(fd)
        raise


def release_owner_maintenance_lock():
    global OWNER_LOCK_FD
    if OWNER_LOCK_FD is not None:
        fd, OWNER_LOCK_FD = OWNER_LOCK_FD, None
        os.close(fd)


def bytes_checked(name):
    value = BUNDLE.get(name)
    if not isinstance(value, dict) or set(value) != {"content", "sha256"}:
        fail("BUNDLE_SCHEMA")
    raw = base64.b64decode(value["content"], validate=True)
    if len(raw) < 10 or len(raw) > EXACT_FILES[name]:
        fail("BUNDLE_SIZE")
    if hashlib.sha256(raw).hexdigest() != value["sha256"]:
        fail("BUNDLE_DIGEST")
    return raw

def preserve_or_write(path, raw, mode):
    protect_path(path)
    if path.exists():
        if not path.is_file() or path.read_bytes() != raw:
            fail("EXISTING_FILE_CONFLICT_" + path.name.upper().replace(".", "_"))
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".nox-owner-", dir=str(path.parent))
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as w:
            w.write(raw)
            w.flush()
            os.fsync(w.fileno())
        # Atomic no-clobber publication: the preflight check alone is racy.
        # A concurrent owner-created file (including a dangling symlink) must
        # never be replaced, even between check and final publication.
        try:
            os.link(temp, path, follow_symlinks=False)
        except FileExistsError:
            fail("CONCURRENT_FILE_CREATE")
        except OSError:
            fail("ATOMIC_PUBLISH_UNAVAILABLE")
        dfd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return True

def emit(data):
    print("NOX_MAINT_LIFELINE=" + json.dumps(data, sort_keys=True,
                                            ensure_ascii=False, separators=(",", ":")), flush=True)

def validate_baseline(baseline):
    if not isinstance(baseline, dict) or set(baseline) != set(REQUIRED):
        fail("CRITICAL_SERVICE_INVENTORY")
    for name in REQUIRED:
        status = baseline[name]
        if not isinstance(status, dict):
            fail("CRITICAL_SERVICE_INVALID")
        state, pid = status.get("state"), status.get("pid")
        if state == "RUNNING" and type(pid) is int and pid > 0:
            continue
        if state in ("STOPPED", "EXITED") and pid is None:
            continue
        fail("CRITICAL_SERVICE_IDENTITY_UNSAFE")
    return baseline


def check_existing_installation(expected):
    """Only complete byte-identical existing installations may be reused."""
    for path, _ in expected:
        protect_path(path)
    present = [path for path, _ in expected if path.exists() or path.is_symlink()]
    if not present:
        return False
    if len(present) != len(expected):
        fail("PARTIAL_INSTALL_REQUIRES_OWNER_RECONCILIATION")
    mismatches = []
    for path, raw in expected:
        if not path.is_file() or path.is_symlink():
            fail("EXISTING_INSTALL_SOURCE_MISMATCH")
        current = path.read_bytes()
        if current != raw:
            # Only bounded fingerprints leave the host, never policy contents.
            mismatches.append({"name": path.name,
                               "actual_sha256": hashlib.sha256(current).hexdigest(),
                               "expected_sha256": hashlib.sha256(raw).hexdigest(),
                               "actual_bytes": len(current)})
    if mismatches:
        emit({"state": "HOLD_EXISTING_LIFELINE_DIFF",
              "changes_not_applied": True,
              "existing_source_fingerprints_only": mismatches})
        fail("EXISTING_INSTALL_SOURCE_MISMATCH")
    return True


LEGACY_LIFELINE_SHA256 = "c04f66ea3bc9cf3fe753aded140d197411104501d8dd52a3cb2cffd8d753446a"
MIGRATED_SCRIPT_BACKUP = None
MIGRATED_SCRIPT_NEW_SHA = None

def replace_script_exact(path, expected_old, replacement):
    """Atomic, owner-locked exact-script swap. No other config or services."""
    protect_path(path)
    def identity(info):
        # Reading a source may legitimately update atime on relatime mounts.
        return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    before_stat = path.lstat()
    before = identity(before_stat)
    if not stat.S_ISREG(before_stat.st_mode) or before_stat.st_nlink != 1:
        fail("LEGACY_SCRIPT_UNSAFE")
    if path.read_bytes() != expected_old:
        fail("LEGACY_SCRIPT_CHANGED")
    if identity(path.lstat()) != before:
        fail("LEGACY_SCRIPT_RACE")
    fd, temp = tempfile.mkstemp(prefix=".nox-lifeline-upgrade-", dir=path.parent)
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "wb") as w:
            w.write(replacement)
            w.flush()
            os.fsync(w.fileno())
        if identity(path.lstat()) != before or path.read_bytes() != expected_old:
            fail("LEGACY_SCRIPT_RACE")
        os.replace(temp, path)
        fd_dir = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd_dir)
        finally:
            os.close(fd_dir)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    if path.read_bytes() != replacement:
        fail("LEGACY_SCRIPT_READBACK")
    return True


def recover_legacy_script():
    """Best-effort rollback without touching a live guard, original services or STOP."""
    global MIGRATED_SCRIPT_BACKUP, MIGRATED_SCRIPT_NEW_SHA
    if MIGRATED_SCRIPT_BACKUP is None:
        return
    path = MIGRATED_SCRIPT_BACKUP
    old = path.read_bytes()
    if hashlib.sha256(old).hexdigest() != LEGACY_LIFELINE_SHA256:
        fail("LEGACY_BACKUP_CORRUPT")
    current = info(GUARD)
    if current["state"] not in ("STOPPED", "EXITED") or current["pid"] is not None:
        fail("LEGACY_ROLLBACK_GUARD_ACTIVE")
    if hashlib.sha256(SCRIPT.read_bytes()).hexdigest() != MIGRATED_SCRIPT_NEW_SHA:
        fail("LEGACY_ROLLBACK_SOURCE_CHANGED")
    replace_script_exact(SCRIPT, SCRIPT.read_bytes(), old)
    emit({"state": "LEGACY_SCRIPT_ROLLBACK_VERIFIED",
          "restored_sha256": LEGACY_LIFELINE_SHA256,
          "owner_stop_preserved": True})
    MIGRATED_SCRIPT_BACKUP = None


def main():
    global OWNER_LOCK_FD, MIGRATED_SCRIPT_BACKUP, MIGRATED_SCRIPT_NEW_SHA
    global AUDIT_SYSTEMD_STATE
    global AUDIT_SCRIPT_BACKUP, AUDIT_CONFIG_BACKUP
    sha = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    request = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    if not AUDIT_SHA.fullmatch(sha) or not request.isdigit():
        fail("OWNER_CONTEXT")
    if os.geteuid() != 0 or not ROOT.is_dir() or not (ROOT / "scripts").is_dir():
        fail("HOST_IDENTITY")
    if not (Path("/etc/supervisor/conf.d").is_dir()):
        fail("SUPERVISOR_MISSING")
    require_owner_fence()
    OWNER_LOCK_FD = acquire_owner_maintenance_lock()
    # No trainer/chat action; the lifeline's memory counters are read-only.
    baseline = {name: info(name) for name in REQUIRED}
    # Installation starts with a *disabled* observer. Permit a known stopped
    # service so the observer can be staged during an outage. Unknown/FATAL or
    # contradictory RUNNING/PID evidence still block writes. The original
    # service state must remain byte-for-byte identical after the install.
    validate_baseline(baseline)
    script = bytes_checked("nox_native_lifeline.py")
    policy = bytes_checked("lifeline.example.json")
    config = bytes_checked("nox-lifeline-guard.conf")
    parsed = json.loads(policy)
    if (parsed.get("schema") != "NOX_LIFELINE_V2" or
        parsed.get("enabled") is not False or
        any(s.get("restart") is not False for s in parsed.get("services", []))):
        fail("INITIAL_POLICY_NOT_READ_ONLY")
    if b"nox-lifeline-guard" not in config or b"nox_native_lifeline.py" not in config:
        fail("SERVICE_CONFIG_SCOPE")
    config, _ = reconcile_audited_config(script, policy, config, request)
    # Never overwrite an existing differing file / old policy / owner configuration.
    for path in (SCRIPT, POLICY, CONFIG):
        protect_path(path)
    # This EXACT previously installed legacy byte fingerprint was observed
    # by authenticated owner SSH. Never broaden it to an unknown version.
    previous = None
    if (SCRIPT.is_file() and not SCRIPT.is_symlink()
        and POLICY.is_file() and not POLICY.is_symlink()
        and CONFIG.is_file() and not CONFIG.is_symlink()):
        previous = SCRIPT.read_bytes()
        if (hashlib.sha256(previous).hexdigest() == LEGACY_LIFELINE_SHA256
            and POLICY.read_bytes() == policy and CONFIG.read_bytes() == config):
            original_guard = info(GUARD)
            if original_guard["state"] not in ("STOPPED", "EXITED") or original_guard["pid"] is not None:
                fail("LEGACY_GUARD_MUST_BE_STOPPED")
            backup = ROOT / "backup/owner_maintenance" / request / "nox_native_lifeline_preupgrade.py"
            if backup.exists() or backup.is_symlink():
                # No clobber: exact same old bytes already backed up is okay.
                if backup.is_symlink() or not backup.is_file() or backup.read_bytes() != previous:
                    fail("LEGACY_BACKUP_CONFLICT")
            else:
                preserve_or_write(backup, previous, 0o600)
            if backup.read_bytes() != previous:
                fail("LEGACY_BACKUP_READBACK")
            compile(script, str(SCRIPT), "exec")
            replace_script_exact(SCRIPT, previous, script)
            MIGRATED_SCRIPT_BACKUP = backup
            MIGRATED_SCRIPT_NEW_SHA = hashlib.sha256(script).hexdigest()
            emit({"state": "LEGACY_SCRIPT_EXACT_UPGRADE",
                  "old_sha256": LEGACY_LIFELINE_SHA256,
                  "new_sha256": MIGRATED_SCRIPT_NEW_SHA,
                  "backup_sha256_verified": True,
                  "original_services_untouched": True})
    existing = check_existing_installation(
        ((SCRIPT, script), (POLICY, policy), (CONFIG, config)))
    compile(script, str(SCRIPT), "exec")
    guard_state = ROOT / "state/lifeline"
    protect_path(guard_state)
    guard_state.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(guard_state, 0o700)
    changes = []
    if AUDIT_SCRIPT_RECONCILED:
        changes.append(str(SCRIPT))
    if AUDIT_CONFIG_RECONCILED:
        changes.append(str(CONFIG))
    for path, raw, mode in ((SCRIPT, script, 0o644), (POLICY, policy, 0o600),
                            (CONFIG, config, 0o644)):
        if preserve_or_write(path, raw, mode):
            changes.append(str(path))
    p = call(["/usr/bin/python3", "-B", str(SCRIPT), "--policy", str(POLICY),
              "--state", str(guard_state / "state.json"), "--once", "--dry-run"], timeout=25)
    if p.returncode or "NOX_LIFELINE_RESULT=" not in p.stdout:
        fail("READ_ONLY_SELF_TEST")
    reread = call(["supervisorctl", "reread"], timeout=15)
    if reread.returncode or (not existing and GUARD not in reread.stdout):
        fail("SUPERVISOR_REREAD")
    if existing:
        guard_before = info(GUARD)
        if guard_before["state"] in ("STOPPED", "EXITED") and guard_before["pid"] is None:
            # Starts only this independent, disabled/read-only observer.
            started = call(["supervisorctl", "start", GUARD], timeout=18)
            if started.returncode:
                fail("EXISTING_GUARD_START")
        elif guard_before["state"] != "RUNNING" or not guard_before["pid"]:
            fail("EXISTING_GUARD_UNSAFE")
    else:
        update = call(["supervisorctl", "update", GUARD], timeout=18)
        if update.returncode:
            fail("SUPERVISOR_UPDATE")
    active = {"state": "UNKNOWN", "pid": None}
    for _ in range(8):
        active = info(GUARD)
        if active["state"] == "RUNNING" and active["pid"]:
            break
        time.sleep(2)
    after = {name: info(name) for name in REQUIRED}
    if (active["state"] != "RUNNING" or not active["pid"]
        or any(after[n] != baseline[n] for n in REQUIRED)):
        emit({"state": "HOLD_NATIVE_ACCEPTANCE", "originals_unchanged": after == baseline,
              "guard_state": active["state"], "policy_enabled": False,
              "files_written": changes, "source_sha": sha})
        fail("HOST_POSTFLIGHT")
    if AUDIT_CONFIG_RECONCILED:
        final_identity = process_identity(active["pid"])
        final_systemd = supervisor_systemd_state()
        if (final_identity != AUDIT_GUARD_IDENTITY or
            final_systemd["active"] != "active" or final_systemd["active_rc"] != 0 or
            final_systemd["enabled"] != "enabled" or final_systemd["enabled_rc"] != 0):
            fail("AUDIT_FINAL_READBACK")
        AUDIT_SYSTEMD_STATE = final_systemd
    statepath = guard_state / "state.json"
    row = json.loads(statepath.read_text(encoding="utf-8")) if statepath.is_file() else {}
    if row.get("last_report", {}).get("schema") != "NOX_LIFELINE_V2":
        # The guard may not have ticked yet. Oneshot already checked that
        # it can read the native Supervisor, so report acceptance as partial.
        readiness = "RUNNING_READ_ONLY_FRESH_TICK_PENDING"
    else:
        readiness = "RUNNING_READ_ONLY_VERIFIED"
    memory_ready = (not AUDIT_CONFIG_RECONCILED or
                    (isinstance(AUDIT_MEMORY_REPORT, dict) and
                     AUDIT_MEMORY_REPORT.get("status") == "OK" and
                     type(AUDIT_MEMORY_REPORT.get("memory.current")) is int and
                     type(AUDIT_MEMORY_REPORT.get("memory.max")) is int and
                     type(AUDIT_MEMORY_REPORT.get("raw_headroom_bytes")) is int and
                     type(AUDIT_MEMORY_REPORT.get("below_2GiB")) is bool and
                     AUDIT_MEMORY_REPORT["raw_headroom_bytes"] ==
                     AUDIT_MEMORY_REPORT["memory.max"] - AUDIT_MEMORY_REPORT["memory.current"] and
                     AUDIT_MEMORY_REPORT["below_2GiB"] ==
                     (AUDIT_MEMORY_REPORT["raw_headroom_bytes"] < 2 * 1024 ** 3)))
    if AUDIT_CONFIG_RECONCILED and not memory_ready:
        fail("AUDIT_MEMORY_FINAL_READBACK")
    if AUDIT_CONFIG_RECONCILED:
        readiness = ("MONITOR_ACTIVE_LOW_MEMORY"
                     if AUDIT_MEMORY_REPORT["below_2GiB"] else "MONITOR_ACTIVE")
    emit({"state": readiness, "host_instance": 60509551, "request": request,
          "source_sha": sha, "original_services_preserved": True,
          "monitor_active": AUDIT_CONFIG_RECONCILED and memory_ready,
          "owner_stop_preserved": True, "owner_maintenance_preserved": True,
          "maintenance_lock": "EXCLUSIVE_HELD_THROUGH_INSTALL",
          "guard_pid": active["pid"], "guard_policy_enabled": False,
          "guard_executable": (final_identity["exe"]
                               if AUDIT_CONFIG_RECONCILED else None),
          "reviewed_executable": (REVIEWED_EXECUTABLE
                                  if AUDIT_CONFIG_RECONCILED else None),
          "guard_start_ticks": (AUDIT_GUARD_IDENTITY["start_ticks"]
                                if AUDIT_GUARD_IDENTITY else None),
          "supervisor_systemd_active": (AUDIT_SYSTEMD_STATE["active"]
                                        if AUDIT_SYSTEMD_STATE else None),
          "supervisor_systemd_enabled": (AUDIT_SYSTEMD_STATE["enabled"]
                                         if AUDIT_SYSTEMD_STATE else None),
          "cgroup_memory": AUDIT_MEMORY_REPORT,
          "cgroup_memory_at": AUDIT_MEMORY_TIMESTAMP,
          "memory_floor_bytes": 2 * 1024 ** 3,
          "owner_native_audit_required": True,
          "owner_native_audit_scope": "--lifeline-only read-only pre/post evidence",
          "owner_native_audit_source": "nox-control/owner_native_audit.py",
          "source_scope_paths": [
              "nox-control/owner_native_lifeline.py",
              "nox-control/nox_native_lifeline.py",
              "nox-control/owner_native_audit.py"],
          "source_scope_reason": (
              "installer reconciles only pinned files; guard reports bounded cgroup telemetry; "
              "independent audit verifies read-only pre/post process, service, and memory evidence"),
          "owner_native_audit_reasons": [
              "independently verify exact /proc/PID/exe, argv, and start ticks",
              "independently verify Supervisor/systemd state and fresh cgroup telemetry",
              "capture read-only evidence immediately before and after reconciliation"],
          "owner_native_audit_completed": False,
          "written_files": len(changes),
          "script_sha256": hashlib.sha256(script).hexdigest(),
          "no_weights_or_training_changed": True})
    AUDIT_SCRIPT_BACKUP = None
    AUDIT_CONFIG_BACKUP = None
    print("NOX_MAINT_LIFELINE_COMPLETE=true", flush=True)
    return 0

if __name__ == "__main__":
    class OwnerAbort(BaseException):
        pass

    def _owner_abort(signum, frame):
        raise OwnerAbort("HOLD_LIFELINE_OWNER_SIGNAL")

    signal.signal(signal.SIGTERM, _owner_abort)
    signal.signal(signal.SIGINT, _owner_abort)
    try:
        result = main()
    except BaseException as exc:
        audit_rollback = "NOT_NEEDED"
        if AUDIT_SCRIPT_BACKUP is not None or AUDIT_CONFIG_BACKUP is not None:
            try:
                recover_audited_preimage()
                audit_rollback = "RESTORED_EXACT_PREIMAGE"
            except BaseException as rollback_exc:
                audit_rollback = "HOLD_BACKUPS_PRESERVED"
                emit({"state": "HOLD_AUDIT_ROLLBACK",
                      "reason": type(rollback_exc).__name__,
                      "script_backup_preserved": AUDIT_SCRIPT_BACKUP is not None,
                      "config_backup_preserved": AUDIT_CONFIG_BACKUP is not None,
                      "original_services_untouched": True})
        if MIGRATED_SCRIPT_BACKUP is not None:
            try:
                recover_legacy_script()
            except Exception as rollback_exc:
                emit({"state": "HOLD_LEGACY_ROLLBACK",
                      "reason": type(rollback_exc).__name__,
                      "backup_preserved": True,
                      "original_services_untouched": True})
        code = str(exc)
        if not re.fullmatch(r"HOLD_LIFELINE_[A-Z0-9_]+", code):
            code = "HOLD_LIFELINE_" + type(exc).__name__.upper()
        emit({"state": "HOLD", "reason": code, "rollback": audit_rollback,
              "monitor_active": False if audit_rollback != "HOLD_BACKUPS_PRESERVED" else None,
              "cgroup_memory": AUDIT_MEMORY_REPORT,
              "cgroup_memory_at": AUDIT_MEMORY_TIMESTAMP,
              "no_original_services_changed": True})
        sys.exit(2)
    finally:
        try:
            release_owner_maintenance_lock()
        except OSError:
            pass
    sys.exit(result)
