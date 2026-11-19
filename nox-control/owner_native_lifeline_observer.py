#!/usr/bin/env python3
"""Install an independent, forced observer-only NOX lifeline systemd unit.

This entrypoint never enables, starts, stops, or edits supervisor.service and
never changes Supervisor program configuration. Its only service mutation is
enable/start of nox-lifeline-observer.service.
"""
from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
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
SCRIPT = ROOT / "scripts/nox_lifeline_observer.py"
POLICY = Path("/etc/nox/lifeline-observer.json")
UNIT = Path("/etc/systemd/system/nox-lifeline-observer.service")
STATE_DIR = ROOT / "state/lifeline-observer"
STATE = STATE_DIR / "state.json"
SERVICE = "nox-lifeline-observer.service"
UNIT_SHA256 = "ed9fd4f1b83043123f656163c49714592e59f6e27dcf015847a24f3d29435ac3"
OWNER_STOP = ROOT / "STOP"
OWNER_MAINTENANCE = ROOT / "state/OWNER_MAINTENANCE.flag"
OWNER_LOCK = ROOT / "state/owner_maintenance.lock"
MAX_BYTES = {"nox_native_lifeline.py": 32_768,
             "lifeline-observer.json": 8_192,
             "nox-lifeline-observer.service": 8_192}
FILES = {"nox_native_lifeline.py": SCRIPT,
         "lifeline-observer.json": POLICY,
         "nox-lifeline-observer.service": UNIT}
SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")
OWNER_LOCK_FD = None
PREIMAGES = {}
INSTALLED = {}
UNIT_ENABLED_BEFORE = None
UNIT_ACTIVE_BEFORE = None
STATE_DIR_PREIMAGE = None
STATE_ARTIFACT_PREIMAGES = {}
STATE_ARTIFACTS = {"state.json": STATE, "lifeline.lock": STATE_DIR / "lifeline.lock"}
REQUEST_ID = None
SOURCE_SHA_VALUE = None


class Hold(RuntimeError):
    pass


def fail(code: str) -> None:
    raise Hold("HOLD_LIFELINE_OBSERVER_" + code)


