#!/usr/bin/env python3
"""Owner-authenticated, read-only census for the exact Engram memfd holder.

This action never writes host state, signals a process, or calls Supervisor.
It emits only stable process identifiers, hashes, counts and memfd metadata.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

SCHEMA = "NOX_OWNER_ENGRAM_MEMFD_AUDIT_V1"
HOLDER_SCRIPT_BASENAME = b"engram_memfd_holder.py"
MEMFD_LABEL = "memfd:engram_iq3xxs (deleted)"
MEMFD_SIZE = 75_266_239_716

MAX_PROC_ENTRIES = 8192
MAX_CMDLINE_BYTES = 16 * 1024
MAX_STAT_BYTES = 8192
MAX_CGROUP_BYTES = 8192
MAX_FD_ENTRIES_PER_PID = 512
MAX_FD_ENTRIES_TOTAL = 8192
MAX_FD_LINK_BYTES = 4096
MAX_FD_BYTES_TOTAL = 1024 * 1024
MAX_CMDLINE_BYTES_TOTAL = 8 * 1024 * 1024
MAX_MAPS_BYTES_PER_PID = 1024 * 1024
MAX_MAPS_BYTES_TOTAL = 8 * 1024 * 1024
MAX_MAPS_LINES_TOTAL = 65536
SHA40 = re.compile(r"^[0-9a-f]{40}$")
IDENTITY_HOLD_ALLOWLIST = {
    "HOLD_PROC_STAT_IDENTITY", "HOLD_PROC_STAT_FIELDS", "HOLD_READ_LIMIT",
    "HOLD_HOLDER_SCRIPT_SHAPE", "HOLD_HOLDER_PATH_IDENTITY",
    "HOLD_HOLDER_EXECUTABLE_SHAPE", "HOLD_HOLDER_CGROUP_UNAVAILABLE",
    "HOLD_HOLDER_IDENTITY_UNSTABLE",
}
HISTORICAL_HOLDER_PID_PRIORITY = 498569
MODEL_PID_PRIORITY = 3266857
MAP_LINE = re.compile(
    rb"^([0-9a-fA-F]+)-([0-9a-fA-F]+)\s+([rwxps-]{4})\s+"
    rb"([0-9a-fA-F]+)\s+([0-9a-fA-F]+):([0-9a-fA-F]+)\s+"
    rb"([0-9]+)(?:\s+(.*))?$"
)


class Hold(RuntimeError):
    def __init__(self, reason: str, diagnostics: dict | None = None):
        super().__init__(reason)
        self.diagnostics = diagnostics or {}


LAST_SCAN = {}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitized_identity_failure(exc: BaseException) -> str:
    if isinstance(exc, Hold) and str(exc) in IDENTITY_HOLD_ALLOWLIST:
        return str(exc)
    return "HOLD_HOLDER_IDENTITY_UNREADABLE"


def _read(path: Path, limit: int) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                 getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    finally:
        os.close(fd)
    if len(raw) > limit:
        raise Hold("HOLD_READ_LIMIT")
    return raw


def _script_path_token(argv: bytes) -> bytes | None:
    matches = [part for part in argv.split(b"\0") if
               part.rsplit(b"/", 1)[-1] == HOLDER_SCRIPT_BASENAME]
    return matches[0] if len(matches) == 1 else None


def proc_identity(proc_root: Path, pid: int) -> dict:
    base = proc_root / str(pid)
    raw = _read(base / "stat", MAX_STAT_BYTES).decode("ascii", "strict")
    prefix = str(pid) + " ("
    end = raw.rfind(") ")
    if not raw.startswith(prefix) or end < len(prefix):
        raise Hold("HOLD_PROC_STAT_IDENTITY")
    fields = raw[end + 2:].split()
    if len(fields) < 20 or not fields[19].isdecimal():
        raise Hold("HOLD_PROC_STAT_FIELDS")
    ticks = int(fields[19])
    argv = _read(base / "cmdline", MAX_CMDLINE_BYTES)
    script_token = _script_path_token(argv)
    if script_token is None:
        raise Hold("HOLD_HOLDER_SCRIPT_SHAPE")
    try:
        exe = os.readlink(base / "exe").encode("utf-8", "surrogateescape")
        cwd = os.readlink(base / "cwd").encode("utf-8", "surrogateescape")
    except OSError as exc:
        raise Hold("HOLD_HOLDER_PATH_IDENTITY") from exc
    exe_name = Path(os.fsdecode(exe).removesuffix(" (deleted)")).name
    if exe_name not in {
            "python", "python3", "python3.11", "python3.12", "python3.13"}:
        raise Hold("HOLD_HOLDER_EXECUTABLE_SHAPE")
    try:
        cgroup = _read(base / "cgroup", MAX_CGROUP_BYTES)
    except (OSError, Hold) as exc:
        raise Hold("HOLD_HOLDER_CGROUP_UNAVAILABLE") from exc
    ticks_after = _parse_start_ticks(_read(base / "stat", MAX_STAT_BYTES), pid)
    if ticks_after != ticks:
        raise Hold("HOLD_HOLDER_IDENTITY_UNSTABLE")
    return {
        "pid": pid,
        "start_ticks": ticks,
        "ppid": int(fields[1]),
        "pgrp": int(fields[2]),
        "exe_path_sha256": digest(exe),
        "argv_sha256": digest(argv),
        "script_path_sha256": digest(script_token),
        "cwd_sha256": digest(cwd),
        "cgroup_sha256": digest(cgroup),
    }


def proc_pid_order(proc_root: Path) -> tuple[list[int], int]:
    pids: list[int] = []
    scanned = 0
    try:
        with os.scandir(proc_root) as entries:
            for entry in entries:
                if not entry.name.isdecimal():
                    continue
                scanned += 1
                LAST_SCAN["proc_entries_seen"] = scanned
                if scanned > MAX_PROC_ENTRIES:
                    LAST_SCAN["proc_table_truncated"] = True
                    raise Hold("HOLD_PROC_TABLE_LIMIT")
                pids.append(int(entry.name))
    except OSError as exc:
        LAST_SCAN["proc_table_unreadable"] = 1
        raise Hold("HOLD_PROC_TABLE_UNAVAILABLE") from exc
    pids.sort(key=lambda pid: (pid not in (HISTORICAL_HOLDER_PID_PRIORITY,
                                          MODEL_PID_PRIORITY),
                               0 if pid == HISTORICAL_HOLDER_PID_PRIORITY else
                               1 if pid == MODEL_PID_PRIORITY else 2, pid))
    return pids, scanned


def fd_memfd_identity(proc_root: Path, pid: int, budget: dict) -> dict:
    fd_dir = proc_root / str(pid) / "fd"
    matches = []
    entries = 0
    unreadable = 0
    label_size_mismatch = 0
    try:
        with os.scandir(fd_dir) as rows:
            for row in rows:
                entries += 1
                budget["entries"] += 1
                if entries > MAX_FD_ENTRIES_PER_PID or budget["entries"] > MAX_FD_ENTRIES_TOTAL:
                    raise Hold("HOLD_FD_CENSUS_LIMIT")
                try:
                    target = os.readlink(row.path)
                    encoded = os.fsencode(target)
                    if len(encoded) > MAX_FD_LINK_BYTES:
                        raise Hold("HOLD_FD_LINK_LIMIT")
                    budget["bytes"] += len(encoded)
                    if budget["bytes"] > MAX_FD_BYTES_TOTAL:
                        raise Hold("HOLD_FD_BYTE_LIMIT")
                    info = os.stat(row.path)
                except FileNotFoundError:
                    budget["fd_races"] += 1
                    continue
                except OSError:
                    unreadable += 1
                    continue
                label = target.rsplit("/", 1)[-1]
                if label == MEMFD_LABEL:
                    if info.st_size != MEMFD_SIZE:
                        label_size_mismatch += 1
                        continue
                    if not stat.S_ISREG(info.st_mode):
                        unreadable += 1
                        continue
                    try:
                        target_after = os.readlink(row.path)
                        info_after = os.stat(row.path)
                    except FileNotFoundError:
                        budget["fd_races"] += 1
                        continue
                    except OSError:
                        unreadable += 1
                        continue
                    encoded_after = os.fsencode(target_after)
                    if len(encoded_after) > MAX_FD_LINK_BYTES:
                        raise Hold("HOLD_FD_LINK_LIMIT")
                    budget["bytes"] += len(encoded_after)
                    if budget["bytes"] > MAX_FD_BYTES_TOTAL:
                        raise Hold("HOLD_FD_BYTE_LIMIT")
                    before_sig = (info.st_dev, info.st_ino, info.st_size, info.st_mode)
                    after_sig = (info_after.st_dev, info_after.st_ino,
                                 info_after.st_size, info_after.st_mode)
                    if target_after != target or before_sig != after_sig:
                        unreadable += 1
                        continue
                    matches.append({"fd_number": int(row.name), "device": int(info.st_dev),
                                    "inode": int(info.st_ino), "size_bytes": int(info.st_size),
                                    "label_sha256": digest(label.encode())})
    except Hold:
        raise
    except OSError:
        if not (proc_root / str(pid)).exists():
            return {"status": "VANISHED", "entries_scanned": entries,
                    "matching_fd_count": 0, "unreadable_entries": unreadable,
                    "label_size_mismatch_count": label_size_mismatch,
                    "identity_count": 0, "matches": []}
        return {"status": "UNREADABLE", "entries_scanned": entries,
                "matching_fd_count": 0, "unreadable_entries": unreadable + 1,
                "label_size_mismatch_count": label_size_mismatch,
                "identity_count": 0, "matches": []}
    identities = {(row["device"], row["inode"], row["size_bytes"], row["label_sha256"])
                  for row in matches}
    return {"status": "OK" if unreadable == 0 else "PARTIAL",
            "entries_scanned": entries, "matching_fd_count": len(matches),
            "unreadable_entries": unreadable,
            "label_size_mismatch_count": label_size_mismatch,
            "identity_count": len(identities), "matches": matches}


def _maps_memfd_rows(raw: bytes, device: int | None,
                     expected_inode: int | None) -> tuple[list[dict], bool, int]:
    rows: list[dict] = []
    expected_device = ((os.major(device), os.minor(device))
                       if device is not None else None)
    scanned = 0
    consumed = 0
    truncated = False
    for line in raw.splitlines(keepends=True):
        scanned += 1
        consumed += len(line)
        if len(line) > 4096:
            truncated = True
            break
        match = MAP_LINE.match(line.rstrip(b"\n"))
        if not match:
            continue
        _start, _end, perms, offset, maj, min_, inode, path = match.groups()
        label = (path or b"").decode("utf-8", "replace")
        observed_device = (int(maj, 16), int(min_, 16))
        observed_inode = int(inode)
        label_is_target = label in (MEMFD_LABEL, "/" + MEMFD_LABEL)
        inode_is_target = expected_inode is not None and observed_inode == expected_inode
        if not (label_is_target or inode_is_target):
            continue
        if (expected_device is not None and observed_device != expected_device) or (
                expected_inode is not None and observed_inode != expected_inode):
            raise Hold("HOLD_MEMFD_MAP_IDENTITY_MISMATCH")
        if not label_is_target:
            raise Hold("HOLD_MEMFD_MAP_LABEL_MISMATCH")
        rows.append({"permissions": perms.decode("ascii"),
                     "offset_bytes": int(offset, 16),
                     "inode": observed_inode,
                     "device": os.makedev(*observed_device),
                     "mapping_size_bytes": int(_end, 16) - int(_start, 16),
                     "path_kind": "EXACT_ENGRAM_MEMFD"})
    return rows, truncated, consumed


def maps_census(proc_root: Path, memfd_device: int | None,
                memfd_inode: int | None) -> dict:
    process_count = 0
    scanned_bytes = 0
    scanned_lines = 0
    skipped_vanished = 0
    matches: list[dict] = []
    truncated = False
    LAST_SCAN.update({"maps_processes_scanned": 0, "maps_bytes_scanned": 0,
                      "maps_lines_scanned": 0, "maps_vanished_during_read": 0,
                      "maps_unreadable_pids": 0, "maps_truncated": False})
    try:
        with os.scandir(proc_root) as entries:
            for entry in entries:
                if not entry.name.isdecimal():
                    continue
                process_count += 1
                LAST_SCAN["maps_processes_scanned"] = process_count
                if process_count > MAX_PROC_ENTRIES:
                    LAST_SCAN["maps_truncated"] = True
                    raise Hold("HOLD_MAPS_PROCESS_LIMIT")
                pid = int(entry.name)
                pdir = Path(entry.path)
                try:
                    before_raw = _read(pdir / "stat", MAX_STAT_BYTES)
                    before = _parse_start_ticks(before_raw, pid)
                    maps_raw = _read(pdir / "maps", MAX_MAPS_BYTES_PER_PID)
                    after_raw = _read(pdir / "stat", MAX_STAT_BYTES)
                    after = _parse_start_ticks(after_raw, pid)
                except FileNotFoundError:
                    skipped_vanished += 1
                    LAST_SCAN["maps_vanished_during_read"] = skipped_vanished
                    continue
                except OSError as exc:
                    LAST_SCAN["maps_unreadable_pids"] += 1
                    raise Hold("HOLD_MAPS_CENSUS_UNAVAILABLE") from exc
                except Hold as exc:
                    if str(exc) == "HOLD_READ_LIMIT":
                        truncated = True
                        LAST_SCAN["maps_truncated"] = True
                        break
                    raise
                if before != after:
                    skipped_vanished += 1
                    LAST_SCAN["maps_vanished_during_read"] = skipped_vanished
                    continue
                scanned_bytes += len(maps_raw)
                LAST_SCAN["maps_bytes_scanned"] = scanned_bytes
                if scanned_bytes > MAX_MAPS_BYTES_TOTAL:
                    truncated = True
                    LAST_SCAN["maps_truncated"] = True
                    break
                rows, row_truncated, row_bytes = _maps_memfd_rows(
                    maps_raw, memfd_device, memfd_inode)
                scanned_lines += maps_raw.count(b"\n") + (1 if maps_raw and not maps_raw.endswith(b"\n") else 0)
                if scanned_lines > MAX_MAPS_LINES_TOTAL:
                    truncated = True
                    LAST_SCAN["maps_truncated"] = True
                    break
                if row_truncated:
                    truncated = True
                    LAST_SCAN["maps_truncated"] = True
                    break
                LAST_SCAN["maps_lines_scanned"] = scanned_lines
                if rows:
                    rows_sha = digest(json.dumps(rows, sort_keys=True,
                                                 separators=(",", ":")).encode())
                    matches.append({"pid": pid, "start_ticks": before,
                                    "mapping_count": len(rows), "mappings": rows,
                                    "matched_rows_sha256": rows_sha})
    except Hold:
        raise
    except OSError as exc:
        LAST_SCAN["maps_unreadable_pids"] += 1
        raise Hold("HOLD_MAPS_CENSUS_UNAVAILABLE") from exc
    if truncated:
        LAST_SCAN["maps_truncated"] = True
        raise Hold("HOLD_MAPS_CENSUS_TRUNCATED")
    for row in matches:
        pdir = proc_root / str(row["pid"])
        try:
            before = _parse_start_ticks(_read(pdir / "stat", MAX_STAT_BYTES), row["pid"])
            raw = _read(pdir / "maps", MAX_MAPS_BYTES_PER_PID)
            after = _parse_start_ticks(_read(pdir / "stat", MAX_STAT_BYTES), row["pid"])
        except (FileNotFoundError, OSError, Hold):
            LAST_SCAN["maps_unreadable_pids"] += 1
            raise Hold("HOLD_MAP_IDENTITY_RECHECK_UNAVAILABLE")
        if before != row["start_ticks"] or after != before:
            raise Hold("HOLD_MAP_PROCESS_CHANGED")
        current_rows, cut, _ = _maps_memfd_rows(raw, memfd_device, memfd_inode)
        current_sha = digest(json.dumps(current_rows, sort_keys=True,
                                        separators=(",", ":")).encode())
        if cut or current_sha != row["matched_rows_sha256"]:
            raise Hold("HOLD_MAP_IDENTITY_CHANGED")
        row["identity_rechecked"] = True
    return {"status": "COMPLETE_BOUNDED_CENSUS", "processes_scanned": process_count,
            "bytes_scanned": scanned_bytes, "lines_scanned": scanned_lines,
            "vanished_during_read": skipped_vanished, "mapping_processes": matches}


def _parse_start_ticks(raw: bytes, pid: int) -> int:
    text = raw.decode("ascii", "strict")
    prefix = str(pid) + " ("
    end = text.rfind(") ")
    if not text.startswith(prefix) or end < len(prefix):
        raise Hold("HOLD_PROC_STAT_IDENTITY")
    fields = text[end + 2:].split()
    if len(fields) < 20 or not fields[19].isdecimal():
        raise Hold("HOLD_PROC_STAT_FIELDS")
    return int(fields[19])


def run_audit(proc_root: Path = Path("/proc")) -> dict:
    global LAST_SCAN
    counters = {
        "proc_entries_seen": 0, "pid_cmdlines_scanned": 0,
        "script_basename_candidate_pids": 0, "cmdline_unreadable_pids": 0,
        "cmdline_truncated_pids": 0, "fd_pids_scanned": 0,
        "fd_entries_scanned": 0, "fd_link_bytes_scanned": 0,
        "fd_unreadable_entries": 0, "fd_races": 0,
        "label_size_mismatch_count": 0, "exact_fd_owner_pids": 0,
        "global_identity_unreadable_pids": 0, "candidate_identity_failures": [],
        "pids_vanished": 0,
        "unstable_pids": 0, "limits_hit": [],
    }
    LAST_SCAN = counters
    pids, entries_seen = proc_pid_order(proc_root)
    counters["proc_entries_seen"] = entries_seen
    global_identity_unreadable = set()
    budget = {"entries": 0, "bytes": 0, "fd_races": 0}
    cmdline_bytes = 0
    fd_owners = []

    for pid in pids:
        pdir = proc_root / str(pid)
        before_ticks = None
        try:
            before_ticks = _parse_start_ticks(_read(pdir / "stat", MAX_STAT_BYTES), pid)
        except FileNotFoundError:
            counters["pids_vanished"] += 1
            continue
        except (OSError, Hold):
            global_identity_unreadable.add(pid)
        argv = None
        try:
            argv = _read(pdir / "cmdline", MAX_CMDLINE_BYTES)
        except FileNotFoundError:
            counters["pids_vanished"] += 1
            argv = None
        except Hold:
            counters["cmdline_truncated_pids"] += 1
            argv = None
        except OSError:
            counters["cmdline_unreadable_pids"] += 1
            argv = None
        script_candidate = False
        if argv is not None:
            counters["pid_cmdlines_scanned"] += 1
            cmdline_bytes += len(argv)
            if cmdline_bytes > MAX_CMDLINE_BYTES_TOTAL:
                counters["cmdline_truncated_pids"] += 1
                counters["limits_hit"].append("CMDLINE_BYTES_TOTAL")
                break
            script_candidate = _script_path_token(argv) is not None
        if script_candidate:
            counters["script_basename_candidate_pids"] += 1
        counters["fd_pids_scanned"] += 1
        try:
            fd_result = fd_memfd_identity(proc_root, pid, budget)
        except Hold as exc:
            counters["fd_entries_scanned"] = budget["entries"]
            counters["fd_link_bytes_scanned"] = budget["bytes"]
            counters["fd_races"] = budget["fd_races"]
            counters["limits_hit"].append(str(exc))
            break
        counters["fd_entries_scanned"] = budget["entries"]
        counters["fd_link_bytes_scanned"] = budget["bytes"]
        counters["fd_races"] = budget["fd_races"]
        counters["fd_unreadable_entries"] += fd_result.get("unreadable_entries", 0)
        counters["label_size_mismatch_count"] += fd_result.get(
            "label_size_mismatch_count", 0)
        if fd_result.get("status") == "VANISHED":
            counters["pids_vanished"] += 1
            continue
        try:
            after_ticks = _parse_start_ticks(_read(pdir / "stat", MAX_STAT_BYTES), pid)
        except FileNotFoundError:
            counters["pids_vanished"] += 1
            if fd_result["matching_fd_count"]:
                counters["unstable_pids"] += 1
            continue
        except (OSError, Hold):
            global_identity_unreadable.add(pid)
            continue
        if before_ticks is None or before_ticks != after_ticks:
            counters["unstable_pids"] += 1
            continue
        if fd_result["identity_count"] > 1:
            counters["limits_hit"].append("FD_IDENTITY_AMBIGUOUS_WITHIN_PID")
            break
        if not fd_result["matching_fd_count"]:
            continue
        counters["exact_fd_owner_pids"] += 1
        owner = {"pid": pid, "start_ticks": before_ticks,
                 "script_basename_candidate": script_candidate,
                 "fd_census": fd_result, "identity": None}
        if script_candidate:
            try:
                identity = proc_identity(proc_root, pid)
                if identity["start_ticks"] != before_ticks:
                    raise Hold("HOLD_HOLDER_IDENTITY_UNSTABLE")
                owner["identity"] = identity
            except Exception as exc:
                failure = {"pid": pid, "failure_code": sanitized_identity_failure(exc)}
                if before_ticks is not None and before_ticks == after_ticks:
                    failure["start_ticks"] = before_ticks
                if (fd_result.get("status") == "OK" and
                        fd_result.get("identity_count") == 1 and
                        fd_result.get("matching_fd_count", 0) > 0 and
                        len(fd_result.get("matches", [])) > 0):
                    match = fd_result["matches"][0]
                    failure["exact_fd_count"] = fd_result["matching_fd_count"]
                    failure["device"] = match["device"]
                    failure["inode"] = match["inode"]
                counters["candidate_identity_failures"].append(failure)
        fd_owners.append(owner)

    counters["global_identity_unreadable_pids"] = len(global_identity_unreadable)
    if counters["limits_hit"]:
        raise Hold("HOLD_CENSUS_LIMIT")

    # When FD census finds no exact label+size descriptor, maps must still be
    # scanned: mmap'd files can outlive their last open descriptor.
    if not fd_owners:
        maps = maps_census(proc_root, None, None)
        label_map_pids = len(maps["mapping_processes"])
        counters["label_map_processes"] = label_map_pids
        counters["mapping_rows"] = sum(x["mapping_count"] for x in maps["mapping_processes"])
        incomplete = bool(counters["cmdline_unreadable_pids"] or
                          counters["cmdline_truncated_pids"] or
                          counters["fd_unreadable_entries"] or
                          counters["global_identity_unreadable_pids"] or
                          counters["unstable_pids"])
        if label_map_pids:
            raise Hold("HOLD_MEMFD_MAPS_FOUND_WITHOUT_FD_IDENTITY",
                       {"maps_census": maps})
        if incomplete:
            raise Hold("HOLD_GLOBAL_CENSUS_PARTIAL")
        return {"schema": SCHEMA, "state": "NO_EXACT_MEMFD_REFERENCE_COMPLETE_CENSUS",
                "complete": True, "scope": "ALL_VISIBLE_PROC_FD_AND_MAPS_BOUNDED",
                "holder": None,
                "memfd": {"label_sha256": digest(MEMFD_LABEL.encode()),
                          "expected_size_bytes": MEMFD_SIZE,
                          "device": None, "inode": None},
                "fd_census": {"status": "COMPLETE_NO_EXACT_LABEL_SIZE_MATCH",
                              "matching_owner_pid_count": 0},
                "maps_census": maps, "scan_counters": counters,
                "host_mutations": False, "signals_sent": False,
                "supervisor_rpc": False}

    if len(fd_owners) != 1:
        raise Hold("HOLD_MEMFD_OWNER_PID_AMBIGUOUS")
    owner = fd_owners[0]
    if not owner["script_basename_candidate"] or owner["identity"] is None:
        raise Hold("HOLD_MEMFD_OWNER_SCRIPT_IDENTITY_UNVERIFIED",
                   {"candidate_identity_failures":
                    counters["candidate_identity_failures"],
                    "global_identity_unreadable_pids":
                    counters["global_identity_unreadable_pids"],
                    "exact_fd_owner_pid_count": counters["exact_fd_owner_pids"]})
    if (counters["cmdline_unreadable_pids"] or counters["cmdline_truncated_pids"] or
            counters["fd_unreadable_entries"] or counters["global_identity_unreadable_pids"] or
            counters["unstable_pids"]):
        raise Hold("HOLD_GLOBAL_CENSUS_PARTIAL")
    fd_matches = owner["fd_census"]["matches"]
    identity_tuples = {(x["device"], x["inode"], x["size_bytes"], x["label_sha256"])
                       for x in fd_matches}
    if len(identity_tuples) != 1:
        raise Hold("HOLD_MEMFD_FD_IDENTITY_AMBIGUOUS")
    memfd_identity = fd_matches[0]
    maps = maps_census(proc_root, memfd_identity["device"], memfd_identity["inode"])
    final = proc_identity(proc_root, owner["pid"])
    if final != owner["identity"]:
        raise Hold("HOLD_HOLDER_IDENTITY_CHANGED_DURING_MAPS_SCAN")
    final_fd = fd_memfd_identity(proc_root, owner["pid"], budget)
    if (final_fd.get("matching_fd_count") != owner["fd_census"]["matching_fd_count"] or
            final_fd.get("matches") != owner["fd_census"]["matches"]):
        raise Hold("HOLD_MEMFD_CHANGED_DURING_MAPS_SCAN")
    final_identity = proc_identity(proc_root, owner["pid"])
    if final_identity != owner["identity"]:
        raise Hold("HOLD_HOLDER_IDENTITY_CHANGED_AFTER_FINAL_FD_SCAN")
    counters["label_map_processes"] = len(maps["mapping_processes"])
    counters["mapping_rows"] = sum(x["mapping_count"] for x in maps["mapping_processes"])
    counters["fd_entries_scanned"] = budget["entries"]
    counters["fd_link_bytes_scanned"] = budget["bytes"]
    return {
        "schema": SCHEMA,
        "state": "READ_ONLY_MEMFD_CENSUS_COMPLETE",
        "complete": True,
        "scope": "UNIQUE_EXACT_HOLDER_AND_BOUNDED_GLOBAL_FD_MAPS_CENSUS",
        "holder": owner["identity"],
        "fd_census": {key: value for key, value in owner["fd_census"].items()
                       if key != "status"},
        "maps_census": maps,
        "memfd": {"label_sha256": digest(MEMFD_LABEL.encode()),
                  "device": memfd_identity["device"], "inode": memfd_identity["inode"],
                  "size_bytes": MEMFD_SIZE},
        "scan_counters": counters,
        "host_mutations": False,
        "signals_sent": False,
        "supervisor_rpc": False,
    }


def main() -> int:
    source_sha = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    request = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    if not SHA40.fullmatch(source_sha) or not request.isdigit():
        raise Hold("HOLD_OWNER_CONTEXT")
    if os.geteuid() != 0:
        raise Hold("HOLD_ROOT_REQUIRED")
    started = time.time()
    try:
        result = run_audit()
        result.update(request_id=int(request), source_sha=source_sha,
                      started_at=started, finished_at=time.time())
        print("NOX_MAINT_MEMFD_AUDIT=" + json.dumps(result, separators=(",", ":")), flush=True)
        print("NOX_MAINT_MEMFD_AUDIT_COMPLETE=true", flush=True)
        return 0
    except Hold as exc:
        print("NOX_MAINT_MEMFD_AUDIT=" + json.dumps({
            "schema": SCHEMA, "request_id": int(request), "source_sha": source_sha,
            "state": str(exc), "complete": False, "partial": True,
            "scan_counters": LAST_SCAN, "diagnostics": exc.diagnostics,
            "host_mutations": False, "signals_sent": False, "supervisor_rpc": False,
            "finished_at": time.time()}, separators=(",", ":")), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
