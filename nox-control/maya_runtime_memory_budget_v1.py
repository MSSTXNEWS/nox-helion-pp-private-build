"""Fail-closed memory budget arithmetic for Maya on the pinned 2x V100 profile.

This consumes a caller-provided measurement receipt and planned allocations. It
does not read hardware, authenticate a receipt, launch Maya, or assert runtime
fit. All successful results remain SOURCE_ONLY and launchable=False.
"""
from __future__ import annotations

from datetime import datetime, timezone

GPU_IDS = (0, 1)
GPU_NAME = "Tesla V100-SXM2-32GB"
MAX_SAMPLE_AGE_SECONDS = 10
MAX_FUTURE_SKEW_SECONDS = 2
MIN_GPU_TOTAL_BYTES = 30 * 1024 ** 3


def _hold(state: str, **details) -> dict:
    return {"state": state, "launchable": False, **details}


def _strict_nonnegative_int(value) -> bool:
    return type(value) is int and value >= 0


def _utc_time(value):
    if not isinstance(value, str) or not value or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _is_fresh(captured_at, now_utc) -> bool:
    sample = _utc_time(captured_at)
    if sample is None:
        return False
    age = (now_utc - sample).total_seconds()
    return -MAX_FUTURE_SKEW_SECONDS <= age <= MAX_SAMPLE_AGE_SECONDS


