#!/usr/bin/env python3
"""Conservative cgroup-v2 memory reclaim watchdog for one exact NOX unit.

The controller only writes a small, rate-limited request to the memory.reclaim
file of a verified systemd service leaf. It never changes limits, signals
processes, or touches model/S03/checkpoint files. The policy is
root-owned and disabled until a specific service and cgroup leaf are pinned.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import time

MIB = 1024 * 1024
GIB = 1024 * MIB
PAGE = 4096
MAX_POLICY_BYTES = 16 * 1024
MAX_STATE_BYTES = 256 * 1024
MAX_CGROUP_FILE_BYTES = 64 * 1024
MAX_PROCESSES = 2048
MAX_HISTORY = 64
MAX_DAILY_REQUESTS = 300
MAX_RECLAIM_STEP = 256 * MIB
MAX_DAILY_BUDGET = 2 * GIB
SCHEMA = "NOX_MEMORY_RECLAIM_WATCHDOG_V1"
POLICY_SCHEMA = "NOX_MEMORY_RECLAIM_POLICY_V1"
UNIT_RE = re.compile(r"nox-[a-z0-9][a-z0-9_.@-]{0,63}\.service\Z")
CGROUP_COMPONENT_RE = re.compile(r"[A-Za-z0-9_.@-]{1,100}\Z")
STATE_ROOT = Path("/var/lib/nox-memory-reclaim")
POLICY_PATH = Path("/etc/nox/memory-reclaim-policy.json")
CGROUP_ROOT = Path("/sys/fs/cgroup")
PROC_ROOT = Path("/proc")
SYSTEMCTL = "/bin/systemctl"
STOP_MARKERS = (
    Path("/root/nox/STOP"), Path("/root/nox/STOP.flag"),
    Path("/root/nox/state/STOP"), Path("/root/nox/state/DRIVE_STOP.flag"),
    Path("/root/nox/state/OWNER_MAINTENANCE.flag"), Path("/workspace/NOX_STOP"),
)


class Hold(RuntimeError):
    """A bounded, sanitized fail-closed condition."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise Hold("HOLD_MEMORY_RECLAIM_" + code)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_fd_at(directory_fd: int, name: str, limit: int = MAX_CGROUP_FILE_BYTES) -> bytes:
    require(name in {
        "cgroup.type", "cgroup.procs", "memory.current", "memory.max",
        "memory.high", "memory.stat", "memory.events", "memory.pressure",
        "memory.reclaim",
    }, "CGROUP_FILE_ALLOWLIST")
    try:
        fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory_fd)
    except OSError:
        raise Hold("HOLD_MEMORY_RECLAIM_CGROUP_FILE_UNAVAILABLE") from None
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode), "CGROUP_FILE_TYPE")
        chunks = []
        total = 0
        while total <= limit:
            part = os.read(fd, min(8192, limit + 1 - total))
            if not part:
                break
            chunks.append(part)
            total += len(part)
        raw = b"".join(chunks)
        require(total <= limit, "CGROUP_FILE_SIZE")
        require(info.st_ino == os.fstat(fd).st_ino, "CGROUP_FILE_CHANGED")
        return raw
    finally:
        os.close(fd)


def _text(raw: bytes, code: str) -> str:
    try:
        return raw.decode("ascii", "strict").strip()
    except UnicodeDecodeError:
        raise Hold("HOLD_MEMORY_RECLAIM_" + code) from None


def _uint(value: str, code: str) -> int:
    require(isinstance(value, str) and value.isdecimal() and len(value) <= 24, code)
    return int(value)


