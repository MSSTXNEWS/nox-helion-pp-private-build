#!/usr/bin/env python3
"""Bounded, owner-pinned release of verified inactive NOX file-cache pages.

One-shot; no dispatcher, chat, model, training, weight, S03 or supervisor writes.
Reuse the storage candidate census, then advise only exact closed file ranges.
"""
from __future__ import annotations

import base64
from collections import Counter
import ctypes
import fcntl
import hashlib
import importlib.util
import json
import mmap
import os
from pathlib import Path
import re
import stat
import tempfile
import time

ROOT = Path("/root/nox")
AREA = ROOT / "state/owner_storage"
SAFE = {"PIP_DOWNLOAD_CACHE", "PIP_WHEEL_CACHE", "OLD_DEBUG_LOG_ROTATION",
        "INACTIVE_DEBUG_LOG_ROTATION"}
DISK_FILESYSTEMS = {"ext4", "xfs", "btrfs", "overlay", "zfs"}
STOP_MARKERS = ("STOP", "STOP.flag", "stop.flag", ".stop", "program/STOP", "state/STOP",
                "state/STOP.flag", "state/OWNER_MAINTENANCE.flag")
PAGE_BYTES = os.sysconf("SC_PAGE_SIZE")
FILE_RANGE_BYTES = 128 * 1024**2
TOTAL_RANGE_BYTES = 2 * 1024**3
TARGET_HEADROOM_BYTES = 8 * 1024**3
try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}


def require(yes, code):
    if not yes:
        raise RuntimeError("HOLD_MEMORY_OWNER_" + code)


def decode(name):
    require(isinstance(BUNDLE, dict) and name in BUNDLE, "BUNDLE_MISSING")
    raw = base64.b64decode(BUNDLE[name], validate=True)
    require(len(raw) <= 1024*1024 and raw and
            b"\x00" not in raw, "BUNDLE_BYTES")
    compile(raw, name, "exec")
    return raw


def require_stop_clear():
    require(not any(os.path.lexists(ROOT / marker) for marker in STOP_MARKERS)
            and not os.path.lexists("/workspace/NOX_STOP"), "STOP")


def require_disk_filesystem(fd):
    with open(f"/proc/self/fdinfo/{fd}", "rb") as stream:
        raw = stream.read(4097)
    ids = re.findall(rb"(?m)^mnt_id:\s+([0-9]+)$", raw)
    require(len(raw) <= 4096 and len(ids) == 1, "FD_MOUNT_ID")
    with open("/proc/self/mountinfo", "rb") as stream:
        raw = stream.read(1024**2 + 1)
    require(len(raw) <= 1024**2, "MOUNTINFO_SIZE")
    filesystems = []
    for line in raw.splitlines():
        left, separator, right = line.partition(b" - ")
        fields = left.split(maxsplit=1)
        details = right.split(maxsplit=1)
        if separator and fields and details and fields[0] == ids[0]:
            filesystems.append(details[0].decode("ascii"))
    require(len(filesystems) == 1 and filesystems[0] in DISK_FILESYSTEMS,
            "FILE_NOT_ON_ALLOWLISTED_DISK_FILESYSTEM")