def run(args, timeout=20):
    try:
        return subprocess.run(args, capture_output=True, text=True, shell=False,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        fail("COMMAND_UNAVAILABLE")


def bounded_read(path: Path, limit: int, *, allow_absent=False):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                     getattr(os, "O_CLOEXEC", 0))
    except FileNotFoundError:
        if allow_absent:
            return None, None
        fail("FILE_MISSING")
    except OSError:
        fail("FILE_UNSAFE")
    try:
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1 or
                meta.st_uid != 0 or meta.st_mode & 0o022 or meta.st_size > limit):
            fail("FILE_UNSAFE")
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, min(8192, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(fd)
        ident = (meta.st_dev, meta.st_ino, meta.st_mode, meta.st_nlink,
                 meta.st_uid, meta.st_gid, meta.st_size, meta.st_mtime_ns,
                 meta.st_ctime_ns)
        ident_after = (after.st_dev, after.st_ino, after.st_mode, after.st_nlink,
                       after.st_uid, after.st_gid, after.st_size, after.st_mtime_ns,
                       after.st_ctime_ns)
        if len(raw) > limit or len(raw) != meta.st_size or ident_after != ident:
            fail("FILE_CHANGED_DURING_READ")
        return raw, ident
    finally:
        os.close(fd)


def checked_bundle(name):
    item = BUNDLE.get(name)
    if not isinstance(item, dict) or set(item) != {"content", "sha256"}:
        fail("BUNDLE_SCHEMA")
    try:
        raw = base64.b64decode(item["content"], validate=True)
    except Exception:
        fail("BUNDLE_BASE64")
    if (not 10 <= len(raw) <= MAX_BYTES[name] or
            hashlib.sha256(raw).hexdigest() != item["sha256"]):
        fail("BUNDLE_DIGEST")
    return raw


def validate_unit(raw):
    if hashlib.sha256(raw).hexdigest() != UNIT_SHA256:
        fail("UNIT_PIN_MISMATCH")
    lines = [line.strip() for line in raw.decode("utf-8", "strict").splitlines()
             if line.strip() and not line.lstrip().startswith("#") and
             not line.lstrip().startswith(";")]
    exec_line = ("ExecStart=/usr/bin/python3 -u /root/nox/scripts/"
                 "nox_lifeline_observer.py --policy /etc/nox/lifeline-observer.json "
                 "--state /root/nox/state/lifeline-observer/state.json --observer-only")
    if lines.count(exec_line) != 1:
        fail("UNIT_EXECSTART_MISMATCH")
    for line in lines:
        key, _, value = line.partition("=")
        if key in {"Wants", "Requires", "Requisite", "BindsTo", "PartOf", "Upholds",
                   "PropagatesReloadTo", "PropagatesStopTo", "JoinsNamespaceOf"} and (
                "supervisor.service" in value or "nox-" in value):
            fail("UNIT_WORKLOAD_DEPENDENCY_FORBIDDEN")
        if key == "After" and any(token == "supervisor.service" or token.startswith("nox-")
                                   for token in value.split()):
            fail("UNIT_WORKLOAD_ORDERING_FORBIDDEN")
    if ("Restart=always" not in lines or "StartLimitIntervalSec=0" not in lines or
            "WantedBy=multi-user.target" not in lines or
            "--observer-only" not in exec_line):
        fail("UNIT_OBSERVER_POLICY_INVALID")


def reject_external_unit_overrides():
    unit_name = UNIT.name
    for candidate in (Path("/run/systemd/system") / unit_name,
                      Path("/usr/lib/systemd/system") / unit_name,
                      Path("/lib/systemd/system") / unit_name):
        if candidate.exists() or candidate.is_symlink():
            fail("EXTERNAL_UNIT_FRAGMENT_PRESENT")
    for base in (Path("/etc/systemd/system"), Path("/run/systemd/system"),
                 Path("/usr/lib/systemd/system"), Path("/lib/systemd/system")):
        dropins = base / (unit_name + ".d")
        if dropins.exists() or dropins.is_symlink():
            try:
                meta = dropins.lstat()
                entries = list(dropins.iterdir()) if stat.S_ISDIR(meta.st_mode) else [dropins]
            except OSError:
                fail("EXTERNAL_UNIT_DROPIN_UNREADABLE")
            if entries:
                fail("EXTERNAL_UNIT_DROPIN_PRESENT")


def protect_parents(path: Path):
    for parent in (path.parent, *path.parent.parents):
        try:
            info = parent.lstat()
        except OSError:
            fail("PARENT_UNAVAILABLE")
        if (stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or
                info.st_uid != 0 or info.st_mode & 0o022):
            fail("PARENT_UNSAFE")
    if path.exists() and path.is_symlink():
        fail("TARGET_SYMLINK")


def atomic_write(path: Path, raw: bytes, mode: int, owner=(0, 0)):
    protect_parents(path)
    old, old_identity = bounded_read(path, max(MAX_BYTES.values(), len(raw)),
                                     allow_absent=True)
    expected = PREIMAGES[str(path)]
    if old != expected[0] or old_identity != expected[1]:
        fail("TARGET_CAS_MISMATCH")
    fd, temp = tempfile.mkstemp(prefix=".nox-lifeline-observer-", dir=path.parent)
    try:
        os.fchown(fd, owner[0], owner[1])
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        current, identity = bounded_read(path, max(MAX_BYTES.values(), len(raw)),
                                         allow_absent=True)
        if current != expected[0] or identity != expected[1]:
            fail("TARGET_CAS_RACE")
        os.replace(temp, path)
        INSTALLED[str(path)] = raw
        dirfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    written, _ = bounded_read(path, max(MAX_BYTES.values(), len(raw)))
    if written != raw:
        fail("TARGET_READBACK")


def unit_state(unit):
    active = run(["systemctl", "is-active", unit], timeout=10)
    enabled = run(["systemctl", "is-enabled", unit], timeout=10)
    active_text = active.stdout.strip()
    enabled_text = enabled.stdout.strip()
    if active_text not in ("active", "inactive", "failed", "unknown"):
        fail("SYSTEMD_ACTIVE_STATE_UNKNOWN")
    if enabled_text not in ("enabled", "disabled", "static", "indirect", "not-found"):
        fail("SYSTEMD_ENABLE_STATE_UNKNOWN")
    if (active_text == "active" and active.returncode != 0) or (
            active_text in ("inactive", "failed", "unknown") and active.returncode == 0):
        fail("SYSTEMD_ACTIVE_RC_CONTRADICTION")
    if (enabled_text == "enabled" and enabled.returncode != 0) or (
            enabled_text in ("disabled", "static", "indirect", "not-found") and
            enabled.returncode == 0):
        fail("SYSTEMD_ENABLE_RC_CONTRADICTION")
    return {"active": active_text, "active_rc": active.returncode,
            "enabled": enabled_text, "enabled_rc": enabled.returncode}


def supervisor_unit_state():
    return unit_state("supervisor.service")


def process_identity(pid):
    if type(pid) is not int or pid <= 0:
        fail("PROCESS_PID")
    base = Path("/proc") / str(pid)

    def read_limit(path, limit):
        try:
            with path.open("rb") as stream:
                return stream.read(limit + 1)
        except OSError:
            fail("PROCESS_IDENTITY_UNAVAILABLE")

    def ticks():
        raw = read_limit(base / "stat", 4096)
        if len(raw) > 4096:
            fail("PROCESS_STAT_LIMIT")
        try:
            pid_raw, rest = raw.split(b" ", 1)
            close = rest.rfind(b")")
            if int(pid_raw) != pid or close < 0:
                raise ValueError
            return int(rest[close + 1:].split()[19])
        except (ValueError, IndexError):
            fail("PROCESS_STAT_INVALID")

    before = ticks()
    try:
        exe_before = os.readlink(base / "exe")
    except OSError:
        fail("PROCESS_IDENTITY_UNAVAILABLE")
    cmd_before = read_limit(base / "cmdline", 16_384)
    env_before = read_limit(base / "environ", 262_144)
    env_after = read_limit(base / "environ", 262_144)
    cmd_after = read_limit(base / "cmdline", 16_384)
    try:
        exe_after = os.readlink(base / "exe")
    except OSError:
        fail("PROCESS_IDENTITY_REREAD_UNAVAILABLE")
    after = ticks()
    if (before != after or exe_before != exe_after or cmd_before != cmd_after or
            env_before != env_after or len(cmd_before) > 16_384 or
            len(env_before) > 262_144 or len(cmd_after) > 16_384 or
            len(env_after) > 262_144 or not cmd_before.endswith(b"\0")):
        fail("PROCESS_IDENTITY_CHANGED")
    argv = tuple(x.decode("utf-8", "strict") for x in cmd_before[:-1].split(b"\0"))
    if argv != EXPECTED_ARGV or exe_before != os.path.realpath("/usr/bin/python3"):
        fail("PROCESS_ARGV_MISMATCH")
    return {"pid": pid, "start_ticks": before, "exe": exe_before, "argv": argv,
            "environment_sha256": hashlib.sha256(env_before).hexdigest()}


EXPECTED_ARGV = ("/usr/bin/python3", "-u", "/root/nox/scripts/nox_lifeline_observer.py",
                 "--policy", "/etc/nox/lifeline-observer.json",
                 "--state", "/root/nox/state/lifeline-observer/state.json",
                 "--observer-only")


def fresh_receipt(started_at):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            raw, _ = bounded_read(STATE, 262_144)
            state = json.loads(raw)
            report = state.get("last_report")
            if (not isinstance(report, dict) or
                    report.get("schema") != "NOX_LIFELINE_V2" or
                    report.get("observer_only_enforced") is not True or
                    report.get("worker_starts_permitted") is not False):
                raise ValueError
            memory = report.get("cgroup_memory")
            if not isinstance(memory, dict):
                raise ValueError
            current, maximum = memory.get("memory.current"), memory.get("memory.max")
            headroom, below = memory.get("raw_headroom_bytes"), memory.get("below_2GiB")
            if (type(current) is not int or type(maximum) is not int or
                    type(headroom) is not int or type(below) is not bool or
                    memory.get("memory_floor_bytes") != 2 * 1024**3 or
                    memory.get("severity") != ("CRITICAL" if below else "OK") or
                    headroom != maximum - current or below != (headroom < 2 * 1024**3) or
                    memory.get("status") != ("OK" if headroom >= 0 else "INCONSISTENT")):
                raise ValueError
            from datetime import datetime
            at = datetime.fromisoformat(report["at"].replace("Z", "+00:00")).timestamp()
            if at < started_at - 2 or at > time.time() + 5:
                raise ValueError
            return report
        except (OSError, ValueError, TypeError, KeyError, RuntimeError):
            time.sleep(1)
    fail("FRESH_OBSERVER_RECEIPT_TIMEOUT")


def acquire_owner_lock():
    global OWNER_LOCK_FD
    for flag in (OWNER_STOP, OWNER_MAINTENANCE):
        try:
            meta = flag.lstat()
        except OSError:
            fail("OWNER_FENCE_MISSING")
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0 or
                meta.st_mode & 0o022):
            fail("OWNER_FENCE_UNSAFE")
    try:
        fd = os.open(OWNER_LOCK, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                     getattr(os, "O_CLOEXEC", 0))
    except OSError:
        fail("OWNER_LOCK_UNAVAILABLE")
    try:
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1 or
                meta.st_uid != 0 or meta.st_mode & 0o022):
            fail("OWNER_LOCK_UNSAFE")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        OWNER_LOCK_FD = fd
    except BlockingIOError:
        os.close(fd)
        fail("OWNER_LOCK_BUSY")
    except BaseException:
        os.close(fd)
        raise


