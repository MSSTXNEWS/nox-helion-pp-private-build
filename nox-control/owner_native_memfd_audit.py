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
HOLDER_SCRIPT = "/root/nox/engram_ram/engram_memfd_holder.py"
HOLDER_CWD = "/root/nox/engram_ram"
MEMFD_LABEL = "memfd:engram_iq3xxs (deleted)"
MEMFD_SIZE = 75_266_239_716

MAX_PROC_ENTRIES = 8192
MAX_CMDLINE_BYTES = 16 * 1024
MAX_STAT_BYTES = 8192
MAX_CGROUP_BYTES = 8192
MAX_FD_ENTRIES_PER_PID = 512
MAX_FD_ENTRIES_TOTAL = 2048
MAX_FD_LINK_BYTES = 4096
MAX_FD_BYTES_TOTAL = 512 * 1024
MAX_MAPS_BYTES_PER_PID = 1024 * 1024
MAX_MAPS_BYTES_TOTAL = 8 * 1024 * 1024
MAX_MAPS_LINES_TOTAL = 65536
SHA40 = re.compile(r"^[0-9a-f]{40}$")
MAP_LINE = re.compile(
    rb"^([0-9a-fA-F]+)-([0-9a-fA-F]+)\s+([rwxps-]{4})\s+"
    rb"([0-9a-fA-F]+)\s+([0-9a-fA-F]+):([0-9a-fA-F]+)\s+"
    rb"([0-9]+)(?:\s+(.*))?$"
)