def resident_bytes(fd, offset, length):
    """Use a no-access mapping to count resident pages without reading them."""
    require(0 < length <= FILE_RANGE_BYTES and length % PAGE_BYTES == 0
            and offset > 0 and offset % PAGE_BYTES == 0, "RESIDENCY_RANGE")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mmap.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
                           ctypes.c_int, ctypes.c_int, ctypes.c_long)
    libc.mmap.restype = ctypes.c_void_p
    libc.mincore.argtypes = (ctypes.c_void_p, ctypes.c_size_t,
                             ctypes.POINTER(ctypes.c_ubyte))
    libc.munmap.argtypes = (ctypes.c_void_p, ctypes.c_size_t)
    libc.mincore.restype = libc.munmap.restype = ctypes.c_int
    bitmap = (ctypes.c_ubyte * (length // PAGE_BYTES))()
    address = libc.mmap(None, length, 0, mmap.MAP_PRIVATE, fd, offset)
    require(address not in (None, ctypes.c_void_p(-1).value), "RESIDENCY_MMAP")
    try:
        require(libc.mincore(address, length, bitmap) == 0, "RESIDENCY_MINCORE")
    finally:
        require(libc.munmap(address, length) == 0, "RESIDENCY_MUNMAP")
    return PAGE_BYTES * sum(flag & 1 for flag in bitmap)


def advise_candidate(storage, candidate, deadline, remaining):
    path = Path(candidate["path"])
    match = storage.cache_advice_kind(path)
    require(match is not None and match[0] in SAFE, "FILE_SCOPE")
    parent = storage.open_parent(path)
    fd = None
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                     dir_fd=parent)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and storage.identity(info) == candidate["identity"],
                "FILE_IDENTITY")
        require_disk_filesystem(fd)
        # The census excludes only this action's descriptor. Other open or
        # mapped copies of the inode still protect the file.
        usage = storage.process_usage(min(deadline, time.monotonic() + 4),
                                      ignore_fd=(os.getpid(), str(fd)))
        current, _ = storage.qualify(path, info, time.time(), usage, cache_only=True)
        require(current is not None and current == candidate
                and storage.digest_bytes(os.pread(fd, 32, 0)) == candidate["prefix_sha256"],
                "FILE_IN_USE_OR_CHANGED")
        # Keep the header page and any partial final page out of the sample.
        length = min(info.st_size - PAGE_BYTES, FILE_RANGE_BYTES, remaining)
        length -= length % PAGE_BYTES
        require(length > 0, "FILE_RANGE")
        before = resident_bytes(fd, PAGE_BYTES, length)
        require(time.monotonic() < deadline, "TIME_BUDGET")
        require_stop_clear()
        require(storage.identity(os.fstat(fd)) == candidate["identity"]
                and storage.identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False))
                == candidate["identity"], "FILE_IDENTITY")
        if before:
            os.posix_fadvise(fd, PAGE_BYTES, length, os.POSIX_FADV_DONTNEED)
        after = resident_bytes(fd, PAGE_BYTES, length)
        require(storage.identity(os.fstat(fd)) == candidate["identity"]
                and storage.identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False))
                == candidate["identity"], "FILE_POST_IDENTITY")
        return {"attempted_range_bytes": length if before else 0,
                "observed_resident_before_bytes": before,
                "observed_resident_after_bytes": after,
                "observed_residency_reduction_bytes": max(0, before - after)}
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def memory_counters(sample):
    limit = sample["limit_bytes"]
    require(isinstance(limit, int) and limit > 0, "CGROUP_LIMIT")
    return {"current_bytes": sample["memory_bytes"], "limit_bytes": limit,
            "headroom_bytes": limit - sample["memory_bytes"],
            "inactive_file_bytes": sample["inactive_file_bytes"],
            "shmem_bytes": sample["shmem_bytes"], "anon_bytes": sample["anon_bytes"],
            "memory_psi": sample["memory_psi"],
            "oom": sample["events"]["oom"], "oom_kill": sample["events"]["oom_kill"]}


