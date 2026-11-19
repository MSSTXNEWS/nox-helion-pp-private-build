#!/usr/bin/env python3
"""Bounded, read-only owner process/GPU snapshot; never invokes helper main()."""
from __future__ import annotations

import ast
import base64
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import selectors
import time
import types
from pathlib import Path

sys.dont_write_bytecode = True

INSTANCE_ID = 60509551
AUDIT_SOURCE_SHA = "b1e33d60983885a7ebd1979bda4ec640b7ca7047"
AUDIT_BLOB_SHA = "e5c439c6733fcb276bec58dbf8af5193694645ac"
GPU_SOURCE_SHA = "a95c7c6e4d52a35db9199e1aa2a5ad01752efc7e"
GPU_BLOB_SHA = "3a3ff33e7709539d5ff6ab6b8614d694a9d2becb"
RESOURCE_SOURCE_SHA = "5fb2c3d91b3c9a241c8b20168d3f674ae13727eb"
RESOURCE_BLOB_SHA = "08ada5def3e96761498a3840445459ee3d672742"
AUDIT_PREFIX = "NOX_MAINT_AUDIT="
PROCESS_CHUNK_PREFIX = "NOX_MAINT_AUDIT_PROCESS_CHUNK="
SERVICE_CHUNK_PREFIX = "NOX_MAINT_AUDIT_SERVICE_CHUNK="
AUDIT_SCOPE_MARKER = "NOX_MAINT_AUDIT_SCOPE=BOUNDED_PROCESS_CENSUS_ONLY"
AUDIT_SCOPE_COMPLETE = "NOX_MAINT_AUDIT_SCOPE_COMPLETE=true"
LOCKS_PREFIX = "NOX_MAINT_KERNEL_LOCKS="
CLEANUP_PREFIX = "NOX_MAINT_COMPOSITE_CLEANUP="
TASK_EVIDENCE_PREFIX = "NOX_MAINT_TASK_EVIDENCE="
GPU_PREFIX = "NOX_MAINT_GPU_INVENTORY="
GPU_RESULT_PREFIX = "NOX_MAINT_GPU_INVENTORY_RESULT="
GPU_COMPLETE = "NOX_MAINT_GPU_INVENTORY_COMPLETE=true"
COMPOSITE_COMPLETE = "NOX_MAINT_AUDIT_GPU_INVENTORY_COMPLETE=true"
AUDIT_SCOPE_SECTIONS = ("hardware", "process_identity_inventory")
TASK_SPEC_SHA256 = {
    "2V14-02": "f353440a6056d219deeafbd1f9554497383cb5367b77447e75e3d603fd7a47c7",
    "2V14-12": "b3f3a9e9120c7d777f594f93a2ed93402e91ce2989c312cf8ce6f2c079c4d2ed",
    "6V14-02": "00b403c24775060bb39c6d81f177c6c73073f1168538ca35a94a0213858f3d73",
}
TASK_OWNER_ID = 340718567
MAX_HELPER_BYTES = 256 * 1024
MAX_OUTPUT_BYTES = 12 * 1024 * 1024
MAX_OUTPUT_LINE_BYTES = 160 * 1024
MAX_PROBE_OUTPUT_BYTES = 128 * 1024
MAX_PROBE_TOTAL_BYTES = 1024 * 1024
MAX_PROBE_COMMANDS = 32
MAX_KERNEL_LOCK_BYTES = 256 * 1024
MAX_KERNEL_LOCK_ROWS = 128
MAX_PROCESS_ROWS = 8192
PROCESS_CHUNK_ROWS = 16
SERVICE_CHUNK_ROWS = 16
MAX_SELF_RSS_BYTES = 32 * 1024**2
READONLY_CGROUP_HEADROOM_MINIMUM = 64 * 1024**2
HELPER_TIMEOUT = 12
OWNER_LEASE_PATH = Path('/root/nox/state/owner_maintenance.lock')
STOP_MARKERS = (
    ("STOP", Path('/root/nox/STOP')),
    ("STOP_FLAG", Path('/root/nox/STOP.flag')),
    ("LOWER_STOP_FLAG", Path('/root/nox/stop.flag')),
    ("DOT_STOP", Path('/root/nox/.stop')),
    ("PROGRAM_STOP", Path('/root/nox/program/STOP')),
    ("STATE_STOP", Path('/root/nox/state/STOP')),
    ("STATE_STOP_FLAG", Path('/root/nox/state/STOP.flag')),
    ("WORKSPACE_STOP", Path('/workspace/NOX_STOP')),
    ("OWNER_MAINTENANCE", Path('/root/nox/state/OWNER_MAINTENANCE.flag')),
    ("MEDIA_STOP", Path('/root/nox/state/MEDIA_STOP.flag')),
    ("TRAIN_HOLD", Path('/root/nox/state/TRAIN_HOLD.flag')),
    ("TRAIN_PAUSE_REQUEST", Path('/root/nox/state/TRAIN_PAUSE_REQUEST.flag')),
)
AUDIT_HELPER_B64 = __NOX_AUDIT_HELPER_B64__
GPU_HELPER_B64 = __NOX_GPU_HELPER_B64__
RESOURCE_HELPER_B64 = __NOX_STORAGE_RECLAIM_HELPER_B64__

probe_state = {"commands": 0, "bytes": 0}
active_lease_fd = None
active_lease = None
PROBE_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": "/root", "LANG": "C", "LC_ALL": "C",
}
output_state = {"bytes": 0}


class Hold(RuntimeError):
    pass


def require(ok, code):
    if not ok:
        raise Hold(code)