class Hold(RuntimeError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
    argv_parts = [part for part in argv.split(b"\0") if part]
    if not argv_parts or HOLDER_SCRIPT.encode() not in argv_parts:
        raise Hold("HOLD_HOLDER_SCRIPT_SHAPE")
    try:
        exe = os.readlink(base / "exe").encode("utf-8", "surrogateescape")
        cwd = os.readlink(base / "cwd").encode("utf-8", "surrogateescape")
    except OSError as exc:
        raise Hold("HOLD_HOLDER_PATH_IDENTITY") from exc
    exe_name = Path(os.fsdecode(exe).removesuffix(" (deleted)")).name
    if cwd != HOLDER_CWD.encode() or exe_name not in {
            "python3", "python3.11", "python3.12", "python3.13"}:
        raise Hold("HOLD_HOLDER_CWD_SHAPE")
    if argv_parts.count(HOLDER_SCRIPT.encode()) != 1:
        raise Hold("HOLD_HOLDER_SCRIPT_SHAPE")
    try:
        cgroup = _read(base / "cgroup", MAX_CGROUP_BYTES)
    except (OSError, Hold) as exc:
        raise Hold("HOLD_HOLDER_CGROUP_UNAVAILABLE") from exc
    return {
        "pid": pid,
        "start_ticks": ticks,
        "ppid": int(fields[1]),
        "pgrp": int(fields[2]),
        "exe_path_sha256": digest(exe),
        "argv_sha256": digest(argv),
        "cwd_sha256": digest(cwd),
        "cgroup_sha256": digest(cgroup),
    }


def holder_script_candidates(proc_root: Path) -> tuple[list[int], int, int]:
    candidates: list[int] = []
    scanned = 0
    unreadable = 0
    try:
        with os.scandir(proc_root) as entries:
            for entry in entries:
                if not entry.name.isdecimal():
                    continue
                scanned += 1
                if scanned > MAX_PROC_ENTRIES:
                    raise Hold("HOLD_PROC_TABLE_LIMIT")
                pid = int(entry.name)
                try:
                    argv = _read(Path(entry.path) / "cmdline", MAX_CMDLINE_BYTES)
                except FileNotFoundError:
                    continue
                except OSError:
                    # A process disappearing during census is not evidence of an
                    # unreadable live holder; other failures are unresolved.
                    try:
                        (Path(entry.path) / "stat").stat()
                    except OSError:
                        continue
                    unreadable += 1
                    continue
                if HOLDER_SCRIPT.encode() in argv.split(b"\0"):
                    candidates.append(pid)
    except OSError as exc:
        raise Hold("HOLD_PROC_TABLE_UNAVAILABLE") from exc
    return candidates, scanned, unreadable


def fd_memfd_identity(proc_root: Path, identity: dict,
                      budget: dict) -> dict:
    fd_dir = proc_root / str(identity["pid"]) / "fd"
    matches = []
    entries = 0
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
                except OSError as exc:
                    raise Hold("HOLD_FD_CENSUS_UNAVAILABLE") from exc
                label = target.rsplit("/", 1)[-1]
                if label == MEMFD_LABEL:
                    try:
                        target_after = os.readlink(row.path)
                        info_after = os.stat(row.path)
                    except OSError as exc:
                        raise Hold("HOLD_FD_CENSUS_UNAVAILABLE") from exc
                    before_sig = (info.st_dev, info.st_ino, info.st_size, info.st_mode)
                    after_sig = (info_after.st_dev, info_after.st_ino,
                                 info_after.st_size, info_after.st_mode)
                    if target_after != target or before_sig != after_sig:
                        raise Hold("HOLD_FD_IDENTITY_UNSTABLE")
                    if (info.st_size != MEMFD_SIZE or not stat.S_ISREG(info.st_mode)):
                        raise Hold("HOLD_MEMFD_FD_IDENTITY_MISMATCH")
                    matches.append({"fd_number": int(row.name), "device": int(info.st_dev),
                                    "inode": int(info.st_ino), "size_bytes": int(info.st_size),
                                    "label_sha256": digest(label.encode())})
    except Hold:
        raise
    except OSError as exc:
        raise Hold("HOLD_FD_CENSUS_UNAVAILABLE") from exc
    identities = {(row["device"], row["inode"], row["size_bytes"], row["label_sha256"])
                  for row in matches}
    if len(identities) > 1:
        raise Hold("HOLD_MEMFD_FD_IDENTITY_AMBIGUOUS")
    identity_row = matches[0] if matches else None
    return {"entries_scanned": entries, "matching_fd_count": len(matches),
            "fd_numbers": sorted(row["fd_number"] for row in matches),
            "match": ({key: identity_row[key] for key in
                       ("device", "inode", "size_bytes", "label_sha256")}
                      if identity_row else None)}


def _maps_memfd_rows(raw: bytes, device: int,
                     expected_inode: int) -> tuple[list[dict], bool, int]:
    rows: list[dict] = []
    major, minor = os.major(device), os.minor(device)
    expected_device = (major, minor)
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
        inode_is_target = observed_inode == expected_inode
        if not (label_is_target or inode_is_target):
            continue
        if observed_device != expected_device or observed_inode != expected_inode:
            raise Hold("HOLD_MEMFD_MAP_IDENTITY_MISMATCH")
        if not label_is_target:
            raise Hold("HOLD_MEMFD_MAP_LABEL_MISMATCH")
        rows.append({"permissions": perms.decode("ascii"),
                     "offset_bytes": int(offset, 16),
                     "inode": observed_inode,
                     "mapping_size_bytes": int(_end, 16) - int(_start, 16),
                     "path_kind": "EXACT_ENGRAM_MEMFD"})
    return rows, truncated, consumed


def maps_census(proc_root: Path, memfd_device: int, memfd_inode: int) -> dict:
    process_count = 0
    scanned_bytes = 0
    scanned_lines = 0
    skipped_vanished = 0
    matches: list[dict] = []
    truncated = False
    try:
        with os.scandir(proc_root) as entries:
            for entry in entries:
                if not entry.name.isdecimal():
                    continue
                process_count += 1
                if process_count > MAX_PROC_ENTRIES:
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
                    continue
                except OSError as exc:
                    raise Hold("HOLD_MAPS_CENSUS_UNAVAILABLE") from exc
                except Hold as exc:
                    if str(exc) == "HOLD_READ_LIMIT":
                        truncated = True
                        break
                    raise
                if before != after:
                    skipped_vanished += 1
                    continue
                scanned_bytes += len(maps_raw)
                if scanned_bytes > MAX_MAPS_BYTES_TOTAL:
                    truncated = True
                    break
                rows, row_truncated, row_bytes = _maps_memfd_rows(
                    maps_raw, memfd_device, memfd_inode)
                scanned_lines += maps_raw.count(b"\n") + (1 if maps_raw and not maps_raw.endswith(b"\n") else 0)
                if scanned_lines > MAX_MAPS_LINES_TOTAL:
                    truncated = True
                    break
                if row_truncated:
                    truncated = True
                    break
                if rows:
                    rows_sha = digest(json.dumps(rows, sort_keys=True,
                                                 separators=(",", ":")).encode())
                    matches.append({"pid": pid, "start_ticks": before,
                                    "mapping_count": len(rows), "mappings": rows,
                                    "matched_rows_sha256": rows_sha})
    except Hold:
        raise
    except OSError as exc:
        raise Hold("HOLD_MAPS_CENSUS_UNAVAILABLE") from exc
    if truncated:
        raise Hold("HOLD_MAPS_CENSUS_TRUNCATED")
    for row in matches:
        pdir = proc_root / str(row["pid"])
        before = _parse_start_ticks(_read(pdir / "stat", MAX_STAT_BYTES), row["pid"])
        raw = _read(pdir / "maps", MAX_MAPS_BYTES_PER_PID)
        after = _parse_start_ticks(_read(pdir / "stat", MAX_STAT_BYTES), row["pid"])
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
    candidates, process_scanned, unreadable = holder_script_candidates(proc_root)
    if unreadable:
        raise Hold("HOLD_HOLDER_CANDIDATE_CENSUS_INCOMPLETE")
    if not candidates:
        raise Hold("HOLD_HOLDER_UNKNOWN")
    budget = {"entries": 0, "bytes": 0}
    identified = []
    for pid in candidates:
        first = proc_identity(proc_root, pid)
        fd = fd_memfd_identity(proc_root, first, budget)
        if fd["matching_fd_count"] == 0:
            continue
        second = proc_identity(proc_root, pid)
        if first != second:
            raise Hold("HOLD_HOLDER_IDENTITY_CHANGED_DURING_FD_SCAN")
        identified.append((first, fd))
    if not identified:
        raise Hold("HOLD_HOLDER_UNKNOWN")
    if len(identified) != 1:
        raise Hold("HOLD_HOLDER_AMBIGUOUS")
    holder, fd = identified[0]
    maps = maps_census(proc_root, fd["match"]["device"], fd["match"]["inode"])
    final = proc_identity(proc_root, holder["pid"])
    if final != holder:
        raise Hold("HOLD_HOLDER_IDENTITY_CHANGED_DURING_MAPS_SCAN")
    final_fd = fd_memfd_identity(proc_root, final, budget)
    if final_fd != fd:
        raise Hold("HOLD_MEMFD_CHANGED_DURING_MAPS_SCAN")
    final_identity = proc_identity(proc_root, holder["pid"])
    if final_identity != holder:
        raise Hold("HOLD_HOLDER_IDENTITY_CHANGED_AFTER_FINAL_FD_SCAN")
    return {
        "schema": SCHEMA,
        "state": "READ_ONLY_MEMFD_CENSUS_COMPLETE",
        "complete": True,
        "scope": "EXACT_HOLDER_AND_BOUNDED_PROC_MAPS_CENSUS",
        "holder": holder,
        "fd_census": fd,
        "maps_census": maps,
        "holder_script_path_sha256": digest(HOLDER_SCRIPT.encode()),
        "holder_cwd_path_sha256": digest(HOLDER_CWD.encode()),
        "memfd": {"label_sha256": digest(MEMFD_LABEL.encode()),
                  "device": fd["match"]["device"], "inode": fd["match"]["inode"],
                  "size_bytes": MEMFD_SIZE},
        "proc_processes_scanned": process_scanned,
        "fd_entries_scanned_total": budget["entries"],
        "fd_link_bytes_scanned_total": budget["bytes"],
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
            "host_mutations": False, "signals_sent": False, "supervisor_rpc": False,
            "finished_at": time.time()}, separators=(",", ":")), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