def release_candidates(storage, governor, audit):
    candidates = audit["cache_advice_candidates"]
    require(audit["process_scan"]["complete"] is True, "INCOMPLETE_PROCESS_CENSUS")
    require(all(candidate["category"] in SAFE for candidate in candidates), "FILE_SCOPE")
    deadline = time.monotonic() + 35
    results = []
    totals = Counter()
    with storage.reclaim_locks():
        require_stop_clear()
        before = memory_counters(governor.sample())
        live = before
        remaining = TOTAL_RANGE_BYTES
        for candidate in candidates[:32]:
            if (remaining < PAGE_BYTES or time.monotonic() >= deadline
                    or live["headroom_bytes"] >= TARGET_HEADROOM_BYTES):
                break
            limit = min(remaining, FILE_RANGE_BYTES, candidate["identity"][2])
            # Reserve the range before the syscall, including when its
            # post-measurement fails and no exact effect can be reported.
            remaining -= limit
            try:
                result = advise_candidate(storage, candidate, deadline, limit)
            except (OSError, RuntimeError) as error:
                reason = str(error)
                results.append({"path_id": candidate["path_id"],
                                "state": reason if re.fullmatch(r"HOLD_[A-Z_]+", reason)
                                else "HOLD_MEMORY_OWNER_CACHE_ADVICE_OS_ERROR"})
                if reason in ("HOLD_MEMORY_OWNER_STOP", "HOLD_MEMORY_OWNER_TIME_BUDGET"):
                    break
            else:
                totals.update(result)
                results.append({"path_id": candidate["path_id"], **result})
            live = memory_counters(governor.sample())
            if (live["oom"], live["oom_kill"]) != (before["oom"], before["oom_kill"]):
                break
        after = memory_counters(governor.sample())
    reduction = totals["observed_residency_reduction_bytes"]
    if reduction:
        state = "FILE_CACHE_RESIDENCY_REDUCED"
    elif not candidates:
        state = "NO_ELIGIBLE_FILE_CACHE_RANGES"
    elif not results and before["headroom_bytes"] >= TARGET_HEADROOM_BYTES:
        state = "REQUESTED_CGROUP_HEADROOM_PRESENT"
    else:
        state = "NO_FILE_CACHE_REDUCTION_OBSERVED"
    return {"state": state, "verified_candidate_count": len(candidates),
            "attempted_range_bytes": totals["attempted_range_bytes"],
            "target_headroom_bytes": TARGET_HEADROOM_BYTES,
            "maximum_advice_range_bytes": TOTAL_RANGE_BYTES,
            "page_cache_residency_reduction_bytes": reduction, "before": before, "after": after,
            "observed_cgroup_headroom_delta_bytes": after["headroom_bytes"] - before["headroom_bytes"],
            "cgroup_delta_includes_other_processes": True, "results": results}


def deleted_open_census():
    """Bounded aggregate of unlinked-but-open inodes, without path/PID export."""
    proc = Path("/proc")
    classes = {key: set() for key in ("MEMFD_SHMEM", "NOX_SSD", "TMPFS_SHM", "OTHER")}
    total = {key:0 for key in classes}
    counts = {key:0 for key in classes}
    incomplete, fds = False, 0
    root_device, shm_device = ROOT.stat().st_dev, Path("/dev/shm").stat().st_dev
    try:
        pids = [x.name for x in os.scandir(proc) if x.name.isdecimal()]
        if len(pids) > 2048:
            incomplete = True
            pids = pids[:2048]
        for pid in pids:
            try:
                for fd in os.scandir(proc / pid / "fd"):
                    fds += 1
                    if fds > 40000:
                        incomplete = True
                        break
                    try:
                        link = os.readlink(fd.path)
                        if not link.endswith(" (deleted)"):
                            continue
                        info = os.stat(fd.path)
                        if not stat.S_ISREG(info.st_mode):
                            continue
                        key = (info.st_dev, info.st_ino)
                        category = ("MEMFD_SHMEM" if link.startswith(("memfd:", "/memfd:")) else
                                    "NOX_SSD" if info.st_dev == root_device else
                                    "TMPFS_SHM" if info.st_dev == shm_device else "OTHER")
                        if key not in classes[category]:
                            classes[category].add(key)
                            total[category] += max(0, info.st_blocks * 512)
                            counts[category] += 1
                    except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
                        continue
                if incomplete:
                    break
            except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
                incomplete = True
    except OSError:
        incomplete = True
    return {"schema": "NOX_OWNER_DELETED_OPEN_AGGREGATE_V1",
            "allocated_bytes_by_device": total, "unique_inodes_by_device":counts,
            "observed_fd_count":fds, "scan_complete":not incomplete,
            "no_file_paths_or_process_ids_exported":True,
            "reclaim_requires_exact_process_handoff_not_killall":True}


