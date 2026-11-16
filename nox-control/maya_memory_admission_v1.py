"""Pure fail-closed memory admission for a 2x V100 Maya source plan.

The helper consumes a caller-supplied live snapshot and verified-pack budget only.
It never probes the host, starts a process, creates a CUDA context, or launches Maya.
"""
from __future__ import annotations

import math
import re
import time

EXPECTED_GPU_IDS = (0, 1)
SHA256 = re.compile(r"[0-9a-f]{64}\\Z")


def _hold(state: str, **detail) -> dict:
    return {"state": state, "launchable": False, **detail}


def _positive_int(value) -> bool:
    return type(value) is int and value > 0


def _nonnegative_int(value) -> bool:
    return type(value) is int and value >= 0


def evaluate_memory_admission(*, snapshot, budget, now_seconds=None,
                              max_age_seconds=15, required_context_tokens=4096,
                              minimum_gpu_reserve_bytes=3 * 1024 * 1024 * 1024,
                              minimum_host_reserve_bytes=1 * 1024 * 1024 * 1024):
    """Check current per-GPU free/total VRAM and cgroup RAM against a verified plan budget."""
    if not isinstance(snapshot, dict) or snapshot.get("status") != "LIVE_READBACK":
        return _hold("HOLD_MEMORY_LIVE_SNAPSHOT_REQUIRED")
    if snapshot.get("source") != "native_live_readback" or snapshot.get("measured") is not True:
        return _hold("HOLD_MEMORY_STATIC_OR_UNVERIFIED_SNAPSHOT")
    captured = snapshot.get("captured_at")
    now = time.time() if now_seconds is None else now_seconds
    if (type(captured) not in (int, float) or not math.isfinite(captured) or
            type(now) not in (int, float) or not math.isfinite(now) or
            type(max_age_seconds) not in (int, float) or max_age_seconds <= 0):
        return _hold("HOLD_MEMORY_TELEMETRY_TIMESTAMP_INVALID")
    age = now - captured
    if age < 0 or age > max_age_seconds:
        return _hold("HOLD_MEMORY_TELEMETRY_STALE", age_seconds=age)

    rows = snapshot.get("gpus")
    if not isinstance(rows, (list, tuple)) or len(rows) != 2:
        return _hold("HOLD_MEMORY_TWO_GPU_READBACK_REQUIRED")
    by_id = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get("gpu_id")) is not int:
            return _hold("HOLD_MEMORY_GPU_READBACK_MALFORMED")
        gpu_id = row["gpu_id"]
        if gpu_id in by_id or gpu_id not in EXPECTED_GPU_IDS:
            return _hold("HOLD_MEMORY_TWO_GPU_READBACK_REQUIRED")
        name = row.get("name")
        total = row.get("total_bytes")
        free = row.get("free_bytes")
        if (not isinstance(name, str) or "v100" not in name.lower() or
                not _positive_int(total) or not _nonnegative_int(free) or free > total):
            return _hold("HOLD_MEMORY_GPU_READBACK_MALFORMED", gpu_id=gpu_id)
        by_id[gpu_id] = {"name": name, "total_bytes": total, "free_bytes": free}
    if set(by_id) != set(EXPECTED_GPU_IDS):
        return _hold("HOLD_MEMORY_TWO_GPU_READBACK_REQUIRED")

    cgroup = snapshot.get("cgroup")
    if not isinstance(cgroup, dict) or cgroup.get("source") != "cgroup_v2":
        return _hold("HOLD_MEMORY_CGROUP_READBACK_REQUIRED")
    limit = cgroup.get("limit_bytes")
    current = cgroup.get("current_bytes")
    free_ram = cgroup.get("free_bytes")
    if (not _positive_int(limit) or not _nonnegative_int(current) or current > limit or
            not _nonnegative_int(free_ram) or free_ram != limit - current):
        return _hold("HOLD_MEMORY_CGROUP_READBACK_MALFORMED")

    if not isinstance(budget, dict) or budget.get("source") != "verified_pack_budget":
        return _hold("HOLD_MEMORY_VERIFIED_MODEL_BUDGET_REQUIRED")
    pack_sha = budget.get("pack_sha256")
    if not isinstance(pack_sha, str) or not SHA256.fullmatch(pack_sha):
        return _hold("HOLD_MEMORY_MODEL_BUDGET_UNPINNED")
    if (type(budget.get("context_tokens")) is not int or
            budget["context_tokens"] != required_context_tokens or
            type(budget.get("parallel_requests")) is not int or
            budget["parallel_requests"] != 1):
        return _hold("HOLD_MEMORY_CONTEXT_OR_PARALLEL_BUDGET_MISMATCH")

    planned = budget.get("per_gpu")
    if not isinstance(planned, (list, tuple)) or len(planned) != 2:
        return _hold("HOLD_MEMORY_PER_GPU_BUDGET_REQUIRED")
    plan_by_id = {}
    per_gpu = []
    for row in planned:
        if not isinstance(row, dict) or type(row.get("gpu_id")) is not int:
            return _hold("HOLD_MEMORY_PER_GPU_BUDGET_MALFORMED")
        gpu_id = row["gpu_id"]
        if gpu_id in plan_by_id or gpu_id not in EXPECTED_GPU_IDS:
            return _hold("HOLD_MEMORY_PER_GPU_BUDGET_MALFORMED")
        names = ("model_resident_bytes", "activation_bytes", "kv_cache_bytes", "reserve_bytes")
        if any(not _nonnegative_int(row.get(k)) for k in names):
            return _hold("HOLD_MEMORY_PER_GPU_BUDGET_MALFORMED", gpu_id=gpu_id)
        if row["model_resident_bytes"] == 0 or row["activation_bytes"] == 0 or row["kv_cache_bytes"] == 0:
            return _hold("HOLD_MEMORY_PER_GPU_BUDGET_INCOMPLETE", gpu_id=gpu_id)
        if row["reserve_bytes"] < minimum_gpu_reserve_bytes:
            return _hold("HOLD_MEMORY_GPU_RESERVE_TOO_SMALL", gpu_id=gpu_id)
        required = sum(row[k] for k in names)
        observed_free = by_id[gpu_id]["free_bytes"]
        if required > observed_free:
            return _hold("HOLD_MEMORY_VRAM_BUDGET_EXCEEDS_FREE", gpu_id=gpu_id,
                         required_bytes=required, free_bytes=observed_free)
        plan_by_id[gpu_id] = row
        per_gpu.append({"gpu_id": gpu_id, "total_bytes": by_id[gpu_id]["total_bytes"],
                        "free_bytes": observed_free, "required_bytes": required,
                        "remaining_bytes": observed_free - required})
    if set(plan_by_id) != set(EXPECTED_GPU_IDS):
        return _hold("HOLD_MEMORY_PER_GPU_BUDGET_REQUIRED")

    host = budget.get("host")
    if not isinstance(host, dict):
        return _hold("HOLD_MEMORY_HOST_BUDGET_REQUIRED")
    host_names = ("model_resident_bytes", "activation_bytes", "kv_cache_bytes", "reserve_bytes")
    if any(not _nonnegative_int(host.get(k)) for k in host_names):
        return _hold("HOLD_MEMORY_HOST_BUDGET_MALFORMED")
    if host["model_resident_bytes"] == 0 or host["activation_bytes"] == 0 or host["kv_cache_bytes"] == 0:
        return _hold("HOLD_MEMORY_HOST_BUDGET_INCOMPLETE")
    if host["reserve_bytes"] < minimum_host_reserve_bytes:
        return _hold("HOLD_MEMORY_HOST_RESERVE_TOO_SMALL")
    host_required = sum(host[k] for k in host_names)
    if host_required > free_ram:
        return _hold("HOLD_MEMORY_RAM_BUDGET_EXCEEDS_FREE",
                     required_bytes=host_required, free_bytes=free_ram)

    return {
        "state": "MEMORY_ADMISSION_PASS_SOURCE_ONLY",
        "launchable": False,
        "measured_snapshot_age_seconds": age,
        "gpu_count": 2,
        "per_gpu": sorted(per_gpu, key=lambda x: x["gpu_id"]),
        "host_required_bytes": host_required,
        "host_free_bytes": free_ram,
        "pack_sha256": pack_sha,
        "context_tokens": budget["context_tokens"],
        "parallel_requests": budget["parallel_requests"],
    }