def evaluate_memory_budget(observation, requested_budget, *, now_utc=None) -> dict:
    """Validate a fresh measurement shape and compare per-device/host budgets.

    now_utc is a deterministic test seam. Production callers should omit it.
    Measurements remain unauthenticated input; a fit result never authorizes
    model launch.
    """
    if now_utc is None:
        now = datetime.now(timezone.utc)
    elif isinstance(now_utc, datetime) and now_utc.tzinfo is not None:
        now = now_utc.astimezone(timezone.utc)
    else:
        return _hold("HOLD_RUNTIME_MEMORY_CLOCK_INVALID")

    if not isinstance(observation, dict) or not isinstance(requested_budget, dict):
        return _hold("HOLD_RUNTIME_MEMORY_TELEMETRY")
    readback_id = observation.get("readback_id")
    if not isinstance(readback_id, str) or not readback_id.strip() or len(readback_id) > 128:
        return _hold("HOLD_RUNTIME_MEMORY_READBACK_ID")
    gpus = observation.get("gpus")
    if not isinstance(gpus, (list, tuple)) or len(gpus) != 2:
        return _hold("HOLD_RUNTIME_GPU_INVENTORY")
    if not all(isinstance(row, dict) for row in gpus):
        return _hold("HOLD_RUNTIME_GPU_INVENTORY")

    by_id = {}
    for row in gpus:
        device_id = row.get("id")
        if type(device_id) is not int or device_id in by_id:
            return _hold("HOLD_RUNTIME_GPU_INVENTORY")
        if row.get("source") != "nvidia-smi":
            return _hold("HOLD_RUNTIME_GPU_SOURCE")
        if not _is_fresh(row.get("captured_at"), now):
            return _hold("HOLD_RUNTIME_GPU_TELEMETRY_STALE")
        if row.get("name") != GPU_NAME:
            return _hold("HOLD_RUNTIME_GPU_IDENTITY", gpu_id=device_id)
        total = row.get("total_bytes")
        free = row.get("free_bytes")
        if (not _strict_nonnegative_int(total) or not _strict_nonnegative_int(free)
                or total < MIN_GPU_TOTAL_BYTES or free <= 0 or free > total):
            return _hold("HOLD_RUNTIME_GPU_MEMORY_READING", gpu_id=device_id)
        by_id[device_id] = row
    if set(by_id) != set(GPU_IDS):
        return _hold("HOLD_RUNTIME_GPU_INVENTORY")

    cgroup = observation.get("cgroup")
    if not isinstance(cgroup, dict) or cgroup.get("source") != "cgroup-v2":
        return _hold("HOLD_RUNTIME_CGROUP_SOURCE")
    if not _is_fresh(cgroup.get("captured_at"), now):
        return _hold("HOLD_RUNTIME_CGROUP_TELEMETRY_STALE")
    current = cgroup.get("current_bytes")
    limit = cgroup.get("max_bytes")
    if (not _strict_nonnegative_int(current) or not _strict_nonnegative_int(limit)
            or limit <= 0 or current > limit):
        return _hold("HOLD_RUNTIME_CGROUP_MEMORY_READING")
    cgroup_free = limit - current

    if requested_budget.get("gpu_ids") != [0, 1]:
        return _hold("HOLD_RUNTIME_BUDGET_GPU_MAP")
    if type(requested_budget.get("context_tokens")) is not int or requested_budget["context_tokens"] != 4096:
        return _hold("HOLD_RUNTIME_BUDGET_CONTEXT")
    list_fields = (
        "model_resident_bytes_by_gpu",
        "activation_bytes_by_gpu",
        "kv_cache_bytes_by_gpu",
        "gpu_reserve_bytes_by_gpu",
    )
    values = {}
    for field in list_fields:
        raw = requested_budget.get(field)
        if (not isinstance(raw, (list, tuple)) or len(raw) != 2
                or any(not _strict_nonnegative_int(value) for value in raw)):
            return _hold("HOLD_RUNTIME_BUDGET_INCOMPLETE", field=field)
        values[field] = tuple(raw)
    host_fields = (
        "host_model_resident_bytes",
        "host_activation_bytes",
        "host_kv_cache_bytes",
        "host_reserve_bytes",
    )
    host = {}
    for field in host_fields:
        raw = requested_budget.get(field)
        if not _strict_nonnegative_int(raw):
            return _hold("HOLD_RUNTIME_BUDGET_INCOMPLETE", field=field)
        host[field] = raw

    if not any(values["model_resident_bytes_by_gpu"]) and not host["host_model_resident_bytes"]:
        return _hold("HOLD_RUNTIME_MODEL_RESIDENCY_UNKNOWN")
    if (not any(values["kv_cache_bytes_by_gpu"]) and
            not host["host_kv_cache_bytes"]):
        return _hold("HOLD_RUNTIME_KV_BUDGET_UNKNOWN")
    if any(reserve <= 0 for reserve in values["gpu_reserve_bytes_by_gpu"]) or host["host_reserve_bytes"] <= 0:
        return _hold("HOLD_RUNTIME_RESERVE_REQUIRED")

    gpu_headroom = {}
    for device_id in GPU_IDS:
        needed = sum(values[field][device_id] for field in list_fields)
        free = by_id[device_id]["free_bytes"]
        if needed > free:
            return _hold("HOLD_RUNTIME_GPU_MEMORY_BUDGET",
                         gpu_id=device_id, free_bytes=free,
                         required_bytes=needed, deficit_bytes=needed - free)
        gpu_headroom[device_id] = free - needed

    host_needed = sum(host.values())
    if host_needed > cgroup_free:
        return _hold("HOLD_RUNTIME_CGROUP_MEMORY_BUDGET",
                     free_bytes=cgroup_free, required_bytes=host_needed,
                     deficit_bytes=host_needed - cgroup_free)

    return {
        "state": "SOURCE_ONLY_MEMORY_BUDGET_FIT_NOT_RUNTIME_VERIFIED",
        "launchable": False,
        "measured": False,
        "telemetry_authenticated": False,
        "readback_id": readback_id,
        "gpu_headroom_bytes": {str(key): value for key, value in gpu_headroom.items()},
        "cgroup_free_bytes": cgroup_free,
        "host_required_bytes": host_needed,
        "context_tokens": requested_budget["context_tokens"],
        "proof_boundary": "Freshness shape and arithmetic only; source cannot authenticate telemetry or prove runtime fit",
    }
