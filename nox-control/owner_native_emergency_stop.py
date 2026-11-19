#!/usr/bin/env python3
"""Owner-only two-step emergency memory relief for one attested NOX model.

This source is inert until called by the pinned owner-maintenance workflow.
It stops only the exact Supervisor model service first. It considers a
SIGTERM for the exact memfd holder only if fresh cgroup headroom remains below
2 GiB after the model service has stopped. It never clears owner markers or
restarts services.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import time

ROOT = Path("/root/nox")
STOP = ROOT / "STOP"
MAINTENANCE = ROOT / "state/OWNER_MAINTENANCE.flag"
LOCK = ROOT / "state/owner_maintenance.lock"
CGROUP_ROOT = Path("/sys/fs/cgroup")
SUPERVISOR_SERVICE = "nox-ds41-8098"
MODEL_PID = 3266857
MODEL_START_TICKS = 172046662
HOLDER_PID = 498569
HOLDER_START_TICKS = 168416044
HOLDER_SCRIPT = "/root/nox/engram_ram/engram_memfd_holder.py"
MEMFD_INODE = 131095
MEMFD_SIZE = 75_266_239_716
MIN_HEADROOM = 2_147_483_648
MAX_STAT_BYTES = 8_192
MAX_MAPS_BYTES = 2 * 1024 * 1024
MAX_TOTAL_MAPS_BYTES = 64 * 1024 * 1024
MAX_PROC_SCAN = 4_096
SHA40 = re.compile(r"^[0-9a-f]{40}$")
STATUS_LINE = re.compile(r"^([A-Za-z0-9_.:-]+)\s+(RUNNING|STOPPED|EXITED)(?:\s+pid\s+([0-9]+))?(?:,.*)?$")

PHASE = {
    "owner_lock": False,
    "stop_marker": False,
    "maintenance_marker": False,
    "model_stop_requested": False,
    "model_stopped": False,
    "holder_term_sent": False,
}
MARKERS = {}


def fail(label: str) -> None:
    raise RuntimeError("HOLD_EMERGENCY_STOP_" + label)


def emit(payload: dict) -> None:
    print("NOX_MAINT_EMERGENCY_STOP=" + json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ), flush=True)


def root_directory(path: Path) -> None:
    try:
        st = path.lstat()
    except OSError:
        fail("REQUIRED_DIRECTORY_MISSING")
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
        fail("UNSAFE_DIRECTORY")


def acquire_lock() -> int:
    root_directory(ROOT)
    root_directory(ROOT / "state")
    try:
        fd = os.open(LOCK, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                     getattr(os, "O_CLOEXEC", 0))
    except OSError:
        fail("OWNER_LOCK_UNAVAILABLE")
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or
                st.st_nlink != 1 or st.st_mode & 0o022):
            fail("OWNER_LOCK_UNSAFE")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("OWNER_LOCK_BUSY")
        PHASE["owner_lock"] = True
        return fd
    except BaseException:
        os.close(fd)
        raise


def check_marker(path: Path, label: str, new_bytes: bytes) -> dict:
    created = False
    try:
        st = path.lstat()
    except FileNotFoundError:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), 0o600)
        except FileExistsError:
            return check_marker(path, label, new_bytes)
        except OSError:
            fail(label + "_CREATE_FAILED")
        created = True
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb", closefd=False) as out:
                out.write(new_bytes)
                out.flush()
                os.fsync(fd)
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or
                    st.st_nlink != 1 or stat.S_IMODE(st.st_mode) != 0o600):
                fail(label + "_READBACK_UNSAFE")
        finally:
            os.close(fd)
        try:
            dfd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            fail(label + "_DIRECTORY_SYNC_FAILED")
        st = path.lstat()
    if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_nlink != 1 or
            st.st_mode & 0o022):
        fail(label + "_UNSAFE")
    try:
        raw = path.read_bytes()
    except OSError:
        fail(label + "_READ_FAILED")
    if len(raw) > 4096:
        fail(label + "_TOO_LARGE")
    if raw != new_bytes:
        fail(label + "_REQUEST_BINDING_MISMATCH")
    result = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
              "created": created, "mode": oct(stat.S_IMODE(st.st_mode))}
    if label == "STOP":
        PHASE["stop_marker"] = True
    else:
        PHASE["maintenance_marker"] = True
    MARKERS[label] = result
    return result


def ensure_owner_fence(request_id: int, source_sha: str) -> dict:
    payload = (f"NOX_OWNER_EMERGENCY_STOP_V1\nrequest_id={request_id}\n"
               f"source_sha={source_sha}\n").encode("ascii")
    # No overwrite: existing flags are accepted only as safe root-owned files.
    return {
        "stop": check_marker(STOP, "STOP", payload),
        "maintenance": check_marker(MAINTENANCE, "MAINTENANCE", payload),
    }


def command(argv: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, shell=False, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        fail("COMMAND_UNAVAILABLE")


def supervisor_status() -> dict:
    p = command(["supervisorctl", "status", SUPERVISOR_SERVICE])
    lines = p.stdout.strip().splitlines()
    m = STATUS_LINE.fullmatch(lines[0]) if len(lines) == 1 else None
    if m is None or m.group(1) != SUPERVISOR_SERVICE or p.returncode not in (0, 3):
        fail("SUPERVISOR_STATUS_UNTRUSTED")
    return {"state": m.group(2), "pid": int(m.group(3)) if m.group(3) else None,
            "rc": p.returncode}


def cgroup_path(pid: int) -> Path:
    try:
        lines = (Path("/proc") / str(pid) / "cgroup").read_text().splitlines()
    except OSError:
        fail("CGROUP_IDENTITY_UNAVAILABLE")
    rows = [line.split(":", 2)[2] for line in lines if line.startswith("0::")]
    if len(rows) != 1:
        fail("CGROUP_V2_IDENTITY_UNAVAILABLE")
    try:
        base = CGROUP_ROOT.resolve(strict=True)
        result = (base / rows[0].lstrip("/")).resolve(strict=True)
        if os.path.commonpath((str(base), str(result))) != str(base):
            fail("CGROUP_PATH_ESCAPE")
    except (OSError, ValueError):
        fail("CGROUP_PATH_UNSAFE")
    return result


def proc_start_ticks(pid: int, missing_ok: bool = False):
    path = Path("/proc") / str(pid) / "stat"
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_STAT_BYTES + 1)
    except FileNotFoundError:
        if missing_ok:
            return None
        fail("PROC_STAT_MISSING")
    except OSError:
        fail("PROC_STAT_UNREADABLE")
    if len(raw) > MAX_STAT_BYTES:
        fail("PROC_STAT_TOO_LARGE")
    text = raw.decode("ascii", "replace")
    match = re.match(r"^([0-9]+) \(", text)
    if match is None or int(match.group(1)) != pid:
        fail("PROC_STAT_PID_MISMATCH")
    try:
        fields = text.rsplit(")", 1)[1].split()
        if len(fields) <= 19:
            fail("PROC_STAT_FIELDS_INCOMPLETE")
        return int(fields[19])
    except (ValueError, IndexError):
        fail("PROC_STAT_PARSE_FAILED")


def stable_start_ticks(pid: int, expected_ticks: int = None, missing_ok: bool = False):
    first = proc_start_ticks(pid, missing_ok=missing_ok)
    if first is None:
        return None
    time.sleep(0.05)
    second = proc_start_ticks(pid, missing_ok=missing_ok)
    if second is None:
        return None
    if first != second:
        fail("PROC_STARTTIME_UNSTABLE")
    if expected_ticks is not None and second != expected_ticks:
        fail("PROC_STARTTIME_MISMATCH")
    return second


def read_maps_bounded(pid: int):
    path = Path("/proc") / str(pid) / "maps"
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_MAPS_BYTES + 1)
    except FileNotFoundError:
        return None
    except OSError:
        return None
    if len(raw) > MAX_MAPS_BYTES:
        return None
    return raw.decode("ascii", "replace")


def mapped_inode(rows: str, device: int, inode: int) -> bool:
    for row in rows.splitlines():
        fields = row.split(maxsplit=5)
        if len(fields) < 5 or not fields[4].isdigit() or int(fields[4]) != inode:
            continue
        try:
            major, minor = (int(x, 16) for x in fields[3].split(":", 1))
        except (ValueError, IndexError):
            fail("MAPS_DEVICE_UNPARSEABLE")
        if os.makedev(major, minor) == device:
            return True
    return False


def process_identity(pid: int, expected_ticks: int, role: str) -> dict:
    ticks = stable_start_ticks(pid, expected_ticks)
    proc = Path("/proc") / str(pid)
    try:
        exe = os.readlink(proc / "exe")
        argv = [x.decode("utf-8", "replace") for x in
                (proc / "cmdline").read_bytes().split(b"\0") if x]
    except OSError:
        fail(role + "_IDENTITY_UNAVAILABLE")
    exe_name = Path(exe.removesuffix(" (deleted)")).name
    if role == "MODEL":
        if exe_name != "llama-server":
            fail("MODEL_EXECUTABLE_MISMATCH")
    elif role == "HOLDER":
        if HOLDER_SCRIPT not in argv:
            fail("HOLDER_ARGV_MISMATCH")
    group = cgroup_path(pid)
    return {"pid": pid, "start_ticks": ticks, "exe": exe_name, "cgroup": str(group)}


def fd_memfd_identity(pid: int) -> dict:
    fd_dir = Path("/proc") / str(pid) / "fd"
    matches = []
    try:
        entries = list(os.scandir(fd_dir))
    except OSError:
        fail("HOLDER_FD_CENSUS_UNAVAILABLE")
    for entry in entries:
        try:
            st = os.stat(entry.path)
            link = os.readlink(entry.path)
        except FileNotFoundError:
            continue
        except OSError:
            fail("HOLDER_FD_IDENTITY_UNAVAILABLE")
        label = link.rsplit("/", 1)[-1]
        if (st.st_ino == MEMFD_INODE and st.st_size == MEMFD_SIZE and
                label == "memfd:engram_iq3xxs (deleted)"):
            matches.append({"fd": entry.name, "device": st.st_dev,
                            "inode": st.st_ino, "size": st.st_size,
                            "label": label})
    if not matches:
        fail("HOLDER_MEMFD_NOT_PRESENT")
    devices = {x["device"] for x in matches}
    if len(devices) != 1:
        fail("HOLDER_MEMFD_DEVICE_AMBIGUOUS")
    return {"device": next(iter(devices)), "inode": MEMFD_INODE,
            "size": MEMFD_SIZE, "fd_count": len(matches)}


def model_maps_memfd(pid: int, memfd_device: int) -> bool:
    rows = read_maps_bounded(pid)
    if rows is None:
        fail("MODEL_MAPS_UNAVAILABLE_OR_OVER_LIMIT")
    if not mapped_inode(rows, memfd_device, MEMFD_INODE):
        fail("MODEL_MEMFD_MAPPING_NOT_PRESENT")
    return True


def same_inode_mapping_census(device: int) -> dict:
    """Bounded whole-host map scan; any uncertainty prevents holder TERM."""
    try:
        pids = sorted(int(entry.name) for entry in Path("/proc").iterdir()
                      if entry.name.isdigit())
    except OSError:
        return {"complete": False, "mapped_pids": [], "unknown_pids": ["proc-list"]}
    if len(pids) > MAX_PROC_SCAN:
        return {"complete": False, "mapped_pids": [], "unknown_pids": ["pid-limit"]}
    mapped = []
    unknown = []
    total_bytes = 0
    for pid in pids:
        try:
            before = proc_start_ticks(pid, missing_ok=True)
        except RuntimeError:
            unknown.append(pid)
            continue
        if before is None:
            continue
        rows = read_maps_bounded(pid)
        if rows is None:
            try:
                after_missing = proc_start_ticks(pid, missing_ok=True)
            except RuntimeError:
                unknown.append(pid)
                continue
            if after_missing is None:
                continue
            unknown.append(pid)
            continue
        total_bytes += len(rows.encode("ascii", "replace"))
        if total_bytes > MAX_TOTAL_MAPS_BYTES:
            unknown.append("maps-budget")
            break
        try:
            has_mapping = mapped_inode(rows, device, MEMFD_INODE)
        except RuntimeError:
            unknown.append(pid)
            continue
        try:
            after = proc_start_ticks(pid, missing_ok=True)
        except RuntimeError:
            unknown.append(pid)
            continue
        if after != before:
            unknown.append(pid)
            continue
        if has_mapping:
            mapped.append(pid)
    return {"complete": not unknown, "mapped_pids": mapped,
            "unknown_pids": unknown, "bytes_scanned": total_bytes,
            "processes_scanned": len(pids)}


def memory_headroom(group: Path) -> dict:
    try:
        raw_max = (group / "memory.max").read_text().strip()
        raw_current = (group / "memory.current").read_text().strip()
        if not raw_max.isdigit() or not raw_current.isdigit():
            fail("CGROUP_MEMORY_LIMIT_UNBOUNDED_OR_INVALID")
        maximum, current = int(raw_max), int(raw_current)
    except OSError:
        fail("CGROUP_MEMORY_UNAVAILABLE")
    if maximum < current:
        fail("CGROUP_MEMORY_COUNTER_CONTRADICTION")
    return {"current": current, "max": maximum, "headroom": maximum - current}


def require_model_running() -> dict:
    status = supervisor_status()
    if status["state"] != "RUNNING" or status["pid"] != MODEL_PID:
        fail("MODEL_SUPERVISOR_IDENTITY_MISMATCH")
    return status


def wait_model_stopped() -> dict:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        status = supervisor_status()
        if status["state"] in ("STOPPED", "EXITED") and status["pid"] is None:
            ticks = proc_start_ticks(MODEL_PID, missing_ok=True)
            if ticks is None or ticks != MODEL_START_TICKS:
                PHASE["model_stopped"] = True
                return status
        time.sleep(0.5)
    fail("MODEL_GRACEFUL_STOP_NOT_VERIFIED")


def wait_holder_exit(pidfd: int) -> None:
    del pidfd
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        ticks = proc_start_ticks(HOLDER_PID, missing_ok=True)
        if ticks is None or ticks != HOLDER_START_TICKS:
            return
        time.sleep(0.5)
    fail("HOLDER_TERM_EXIT_NOT_VERIFIED")


def run_action(request_id: int, source_sha: str) -> dict:
    # Fresh, read-only identity and memory preflight happens before any marker.
    status = require_model_running()
    model = process_identity(MODEL_PID, MODEL_START_TICKS, "MODEL")
    holder = process_identity(HOLDER_PID, HOLDER_START_TICKS, "HOLDER")
    if model["cgroup"] != holder["cgroup"]:
        fail("TARGETS_NOT_IN_SAME_CGROUP")
    memfd = fd_memfd_identity(HOLDER_PID)
    model_maps_memfd(MODEL_PID, memfd["device"])
    before = memory_headroom(Path(model["cgroup"]))
    if before["headroom"] >= MIN_HEADROOM:
        fail("HEADROOM_ALREADY_SAFE")

    # Fence only after a fresh low-headroom preflight; flags are no-clobber
    # and must bind byte-for-byte to this exact owner request and source SHA.
    fence = ensure_owner_fence(request_id, source_sha)

    # Revalidate before issuing the exact Supervisor graceful stop.
    status = require_model_running()
    process_identity(MODEL_PID, MODEL_START_TICKS, "MODEL")
    process_identity(HOLDER_PID, HOLDER_START_TICKS, "HOLDER")
    latest_memfd = fd_memfd_identity(HOLDER_PID)
    if latest_memfd["device"] != memfd["device"]:
        fail("HOLDER_MEMFD_CHANGED_BEFORE_STOP")
    PHASE["model_stop_requested"] = True
    stopped = command(["supervisorctl", "stop", SUPERVISOR_SERVICE], timeout=35)
    if stopped.returncode != 0:
        fail("SUPERVISOR_STOP_COMMAND_FAILED")
    after_status = wait_model_stopped()

    process_identity(HOLDER_PID, HOLDER_START_TICKS, "HOLDER")
    fd_memfd_identity(HOLDER_PID)
    after_model = memory_headroom(Path(holder["cgroup"]))
    if after_model["headroom"] >= MIN_HEADROOM:
        return {"state": "MODEL_STOPPED_HOLDER_PRESERVED_HEADROOM_MET",
                "model": model, "holder": holder, "memfd": memfd,
                "before": before, "after_model": after_model,
                "minimum_headroom": MIN_HEADROOM, "markers": fence,
                "supervisor_after": after_status, "holder_signal": "NONE"}

    # Holder is eligible only after the model PID/starttime is gone/reused and
    # a bounded whole-host scan finds no same-inode map and no unknown maps.
    mappings = same_inode_mapping_census(memfd["device"])
    if not mappings["complete"] or mappings["mapped_pids"]:
        return {"state": "MODEL_STOPPED_HOLDER_PRESERVED_MAPPING_REMAINS_OR_UNKNOWN",
                "model": model, "holder": holder, "memfd": memfd,
                "before": before, "after_model": after_model,
                "mapping_census": mappings, "minimum_headroom": MIN_HEADROOM,
                "markers": fence, "supervisor_after": after_status,
                "holder_signal": "NONE"}
    latest_headroom = memory_headroom(Path(holder["cgroup"]))
    if latest_headroom["headroom"] >= MIN_HEADROOM:
        return {"state": "MODEL_STOPPED_HOLDER_PRESERVED_HEADROOM_MET",
                "model": model, "holder": holder, "memfd": memfd,
                "before": before, "after_model": after_model,
                "after_mapping_census": latest_headroom,
                "mapping_census": mappings, "minimum_headroom": MIN_HEADROOM,
                "markers": fence, "supervisor_after": after_status,
                "holder_signal": "NONE"}

    # Fresh exact PID/starttime/inode check precedes the only direct signal.
    if supervisor_status()["state"] not in ("STOPPED", "EXITED"):
        fail("MODEL_NOT_STILL_STOPPED")
    latest_holder = process_identity(HOLDER_PID, HOLDER_START_TICKS, "HOLDER")
    latest_memfd = fd_memfd_identity(HOLDER_PID)
    if (latest_holder["cgroup"] != holder["cgroup"] or
            latest_memfd["device"] != memfd["device"]):
        fail("HOLDER_MEMFD_IDENTITY_CHANGED")
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        fail("PIDFD_SIGNAL_UNAVAILABLE")
    try:
        pidfd = os.pidfd_open(HOLDER_PID, 0)
    except OSError:
        fail("HOLDER_PIDFD_OPEN_FAILED")
    try:
        process_identity(HOLDER_PID, HOLDER_START_TICKS, "HOLDER")
        latest_memfd = fd_memfd_identity(HOLDER_PID)
        if latest_memfd["device"] != memfd["device"]:
            fail("HOLDER_MEMFD_CHANGED_BEFORE_SIGNAL")
        if memory_headroom(Path(holder["cgroup"]))["headroom"] >= MIN_HEADROOM:
            return {"state": "MODEL_STOPPED_HOLDER_PRESERVED_HEADROOM_MET",
                    "model": model, "holder": holder, "memfd": memfd,
                    "before": before, "after_model": after_model,
                    "mapping_census": mappings, "markers": fence,
                    "supervisor_after": after_status, "holder_signal": "NONE"}
        signal.pidfd_send_signal(pidfd, signal.SIGTERM, None, 0)
        PHASE["holder_term_sent"] = True
        wait_holder_exit(pidfd)
    except OSError:
        fail("HOLDER_TERM_FAILED")
    finally:
        os.close(pidfd)

    after_holder = memory_headroom(Path(holder["cgroup"]))
    return {"state": ("HOLDER_TERM_SENT_HEADROOM_MET" if
                      after_holder["headroom"] >= MIN_HEADROOM else
                      "HOLDER_TERM_SENT_HEADROOM_STILL_SHORT"),
            "model": model, "holder": holder, "memfd": memfd,
            "before": before, "after_model": after_model,
            "after_holder": after_holder, "mapping_census": mappings,
            "minimum_headroom": MIN_HEADROOM, "markers": fence,
            "supervisor_after": after_status,
            "holder_signal": "SIGTERM_PIDFD_ONLY"}


def main() -> int:
    source_sha = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    request = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    if not SHA40.fullmatch(source_sha) or not request.isdigit():
        fail("OWNER_CONTEXT")
    if os.geteuid() != 0:
        fail("ROOT_REQUIRED")
    lock_fd = acquire_lock()
    try:
        receipt = run_action(int(request), source_sha)
        emit({"source_sha": source_sha, "request_id": int(request),
              "owner_fence_retained": True, **receipt})
        print("NOX_MAINT_EMERGENCY_STOP_COMPLETE=true", flush=True)
        return 0
    finally:
        with contextlib.suppress(Exception):
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        label = str(exc)
        if not re.fullmatch(r"HOLD_EMERGENCY_STOP_[A-Z0-9_]+", label):
            label = "HOLD_EMERGENCY_STOP_" + type(exc).__name__.upper()
        emit({"state": label, "phase": PHASE, "markers": MARKERS,
              "owner_fence_retained": bool(PHASE["stop_marker"] or PHASE["maintenance_marker"]),
              "no_rollback_or_restart": True})
        print("NOX_MAINT_EMERGENCY_STOP_RESULT=" + label, flush=True)
        raise SystemExit(2)