def parse_kv(raw: str, code: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in raw.splitlines():
        parts = line.split()
        require(len(parts) == 2 and parts[0] not in result, code)
        result[parts[0]] = _uint(parts[1], code)
    require(bool(result), code)
    return result


def parse_pressure(raw: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for line in raw.splitlines():
        parts = line.split()
        require(len(parts) >= 2 and parts[0] in ("some", "full")
                and parts[0] not in result, "PRESSURE_ROW")
        row: dict[str, float] = {}
        for field in parts[1:]:
            key, sep, value = field.partition("=")
            require(bool(sep) and key not in row, "PRESSURE_FIELD")
            if key == "avg10":
                try:
                    number = float(value)
                except (ValueError, OverflowError):
                    raise Hold("HOLD_MEMORY_RECLAIM_PRESSURE_VALUE") from None
                require(math.isfinite(number) and 0 <= number <= 100,
                        "PRESSURE_VALUE")
                row[key] = number
        require("avg10" in row, "PRESSURE_AVG10")
        result[parts[0]] = row["avg10"]
    require("some" in result and "full" in result, "PRESSURE_MISSING")
    return result


def clean_file_estimate(stats: dict[str, int]) -> int:
    needed = ("file", "shmem", "inactive_file", "file_mapped",
              "file_dirty", "file_writeback")
    require(all(type(stats.get(k)) is int and stats[k] >= 0 for k in needed),
            "MEMORY_STAT_REQUIRED")
    require(stats["shmem"] <= stats["file"]
            and stats["file_mapped"] <= stats["file"], "MEMORY_STAT_INCONSISTENT")
    # Conservative estimate only: exclude tmpfs/shared-memory, mmap-backed,
    # dirty, and writeback pages, then intersect with the inactive file LRU.
    unshared_unmapped_clean = max(
        0, stats["file"] - stats["shmem"] - stats["file_mapped"]
        - stats["file_dirty"] - stats["file_writeback"])
    return min(stats["inactive_file"], unshared_unmapped_clean)


def safe_control_group(value: str, unit: str) -> str:
    require(isinstance(unit, str) and UNIT_RE.fullmatch(unit), "UNIT_ALLOWLIST")
    require(isinstance(value, str) and value.startswith("/")
            and not value.endswith("/") and len(value) <= 512, "CONTROL_GROUP_FORMAT")
    parts = value.split("/")[1:]
    require(2 <= len(parts) <= 8 and all(
        p not in ("", ".", "..") and CGROUP_COMPONENT_RE.fullmatch(p) for p in parts),
        "CONTROL_GROUP_COMPONENT")
    require(parts[-1] == unit and parts[0] in ("system.slice", "nox.slice",
            "nox-memory-managed.slice"), "CONTROL_GROUP_UNIT_MISMATCH")
    return value


def validate_policy(policy: object) -> dict:
    fields = {
        "schema", "enabled", "target_unit", "expected_control_group",
        "high_watermark_fraction", "low_watermark_fraction", "max_reclaim_bytes",
        "minimum_reclaim_bytes", "daily_budget_bytes", "cooldown_seconds",
        "poll_seconds",
    }
    require(isinstance(policy, dict) and set(policy) == fields, "POLICY_SCHEMA")
    require(policy["schema"] == POLICY_SCHEMA and type(policy["enabled"]) is bool,
            "POLICY_VERSION")
    high = policy["high_watermark_fraction"]
    low = policy["low_watermark_fraction"]
    require(type(high) in (int, float) and type(low) in (int, float)
            and math.isfinite(high) and math.isfinite(low)
            and 0.5 <= low < high <= 0.98, "POLICY_WATERMARKS")
    for name, value, minimum, maximum in (
        ("max_reclaim_bytes", policy["max_reclaim_bytes"], PAGE, MAX_RECLAIM_STEP),
        ("minimum_reclaim_bytes", policy["minimum_reclaim_bytes"], PAGE, MAX_RECLAIM_STEP),
        ("daily_budget_bytes", policy["daily_budget_bytes"], PAGE, MAX_DAILY_BUDGET),
        ("cooldown_seconds", policy["cooldown_seconds"], 300, 86400),
        ("poll_seconds", policy["poll_seconds"], 10, 600),
    ):
        require(type(value) is int and minimum <= value <= maximum,
                "POLICY_" + name.upper())
    require(policy["minimum_reclaim_bytes"] <= policy["max_reclaim_bytes"]
            and policy["daily_budget_bytes"] >= policy["max_reclaim_bytes"],
            "POLICY_RECLAIM_BUDGET")
    if policy["enabled"]:
        unit = policy["target_unit"]
        require(isinstance(unit, str) and UNIT_RE.fullmatch(unit), "UNIT_ALLOWLIST")
        safe_control_group(policy["expected_control_group"], unit)
    else:
        require(policy["target_unit"] == "" and policy["expected_control_group"] == "",
                "DISABLED_POLICY_TARGET")
    return policy


def _path_no_symlink(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    for item in (absolute, *absolute.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode), "PATH_SYMLINK")


def load_policy(path: Path = POLICY_PATH) -> tuple[dict, str]:
    _path_no_symlink(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise Hold("HOLD_MEMORY_RECLAIM_POLICY_FILE_UNAVAILABLE") from None
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0
                and info.st_nlink == 1 and (stat.S_IMODE(info.st_mode) & 0o077) == 0
                and info.st_size <= MAX_POLICY_BYTES, "POLICY_FILE_OWNER_OR_MODE")
        chunks = []
        total = 0
        while total <= MAX_POLICY_BYTES:
            part = os.read(fd, min(4096, MAX_POLICY_BYTES + 1 - total))
            if not part:
                break
            chunks.append(part)
            total += len(part)
        raw = b"".join(chunks)
        require(total <= MAX_POLICY_BYTES, "POLICY_FILE_SIZE")
        after = os.fstat(fd)
        try:
            named = path.lstat()
        except OSError:
            raise Hold("HOLD_MEMORY_RECLAIM_POLICY_FILE_CHANGED") from None
        require((info.st_dev, info.st_ino) == (after.st_dev, after.st_ino)
                == (named.st_dev, named.st_ino), "POLICY_FILE_CHANGED")
    finally:
        os.close(fd)
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise Hold("HOLD_MEMORY_RECLAIM_POLICY_JSON") from None
    return validate_policy(value), sha256(raw)


def _systemctl(args: list[str]) -> str:
    try:
        result = subprocess.run([SYSTEMCTL, *args], shell=False, check=False,
                                timeout=5, capture_output=True, text=True,
                                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    except (OSError, subprocess.TimeoutExpired):
        raise Hold("HOLD_MEMORY_RECLAIM_SYSTEMD_UNAVAILABLE") from None
    require(result.returncode == 0, "SYSTEMD_LOOKUP")
    return result.stdout.strip()


def resolve_target(unit: str, expected_group: str, cgroup_root: Path = CGROUP_ROOT) -> tuple[int, tuple[int, int, int]]:
    expected_group = safe_control_group(expected_group, unit)
    require(_systemctl(["is-active", "--quiet", unit]) == "", "UNIT_NOT_ACTIVE")
    observed_group = _systemctl(["show", "--no-pager", "--property=ControlGroup", "--value", unit])
    require(observed_group == expected_group, "CONTROL_GROUP_CHANGED")
    try:
        root_fd = os.open(cgroup_root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError:
        raise Hold("HOLD_MEMORY_RECLAIM_CGROUP_ROOT_UNAVAILABLE") from None
    current_fd: int | None = None
    returned = False
    try:
        root_info = os.fstat(root_fd)
        require(stat.S_ISDIR(root_info.st_mode), "CGROUP_ROOT_TYPE")
        current_fd = os.dup(root_fd)
        for component in expected_group.split("/")[1:]:
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
                               | os.O_NOFOLLOW, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        info = os.fstat(current_fd)
        require(info.st_uid == os.geteuid() and stat.S_ISDIR(info.st_mode), "LEAF_OWNER")
        identity = (info.st_dev, info.st_ino, info.st_uid)
        entries = list(os.scandir(current_fd))
        require(not any(entry.is_dir(follow_symlinks=False) for entry in entries),
                "NOT_A_LEAF")
        cgroup_type = _text(_read_fd_at(current_fd, "cgroup.type"), "CGROUP_TYPE")
        require(cgroup_type == "domain", "CGROUP_TYPE_UNSUPPORTED")
        # Require the interface before sampling or considering any action.
        try:
            reclaim_stat = os.stat("memory.reclaim", dir_fd=current_fd, follow_symlinks=False)
        except OSError:
            raise Hold("HOLD_MEMORY_RECLAIM_INTERFACE_MISSING") from None
        require(stat.S_ISREG(reclaim_stat.st_mode), "MEMORY_RECLAIM_MISSING")
        returned = True
        return current_fd, identity
    except OSError:
        raise Hold("HOLD_MEMORY_RECLAIM_LEAF_SCAN") from None
    finally:
        if current_fd is not None and not returned:
            os.close(current_fd)
        os.close(root_fd)


def process_start_ticks(proc_root: Path, pid: int) -> int:
    require(1 <= pid <= 2**31 - 1, "PID_RANGE")
    try:
        raw = (proc_root / str(pid) / "stat").read_bytes()
    except OSError:
        raise Hold("HOLD_MEMORY_RECLAIM_MEMBERSHIP_INCOMPLETE") from None
    end = raw.rfind(b")")
    require(end > 0, "PROC_STAT_FORMAT")
    fields = raw[end + 1:].split()
    require(len(fields) >= 20 and fields[0] not in (b"Z", b"X"), "PROC_STAT_EXITED")
    return _uint(fields[19].decode("ascii", "strict"), "PROC_START_TICKS")


def membership(directory_fd: int, proc_root: Path = PROC_ROOT) -> tuple[list[tuple[int, int]], str]:
    raw = _text(_read_fd_at(directory_fd, "cgroup.procs"), "CGROUP_PROCS")
    pids: list[int] = []
    for line in raw.splitlines():
        pids.append(_uint(line, "CGROUP_PROCS_FORMAT"))
        require(len(pids) <= MAX_PROCESSES, "CGROUP_PROCESS_LIMIT")
    require(bool(pids) and len(pids) == len(set(pids)), "CGROUP_MEMBERSHIP_EMPTY_OR_DUPLICATE")
    identities = sorted((pid, process_start_ticks(proc_root, pid)) for pid in pids)
    fingerprint = sha256(json.dumps(identities, separators=(",", ":")).encode())
    return identities, fingerprint


def sample_cgroup(directory_fd: int, now: float | None = None) -> dict:
    start = time.monotonic_ns()
    current_before = _uint(_text(_read_fd_at(directory_fd, "memory.current"), "CURRENT"), "CURRENT")
    max_raw = _text(_read_fd_at(directory_fd, "memory.max"), "MAX")
    high_raw = _text(_read_fd_at(directory_fd, "memory.high"), "HIGH")
    require(max_raw.isdecimal() and (high_raw == "max" or high_raw.isdecimal()),
            "LIMIT_FORMAT")
    limit = _uint(max_raw, "MAX")
    high = None if high_raw == "max" else _uint(high_raw, "HIGH")
    require(limit > 0 and (high is None or high > 0), "LIMIT_ZERO")
    stats = parse_kv(_text(_read_fd_at(directory_fd, "memory.stat"), "MEMORY_STAT"), "MEMORY_STAT")
    events = parse_kv(_text(_read_fd_at(directory_fd, "memory.events"), "MEMORY_EVENTS"), "MEMORY_EVENTS")
    require(all(key in events for key in ("high", "oom", "oom_kill")), "EVENTS_REQUIRED")
    pressure = parse_pressure(_text(_read_fd_at(directory_fd, "memory.pressure"), "PRESSURE"))
    current_after = _uint(_text(_read_fd_at(directory_fd, "memory.current"), "CURRENT"), "CURRENT")
    finish = time.monotonic_ns()
    require(finish - start <= 2_000_000_000, "SAMPLE_TOO_SLOW")
    require(abs(current_after - current_before) <= max(64 * MIB, current_before // 20),
            "SAMPLE_UNSTABLE")
    estimate = clean_file_estimate(stats)
    return {
        "sampled_at_unix": time.time() if now is None else now,
        "sample_duration_ns": finish - start,
        "memory_current_bytes": current_after,
        "memory_max_bytes": limit,
        "memory_high_bytes": high,
        "memory_stat": {key: stats[key] for key in (
            "anon", "file", "shmem", "inactive_file", "active_file",
            "file_mapped", "file_dirty", "file_writeback") if key in stats},
        "clean_inactive_file_estimate_bytes": estimate,
        "events": {key: events[key] for key in ("high", "oom", "oom_kill")},
        "psi_avg10": pressure,
    }


def _secure_state_directory(path: Path) -> None:
    _path_no_symlink(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o700, "STATE_DIRECTORY_OWNER_OR_MODE")


def _state_lock(path: Path) -> int:
    lock = path / "controller.lock"
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        named = lock.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
                and (info.st_dev, info.st_ino) == (named.st_dev, named.st_ino), "STATE_LOCK_IDENTITY")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Hold("HOLD_MEMORY_RECLAIM_BUSY") from None
        again = lock.lstat()
        require((info.st_dev, info.st_ino) == (again.st_dev, again.st_ino),
                "STATE_LOCK_REPLACED")
        return fd
    except BaseException:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)
        raise


def _load_state(path: Path) -> dict:
    file = path / "state.json"
    try:
        info = file.lstat()
    except FileNotFoundError:
        return {"schema": SCHEMA, "history": []}
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
            and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600
            and info.st_size <= MAX_STATE_BYTES, "STATE_FILE_OWNER_OR_MODE")
    try:
        fd = os.open(file, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise Hold("HOLD_MEMORY_RECLAIM_STATE_FILE_CHANGED") from None
    try:
        opened = os.fstat(fd)
        require((info.st_dev, info.st_ino) == (opened.st_dev, opened.st_ino)
                and stat.S_ISREG(opened.st_mode) and opened.st_uid == os.geteuid()
                and opened.st_nlink == 1 and stat.S_IMODE(opened.st_mode) == 0o600,
                "STATE_FILE_CHANGED")
        chunks = []
        total = 0
        while total <= MAX_STATE_BYTES:
            part = os.read(fd, min(65536, MAX_STATE_BYTES + 1 - total))
            if not part:
                break
            chunks.append(part)
            total += len(part)
        require(total <= MAX_STATE_BYTES, "STATE_FILE_SIZE")
        named = file.lstat()
        final = os.fstat(fd)
        require((info.st_dev, info.st_ino) == (named.st_dev, named.st_ino)
                == (final.st_dev, final.st_ino), "STATE_FILE_CHANGED")
        raw = b"".join(chunks)
    finally:
        os.close(fd)
    try:
        state = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise Hold("HOLD_MEMORY_RECLAIM_STATE_JSON") from None
    require(isinstance(state, dict) and state.get("schema") == SCHEMA
            and isinstance(state.get("history", []), list), "STATE_SCHEMA")
    return state


def _write_state(path: Path, state: dict) -> None:
    state = copy.deepcopy(state)
    state["schema"] = SCHEMA
    state["history"] = state.get("history", [])[-MAX_HISTORY:]
    raw = (json.dumps(state, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    require(len(raw) <= MAX_STATE_BYTES, "STATE_SIZE")
    target = path / "state.json"
    try:
        info = target.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600,
                "STATE_FILE_OWNER_OR_MODE")
    except FileNotFoundError:
        pass
    temp = path / (".state-" + secrets.token_hex(8) + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, target)
        directory_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temp.unlink(missing_ok=True)


def _record(state: dict, event: dict) -> dict:
    state = copy.deepcopy(state)
    event = dict(event)
    event.setdefault("recorded_at", dt.datetime.now(dt.timezone.utc).isoformat())
    state.setdefault("history", []).append(event)
    state["history"] = state["history"][-MAX_HISTORY:]
    state["latest"] = event
    return state


def _stop_present() -> bool:
    return any(os.path.lexists(path) for path in STOP_MARKERS)


def _target_path_identity(cgroup_root: Path, control_group: str) -> tuple[int, int, int]:
    path = cgroup_root.joinpath(*control_group.split("/")[1:])
    try:
        info = os.stat(path, follow_symlinks=False)
    except OSError:
        raise Hold("HOLD_MEMORY_RECLAIM_LEAF_PATH_UNAVAILABLE") from None
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid(), "LEAF_PATH_IDENTITY")
    return info.st_dev, info.st_ino, info.st_uid


def _append_event(state: dict, path: Path, event: dict) -> dict:
    updated = _record(state, event)
    _write_state(path, updated)
    return updated["latest"]


def _record_policy_hold(state_dir: Path, code: str, source_pin: str | None) -> dict:
    """Persist a sanitized policy-load HOLD without performing a cgroup lookup."""
    _secure_state_directory(state_dir)
    lock_fd = _state_lock(state_dir)
    try:
        state = _load_state(state_dir)
        event = {"kind": "HOLD", "code": code, "source_sha256": source_pin,
                 "policy_sha256": None}
        return _append_event(state, state_dir, event)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def _recent_requested(state: dict, now: float) -> int:
    total = 0
    requests = state.get("daily_requests", [])
    require(isinstance(requests, list) and len(requests) <= MAX_DAILY_REQUESTS,
            "DAILY_BUDGET_STATE")
    for row in requests:
        require(isinstance(row, list) and len(row) == 2
                and type(row[0]) in (int, float) and type(row[1]) is int
                and math.isfinite(row[0]) and row[1] >= 0, "DAILY_BUDGET_STATE")
        if 0 <= now - row[0] < 86400:
            total += row[1]
    return total


def _event_delta(current: dict, previous: dict | None) -> dict | None:
    if previous is None:
        return None
    result = {}
    for name in ("high", "oom", "oom_kill"):
        old = previous.get(name)
        new = current.get(name)
        require(type(old) is int and type(new) is int and 0 <= old <= new,
                "EVENT_COUNTER_RESET")
        result[name] = new - old
    return result


def _source_sha() -> str:
    path = Path(__file__)
    _path_no_symlink(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        chunks = []
        while True:
            part = os.read(fd, 65536)
            if not part:
                break
            chunks.append(part)
        return sha256(b"".join(chunks))
    finally:
        os.close(fd)


def write_reclaim(directory_fd: int, requested_bytes: int) -> None:
    value = f"{requested_bytes} swappiness=0\n".encode("ascii")
    fd = os.open("memory.reclaim", os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                 dir_fd=directory_fd)
    try:
        written = os.write(fd, value)
        require(written == len(value), "RECLAIM_WRITE_SHORT")
    finally:
        os.close(fd)


def run_cycle(policy: dict, state_dir: Path = STATE_ROOT, *,
              cgroup_root: Path = CGROUP_ROOT, proc_root: Path = PROC_ROOT,
              source_sha: str | None = None, policy_sha: str | None = None,
              now: float | None = None, resolve=resolve_target,
              sample=sample_cgroup, member=membership, writer=write_reclaim,
              stop_check=_stop_present) -> dict:
    policy = validate_policy(policy)
    _secure_state_directory(state_dir)
    lock_fd = _state_lock(state_dir)
    try:
        stamp = time.time() if now is None else now
        source_pin = source_sha or _source_sha()
        policy_pin = policy_sha or sha256(json.dumps(policy, sort_keys=True,
            separators=(",", ":")).encode())
        state = _load_state(state_dir)
        if state.get("pending"):
            raise Hold("HOLD_MEMORY_RECLAIM_UNRESOLVED_ACTION")
        if not policy["enabled"]:
            event = {"kind": "DISABLED", "action": "NONE", "source_sha256": source_pin,
                     "policy_sha256": policy_pin}
            return _append_event(state, state_dir, event)
        if stop_check():
            raise Hold("HOLD_MEMORY_RECLAIM_STOP_MARKER")

        unit = policy["target_unit"]
        group = policy["expected_control_group"]
        leaf_fd, leaf_id = resolve(unit, group, cgroup_root)
        try:
            members_before, members_hash = member(leaf_fd, proc_root)
            before = sample(leaf_fd)
            require(not stop_check(), "STOP_MARKER")
            path_id_before = _target_path_identity(cgroup_root, group)
            require(path_id_before == leaf_id, "LEAF_REPLACED")
            current = before["memory_current_bytes"]
            threshold_base = min(before["memory_max_bytes"],
                                 before["memory_high_bytes"] or before["memory_max_bytes"])
            high_bytes = int(threshold_base * policy["high_watermark_fraction"])
            low_bytes = int(threshold_base * policy["low_watermark_fraction"])
            previous_id = state.get("target_identity")
            previous_events = state.get("last_events")
            if previous_id is not None and previous_id != list(leaf_id):
                event = {"kind": "HOLD", "code": "HOLD_MEMORY_RECLAIM_TARGET_IDENTITY_CHANGED",
                         "target_unit": unit, "control_group": group,
                         "source_sha256": source_pin, "policy_sha256": policy_pin}
                _append_event(state, state_dir, event)
                updated = _load_state(state_dir)
                updated["target_identity"] = list(leaf_id)
                updated["last_events"] = before["events"]
                _write_state(state_dir, updated)
                return event
            if previous_events is None:
                event = {"kind": "BASELINE", "action": "NO_RECLAIM", "target_unit": unit,
                         "control_group": group, "target_identity": list(leaf_id),
                         "membership_count": len(members_before), "membership_sha256": members_hash,
                         "sample": before, "source_sha256": source_pin, "policy_sha256": policy_pin}
                updated = _record(state, event)
                updated["target_identity"] = list(leaf_id)
                updated["last_events"] = before["events"]
                _write_state(state_dir, updated)
                return event
            deltas = _event_delta(before["events"], previous_events)
            state["last_events"] = before["events"]
            state["target_identity"] = list(leaf_id)
            if deltas["oom"] or deltas["oom_kill"]:
                raise Hold("HOLD_MEMORY_RECLAIM_RECENT_OOM")
            if current < high_bytes:
                event = {"kind": "OBSERVE", "action": "BELOW_THRESHOLD", "target_unit": unit,
                         "control_group": group, "target_identity": list(leaf_id),
                         "current_bytes": current, "high_watermark_bytes": high_bytes,
                         "low_watermark_bytes": low_bytes, "sample": before,
                         "source_sha256": source_pin, "policy_sha256": policy_pin}
                return _append_event(state, state_dir, event)
            last_action = state.get("last_action_unix")
            if last_action is not None:
                require(type(last_action) in (int, float) and stamp >= last_action,
                        "HOLD_CLOCK_MOVED_BACKWARD")
                if stamp - last_action < policy["cooldown_seconds"]:
                    event = {"kind": "OBSERVE", "action": "COOLDOWN", "target_unit": unit,
                             "control_group": group, "current_bytes": current,
                             "high_watermark_bytes": high_bytes, "source_sha256": source_pin,
                             "policy_sha256": policy_pin}
                    return _append_event(state, state_dir, event)
            estimated = before["clean_inactive_file_estimate_bytes"]
            requested = min(policy["max_reclaim_bytes"], estimated,
                            max(0, current - low_bytes),
                            max(0, policy["daily_budget_bytes"] - _recent_requested(state, stamp)))
            requested = requested // PAGE * PAGE
            if requested < policy["minimum_reclaim_bytes"]:
                event = {"kind": "OBSERVE", "action": "HOLD_NO_SAFE_CLEAN_CACHE",
                         "target_unit": unit, "control_group": group,
                         "target_identity": list(leaf_id), "current_bytes": current,
                         "high_watermark_bytes": high_bytes, "clean_inactive_file_estimate_bytes": estimated,
                         "shmem_protected_bytes": before["memory_stat"]["shmem"],
                         "mapped_file_protected_bytes": before["memory_stat"]["file_mapped"],
                         "source_sha256": source_pin, "policy_sha256": policy_pin}
                return _append_event(state, state_dir, event)

            # Revalidate exact service/cgroup and membership immediately before
            # the durable intent, then re-open the service identity for the write.
            members_check, members_hash_check = member(leaf_fd, proc_root)
            require(members_before == members_check and members_hash == members_hash_check,
                    "MEMBERSHIP_CHANGED")
            require(not stop_check(), "STOP_MARKER")
            require(_target_path_identity(cgroup_root, group) == leaf_id,
                    "LEAF_REPLACED")
            fresh_fd, fresh_id = resolve(unit, group, cgroup_root)
            try:
                require(fresh_id == leaf_id, "LEAF_REPLACED")
                members_final, members_hash_final = member(fresh_fd, proc_root)
                require(members_final == members_before and members_hash_final == members_hash,
                        "MEMBERSHIP_CHANGED")
                final_before = sample(fresh_fd)
                require(final_before["memory_current_bytes"] >= high_bytes,
                        "THRESHOLD_CLEARED")
                require(final_before["clean_inactive_file_estimate_bytes"] >=
                        policy["minimum_reclaim_bytes"], "CLEAN_CACHE_CHANGED")
                requested = min(requested, final_before["clean_inactive_file_estimate_bytes"],
                                max(0, final_before["memory_current_bytes"] - low_bytes))
                requested = requested // PAGE * PAGE
                require(requested >= policy["minimum_reclaim_bytes"], "REQUEST_TOO_SMALL")
                # Close the sample-to-write gap against service restarts,
                # changing cgroup membership, and maintenance STOP markers.
                require(_systemctl(["is-active", "--quiet", unit]) == "", "UNIT_NOT_ACTIVE")
                require(_systemctl(["show", "--no-pager", "--property=ControlGroup",
                                    "--value", unit]) == group, "CONTROL_GROUP_CHANGED")
                latest_members, latest_members_hash = member(fresh_fd, proc_root)
                require(latest_members == members_before
                        and latest_members_hash == members_hash, "MEMBERSHIP_CHANGED")
                require(_target_path_identity(cgroup_root, group) == fresh_id,
                        "LEAF_REPLACED")
                require(not stop_check(), "STOP_MARKER")
                pending_id = secrets.token_hex(16)
                pending = {"request_id": pending_id, "target_unit": unit,
                           "control_group": group, "target_identity": list(fresh_id),
                           "requested_bytes": requested, "unix_time": stamp,
                           "before": final_before, "membership_sha256": members_hash}
                state["pending"] = pending
                state["last_action_unix"] = stamp
                state = _record(state, {"kind": "RECLAIM_INTENT", **pending,
                                        "source_sha256": source_pin,
                                        "policy_sha256": policy_pin})
                _write_state(state_dir, state)
                try:
                    writer(fresh_fd, requested)
                except OSError as exc:
                    # A cgroupfs write can fail after partial reclaim. Keep the
                    # durable pending record; the next cycle must not retry.
                    event = {"kind": "HOLD", "code": "HOLD_MEMORY_RECLAIM_WRITE_AMBIGUOUS",
                             "request_id": pending_id, "errno": int(exc.errno or 0),
                             "requested_bytes": requested, "target_unit": unit,
                             "control_group": group, "source_sha256": source_pin,
                             "policy_sha256": policy_pin}
                    state = _record(state, event)
                    _write_state(state_dir, state)
                    return event
                after_fd, after_id = resolve(unit, group, cgroup_root)
                try:
                    require(after_id == fresh_id, "LEAF_CHANGED_AFTER_RECLAIM")
                    after = sample(after_fd)
                finally:
                    os.close(after_fd)
                observed_change = final_before["memory_current_bytes"] - after["memory_current_bytes"]
                event = {"kind": "RECLAIM_ATTEMPT", "action": "MEMORY_RECLAIM_SWAPPINESS_0",
                         "request_id": pending_id, "target_unit": unit,
                         "control_group": group, "target_identity": list(fresh_id),
                         "requested_bytes": requested, "unix_time": stamp,
                         "kernel_result_scope": "REQUESTED_BYTES_ONLY_KERNEL_MAY_OVER_OR_UNDER_RECLAIM",
                         "observed_memory_change_bytes": observed_change,
                         "before": final_before, "after": after,
                         "membership_count": len(members_before),
                         "membership_sha256": members_hash,
                         "source_sha256": source_pin, "policy_sha256": policy_pin}
                state["pending"] = None
                state["last_action_unix"] = stamp
                requests = state.setdefault("daily_requests", [])
                require(isinstance(requests, list) and len(requests) < MAX_DAILY_REQUESTS,
                        "DAILY_BUDGET_STATE")
                requests.append([stamp, requested])
                state["daily_requests"] = [row for row in requests
                                            if 0 <= stamp - row[0] < 86400]
                updated = _record(state, event)
                _write_state(state_dir, updated)
                return event
            finally:
                os.close(fresh_fd)
        finally:
            os.close(leaf_fd)
    except Hold as exc:
        code = str(exc)
        code = code if re.fullmatch(r"HOLD_MEMORY_RECLAIM_[A-Z0-9_]{1,100}", code) else "HOLD_MEMORY_RECLAIM_INTERNAL"
        event = {"kind": "HOLD", "code": code,
                 "target_unit": policy.get("target_unit") or None,
                 "control_group": policy.get("expected_control_group") or None,
                 "source_sha256": locals().get("source_pin"),
                 "policy_sha256": locals().get("policy_pin")}
        # A pending transaction is deliberately retained for human review.
        state = _load_state(state_dir)
        return _append_event(state, state_dir, event)
    except Exception:
        event = {"kind": "HOLD", "code": "HOLD_MEMORY_RECLAIM_INTERNAL",
                 "target_unit": policy.get("target_unit") or None,
                 "control_group": policy.get("expected_control_group") or None,
                 "source_sha256": locals().get("source_pin"),
                 "policy_sha256": locals().get("policy_pin")}
        state = _load_state(state_dir)
        return _append_event(state, state_dir, event)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default=str(POLICY_PATH))
    parser.add_argument("--state", default=str(STATE_ROOT))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    source_pin = _source_sha()
    while True:
        try:
            policy, policy_sha = load_policy(Path(args.policy))
        except Hold as exc:
            code = str(exc)
            code = code if re.fullmatch(r"HOLD_MEMORY_RECLAIM_[A-Z0-9_]{1,100}", code) else "HOLD_MEMORY_RECLAIM_POLICY_INVALID"
            try:
                event = _record_policy_hold(Path(args.state), code, source_pin)
            except Exception:
                event = {"kind": "HOLD", "code": "HOLD_MEMORY_RECLAIM_POLICY_RECEIPT_FAILED"}
            print(json.dumps({"event": SCHEMA, "result": event},
                             sort_keys=True, separators=(",", ":")), flush=True)
            if args.once:
                return 2
            time.sleep(60)
            continue
        try:
            event = run_cycle(policy, Path(args.state), source_sha=source_pin,
                              policy_sha=policy_sha)
        except Exception:
            try:
                event = _record_policy_hold(Path(args.state),
                    "HOLD_MEMORY_RECLAIM_INTERNAL", source_pin)
            except Exception:
                event = {"kind": "HOLD", "code": "HOLD_MEMORY_RECLAIM_RECEIPT_FAILED"}
        print(json.dumps({"event": SCHEMA, "result": event},
                         sort_keys=True, separators=(",", ":"), allow_nan=False), flush=True)
        if args.once:
            return 0 if event.get("kind") != "HOLD" else 2
        time.sleep(policy["poll_seconds"])


if __name__ == "__main__":
    raise SystemExit(main())