def save_backup(request, path, raw):
    if raw is None:
        return None
    backup_dir = ROOT / "backup/owner_maintenance" / request
    for directory in (ROOT / "backup", ROOT / "backup/owner_maintenance", backup_dir):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        try:
            info = directory.lstat()
        except OSError:
            fail("BACKUP_DIRECTORY_UNAVAILABLE")
        if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or
                info.st_uid != 0 or info.st_mode & 0o022):
            fail("BACKUP_DIRECTORY_UNSAFE")
    protect_parents(backup_dir / "backup-probe")
    os.chmod(backup_dir, 0o700)
    digest = hashlib.sha256(raw).hexdigest()
    backup = backup_dir / (path.name + ".preimage-" + digest)
    try:
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        existing, _ = bounded_read(backup, max(MAX_BYTES.values(), len(raw)))
        if existing != raw:
            fail("BACKUP_CONFLICT")
        return str(backup)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    checked, _ = bounded_read(backup, max(MAX_BYTES.values(), len(raw)))
    if checked != raw:
        fail("BACKUP_READBACK")
    return str(backup)


def ensure_private_directory(path: Path):
    global STATE_DIR_PREIMAGE
    created = False
    try:
        path.mkdir(mode=0o700)
        created = True
    except FileExistsError:
        created = False
    try:
        info = path.lstat()
    except OSError:
        if created:
            try:
                check = path.lstat()
                if stat.S_ISDIR(check.st_mode) and not stat.S_ISLNK(check.st_mode):
                    path.rmdir()
            except OSError:
                STATE_DIR_PREIMAGE = {"created": True, "capture_failed": True}
        fail("STATE_DIRECTORY_UNAVAILABLE")
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or
            info.st_uid != 0 or info.st_mode & 0o022):
        fail("STATE_DIRECTORY_UNSAFE")
    if created:
        info = path.lstat()
    STATE_DIR_PREIMAGE = {"created": created, "mode": stat.S_IMODE(info.st_mode),
                          "uid": info.st_uid, "gid": info.st_gid,
                          "device": info.st_dev, "inode": info.st_ino}