def go():
    request = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    commit = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    require(re.fullmatch(r"[0-9]{1,20}", request)
            and re.fullmatch(r"[0-9a-f]{40}", commit), "OWNER_CONTEXT")
    require_stop_clear()
    require(AREA.is_dir() and not AREA.is_symlink(), "AREA")
    info = AREA.stat()
    require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) & 0o022 == 0,
            "AREA_OWNER")
    governor_raw = decode("owner_memory_governor.py")
    storage_raw = decode("owner_storage_reclaim.py")
    # The governor remains purely observational.
    govern_path = AREA / ("memory_governor_" + request + ".py")
    require(not govern_path.exists() and not govern_path.is_symlink(), "GOVERNOR_COLLISION")
    fd = os.open(govern_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    staged = None
    try:
        with os.fdopen(fd, "wb") as dst:
            dst.write(governor_raw); dst.flush(); os.fsync(dst.fileno())
        require(hashlib.sha256(govern_path.read_bytes()).digest()
                == hashlib.sha256(governor_raw).digest(), "GOVERNOR_READBACK")
        spec = importlib.util.spec_from_file_location("nox_temp_memory_governor", govern_path)
        g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(g)
        before = g.sample()
        decision = g.decide(before)
        deleted_open = deleted_open_census()
        print("NOX_MAINT_MEMORY_DELETED_OPEN=" + json.dumps(
            deleted_open, separators=(",", ":"), allow_nan=False), flush=True)
        # A new native sibling process is not an always-on daemon.
        print("NOX_MAINT_MEMORY_CGROUP=" + json.dumps(
            {"schema": before["schema"], "memory_bytes": before["memory_bytes"],
             "limit_bytes": before["limit_bytes"], "anon_bytes": before["anon_bytes"],
             "shmem_bytes": before["shmem_bytes"],
             "inactive_file_bytes": before["inactive_file_bytes"],
             "reclaimable_file_estimate_bytes":
                 before["reclaimable_file_estimate_bytes"],
             "memory_psi": before["memory_psi"], "decision": decision},
            separators=(",", ":"), allow_nan=False), flush=True)
        require_stop_clear()
        # The original audit stores helper_sha256 derived from __file__.
        # An ephemeral, mode-0600 copy is necessary for its exact self-pin.
        fd, path = tempfile.mkstemp(prefix=".owner-storage-source-",
                                    suffix=".py", dir=AREA)
        staged = Path(path)
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(storage_raw)
            output.flush(); os.fsync(output.fileno())
        require(hashlib.sha256(staged.read_bytes()).digest()
                == hashlib.sha256(storage_raw).digest(), "STORAGE_READBACK")
        spec = importlib.util.spec_from_file_location("nox_temp_storage_reclaim", staged)
        storage = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(storage)
        audit = storage.audit(request, commit, cache_only=True)
        audit_path = storage.receipt_directory() / ("ram_cache_audit_" + request + ".json")
        audit_sha = storage.write_receipt(audit_path, audit)
        require(audit.get("files_deleted") == 0 and
                audit.get("helper_sha256") == hashlib.sha256(storage_raw).hexdigest(),
                "AUDIT_SCOPE")
        print("NOX_MAINT_MEMORY_DISK_AUDIT=" + json.dumps({
            **storage.public_summary(audit), "receipt_sha256": audit_sha},
            separators=(",", ":"), allow_nan=False), flush=True)
        result = release_candidates(storage, g, audit)
        partial = any(row.get("complete") is not True
                      for row in audit.get("coverage", []))
        print("NOX_MAINT_MEMORY_FINAL=" + json.dumps({
            **result,
            "schema":"NOX_FILE_CACHE_RELEASE_RECEIPT_V1",
            "owner_source_sha":commit, "request":request,
            "cache_audit_coverage_partial":partial,
            "cgroup_proactive_reclaim_executed":False,
            "global_drop_caches_executed":False,
            "model_or_training_restarted":False,
            "files_deleted":0,
            "weights_or_S03_modified_by_action":False,
            "cache_audit_receipt_sha256":audit_sha,
            "finished_at":time.time()},
            separators=(",", ":"), allow_nan=False),flush=True)
        print("NOX_MAINT_REPAIR_COMPLETE=true", flush=True)
    finally:
        if staged is not None and staged.exists():
            staged.unlink()
        if govern_path.exists():
            govern_path.unlink()


if __name__ == "__main__":
    go()