def git_blob_sha(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def owner_context():
    source = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    request = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", source)), "HOLD_COMPOSITE_SOURCE_PIN")
    require(bool(re.fullmatch(r"[1-9][0-9]{0,19}", request)), "HOLD_COMPOSITE_REQUEST_PIN")
    return source, request


def stop_gate():
    states = {}
    failure = None
    for label, path in STOP_MARKERS:
        try:
            os.stat(path, follow_symlinks=False)
            states[label] = "PRESENT"
            failure = failure or "HOLD_COMPOSITE_STOP_PRESENT"
        except FileNotFoundError:
            states[label] = "ABSENT"
        except OSError:
            states[label] = "UNKNOWN"
            failure = failure or "HOLD_COMPOSITE_STOP_STATE_UNKNOWN"
    if failure:
        raise Hold(failure)
    return states


AUDIT_ALLOWED_IMPORTS = frozenset({
    "__future__", "csv", "hashlib", "io", "json", "os", "pathlib", "re",
    "shutil", "subprocess", "sys", "time",
})
AUDIT_ALLOWED_CONSTANTS = frozenset({
    "SAFE", "ROOTS", "MAX_GPU_APPS", "MAX_PROC_ENTRIES",
    "MAX_PARENT_DEPTH", "GPU_APP_QUERY", "GPU_UUID", "CGROUP_PATH",
    "SUPERVISOR_STATUS",
})
AUDIT_ALLOWED_FUNCTIONS = frozenset({
    "run", "num", "_read_proc_text", "_status_identity", "_proc_cgroups",
    "_ns_link", "read_proc_identity", "parse_gpu_apps", "_capture_gpu_apps",
    "_parse_supervisor_status", "_capture_services", "_nspid_aliases",
    "_service_relation", "_capture_proc_targets", "_target_signature",
    "_link_gpu_apps", "_candidate_from_link", "_candidate_matches_identity",
    "_gpu_candidates_by_pid", "gpu_process_census", "_format_gpu_app",
    "hardware", "_proc_stat", "proc_start_ticks",
    "_capture_process_identity_inventory",
})
GPU_ALLOWED_CONSTANTS = frozenset({
    "ACTION", "INSTANCE_ID", "SCHEMA", "NVIDIA_SMI", "QUERY",
    "MAX_OUTPUT_BYTES", "MAX_ROW_BYTES", "MAX_GPUS",
    "MAX_DRIVER_RESERVED_MIB", "MEMORY_SEMANTICS", "UUID_RE", "SOURCE_RE",
})
GPU_ALLOWED_FUNCTIONS = frozenset({
    "_hold", "_read_host_clock", "parse_gpu_rows", "capture_snapshot",
    "_identity_rows", "build_inventory", "inventory_digest", "run_action",
})
RESOURCE_ALLOWED_CONSTANTS = frozenset({
    "ROOT", "SHM", "CGROUP", "GIB", "BROWSER_RUNTIME_HEADROOM",
})
RESOURCE_ALLOWED_FUNCTIONS = frozenset({"filesystem_budget"})


def load_filtered_pinned_module(name, encoded, expected_blob,
                                allowed_constants, allowed_functions):
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception:
        raise Hold("HOLD_COMPOSITE_HELPER_ENCODING") from None
    require(0 < len(raw) <= MAX_HELPER_BYTES, "HOLD_COMPOSITE_HELPER_SIZE")
    require(git_blob_sha(raw) == expected_blob, "HOLD_COMPOSITE_HELPER_BLOB_PIN")
    module = types.ModuleType(name)
    module.__file__ = "<pinned:" + name + ">"
    try:
        source = raw.decode("utf-8", errors="strict")
        tree = ast.parse(source, filename=module.__file__, mode="exec")
        selected = []
        seen_functions = set()
        seen_constants = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                aliases = [alias for alias in node.names
                           if alias.name in AUDIT_ALLOWED_IMPORTS]
                if aliases:
                    selected.append(ast.Import(names=aliases))
            elif isinstance(node, ast.ImportFrom):
                if node.module in AUDIT_ALLOWED_IMPORTS:
                    selected.append(node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in allowed_functions:
                    selected.append(node)
                    seen_functions.add(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names = {
                    target.id for target in targets if isinstance(target, ast.Name)
                }
                if names and names <= allowed_constants:
                    selected.append(node)
                    seen_constants.update(names)
        require(allowed_functions <= seen_functions,
                "HOLD_COMPOSITE_HELPER_FUNCTION_PIN")
        require(allowed_constants <= seen_constants,
                "HOLD_COMPOSITE_HELPER_CONSTANT_PIN")
        filtered = ast.Module(body=selected, type_ignores=[])
        ast.fix_missing_locations(filtered)
        code = compile(filtered, module.__file__, "exec", dont_inherit=True)
        exec(code, module.__dict__)
    except Hold:
        raise
    except Exception:
        raise Hold("HOLD_COMPOSITE_HELPER_LOAD") from None
    require("main" not in module.__dict__, "HOLD_COMPOSITE_MAIN_EXCLUDED")
    return module


# Only the bounded census definitions are compiled; helper main and pool import are excluded.
def load_audit_helper(encoded):
    return load_filtered_pinned_module(
        "_nox_pinned_owner_audit", encoded, AUDIT_BLOB_SHA,
        AUDIT_ALLOWED_CONSTANTS, AUDIT_ALLOWED_FUNCTIONS)


def load_gpu_helper(encoded):
    return load_filtered_pinned_module(
        "_nox_pinned_gpu_inventory", encoded, GPU_BLOB_SHA,
        GPU_ALLOWED_CONSTANTS, GPU_ALLOWED_FUNCTIONS)


def load_resource_gate(encoded):
    module = load_filtered_pinned_module(
        "_nox_pinned_resource_budget", encoded, RESOURCE_BLOB_SHA,
        RESOURCE_ALLOWED_CONSTANTS, RESOURCE_ALLOWED_FUNCTIONS)
    if (
        not callable(getattr(module, "filesystem_budget", None))
        or type(getattr(module, "BROWSER_RUNTIME_HEADROOM", None)) is not int
        or module.BROWSER_RUNTIME_HEADROOM != 4 * 1024**3
    ):
        raise Hold("HOLD_COMPOSITE_RESOURCE_GATE_PIN")
    return module


def resource_gate(storage):
    try:
        budget = storage.filesystem_budget()
        cgroup = budget.get("cgroup") if isinstance(budget, dict) else None
    except Exception:
        raise Hold("HOLD_COMPOSITE_CGROUP_UNAVAILABLE") from None
    if not isinstance(cgroup, dict):
        raise Hold("HOLD_COMPOSITE_CGROUP_BUDGET")
    limit = cgroup.get("limit_bytes")
    current = cgroup.get("current_bytes")
    headroom = cgroup.get("headroom_bytes")
    if (
        type(limit) is not int or type(current) is not int
        or type(headroom) is not int or limit <= 0
        or current < 0 or current > limit
        or cgroup.get("state") != "VERIFIED"
        or headroom != limit - current
        or headroom < READONLY_CGROUP_HEADROOM_MINIMUM
    ):
        raise Hold("HOLD_COMPOSITE_READONLY_MEMORY_HEADROOM")
    return {
        "limit_bytes": limit, "current_bytes": current,
        "headroom_bytes": headroom,
        "readonly_minimum_bytes": READONLY_CGROUP_HEADROOM_MINIMUM,
        "browser_training_threshold_bytes": storage.BROWSER_RUNTIME_HEADROOM,
        "browser_training_gate_applied": False,
    }


def self_rss_gate():
    try:
        with Path("/proc/self/status").open("rb") as stream:
            raw = stream.read(8193)
    except OSError:
        raise Hold("HOLD_COMPOSITE_SELF_RSS_UNAVAILABLE") from None
    if len(raw) > 8192:
        raise Hold("HOLD_COMPOSITE_SELF_RSS_BOUND")
    try:
        text = raw.decode("ascii", errors="strict")
    except UnicodeDecodeError:
        raise Hold("HOLD_COMPOSITE_SELF_RSS_ENCODING") from None
    match = re.search(r"^VmRSS:\s+([0-9]+)\s+kB$", text, re.MULTILINE)
    if match is None:
        raise Hold("HOLD_COMPOSITE_SELF_RSS_UNAVAILABLE")
    rss = int(match.group(1)) * 1024
    if rss > MAX_SELF_RSS_BYTES:
        raise Hold("HOLD_COMPOSITE_SELF_RSS_BOUND")
    return rss

def host_identity():
    try:
        with Path("/proc/sys/kernel/random/boot_id").open("rb") as stream:
            boot_raw = stream.read(128)
        with Path("/proc/uptime").open("rb") as stream:
            uptime_raw = stream.read(128)
        if len(boot_raw) > 127 or len(uptime_raw) > 127:
            raise Hold("HOLD_COMPOSITE_HOST_ID_BOUND")
        boot_id = boot_raw.decode("ascii", errors="strict").strip()
        uptime_text = uptime_raw.decode("ascii", errors="strict").split()[0]
        uptime = float(uptime_text)
    except Hold:
        raise
    except Exception:
        raise Hold("HOLD_COMPOSITE_HOST_ID_UNAVAILABLE") from None
    if (
        re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", boot_id) is None
        or not (0 <= uptime < 10**9)
    ):
        raise Hold("HOLD_COMPOSITE_HOST_ID_INVALID")
    return {"boot_id": boot_id, "uptime_seconds": uptime}


def check_gate(storage, lease_fd=None, lease=None):
    stop_markers = stop_gate()
    budget = resource_gate(storage)
    budget["self_rss_bytes"] = self_rss_gate()
    budget["self_rss_maximum_bytes"] = MAX_SELF_RSS_BYTES
    budget["stop_markers"] = stop_markers
    budget["host"] = host_identity()
    lease_fd = active_lease_fd if lease_fd is None else lease_fd
    lease = active_lease if lease is None else lease
    if lease_fd is not None:
        require(isinstance(lease, dict), "HOLD_COMPOSITE_OWNER_LEASE_STATE")
        budget["owner_lease"] = check_owner_lock_file(lease_fd, lease)
    else:
        budget["owner_lease"] = {"lease_state": "NOT_ACQUIRED"}
    return budget

def acquire_owner_lease():
    fd = -1
    try:
        fd = os.open(
            OWNER_LEASE_PATH,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
            getattr(os, "O_CLOEXEC", 0),
        )
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise Hold("HOLD_COMPOSITE_OWNER_LEASE_FILE")
        current = os.stat(OWNER_LEASE_PATH, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            raise Hold("HOLD_COMPOSITE_OWNER_LEASE_CHANGED")
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Hold("HOLD_COMPOSITE_OWNER_LEASE_BUSY") from None
        return fd, {
            "path_id": "owner_maintenance.lock",
            "device": info.st_dev, "inode": info.st_ino,
            "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid,
            "gid": info.st_gid, "nlink": info.st_nlink,
            "lease_state": "HELD_SHARED_NONBLOCKING",
        }
    except Hold:
        if fd >= 0:
            os.close(fd)
        raise
    except OSError:
        if fd >= 0:
            os.close(fd)
        raise Hold("HOLD_COMPOSITE_OWNER_LEASE_UNAVAILABLE") from None


def release_owner_lease(fd):
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def emit(prefix, value):
    try:
        line = prefix + json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False)
        encoded = line.encode("ascii")
    except Exception:
        raise Hold("HOLD_COMPOSITE_RESULT_ENCODING") from None
    require(len(encoded) <= MAX_OUTPUT_LINE_BYTES,
            "HOLD_COMPOSITE_RESULT_LINE_BOUND")
    output_state["bytes"] += len(encoded) + 1
    require(output_state["bytes"] <= MAX_OUTPUT_BYTES,
            "HOLD_COMPOSITE_RESULT_OUTPUT_BOUND")
    print(line, flush=True)


def emit_gate_snapshot(stage, source, request, lease, storage):
    budget = check_gate(storage, active_lease_fd, active_lease)
    record = {
        "schema": "NOX_OWNER_READONLY_AUDIT_GATE_V1",
        "source_sha": source, "request_id": int(request), "stage": stage,
        "observed_at_unix": time.time(),
        "monotonic_observed_ns": time.monotonic_ns(),
        "github_owner_id": TASK_OWNER_ID,
        "native_effective_uid": os.geteuid(),
        "host": budget["host"],
        "stop_state": "CLEAR",
        "stop_markers": budget["stop_markers"],
        "owner_lease_state": lease["lease_state"],
        "owner_lease_file": lease,
        "resource": budget,
        "resource_source_sha": RESOURCE_SOURCE_SHA,
        "resource_blob_sha": RESOURCE_BLOB_SHA,
    }
    emit("NOX_MAINT_AUDIT_GATE=", record)
    return record

def _allowed_probe(argv):
    if argv == [
        "supervisorctl", "status",
    ]:
        return True
    if (len(argv) != 3
            or argv[0] not in ("nvidia-smi", "/usr/bin/nvidia-smi")
            or argv[2] != "--format=csv,noheader,nounits"):
        return False
    return argv[1] in (
        "--query-compute-apps=pid,gpu_uuid,used_gpu_memory",
        "--query-gpu=index,name,uuid,memory.total,memory.used,utilization.gpu,temperature.gpu",
        "--query-gpu=index,name,uuid,memory.total,memory.used,memory.free",
    )


def _terminate_own_probe(child):
    # Popen.kill targets only the exact child PID returned by our own Popen.
    # Probes are fixed, read-only nvidia-smi/supervisorctl commands.
    if child.poll() is None:
        child.kill()
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            raise Hold("HOLD_COMPOSITE_PROBE_CHILD_CLEANUP") from None


def bounded_probe(argv, timeout, storage):
    if (
        not isinstance(argv, (list, tuple)) or not argv
        or any(not isinstance(arg, str) or "\0" in arg for arg in argv)
        or not _allowed_probe(list(argv))
    ):
        raise Hold("HOLD_COMPOSITE_PROBE_ARGUMENTS")
    if type(timeout) not in (int, float) or not 0 < timeout <= HELPER_TIMEOUT:
        raise Hold("HOLD_COMPOSITE_PROBE_TIMEOUT_PIN")
    probe_state["commands"] += 1
    require(probe_state["commands"] <= MAX_PROBE_COMMANDS,
            "HOLD_COMPOSITE_PROBE_COUNT_BOUND")
    check_gate(storage)
    child = None
    selector = selectors.DefaultSelector()
    data = bytearray()
    try:
        child = subprocess.Popen(
            list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=PROBE_ENV, close_fds=True,
        )
        if child.stdout is None:
            raise Hold("HOLD_COMPOSITE_PROBE_PIPE")
        fd = child.stdout.fileno()
        os.set_blocking(fd, False)
        selector.register(fd, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        eof = False
        while not eof:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _terminate_own_probe(child)
                raise Hold("HOLD_COMPOSITE_PROBE_TIMEOUT")
            events = selector.select(min(0.1, remaining))
            if not events and child.poll() is not None:
                # A descendant retaining stdout is outside this helper's
                # bounded contract; stop waiting and fail closed.
                raise Hold("HOLD_COMPOSITE_PROBE_PIPE_NOT_CLOSED")
            for key, _ in events:
                remaining_bytes = MAX_PROBE_OUTPUT_BYTES + 1 - len(data)
                require(remaining_bytes > 0,
                        "HOLD_COMPOSITE_PROBE_OUTPUT_BOUND")
                chunk = os.read(key.fd, min(65536, remaining_bytes))
                if not chunk:
                    eof = True
                    selector.unregister(key.fd)
                    break
                data.extend(chunk)
                if len(data) > MAX_PROBE_OUTPUT_BYTES:
                    _terminate_own_probe(child)
                    raise Hold("HOLD_COMPOSITE_PROBE_OUTPUT_BOUND")
        returncode = child.wait(timeout=1)
        probe_state["bytes"] += len(data)
        require(probe_state["bytes"] <= MAX_PROBE_TOTAL_BYTES,
                "HOLD_COMPOSITE_PROBE_TOTAL_BOUND")
        try:
            output = bytes(data).decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise Hold("HOLD_COMPOSITE_PROBE_ENCODING") from None
        check_gate(storage)
        return returncode, output
    except Hold:
        if child is not None:
            _terminate_own_probe(child)
        raise
    except (OSError, subprocess.SubprocessError):
        if child is not None:
            _terminate_own_probe(child)
        raise Hold("HOLD_COMPOSITE_PROBE_START") from None
    finally:
        selector.close()
        if child is not None and child.stdout is not None:
            child.stdout.close()

def audit_run(argv, seconds=12):
    code, text = bounded_probe(argv, seconds, active_storage)
    return code, text


def gpu_run(argv, capture_output=True, text=True, timeout=12, check=False):
    code, output = bounded_probe(argv, timeout, active_storage)
    if not text:
        output = output.encode("utf-8")
    return types.SimpleNamespace(returncode=code, stdout=output, stderr="")


def parse_kernel_lock_line(line):
    parts = line.split()
    offset = 2 if len(parts) > 1 and parts[1] == "->" else 1
    if len(parts) < offset + 5:
        return {"state": "UNPARSED", "raw": line}
    try:
        lock_type = parts[offset]
        advisory = parts[offset + 1]
        mode = parts[offset + 2]
        pid_value = None if parts[offset + 3] == "-1" else int(parts[offset + 3])
        device_parts = parts[offset + 4].split(":")
        if len(device_parts) != 3:
            raise ValueError("device")
        device_major = int(device_parts[0], 16)
        device_minor = int(device_parts[1], 16)
        inode = int(device_parts[2], 10)
    except (ValueError, IndexError):
        return {"state": "UNPARSED", "raw": line}
    return {
        "state": "PARSED", "raw": line, "lock_type": lock_type,
        "advisory": advisory, "mode": mode, "pid": pid_value,
        "device_major": device_major, "device_minor": device_minor,
        "inode": inode, "range": parts[offset + 5:offset + 7],
    }


def capture_kernel_locks():
    fd = -1
    try:
        fd = os.open(
            "/proc/locks",
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
            getattr(os, "O_CLOEXEC", 0),
        )
        raw = os.read(fd, MAX_KERNEL_LOCK_BYTES + 1)
    except OSError:
        raise Hold("HOLD_COMPOSITE_KERNEL_LOCKS_UNAVAILABLE") from None
    finally:
        if fd >= 0:
            os.close(fd)
    require(len(raw) <= MAX_KERNEL_LOCK_BYTES,
            "HOLD_COMPOSITE_KERNEL_LOCKS_SIZE")
    try:
        text = raw.decode("ascii", errors="strict")
    except UnicodeDecodeError:
        raise Hold("HOLD_COMPOSITE_KERNEL_LOCKS_ENCODING") from None
    lines = text.splitlines()
    require(all(len(line) <= 512 for line in lines),
            "HOLD_COMPOSITE_KERNEL_LOCKS_LINE_BOUND")
    require(len(lines) <= MAX_KERNEL_LOCK_ROWS,
            "HOLD_COMPOSITE_KERNEL_LOCKS_ROW_BOUND")
    parsed = [parse_kernel_lock_line(line) for line in lines]
    return {
        "source": "/proc/locks",
        "state": "LOCK_ROWS_PRESENT" if lines else "NO_LOCKS_PRESENT",
        "row_count": len(lines), "parse_complete": all(
            row.get("state") == "PARSED" for row in parsed),
        "rows": parsed,
    }


def check_owner_lock_file(fd, lease):
    try:
        info = os.fstat(fd)
        current = os.stat(OWNER_LEASE_PATH, follow_symlinks=False)
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
        raise Hold("HOLD_COMPOSITE_OWNER_LEASE_LOST") from None
    except OSError:
        raise Hold("HOLD_COMPOSITE_OWNER_LEASE_REVALIDATION") from None
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) & 0o077
        or (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino)
        or info.st_dev != lease.get("device")
        or info.st_ino != lease.get("inode")
        or lease.get("lease_state") != "HELD_SHARED_NONBLOCKING"
    ):
        raise Hold("HOLD_COMPOSITE_OWNER_LEASE_CHANGED")
    return {
        "path_id": "owner_maintenance.lock", "device": info.st_dev,
        "inode": info.st_ino, "mode": stat.S_IMODE(info.st_mode),
        "uid": info.st_uid, "gid": info.st_gid,
        "nlink": info.st_nlink, "lease_state": lease["lease_state"],
        "flock_revalidated": True,
    }

def lease_kernel_lock_matches(snapshot, lease):
    expected_major = os.major(lease["device"])
    expected_minor = os.minor(lease["device"])
    matched = [
        row for row in snapshot.get("rows", [])
        if row.get("state") == "PARSED"
        and row.get("device_major") == expected_major
        and row.get("device_minor") == expected_minor
        and row.get("inode") == lease["inode"]
    ]
    own_read_locks = [
        row for row in matched
        if row.get("pid") == os.getpid()
        and row.get("lock_type") == "FLOCK"
        and row.get("mode") == "READ"
    ]
    return matched, own_read_locks


def validate_gpu(code, lines, request):
    if code != 0 or len(lines) != 2 or lines[1] != GPU_COMPLETE:
        return False
    if not lines[0].startswith(GPU_PREFIX):
        return False
    try:
        receipt = json.loads(lines[0][len(GPU_PREFIX):])
    except (TypeError, ValueError):
        return False
    if (
        not isinstance(receipt, dict)
        or set(receipt) != {
            "schema", "action", "instance_id", "source_sha", "request_id",
            "inventory_sha256", "inventory",
        }
        or receipt.get("schema") != "NOX_GPU_INVENTORY_V1"
        or receipt.get("action") != "gpu_inventory"
        or type(receipt.get("instance_id")) is not int
        or receipt.get("instance_id") != INSTANCE_ID
        or receipt.get("source_sha") != GPU_SOURCE_SHA
        or type(receipt.get("request_id")) is not int
        or receipt.get("request_id") != int(request)
        or not isinstance(receipt.get("inventory_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", receipt["inventory_sha256"]) is None
    ):
        return False
    inventory = receipt["inventory"]
    if (
        not isinstance(inventory, dict)
        or set(inventory) != {
            "schema", "action", "instance_id", "boot_id", "uptime_scope",
            "memory_semantics", "identity_stable", "snapshots",
        }
        or inventory.get("schema") != "NOX_GPU_INVENTORY_V1"
        or inventory.get("action") != "gpu_inventory"
        or type(inventory.get("instance_id")) is not int
        or inventory.get("instance_id") != INSTANCE_ID
        or inventory.get("uptime_scope") != "two monotonic host snapshots; point-in-time only"
        or inventory.get("memory_semantics") != "nvidia-smi MiB; 0<=total-used-free<=1024 reserved"
        or inventory.get("identity_stable") is not True
        or not isinstance(inventory.get("boot_id"), str)
        or re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", inventory["boot_id"]) is None
        or not isinstance(inventory.get("snapshots"), list)
        or len(inventory["snapshots"]) != 2
    ):
        return False
    identities = []
    uptimes = []
    prior_end = None
    for snapshot in inventory["snapshots"]:
        if (
            not isinstance(snapshot, dict)
            or set(snapshot) != {
                "boot_id", "uptime_seconds", "monotonic_started_ns",
                "monotonic_finished_ns", "nvidia_smi_rc", "rows",
            }
            or snapshot.get("boot_id") != inventory["boot_id"]
            or type(snapshot.get("nvidia_smi_rc")) is not int
            or snapshot["nvidia_smi_rc"] != 0
            or type(snapshot.get("monotonic_started_ns")) is not int
            or type(snapshot.get("monotonic_finished_ns")) is not int
            or snapshot["monotonic_started_ns"] < 0
            or snapshot["monotonic_finished_ns"] < snapshot["monotonic_started_ns"]
            or (prior_end is not None and snapshot["monotonic_started_ns"] <= prior_end)
            or not isinstance(snapshot.get("uptime_seconds"), (int, float))
            or isinstance(snapshot["uptime_seconds"], bool)
            or not 0 <= snapshot["uptime_seconds"] < 10**9
            or not isinstance(snapshot.get("rows"), list)
            or len(snapshot["rows"]) != 2
        ):
            return False
        prior_end = snapshot["monotonic_finished_ns"]
        rows = []
        seen_indices = set()
        seen_uuids = set()
        for row in snapshot["rows"]:
            fields = {
                "index", "model", "uuid", "memory_total_mib",
                "memory_used_mib", "memory_free_mib",
            }
            if (
                not isinstance(row, dict)
                or set(row) != fields
                or type(row.get("index")) is not int
                or not 0 <= row["index"] <= 31
                or row.get("model") != "Tesla V100-SXM2-32GB"
                or not isinstance(row.get("uuid"), str)
                or re.fullmatch(r"GPU-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", row["uuid"]) is None
                or row["index"] in seen_indices
                or row["uuid"] in seen_uuids
            ):
                return False
            numbers = [row.get(key) for key in (
                "memory_total_mib", "memory_used_mib", "memory_free_mib",
            )]
            if any(type(value) is not int or not 0 <= value <= 10**7 for value in numbers):
                return False
            total, used, free = numbers
            if (
                total <= 0 or used > total or free > total
                or used + free > total
                or total - used - free > min(1024, total // 10)
            ):
                return False
            seen_indices.add(row["index"])
            seen_uuids.add(row["uuid"])
            rows.append((row["index"], row["model"], row["uuid"], total))
        if rows != sorted(rows):
            return False
        identities.append(rows)
        uptimes.append(snapshot["uptime_seconds"])
    if identities[0] != identities[1] or uptimes[1] <= uptimes[0]:
        return False
    canonical = json.dumps(
        inventory, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(canonical).hexdigest() == receipt["inventory_sha256"]



def json_sha256(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def validate_process_inventory(inventory):
    if not isinstance(inventory, dict):
        return False
    rows = inventory.get("rows")
    if (
        inventory.get("scope") != "ALL_NUMERIC_PROC_PIDS_MINIMAL_IDENTITY"
        or inventory.get("complete") is not True
        or inventory.get("truncated") is not False
        or inventory.get("enumeration_error") is not None
        or inventory.get("read_failure_count") != 0
        or inventory.get("read_failure_pids") != []
        or type(inventory.get("entries_seen")) is not int
        or type(inventory.get("row_count")) is not int
        or type(inventory.get("cap")) is not int
        or inventory["cap"] != MAX_PROCESS_ROWS
        or not isinstance(rows, list) or not rows
        or inventory["entries_seen"] != len(rows)
        or inventory["row_count"] != len(rows)
        or len(rows) > MAX_PROCESS_ROWS
        or not isinstance(inventory.get("rows_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", inventory["rows_sha256"]) is None
        or json_sha256(rows) != inventory["rows_sha256"]
    ):
        return False
    prior_pid = 0
    for row in rows:
        if (
            not isinstance(row, dict)
            or row.get("identity_state") != "VERIFIED"
            or type(row.get("pid")) is not int or row["pid"] <= prior_pid
            or type(row.get("ppid")) is not int or row["ppid"] < 0
            or type(row.get("uid")) is not int or row["uid"] < 0
            or type(row.get("start_ticks")) is not int or row["start_ticks"] <= 0
            or not isinstance(row.get("comm"), str) or not row["comm"]
            or row.get("exe_state") != "AVAILABLE"
            or not isinstance(row.get("exe"), str) or not row["exe"]
            or not isinstance(row.get("nspid"), list) or not row["nspid"]
            or any(type(value) is not int or value <= 0 for value in row["nspid"])
            or not isinstance(row.get("namespaces"), dict)
            or any(not isinstance(row["namespaces"].get(name), str)
                   for name in ("pid", "mnt", "cgroup"))
            or "missing_fields" in row
        ):
            return False
        prior_pid = row["pid"]
    return True


def validate_service_census(services):
    if not isinstance(services, dict):
        return False
    rows = services.get("services")
    health = services.get("service_health")
    if (
        services.get("complete") is not True
        or services.get("inventory_complete") is not True
        or services.get("rows_complete") is not True
        or services.get("identity_complete") is not True
        or services.get("status_consistent") is not True
        or services.get("truncated") is not False
        or services.get("rejected_lines") != 0
        or services.get("duplicate_service_names") is not False
        or not isinstance(health, dict) or health.get("state") != "HEALTHY"
        or not isinstance(rows, list) or not rows or len(rows) > 512
    ):
        return False
    names = set()
    for row in rows:
        identity = row.get("identity") if isinstance(row, dict) else None
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("service"), str) or not row["service"]
            or row["service"] in names
            or row.get("state") != "RUNNING"
            or type(row.get("pid")) is not int or row["pid"] <= 0
            or row.get("identity_state") != "VERIFIED"
            or not isinstance(identity, dict)
            or identity.get("pid") != row["pid"]
            or type(identity.get("start_ticks")) is not int
            or identity["start_ticks"] <= 0
            or type(identity.get("uid")) is not int
            or identity["uid"] < 0
            or identity.get("executable_state") != "AVAILABLE"
            or not isinstance(identity.get("executable"), str)
            or not identity["executable"]
        ):
            return False
        names.add(row["service"])
    return True


def validate_audit_scope(rows, process_summary, service_summary):
    if not isinstance(rows, (list, tuple)) or len(rows) != len(AUDIT_SCOPE_SECTIONS):
        return False
    for expected, row in zip(AUDIT_SCOPE_SECTIONS, rows):
        if (
            not isinstance(row, dict) or row.get("section") != expected
            or type(row.get("worker_pid")) is not int or row["worker_pid"] <= 1
            or "error" in row or not isinstance(row.get("result"), dict)
        ):
            return False
    p = rows[1]["result"]
    return (
        isinstance(process_summary, dict)
        and p.get("row_count") == process_summary.get("row_count")
        and p.get("rows_sha256") == process_summary.get("rows_sha256")
        and isinstance(service_summary, dict)
    )


def emit_row_chunks(prefix, kind, source, request, rows, rows_sha, chunk_size):
    total = (len(rows) + chunk_size - 1) // chunk_size
    for index in range(total):
        start = index * chunk_size
        chunk = rows[start:start + chunk_size]
        emit(prefix, {
            "schema": "NOX_AUDIT_ROWS_CHUNK_V1",
            "source_sha": source, "request_id": int(request),
            "kind": kind, "chunk_index": index, "chunk_count": total,
            "row_offset": start, "row_count": len(chunk),
            "complete_source_row_count": len(rows),
            "complete_source_rows_sha256": rows_sha,
            "chunk_sha256": json_sha256(chunk),
            "rows": chunk,
        })


def task_evidence(source, request, audit_rows, lock_receipt, gpu_receipt,
                  gate_receipts, process_summary, service_summary,
                  process_complete, services_complete, host_boot_id):
    def digest(value):
        return json_sha256(value)

    process_row = audit_rows[1]
    row_count = process_summary.get("row_count", 0)
    supervisor = service_summary.get("service_health", {})
    gpu_rows = gpu_receipt.get("inventory", {}).get("snapshots", [{}])[0].get("rows", [])
    tasks = [
        {
            "task_id": "2V14-02",
            "task_spec_sha256": TASK_SPEC_SHA256["2V14-02"],
            "state": "OBSERVED_BOUNDED"
            if process_complete and lock_receipt.get("state") in ("READ", "NO_LOCKS_PRESENT")
            else "HOLD",
            "criterion_fields": [
                "owner_id", "PID/start_ticks", "explicit STOP and maintenance markers",
                "/proc/locks cross-linked by device/inode/PID",
                "explicit no-lock result when table is empty",
            ],
            "evidence_sha256": digest({
                "process_inventory_summary": process_summary,
                "lock_receipt": lock_receipt, "gate_receipts": gate_receipts,
                "host_boot_id": host_boot_id, "source_sha": source,
                "request_id": int(request),
            }),
            "process_identity_row_count": row_count,
        },
        {
            "task_id": "2V14-12",
            "task_spec_sha256": TASK_SPEC_SHA256["2V14-12"],
            "state": "OBSERVED"
            if len(gpu_rows) == 2 and gpu_receipt.get("inventory", {}).get("boot_id") == host_boot_id
            else "HOLD",
            "criterion_fields": [
                "exactly two V100s", "unique UUIDs", "total/used/free VRAM arithmetic",
                "two successful stable monotonic snapshots on the same boot",
            ],
            "evidence_sha256": digest({
                "gpu_receipt": gpu_receipt, "gate_receipts": gate_receipts,
                "host_boot_id": host_boot_id, "source_sha": source,
                "request_id": int(request),
            }),
        },
        {
            "task_id": "6V14-02",
            "task_spec_sha256": TASK_SPEC_SHA256["6V14-02"],
            "state": "OBSERVED_COMPLETE"
            if process_complete and services_complete else "HOLD",
            "criterion_fields": [
                "complete nontruncated /proc UID/PID/start_ticks/exe census",
                "all identity rows verified with no unavailable rows",
                "full RUNNING supervisor service census with healthy status",
            ],
            "evidence_sha256": digest({
                "process_inventory_summary": process_summary,
                "service_census_summary": service_summary,
                "gate_receipts": gate_receipts, "host_boot_id": host_boot_id,
                "source_sha": source, "request_id": int(request),
            }),
            "process_identity_row_count": row_count,
            "service_row_count": service_summary.get("service_count", 0),
            "process_identity_complete": process_complete,
            "service_census_complete": services_complete,
            "service_health": supervisor.get("state", "UNKNOWN"),
        },
    ]
    return {
        "schema": "NOX_TASK_EVIDENCE_BINDING_V1",
        "composite_source_sha": source, "request_id": int(request),
        "github_owner_id": TASK_OWNER_ID, "host_boot_id": host_boot_id,
        "task_ids": ["2V14-02", "2V14-12", "6V14-02"],
        "task_spec_sha256": dict(TASK_SPEC_SHA256),
        "criterion_map": {
            "2V14-02": ["owner ID", "PID/start_ticks", "STOP markers",
                        "/proc/locks dev/inode/PID cross-links", "explicit no-lock result"],
            "2V14-12": ["two V100 model/UUID/VRAM snapshots"],
            "6V14-02": ["complete /proc identities", "full healthy supervisor census"],
        },
        "process_identity_rows_sha256": process_summary.get("rows_sha256"),
        "service_rows_sha256": service_summary.get("rows_sha256"),
        "evidence": tasks,
        "gate_receipt_count": len(gate_receipts),
        "acceptance_state": "EVIDENCE_ONLY_NOT_ACCEPTED",
        "acceptance_increment": 0,
    }


def main():
    global active_storage, active_lease_fd, active_lease
    source, request = owner_context()
    audit_ok = gpu_ok = locks_ok = False
    process_complete = services_complete = False
    lease_fd = None
    lease = None
    exit_code = 2
    pending_task_evidence = None
    release_succeeded = True
    lease_was_acquired = False
    gate_receipts = []
    storage = load_resource_gate(RESOURCE_HELPER_B64)
    print("NOX_MAINT_COMPOSITE_SOURCE_SHA=" + source, flush=True)
    print("NOX_MAINT_OWNER_REQUEST_ID=" + request, flush=True)
    print("NOX_MAINT_AUDIT_SOURCE_SHA=" + AUDIT_SOURCE_SHA, flush=True)
    print("NOX_MAINT_GPU_INVENTORY_SOURCE_SHA=" + GPU_SOURCE_SHA, flush=True)
    print("NOX_MAINT_RESOURCE_SOURCE_SHA=" + RESOURCE_SOURCE_SHA, flush=True)

    try:
        check_gate(storage)
        lease_fd, lease = acquire_owner_lease()
        lease_was_acquired = True
        active_storage, active_lease_fd, active_lease = storage, lease_fd, lease
        gate_receipts.append(emit_gate_snapshot("PRE_AUDIT", source, request, lease, storage))

        audit_module = load_audit_helper(AUDIT_HELPER_B64)
        gpu_module = load_gpu_helper(GPU_HELPER_B64)
        # The AST allowlist loads only the bounded identity and service census helpers.
        audit_module.MAX_PROC_ENTRIES = MAX_PROCESS_ROWS
        audit_module.run = audit_run

        process_summary = {}
        service_summary = {}
        audit_rows = ()
        process_rows = []
        service_rows = []
        try:
            gate_receipts.append(emit_gate_snapshot("PRE_AUDIT_HELPER_CALL", source, request, lease, storage))
            census = audit_module.gpu_process_census(run_fn=audit_run)
            hardware_result = audit_module.hardware(census)
            process_inventory = census.get("process_identity_inventory")
            services = census.get("supervisor_services")
            process_complete = validate_process_inventory(process_inventory)
            services_complete = validate_service_census(services)
            process_rows = process_inventory.get("rows", []) if isinstance(process_inventory, dict) else []
            service_rows = services.get("services", []) if isinstance(services, dict) else []
            process_summary = {
                "scope": "ALL_NUMERIC_PROC_PIDS_MINIMAL_IDENTITY",
                "complete": process_complete,
                "truncated": process_inventory.get("truncated") if isinstance(process_inventory, dict) else None,
                "entries_seen": process_inventory.get("entries_seen") if isinstance(process_inventory, dict) else None,
                "row_count": process_inventory.get("row_count") if isinstance(process_inventory, dict) else None,
                "cap": process_inventory.get("cap") if isinstance(process_inventory, dict) else None,
                "read_failure_count": process_inventory.get("read_failure_count") if isinstance(process_inventory, dict) else None,
                "rows_sha256": process_inventory.get("rows_sha256") if isinstance(process_inventory, dict) else None,
            }
            service_summary = {
                "complete": services_complete,
                "service_count": len(service_rows),
                "rows_sha256": json_sha256(service_rows),
                "service_health": services.get("service_health", {}) if isinstance(services, dict) else {},
                "inventory_complete": services.get("inventory_complete") if isinstance(services, dict) else None,
                "rows_complete": services.get("rows_complete") if isinstance(services, dict) else None,
                "identity_complete": services.get("identity_complete") if isinstance(services, dict) else None,
                "status_consistent": services.get("status_consistent") if isinstance(services, dict) else None,
                "truncated": services.get("truncated") if isinstance(services, dict) else None,
            }
            compact_hardware = {
                key: hardware_result.get(key)
                for key in ("gpu_rc", "gpu", "cpus", "load", "cgroup_max",
                            "cgroup_current", "cpu_max", "disk")
                if isinstance(hardware_result, dict) and key in hardware_result
            }
            compact_hardware["process_identity_summary"] = process_summary
            compact_hardware["supervisor_services_summary"] = service_summary
            audit_rows = (
                {"section": "hardware", "worker_pid": os.getpid(),
                 "result": compact_hardware},
                {"section": "process_identity_inventory", "worker_pid": os.getpid(),
                 "result": process_summary},
            )
            audit_ok = (
                process_complete and services_complete
                and isinstance(hardware_result, dict)
                and hardware_result.get("gpu_rc") == 0
                and bool(hardware_result.get("gpu"))
                and validate_audit_scope(audit_rows, process_summary, service_summary)
            )
            gate_receipts.append(emit_gate_snapshot("POST_AUDIT", source, request, lease, storage))
            if audit_ok:
                print(AUDIT_SCOPE_MARKER, flush=True)
                for row in audit_rows:
                    emit(AUDIT_PREFIX, row)
                emit_row_chunks(
                    PROCESS_CHUNK_PREFIX, "process_identity", source, request,
                    process_rows, process_summary["rows_sha256"], PROCESS_CHUNK_ROWS)
                emit_row_chunks(
                    SERVICE_CHUNK_PREFIX, "supervisor_service", source, request,
                    service_rows, service_summary["rows_sha256"], SERVICE_CHUNK_ROWS)
                print(AUDIT_SCOPE_COMPLETE, flush=True)
            else:
                emit("NOX_MAINT_AUDIT_RESULT=", {
                    "state": "HOLD_COMPOSITE_AUDIT_INCOMPLETE",
                    "process_identity_complete": process_complete,
                    "service_census_complete": services_complete,
                })
        except Hold as exc:
            emit("NOX_MAINT_AUDIT_RESULT=", {"state": str(exc)})
        except Exception as exc:
            emit("NOX_MAINT_AUDIT_RESULT=", {
                "state": "HOLD_COMPOSITE_AUDIT_" + type(exc).__name__.upper(),
            })

        lock_receipt = {"state": "HOLD_COMPOSITE_LOCKS_NOT_CAPTURED"}
        try:
            gate_receipts.append(emit_gate_snapshot("PRE_KERNEL_LOCKS", source, request, lease, storage))
            kernel_locks = capture_kernel_locks()
            lock_file = check_owner_lock_file(lease_fd, lease)
            matching_rows, own_read_locks = lease_kernel_lock_matches(kernel_locks, lease)
            if not kernel_locks.get("parse_complete"):
                raise Hold("HOLD_COMPOSITE_KERNEL_LOCKS_PARSE")
            if kernel_locks.get("row_count") == 0:
                lock_state = "NO_LOCKS_PRESENT"
                locks_ok = True
            elif own_read_locks:
                lock_state = "READ"
                locks_ok = True
            else:
                lock_state = "HOLD_COMPOSITE_LEASE_KERNEL_LOCK_UNVERIFIED"
                locks_ok = False
            lock_receipt = {
                "schema": "NOX_KERNEL_LOCKS_V1",
                "source_sha": source, "request_id": int(request),
                "github_owner_id": TASK_OWNER_ID,
                "host_boot_id": host_identity()["boot_id"],
                "native_pid": os.getpid(),
                "state": lock_state,
                "owner_maintenance_lock": lock_file,
                "lease_kernel_lock_match_count": len(matching_rows),
                "lease_kernel_lock_matches": matching_rows[:8],
                "own_shared_flock_match_count": len(own_read_locks),
                "own_shared_flock_matches": own_read_locks[:8],
                "kernel_locks": kernel_locks,
            }
            emit(LOCKS_PREFIX, lock_receipt)
        except Hold as exc:
            lock_receipt = {
                "schema": "NOX_KERNEL_LOCKS_V1",
                "source_sha": source, "request_id": int(request),
                "state": str(exc),
            }
            emit(LOCKS_PREFIX, lock_receipt)

        gpu_receipt = {}
        try:
            gate_receipts.append(emit_gate_snapshot("PRE_GPU", source, request, lease, storage))
            gpu_env = {
                **PROBE_ENV,
                "NOX_OWNER_ACTION": "gpu_inventory",
                "NOX_OWNER_INSTANCE_ID": str(INSTANCE_ID),
                "NOX_OWNER_SOURCE_SHA": GPU_SOURCE_SHA,
                "NOX_OWNER_REQUEST_ID": request,
            }
            gpu_receipt = gpu_module.run_action(env=gpu_env, run=gpu_run)
            gpu_lines = [
                GPU_PREFIX + json.dumps(gpu_receipt, sort_keys=True, separators=(",", ":")),
                GPU_COMPLETE,
            ]
            gpu_ok = validate_gpu(0, gpu_lines, request)
            gate_receipts.append(emit_gate_snapshot("POST_GPU", source, request, lease, storage))
            if gpu_ok:
                emit(GPU_PREFIX, gpu_receipt)
                print(GPU_COMPLETE, flush=True)
            else:
                emit(GPU_RESULT_PREFIX, "HOLD_COMPOSITE_GPU_RESULT")
        except Hold as exc:
            emit(GPU_RESULT_PREFIX, str(exc))
            gpu_receipt = {}
        except Exception as exc:
            emit(GPU_RESULT_PREFIX,
                 "HOLD_COMPOSITE_GPU_" + type(exc).__name__.upper())
            gpu_receipt = {}

        if audit_ok and gpu_ok:
            pending_task_evidence = task_evidence(
                source, request, audit_rows, lock_receipt, gpu_receipt,
                gate_receipts, process_summary, service_summary,
                process_complete, services_complete, host_identity()["boot_id"])
            if locks_ok:
                exit_code = 0
    except Hold as exc:
        emit("NOX_MAINT_AUDIT_RESULT=", {"state": str(exc)})
        emit(GPU_RESULT_PREFIX, str(exc))
        exit_code = 2
    finally:
        if lease_fd is not None:
            try:
                check_owner_lock_file(lease_fd, lease)
                release_owner_lease(lease_fd)
                print("NOX_MAINT_OWNER_LEASE_RELEASE=RELEASED", flush=True)
            except OSError:
                try:
                    os.close(lease_fd)
                except OSError:
                    pass
                print("NOX_MAINT_OWNER_LEASE_RELEASE=HOLD_RELEASE_FAILED", flush=True)
                release_succeeded = False
                exit_code = 2
            except Hold:
                try:
                    os.close(lease_fd)
                except OSError:
                    pass
                print("NOX_MAINT_OWNER_LEASE_RELEASE=HOLD_LEASE_IDENTITY", flush=True)
                release_succeeded = False
                exit_code = 2

    active_lease_fd, active_lease = None, None
    emit(CLEANUP_PREFIX, {
        "schema": "NOX_COMPOSITE_CLEANUP_V1",
        "temporary_staging_used": False,
        "temporary_artifacts_created": 0,
        "temporary_artifacts_removed": 0,
        "state": "NO_TEMP_FILES_CREATED",
        "owner_lease_release": (
            "RELEASED" if lease_was_acquired and release_succeeded
            else "NOT_ACQUIRED" if not lease_was_acquired else "HOLD_RELEASE_FAILED"
        ),
    })
    if pending_task_evidence is not None and release_succeeded:
        emit(TASK_EVIDENCE_PREFIX, pending_task_evidence)
    if exit_code == 0 and release_succeeded:
        print(COMPOSITE_COMPLETE, flush=True)
        return 0
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