def snapshot_state_artifacts(request):
    for name, path in STATE_ARTIFACTS.items():
        raw, identity = bounded_read(path, 262_144, allow_absent=True)
        if raw is not None:
            backup = save_backup(request, path, raw)
        else:
            backup = None
        STATE_ARTIFACT_PREIMAGES[name] = (raw, identity)
        STATE_ARTIFACT_PREIMAGES[name + ".receipt"] = {
            "sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None,
            "absent": raw is None,
            "mode": stat.S_IMODE(identity[2]) if identity else None,
            "uid": identity[4] if identity else None,
            "gid": identity[5] if identity else None,
            "device": identity[0] if identity else None,
            "inode": identity[1] if identity else None,
            "backup": backup,
        }


def restore_state_artifacts():
    # The dedicated service has been stopped before this runs. Restore only
    # root-owned regular files in our private state directory.
    for name, path in STATE_ARTIFACTS.items():
        original, original_identity = STATE_ARTIFACT_PREIMAGES[name]
        current, current_identity = bounded_read(path, 262_144, allow_absent=True)
        if current == original and current_identity == original_identity:
            continue
        if current is not None and (current_identity is None or current_identity[4] != 0):
            fail("STATE_ARTIFACT_ROLLBACK_UNSAFE")
        if original is None:
            if current is not None:
                path.unlink()
        else:
            parent = path.parent
            fd, temp = tempfile.mkstemp(prefix=".nox-lifeline-restore-", dir=parent)
            try:
                os.fchown(fd, original_identity[4], original_identity[5])
                os.fchmod(fd, stat.S_IMODE(original_identity[2]))
                with os.fdopen(fd, "wb") as stream:
                    stream.write(original)
                    stream.flush()
                    os.fsync(stream.fileno())
                check, check_identity = bounded_read(path, 262_144, allow_absent=True)
                if check != current or check_identity != current_identity:
                    fail("STATE_ARTIFACT_ROLLBACK_CAS")
                os.replace(temp, path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
        dirfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    if STATE_DIR_PREIMAGE is not None:
        info = STATE_DIR.lstat()
        expected = STATE_DIR_PREIMAGE
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != expected["uid"] or
                info.st_gid != expected["gid"] or info.st_dev != expected["device"] or
                info.st_ino != expected["inode"]):
            fail("STATE_DIRECTORY_ROLLBACK_UNSAFE")
        if expected["created"]:
            try:
                STATE_DIR.rmdir()
            except OSError:
                fail("STATE_DIRECTORY_NOT_EMPTY_ON_ROLLBACK")
        elif stat.S_IMODE(info.st_mode) != expected["mode"]:
            os.chmod(STATE_DIR, expected["mode"])


