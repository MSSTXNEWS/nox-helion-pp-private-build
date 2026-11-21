#!/usr/bin/env python3
"""Bounded, owner-pinned NOX memory/storage cleanup through existing transport.

One-shot; no dispatcher, chat, model, training, weight, S03 or supervisor writes.
AUDIT -> revalidate exact fresh SHA receipt -> reclaim only allowlisted
unused ephemeral files, using the existing owner_storage_reclaim implementation.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time

ROOT = Path("/root/nox")
AREA = ROOT / "state/owner_storage"
ACTION = "AUDIT_THEN_EXACT_EPHEMERAL_RECLAIM"
SAFE = {"PIP_DOWNLOAD_CACHE", "PIP_WHEEL_CACHE", "OLD_DEBUG_LOG_ROTATION",
        "INACTIVE_ELF_CORE"}
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
    require(not any((ROOT / p).exists() or (ROOT / p).is_symlink()
                    for p in ("STOP", "STOP.flag", "stop.flag", ".stop",
                              "state/STOP", "state/STOP.flag")), "STOP")
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
        require(not any((ROOT/p).exists() or (ROOT/p).is_symlink()
                        for p in ("STOP", "state/STOP")), "STOP_CHANGED")
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
        audit = storage.audit(request, commit)
        audit_path = storage.receipt_directory() / ("audit_" + request + ".json")
        audit_sha = storage.write_receipt(audit_path, audit)
        require(audit.get("files_deleted") == 0 and
                audit.get("helper_sha256") == hashlib.sha256(storage_raw).hexdigest(),
                "AUDIT_SCOPE")
        print("NOX_MAINT_MEMORY_DISK_AUDIT=" + json.dumps({
            **storage.public_summary(audit), "receipt_sha256": audit_sha},
            separators=(",", ":"), allow_nan=False), flush=True)
        candidates = audit.get("cleanup_candidates", [])
        safe = (audit.get("process_scan", {}).get("complete") is True
                and all(row.get("category") in SAFE for row in candidates))
        page_cache_result = None
        # A full directory inventory is not required to delete a specific
        # already-audited regular file: the existing reclaim() rechecks its
        # inode, mode, age, open/mmap use, prefix digest and process census.
        # Still report partial coverage; never claim a complete disk audit.
        partial = any(row.get("complete") is not True
                      for row in audit.get("coverage", []))
        require(safe or not candidates, "INCOMPLETE_PROCESS_CENSUS")
        if candidates:
            require(not any((ROOT/p).exists() or (ROOT/p).is_symlink()
                            for p in ("STOP", "state/STOP")), "STOP_RECHECK")
            limit = before.get("limit_bytes")
            memory = before.get("memory_bytes")
            headroom = (max(0, limit - memory)
                        if type(limit) is int and type(memory) is int else None)
            if headroom is not None and headroom < 4 * 1024**3:
                # Below the browser runtime 4 GiB memory prerequisite, evict only
                # clean cache hints from the exact cold, non-model candidates.
                # Keep those files intact; no unlink, kill, model unload or restart.
                page_cache_result = storage.reclaim_page_cache(
                    request, commit, request, audit_sha)
                print("NOX_MAINT_MEMORY_PAGE_CACHE=" + json.dumps(
                    storage.public_summary(page_cache_result),
                    separators=(",", ":"), allow_nan=False), flush=True)
                print("NOX_MAINT_MEMORY_DISK_RECLAIM=" + json.dumps({
                    "state":"SKIPPED_BELOW_4_GIB_BROWSER_MEMORY_PREREQUISITE",
                    "files_deleted":0,"weight_bytes_deleted":0,
                    "checkpoint_bytes_deleted":0,
                    "source_memory_credentials_bytes_deleted":0}), flush=True)
            else:
                # Existing tool checks exact inode identity, age, open/mapped
                # status, second process census, SHA receipt, lease and candidates.
                result = storage.reclaim(request, commit, request, audit_sha)
                print("NOX_MAINT_MEMORY_DISK_RECLAIM=" + json.dumps(
                    storage.public_summary(result), separators=(",", ":"),
                    allow_nan=False), flush=True)
        else:
            print("NOX_MAINT_MEMORY_DISK_RECLAIM=" + json.dumps({
                "state":"NO_ELIGIBLE_EPHEMERAL_FILES", "files_deleted":0,
                "weight_bytes_deleted":0,"checkpoint_bytes_deleted":0,
                "source_memory_credentials_bytes_deleted":0}), flush=True)
        after = g.sample()
        print("NOX_MAINT_MEMORY_FINAL=" + json.dumps({
            "schema":"NOX_MEMORY_SAFE_CLEANUP_RECEIPT_V1",
            "state":"BOUNDED_AUDIT_AND_CLEANUP_COMPLETE",
            "owner_source_sha":commit, "request":request,
            "memory_before_bytes":before["memory_bytes"],
            "memory_after_bytes":after["memory_bytes"],
            "memory_delta_includes_other_processes":True,
            "disk_audit_coverage_partial":partial,
            "cgroup_proactive_reclaim_executed":False,
            "exact_file_page_cache_advice_executed":bool(page_cache_result and
                page_cache_result.get("advised_files")),
            "page_cache_reclaimed_bytes_claimed":0,
            "native_admission_floor_bytes":2 * 1024**3,
            "native_job_admitted":False,
            "browser_runtime_memory_floor_bytes":4 * 1024**3,
            "browser_runtime_disk_floor_bytes":7 * 1024**3,
            "browser_runtime_admitted":False,
            "browser_disk_prerequisite_checked":False,
            "global_drop_caches_executed":False,
            "model_or_training_restarted":False,
            "weights_or_S03_modified_by_action":False,
            "ephemeral_file_cleanup_receipt_sha256":audit_sha,
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
