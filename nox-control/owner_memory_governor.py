#!/usr/bin/env python3
"""NOX memory governor: finite read-only cgroup v2 assessment.

No scheduler, shell, root action, global cache eviction, or service mutation.
Temporary-file removal is delegated to the existing two-step, SHA-pinned
owner_storage_reclaim audit -> explicit reclaim transaction.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

SCHEMA = "NOX_NATIVE_MEMORY_GOVERNOR_V1"
MIB = 1024 * 1024
GIB = 1024 * MIB
MAX_READ = 32768
RECOMMENDED_CACHE_MIN = 8 * GIB

class MemoryHold(ValueError):
    pass


def _require(valid, code):
    if not valid:
        raise MemoryHold("HOLD_MEMORY_GOVERNOR_" + code)


def _number(text):
    _require(isinstance(text, str) and text.isdecimal() and len(text) <= 24,
             "COUNTER_FORMAT")
    return int(text)


def _read(root, name, required=True):
    # No arbitrary paths: root is the fixed cgroup directory or a local fake
    # with an exact filename from the finite hardcoded sampler below.
    _require(name in ("memory.current", "memory.max", "memory.stat",
                     "memory.events", "memory.pressure", "cpu.pressure",
                     "memory.swap.current", "memory.swap.max",
                     "memory.zswap.current"), "CGROUP_FILE_NAME")
    path = Path(root) / name
    _require(not path.is_symlink(), "CGROUP_SYMLINK")
    try:
        with path.open("r", encoding="ascii") as stream:
            value = stream.read(MAX_READ + 1)
    except FileNotFoundError:
        if not required:
            return None
        raise MemoryHold("HOLD_MEMORY_GOVERNOR_REQUIRED_FILE") from None
    _require(len(value) <= MAX_READ, "FILE_SIZE")
    return value


def _kv(raw):
    _require(isinstance(raw, str), "STAT_FORMAT")
    result = {}
    for line in raw.strip().splitlines():
        fields = line.split()
        _require(len(fields) == 2 and fields[0] not in result,
                 "DUPLICATE_OR_MALFORMED_STAT")
        result[fields[0]] = _number(fields[1])
    return result


def _psi(raw):
    result = {}
    _require(isinstance(raw, str), "PRESSURE_FORMAT")
    for line in raw.strip().splitlines():
        fields = line.split()
        _require(len(fields) >= 2 and fields[0] in ("some", "full")
                 and fields[0] not in result, "PRESSURE_ROW")
        row = {}
        for item in fields[1:]:
            name, sep, value = item.partition("=")
            _require(sep and name in ("avg10", "avg60", "avg300", "total")
                     and name not in row, "PRESSURE_KEY")
            if name == "total":
                row[name] = _number(value)
            else:
                try:
                    number = float(value)
                except (ValueError, OverflowError):
                    raise MemoryHold("HOLD_MEMORY_GOVERNOR_PRESSURE_VALUE") from None
                _require(math.isfinite(number) and 0 <= number <= 100,
                         "PRESSURE_VALUE")
                row[name] = number
        _require("avg10" in row, "PRESSURE_AVG10")
        result[fields[0]] = row
    _require("some" in result and "full" in result, "PRESSURE_MISSING")
    return result


def sample(root="/sys/fs/cgroup"):
    """One point-in-time sample; cgroup counters may change during the read."""
    current = _number(_read(root, "memory.current").strip())
    max_text = _read(root, "memory.max").strip()
    _require(max_text == "max" or max_text.isdecimal(), "LIMIT")
    limit = None if max_text == "max" else _number(max_text)
    _require(limit is None or limit > 0, "LIMIT_ZERO")
    stats = _kv(_read(root, "memory.stat"))
    events = _kv(_read(root, "memory.events"))
    for key in ("file", "shmem", "inactive_file", "anon"):
        _require(key in stats, "MISSING_MEMORY_STAT")
    _require(stats["shmem"] <= stats["file"], "SHMEM_EXCEEDS_FILE")
    reclaimable_file = min(stats["inactive_file"],
                           max(0, stats["file"] - stats["shmem"]))
    swap_current = _read(root, "memory.swap.current", False)
    swap_max = _read(root, "memory.swap.max", False)
    zswap = _read(root, "memory.zswap.current", False)
    return {"schema": SCHEMA, "memory_bytes": current, "limit_bytes": limit,
            "anon_bytes": stats["anon"], "file_bytes": stats["file"],
            "shmem_bytes": stats["shmem"],
            "inactive_file_bytes": stats["inactive_file"],
            "reclaimable_file_estimate_bytes": reclaimable_file,
            "effective_bytes_estimate": max(0, current - reclaimable_file),
            "memory_psi": _psi(_read(root, "memory.pressure")),
            "cpu_psi": _psi(_read(root, "cpu.pressure")),
            "events": {name: events.get(name, 0)
                       for name in ("low", "high", "max", "oom", "oom_kill")},
            "swap_current_bytes": (_number(swap_current.strip())
                                   if swap_current is not None else None),
            "swap_max_bytes": (_number(swap_max.strip())
                               if swap_max is not None and
                               swap_max.strip() != "max" else None),
            "zswap_bytes": (_number(zswap.strip()) if zswap is not None else None),
            "sampling_scope": "CGroupV2_SINGLE_SNAPSHOT_NO_ATOMICITY"}


def decide(sampled, previous=None, chat_active=False, writer_busy=False):
    """Fail closed: recommend admissions; never execute reclaim or delete files."""
    _require(isinstance(sampled, dict) and sampled.get("schema") == SCHEMA,
             "SNAPSHOT_SCHEMA")
    limit, current = sampled.get("limit_bytes"), sampled.get("memory_bytes")
    _require(type(current) is int and current >= 0, "CURRENT")
    _require(limit is None or type(limit) is int and limit > 0, "LIMIT")
    reclaimable = sampled.get("reclaimable_file_estimate_bytes")
    _require(type(reclaimable) is int and 0 <= reclaimable <= current,
             "RECLAIMABLE")
    psi = sampled.get("memory_psi", {})
    _require(isinstance(psi, dict) and isinstance(psi.get("some"), dict)
             and isinstance(psi.get("full"), dict), "PSI")
    some = psi["some"].get("avg10")
    full = psi["full"].get("avg10")
    _require(all(type(x) in (int, float) and math.isfinite(x)
                 and 0 <= x <= 100 for x in (some, full)), "PSI_VALUES")
    events = sampled.get("events", {})
    _require(isinstance(events, dict) and
             all(type(events.get(k)) is int and events[k] >= 0
                 for k in ("oom", "oom_kill", "high")), "EVENTS")
    increased = {}
    if previous is not None:
        prev = previous.get("events") if isinstance(previous, dict) else None
        _require(isinstance(prev, dict), "PREVIOUS_EVENTS")
        for key in ("oom", "oom_kill", "high"):
            count = prev.get(key)
            _require(type(count) is int and 0 <= count <= events[key],
                     "EVENT_COUNTER_RESET")
            increased[key] = events[key] - count
    else:
        increased = {"oom": None, "oom_kill": None, "high": None}
    raw_ratio = current / limit if limit else None
    effective = max(0, current - reclaimable)
    effective_ratio = effective / limit if limit else None
    severe = (full >= 2 or some >= 10
              or (increased["oom_kill"] is not None
                  and increased["oom_kill"] > 0)
              or (effective_ratio is not None and effective_ratio >= .94))
    caution = (some >= 2 or full >= .2
               or (increased["high"] is not None and increased["high"] > 0)
               or (effective_ratio is not None and effective_ratio >= .85))
    if severe:
        state, background = "PRESSURE_CRITICAL", "HOLD_NEW_BACKGROUND_SUBMITS"
    elif caution:
        state, background = "PRESSURE_ELEVATED", "REDUCE_BACKGROUND_CONCURRENCY"
    else:
        state, background = "CACHE_HEALTHY", "USE_EXISTING_BOUNDED_CPU_ADMISSION"
    if chat_active:
        background = "YIELD_TO_FOREGROUND_CHAT"
    elif writer_busy:
        background = "HOLD_OWNER_MAINTENANCE"
    # A high raw cgroup ratio alone is *not* evidence of a leak.
    # Reclaim targets model-mapped pagecache too; never automatically call
    # memory.reclaim, drop_caches, madvise, or unlink persistent assets.
    return {"schema": SCHEMA, "state": state,
            "background_action": background, "raw_ratio": raw_ratio,
            "effective_ratio_estimate": effective_ratio,
            "reclaimable_file_estimate_bytes": reclaimable,
            "shmem_protected_bytes": sampled["shmem_bytes"],
            "psi_some_avg10": some, "psi_full_avg10": full,
            "oom_kill_delta": increased["oom_kill"],
            "high_event_delta": increased["high"],
            "disk_cleanup": "EXISTING_SHA_PINNED_STORAGE_AUDIT_THEN_OWNER_RECLAIM",
            "cache_action": ("REVIEW_COLD_FILE_FADVISE_CANDIDATES"
                             if severe and reclaimable >= RECOMMENDED_CACHE_MIN
                             else "PRESERVE_PAGE_CACHE"),
            "automated_reclaim_executed": False,
            "model_shmem_deleted": False, "s03_or_checkpoints_deleted": False,
            "weights_modified": False,
            "source": "LINUX_CGROUP_V2_COUNTERS_NOT_A_BENCHMARK"}


def main():
    observed = sample()
    result = decide(observed)
    # Never export filenames, memory addresses, PIDs, user data or environment.
    print("NOX_MEMORY_GOVERNOR=" +
          json.dumps({"sample": observed, "decision": result},
                     sort_keys=True, separators=(",", ":"), allow_nan=False),
          flush=True)


if __name__ == "__main__":
    main()