def restore_exact_preimages():
    # Roll back only files that still equal this transaction's installed bytes.
    for name, path in FILES.items():
        installed = INSTALLED.get(str(path))
        if installed is None:
            continue
        current, identity = bounded_read(path, max(MAX_BYTES.values(), len(installed)),
                                         allow_absent=True)
        if current != installed:
            fail("ROLLBACK_FILE_CHANGED")
        original, _ = PREIMAGES[str(path)]
        original_identity = PREIMAGES[str(path)][1]
        if original is None:
            path.unlink()
            dirfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
        else:
            # Compare-and-swap from our installed bytes back to the exact preimage.
            PREIMAGES[str(path)] = (installed, identity)
            atomic_write(path, original, stat.S_IMODE(original_identity[2]),
                         owner=(original_identity[4], original_identity[5]))
    reload_result = run(["systemctl", "daemon-reload"], timeout=20)
    if reload_result.returncode:
        fail("ROLLBACK_DAEMON_RELOAD")


def main():
    global UNIT_ENABLED_BEFORE, UNIT_ACTIVE_BEFORE, REQUEST_ID, SOURCE_SHA_VALUE
    source_sha = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    SOURCE_SHA_VALUE = source_sha if SOURCE_SHA.fullmatch(source_sha) else None
    request = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    if not SOURCE_SHA.fullmatch(source_sha) or not request.isdigit():
        fail("OWNER_CONTEXT")
    REQUEST_ID = request
    if os.geteuid() != 0:
        fail("ROOT_REQUIRED")
    if not Path("/run/systemd/system").is_dir():
        fail("SYSTEMD_NOT_RUNNING")
    acquire_owner_lock()
    before_supervisor = supervisor_unit_state()
    unit_before = unit_state(SERVICE)
    if (unit_before["active"] not in ("active", "inactive", "unknown") or
            unit_before["enabled"] not in ("enabled", "disabled", "not-found")):
        fail("OBSERVER_PREIMAGE_UNIT_STATE_UNSUPPORTED")
    UNIT_ENABLED_BEFORE, UNIT_ACTIVE_BEFORE = unit_before["enabled"], unit_before["active"]
    if UNIT_ACTIVE_BEFORE == "active":
        fail("OBSERVER_ALREADY_ACTIVE")

    bundle = {name: checked_bundle(name) for name in MAX_BYTES}
    policy = json.loads(bundle["lifeline-observer.json"])
    if (policy.get("enabled") is not False or not isinstance(policy.get("services"), list) or
            any(item.get("restart") is not False for item in policy["services"])):
        fail("BUNDLED_POLICY_NOT_OBSERVER_ONLY")
    validate_unit(bundle["nox-lifeline-observer.service"])
    reject_external_unit_overrides()
    compile(bundle["nox_native_lifeline.py"], str(SCRIPT), "exec")

    preimage_receipts = {}
    for name, path in FILES.items():
        protect_parents(path)
        old, identity = bounded_read(path, MAX_BYTES[name], allow_absent=True)
        desired = bundle[name]
        if old is not None and old != desired:
            fail("UNEXPECTED_PREIMAGE_" + name.upper().replace(".", "_"))
        PREIMAGES[str(path)] = (old, identity)
        backup = save_backup(request, path, old)
        preimage_receipts[str(path)] = {
            "sha256": hashlib.sha256(old).hexdigest() if old is not None else None,
            "absent": old is None,
            "mode": stat.S_IMODE(identity[2]) if identity is not None else None,
            "uid": identity[4] if identity is not None else None,
            "gid": identity[5] if identity is not None else None,
            "device": identity[0] if identity is not None else None,
            "inode": identity[1] if identity is not None else None,
            "backup": backup,
        }

    protect_parents(STATE_DIR / "state.json")
    ensure_private_directory(STATE_DIR)
    snapshot_state_artifacts(request)
    started_at = time.time()
    for name, path in FILES.items():
        desired = bundle[name]
        atomic_write(path, desired, 0o600 if path == POLICY else 0o644)
    reloaded = run(["systemctl", "daemon-reload"], timeout=20)
    if reloaded.returncode:
        fail("DAEMON_RELOAD")
    reject_external_unit_overrides()
    installed_unit, _ = bounded_read(UNIT, MAX_BYTES["nox-lifeline-observer.service"])
    if installed_unit != bundle["nox-lifeline-observer.service"]:
        fail("UNIT_BLOB_CHANGED_BEFORE_ENABLE")
    enabled = run(["systemctl", "enable", "--now", SERVICE], timeout=35)
    if enabled.returncode:
        fail("OBSERVER_ENABLE_START")

    state = unit_state(SERVICE)
    if state["active"] != "active" or state["enabled"] != "enabled":
        fail("OBSERVER_SYSTEMD_READBACK")
    show = run(["systemctl", "show", SERVICE, "--property=MainPID", "--value"], timeout=10)
    if show.returncode != 0:
        fail("OBSERVER_MAINPID_QUERY")
    try:
        pid = int(show.stdout.strip())
    except ValueError:
        fail("OBSERVER_MAINPID")
    identity = process_identity(pid)
    report = fresh_receipt(started_at)
    final_state = unit_state(SERVICE)
    final_show = run(["systemctl", "show", SERVICE, "--property=MainPID", "--value"], timeout=10)
    if final_show.returncode != 0:
        fail("OBSERVER_FINAL_MAINPID_QUERY")
    try:
        final_pid = int(final_show.stdout.strip())
    except ValueError:
        fail("OBSERVER_FINAL_MAINPID")
    final_identity = process_identity(final_pid)
    if (final_state["active"] != "active" or final_state["enabled"] != "enabled" or
            final_pid != pid or final_identity["start_ticks"] != identity["start_ticks"] or
            final_identity["argv"] != identity["argv"] or
            final_identity["exe"] != identity["exe"]):
        fail("OBSERVER_IDENTITY_CHANGED_AFTER_RECEIPT")
    after_supervisor = supervisor_unit_state()
    if before_supervisor != after_supervisor:
        fail("GLOBAL_SUPERVISOR_STATE_CHANGED")

    memory = report["cgroup_memory"]
    emit({"state": "OBSERVER_ACTIVE_CRITICAL_MEMORY" if memory["below_2GiB"] else "OBSERVER_ACTIVE",
          "source_sha": source_sha, "request_id": request,
          "service": SERVICE, "service_active": state["active"],
          "service_enabled": state["enabled"], "pid": pid,
          "start_ticks": identity["start_ticks"], "argv_sha256": hashlib.sha256(
              b"\0".join(x.encode() for x in identity["argv"])).hexdigest(),
          "script_sha256": hashlib.sha256(bundle["nox_native_lifeline.py"]).hexdigest(),
          "policy_sha256": hashlib.sha256(bundle["lifeline-observer.json"]).hexdigest(),
          "unit_sha256": hashlib.sha256(bundle["nox-lifeline-observer.service"]).hexdigest(),
          "observer_only_enforced": True, "worker_starts_permitted": False,
          "global_supervisor_before": before_supervisor,
          "global_supervisor_after": after_supervisor,
          "cgroup_memory": memory, "cgroup_memory_at": report["at"],
          "memory_floor_bytes": 2 * 1024**3,
          "preimages_backed_up": True,
          "preimages": preimage_receipts,
          "state_directory_preimage": STATE_DIR_PREIMAGE,
          "state_artifact_preimages": {key: value for key, value in
                                        STATE_ARTIFACT_PREIMAGES.items()
                                        if key.endswith(".receipt")},
          "rollback": "PREIMAGE_CONTENT_MODE_OWNER_CAS;FILE_INODES_NOT_RESTORABLE",
          "weights_training_supervisor_workloads_changed": False})
    print("NOX_MAINT_LIFELINE_COMPLETE=true", flush=True)
    return 0


