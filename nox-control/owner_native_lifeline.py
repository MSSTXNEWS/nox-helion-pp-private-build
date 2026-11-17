#!/usr/bin/env python3
"""NOX owner-only one-shot deploy of bounded native Supervisor lifeline.

Run solely by the existing pinned GitHub -> authenticated Vast #60509551
SSH owner-maintenance transport. No weight/S03/chat/trainer mutations.
"""
from __future__ import annotations
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
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
    for path, raw in expected:
        if not path.is_file() or path.is_symlink() or path.read_bytes() != raw:
            fail("EXISTING_INSTALL_SOURCE_MISMATCH")
    return True


def main():
    global OWNER_LOCK_FD
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
    # No interaction with trainer, chat port or memory.
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
    # Never overwrite an existing differing file / old policy / owner configuration.
    for path in (SCRIPT, POLICY, CONFIG):
        protect_path(path)
    existing = check_existing_installation(
        ((SCRIPT, script), (POLICY, policy), (CONFIG, config)))
    compile(script, str(SCRIPT), "exec")
    guard_state = ROOT / "state/lifeline"
    protect_path(guard_state)
    guard_state.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(guard_state, 0o700)
    changes = []
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
    statepath = guard_state / "state.json"
    row = json.loads(statepath.read_text(encoding="utf-8")) if statepath.is_file() else {}
    if row.get("last_report", {}).get("schema") != "NOX_LIFELINE_V2":
        # The guard may not have ticked yet. Oneshot already checked that
        # it can read the native Supervisor, so report acceptance as partial.
        readiness = "RUNNING_READ_ONLY_FRESH_TICK_PENDING"
    else:
        readiness = "RUNNING_READ_ONLY_VERIFIED"
    emit({"state": readiness, "host_instance": 60509551, "request": request,
          "source_sha": sha, "original_services_preserved": True,
          "owner_stop_preserved": True, "owner_maintenance_preserved": True,
          "maintenance_lock": "EXCLUSIVE_HELD_THROUGH_INSTALL",
          "guard_pid": active["pid"], "guard_policy_enabled": False,
          "written_files": len(changes),
          "script_sha256": hashlib.sha256(script).hexdigest(),
          "no_weights_or_training_changed": True})
    print("NOX_MAINT_LIFELINE_COMPLETE=true", flush=True)
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        code = str(exc)
        if not re.fullmatch(r"HOLD_LIFELINE_[A-Z0-9_]+", code):
            code = "HOLD_LIFELINE_" + type(exc).__name__.upper()
        emit({"state": "HOLD", "reason": code, "no_original_services_changed": True})
        sys.exit(2)
    finally:
        try:
            release_owner_maintenance_lock()
        except OSError:
            pass
