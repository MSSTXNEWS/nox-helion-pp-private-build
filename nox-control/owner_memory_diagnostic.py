"""Bounded, read-only NOX memory diagnostic; never authorizes cleanup."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

SCHEMA = "NOX_OWNER_MEMORY_DIAGNOSTIC_V1"
EXPECTED_INSTANCE_ID = 60509551
LEASE_SCHEMA = "NOX_NATIVE_SUBAGENT_LEASE_READONLY_V1"
LEASE_STATE = "VERIFIED_OWNER_FLOCK_READONLY"
DEFAULT_SERVICES = (
    "nox-chat-8081",
    "nox-dispatcher-t855u",
    "nox-ds41-8098",
    "nox-proxy",
    "nox-web29-18775",
)
MAX_CGROUP_FILE = 65536
MAX_PROC_FILE = 65536
MAX_PROC_COUNT = 5
MAX_FDS_PER_PROCESS = 512
MAX_FD_TARGET = 4096
MAX_LEASE_AGE = 5.0
MEMORY_CATEGORIES = (
    "anon", "file", "kernel", "kernel_stack", "pagetables", "sock", "shmem",
    "file_mapped", "file_dirty", "file_writeback", "inactive_anon",
    "active_anon", "inactive_file", "active_file", "unevictable",
    "slab_reclaimable", "slab_unreclaimable", "slab",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SERVICE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")


class DiagnosticHold(Exception):
    def __init__(self, code: str):
        self.code = code


def _hold(code: str):
    return {
        "schema": SCHEMA,
        "state": "HOLD",
        "hold_reason": code,
        "verified": False,
        "lease_scope": "FLOCK_ONLY_NOT_MAINTENANCE_OR_CAS",
        "cleanup_authorized": False,
        "mutation_authorized": False,
    }


def _read_bounded(path: Path, limit: int) -> bytes:
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise DiagnosticHold("HOLD_UNSAFE_FILE")
        if before.st_size > limit:
            raise DiagnosticHold("HOLD_FILE_SIZE_BOUND")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        try:
            opened = os.fstat(fd)
            if (not stat.S_ISREG(opened.st_mode) or opened.st_dev != before.st_dev
                    or opened.st_ino != before.st_ino or opened.st_size > limit):
                raise DiagnosticHold("HOLD_FILE_IDENTITY")
            chunks = []
            total = 0
            while total <= limit:
                part = os.read(fd, min(8192, limit + 1 - total))
                if not part:
                    break
                chunks.append(part)
                total += len(part)
            after = os.fstat(fd)
            if total > limit or (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
                    after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise DiagnosticHold("HOLD_FILE_CHANGED")
            return b"".join(chunks)
        finally:
            os.close(fd)
    except DiagnosticHold:
        raise
    except (OSError, ValueError):
        raise DiagnosticHold("HOLD_EVIDENCE_UNAVAILABLE")


def _read_stat_starttime(proc_root: Path, pid: int) -> int:
    raw = _read_bounded(proc_root / str(pid) / "stat", MAX_PROC_FILE).decode("ascii", "strict")
    prefix, tail = raw.rsplit(") ", 1)
    if not prefix.startswith(str(pid) + " ("):
        raise DiagnosticHold("HOLD_PID_IDENTITY")
    fields = tail.split()
    if len(fields) <= 19 or not fields[19].isdigit():
        raise DiagnosticHold("HOLD_PID_STARTTIME")
    return int(fields[19])


def _validate_lease(receipt, observed_at, now):
    if not isinstance(receipt, dict):
        raise DiagnosticHold("HOLD_LEASE_UNKNOWN")
    if (receipt.get("schema") != LEASE_SCHEMA or receipt.get("state") != LEASE_STATE
            or receipt.get("verified") is not True or receipt.get("lease_kind") != "FLOCK"
            or receipt.get("owner_authorized") is not True
            or receipt.get("owner_instance_id") != EXPECTED_INSTANCE_ID):
        raise DiagnosticHold("HOLD_LEASE_UNKNOWN")
    pid = receipt.get("holder_pid")
    ticks = receipt.get("holder_start_ticks")
    if (type(pid) is not int or pid < 2 or type(ticks) is not int or ticks <= 0
            or receipt.get("supervisor_pid") != pid
            or receipt.get("supervisor_start_ticks") != ticks
            or type(receipt.get("lock_inode")) is not int or receipt["lock_inode"] <= 0
            or type(receipt.get("lock_device_major")) is not int
            or type(receipt.get("lock_device_minor")) is not int
            or not SHA256_RE.fullmatch(str(receipt.get("owner_config_sha256", "")))):
        raise DiagnosticHold("HOLD_LEASE_IDENTITY")
    if (type(observed_at) not in (int, float) or type(now) not in (int, float)
            or observed_at > now + 1 or now - observed_at > MAX_LEASE_AGE):
        raise DiagnosticHold("HOLD_LEASE_STALE")
    return pid, ticks


def _parse_supervisor(text: str, rc: int, allowlist):
    if type(rc) is not int or rc != 0 or not isinstance(text, str) or len(text) > 65536:
        raise DiagnosticHold("HOLD_SUPERVISOR_UNKNOWN")
    wanted = set(allowlist)
    rows = {}
    for line in text.splitlines():
        fields = line.split()
        if not fields or fields[0] not in wanted:
            continue
        if fields[0] in rows or len(fields) < 4 or fields[1] != "RUNNING" or fields[2] != "pid":
            raise DiagnosticHold("HOLD_SUPERVISOR_AMBIGUOUS")
        if not fields[3].rstrip(',').isdigit():
            raise DiagnosticHold("HOLD_SUPERVISOR_PID")
        rows[fields[0]] = int(fields[3].rstrip(','))
    if set(rows) != wanted:
        raise DiagnosticHold("HOLD_SUPERVISOR_COVERAGE")
    if len(set(rows.values())) != len(rows):
        raise DiagnosticHold("HOLD_SUPERVISOR_DUPLICATE_PID")
    return rows


def _cgroup_snapshot(root: Path):
    if stat.S_ISLNK(root.lstat().st_mode) or not root.is_dir():
        raise DiagnosticHold("HOLD_CGROUP_ROOT")
    current_raw = _read_bounded(root / "memory.current", 128).decode("ascii", "strict").strip()
    max_raw = _read_bounded(root / "memory.max", 128).decode("ascii", "strict").strip()
    if not current_raw.isdigit() or not max_raw.isdigit():
        raise DiagnosticHold("HOLD_CGROUP_COUNTER")
    raw = _read_bounded(root / "memory.stat", MAX_CGROUP_FILE).decode("ascii", "strict")
    counters = {}
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) != 2 or not re.fullmatch(r"[a-z_]{1,64}", fields[0]) or not fields[1].isdigit():
            raise DiagnosticHold("HOLD_MEMORY_STAT_SCHEMA")
        if fields[0] in counters:
            raise DiagnosticHold("HOLD_MEMORY_STAT_DUPLICATE")
        counters[fields[0]] = int(fields[1])
    if any(key not in counters for key in MEMORY_CATEGORIES):
        raise DiagnosticHold("HOLD_MEMORY_CATEGORY_MISSING")
    return {
        "current": int(current_raw),
        "max": int(max_raw),
        "categories": {key: counters[key] for key in MEMORY_CATEGORIES},
    }


def _parse_kib(text: str, key: str):
    matches = re.findall(r"^" + re.escape(key) + r":\s*([0-9]+)\s+kB\s*$", text, re.M)
    if len(matches) != 1:
        raise DiagnosticHold("HOLD_MISSING_PSS" if key == "Pss" else "HOLD_MISSING_RSS")
    return int(matches[0]) * 1024


def _artifact_identities(proc_root: Path, pid: int, start_ticks: int, *, fd_reader=None):
    fd_dir = proc_root / str(pid) / "fd"
    try:
        entries = sorted(fd_dir.iterdir(), key=lambda p: p.name)
    except OSError:
        raise DiagnosticHold("HOLD_FD_INVENTORY")
    if len(entries) > MAX_FDS_PER_PROCESS:
        raise DiagnosticHold("HOLD_FD_BOUND")
    rows = []
    for fd in entries:
        if not fd.name.isdigit():
            raise DiagnosticHold("HOLD_FD_SCHEMA")
        try:
            target = fd_reader(fd) if fd_reader else os.readlink(fd)
        except OSError:
            raise DiagnosticHold("HOLD_FD_IDENTITY")
        if not isinstance(target, str) or len(target) > MAX_FD_TARGET:
            raise DiagnosticHold("HOLD_FD_TARGET_BOUND")
        lower = target.lower()
        basename = lower.rsplit("/", 1)[-1].split(" (deleted)", 1)[0]
        if target.startswith("/memfd:") or target.startswith("memfd:"):
            kind = "MEMFD"
        elif basename.endswith((".gguf", ".safetensors", ".sft", ".bin", ".pt", ".pth", ".ckpt", ".checkpoint")):
            kind = "WEIGHT_OR_CHECKPOINT"
        else:
            kind = "FILE_IDENTITY"
        # This is a digest of the descriptor target identity only, never file bytes.
        token = hashlib.sha256((str(pid) + ":" + str(start_ticks) + ":" + target).encode("utf-8", "surrogateescape")).hexdigest()
        rows.append({"kind": kind, "identity_sha256": token})
    return rows


def _process_memory(proc_root: Path, service: str, pid: int, expected_start=None, fd_reader=None):
    start_before = _read_stat_starttime(proc_root, pid)
    if expected_start is not None and start_before != expected_start:
        raise DiagnosticHold("HOLD_PID_STARTTIME_MISMATCH")
    status = _read_bounded(proc_root / str(pid) / "status", MAX_PROC_FILE).decode("ascii", "strict")
    smaps = _read_bounded(proc_root / str(pid) / "smaps_rollup", MAX_PROC_FILE).decode("ascii", "strict")
    rss = _parse_kib(status, "VmRSS")
    pss = _parse_kib(smaps, "Pss")
    artifacts = _artifact_identities(proc_root, pid, start_before, fd_reader=fd_reader)
    start_after = _read_stat_starttime(proc_root, pid)
    if start_before != start_after:
        raise DiagnosticHold("HOLD_PROCESS_CHURN")
    return {
        "service": service,
        "pid": pid,
        "start_ticks": start_after,
        "rss_bytes": rss,
        "pss_bytes": pss,
        "artifact_identities": artifacts,
    }


def collect_owner_memory_diagnostic(*, cgroup_root, proc_root, supervisor_status,
        supervisor_rc, supervisor_status_after, supervisor_rc_after, lease_receipt,
        lease_observed_at, now_unix=None, service_allowlist=DEFAULT_SERVICES,
        fd_reader=None):
    """Collect an offline-injectable snapshot; verified means diagnostic completeness only."""
    now = time.time() if now_unix is None else now_unix
    try:
        if not service_allowlist or len(service_allowlist) > MAX_PROC_COUNT:
            raise DiagnosticHold("HOLD_ALLOWLIST_BOUND")
        if len(set(service_allowlist)) != len(service_allowlist) or any(
                not isinstance(s,str) or not SERVICE_RE.fullmatch(s) for s in service_allowlist):
            raise DiagnosticHold("HOLD_ALLOWLIST_SCHEMA")
        if "nox-dispatcher-t855u" not in service_allowlist:
            raise DiagnosticHold("HOLD_ALLOWLIST_LEASE_SERVICE")
        lease_pid, lease_ticks = _validate_lease(lease_receipt, lease_observed_at, now)
        before_services = _parse_supervisor(supervisor_status, supervisor_rc, service_allowlist)
        after_services = _parse_supervisor(supervisor_status_after, supervisor_rc_after, service_allowlist)
        if before_services != after_services:
            raise DiagnosticHold("HOLD_SUPERVISOR_CHURN")
        dispatcher = "nox-dispatcher-t855u"
        if dispatcher in before_services and before_services[dispatcher] != lease_pid:
            raise DiagnosticHold("HOLD_LEASE_SUPERVISOR_MISMATCH")
        cgroup_before = _cgroup_snapshot(Path(cgroup_root))
        processes = []
        for service in service_allowlist:
            pid = before_services[service]
            expected_start = lease_ticks if pid == lease_pid else None
            processes.append(_process_memory(Path(proc_root), service, pid,
                                             expected_start=expected_start, fd_reader=fd_reader))
        cgroup_after = _cgroup_snapshot(Path(cgroup_root))
        if cgroup_before != cgroup_after:
            raise DiagnosticHold("HOLD_COUNTER_DRIFT")
        # Recheck every PID after all processes and cgroup counters were sampled.
        for row in processes:
            if _read_stat_starttime(Path(proc_root), row["pid"]) != row["start_ticks"]:
                raise DiagnosticHold("HOLD_PROCESS_CHURN")
        return {
            "schema": SCHEMA,
            "state": "READ_ONLY_DIAGNOSTIC_COMPLETE",
            "verified": True,
            "diagnostic_only": True,
            "lease_scope": "FLOCK_ONLY_NOT_MAINTENANCE_OR_CAS",
            "lease_owner_pid": lease_pid,
            "lease_owner_start_ticks": lease_ticks,
            "owner_instance_id": EXPECTED_INSTANCE_ID,
            "cgroup_memory_current_bytes": cgroup_after["current"],
            "cgroup_memory_max_bytes": cgroup_after["max"],
            "cgroup_memory_categories_bytes": cgroup_after["categories"],
            "processes": processes,
            "cleanup_authorized": False,
            "mutation_authorized": False,
            "safe_to_clear_categories": [],
            "artifact_identity_scope": "SHA256_OF_FD_TARGET_IDENTITY_ONLY_NO_FILE_CONTENT_HASH",
        }
    except DiagnosticHold as exc:
        return _hold(exc.code)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, IndexError):
        return _hold("HOLD_EVIDENCE_UNAVAILABLE")


def read_only_owner_memory_diagnostic():
    """Live read-only entrypoint; never mutates host. Not called by this module."""
    import owner_native_inspect
    root = Path("/root/nox")
    proc_root = Path("/proc")
    cgroup_root = Path("/sys/fs/cgroup")
    lease = owner_native_inspect.native_subagents_writer_lease_readback(root=root, proc_root=proc_root)
    observed_at = time.time()
    if lease.get("verified") is not True:
        return _hold("HOLD_LEASE_UNKNOWN")
    cmd = ["supervisorctl", "status", *DEFAULT_SERVICES]
    try:
        first = subprocess.run(cmd, shell=False, capture_output=True, text=True, timeout=8, check=False)
        second = subprocess.run(cmd, shell=False, capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return _hold("HOLD_SUPERVISOR_UNKNOWN")
    return collect_owner_memory_diagnostic(
        cgroup_root=cgroup_root, proc_root=proc_root,
        supervisor_status=first.stdout, supervisor_rc=first.returncode,
        supervisor_status_after=second.stdout, supervisor_rc_after=second.returncode,
        lease_receipt=lease, lease_observed_at=observed_at, now_unix=time.time(),
    )