def emit(value):
    print("NOX_MAINT_LIFELINE_OBSERVER_RECEIPT=" + json.dumps(value, sort_keys=True), flush=True)


if __name__ == "__main__":
    class OwnerAbort(BaseException):
        pass

    def _owner_abort(signum, frame):
        raise OwnerAbort("HOLD_LIFELINE_OBSERVER_OWNER_SIGNAL")

    signal.signal(signal.SIGTERM, _owner_abort)
    signal.signal(signal.SIGINT, _owner_abort)
    try:
        result = main()
    except BaseException as exc:
        rollback = "NOT_NEEDED"
        if INSTALLED or STATE_DIR_PREIMAGE is not None:
            try:
                if INSTALLED:
                    if UNIT_ACTIVE_BEFORE != "active":
                        stopped = run(["systemctl", "stop", SERVICE], timeout=20)
                        if stopped.returncode:
                            fail("ROLLBACK_SERVICE_STOP")
                        current = unit_state(SERVICE)
                        if current["active"] == "active":
                            fail("ROLLBACK_SERVICE_STILL_ACTIVE")
                    if UNIT_ENABLED_BEFORE != "enabled":
                        disabled = run(["systemctl", "disable", SERVICE], timeout=20)
                        if disabled.returncode:
                            fail("ROLLBACK_SERVICE_DISABLE")
                    restore_exact_preimages()
                    restored_state = unit_state(SERVICE)
                    if (restored_state["active"] != UNIT_ACTIVE_BEFORE or
                            restored_state["enabled"] != UNIT_ENABLED_BEFORE):
                        fail("ROLLBACK_SERVICE_STATE_MISMATCH")
                restore_state_artifacts()
                rollback = "PREIMAGE_CONTENT_MODE_OWNER_RESTORED;FILE_INODES_NOT_RESTORABLE"
            except BaseException:
                rollback = "HOLD_BACKUPS_AND_INSTALLED_BLOBS_PRESERVED"
        code = str(exc)
        if not re.fullmatch(r"HOLD_LIFELINE_OBSERVER_[A-Z0-9_]+", code):
            code = "HOLD_LIFELINE_OBSERVER_" + type(exc).__name__.upper()
        emit({"state": "HOLD", "reason": code, "rollback": rollback,
              "source_sha": SOURCE_SHA_VALUE, "request_id": REQUEST_ID,
              "global_supervisor_mutated": False,
              "installed_paths": list(INSTALLED)})
        sys.exit(2)
    finally:
        if OWNER_LOCK_FD is not None:
            os.close(OWNER_LOCK_FD)
    sys.exit(result)
