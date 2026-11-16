"""Estimate-only memory arithmetic for Maya's 2x V100 profile.

No trusted pack+telemetry verifier is currently available. Therefore this module
never admits a runtime plan: even fresh, correctly-shaped inputs and arithmetic
within caller-reported capacities return HOLD_UNVERIFIED_PROVENANCE. The labels,
readback ID, timestamps, and allocation budgets are caller-controlled metadata,
not authentication.

A future verifier must bind, in one owner-authorized receipt: (1) exact model
pack file hashes and tensor/expert placement; (2) the actual context, activation,
and KV allocation recipe; (3) per-device nvidia-smi and cgroup-v2 readbacks
with source time; and (4) the STOP/lease admission. Only a verifier that checks
that receipt may issue a trusted runtime-admission state.
"""
from __future__ import annotations

from datetime import datetime, timezone

GPU_IDS = (0, 1)
GPU_NAME = "Tesla V100-SXM2-32GB"
MAX_SAMPLE_AGE_SECONDS = 10
MAX_FUTURE_SKEW_SECONDS = 2
MIN_GPU_TOTAL_BYTES = 30 * 1024 ** 3
VERIFIER_BOUNDARY = (
    "HOLD until an owner-authorized verifier binds exact model-pack hashes, "
    "tensor placement, activation/KV recipe, fresh per-GPU/cgroup telemetry, "
    "and STOP/lease receipt; caller labels are not proof"
)


def _hold(state: str, **details) -> dict:
    return {
        **details,
        "state": state,
        "admission_state": "HOLD_UNVERIFIED_PROVENANCE",
        "admission": False,
        "launchable": False,
        "estimate_only": True,
        "telemetry_authenticated": False,
        "provenance_verified": False,
    }


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


def evaluate_memory_budget(observation, requested_budget) -> dict:
    """Return holds/estimates only; this function cannot authorize admission."""
    now = datetime.now(timezone.utc)
    if not isinstance(observation, dict) or not isinstance(requested_budget, dict):
        return _hold("HOLD_RUNTIME_MEMORY_TELEMETRY", verifier_boundary=VERIFIER_BOUNDARY)
    readback_id = observation.get("readback_id")
    if not isinstance(readback_id, str) or not readback_id.strip() or len(readback_id) > 128:
        return _hold("HOLD_RUNTIME_MEMORY_READBACK_ID", verifier_boundary=VERIFIER_BOUNDARY)
    gpus = observation.get("gpus")
    if not isinstance(gpus, (list, tuple)) or len(gpus) != 2:
        return _hold("HOLD_RUNTIME_GPU_INVENTORY", verifier_boundary=VERIFIER_BOUNDARY)
    if not all(isinstance(row, dict) for row in gpus):
        return _hold("HOLD_RUNTIME_GPU_INVENTORY", verifier_boundary=VERIFIER_BOUNDARY)

    by_id = {}
    for row in gpus:
        device_id = row.get("id")
        if type(device_id) is not int or device_id in by_id:
            return _hold("HOLD_RUNTIME_GPU_INVENTORY", verifier_boundary=VERIFIER_BOUNDARY)
        # Source strings are shape labels only; they do not authenticate a collector.
        if row.get("source") != "nvidia-smi":
            return _hold("HOLD_RUNTIME_GPU_SOURCE", gpu_id=device_id,
                         verifier_boundary=VERIFIER_BOUNDARY)
        if not _is_fresh(row.get("captured_at"), now):
            return _hold("HOLD_RUNTIME_GPU_TELEMETRY_STALE", gpu_id=device_id,
                         verifier_boundary=VERIFIER_BOUNDARY)
        if row.get("name") != GPU_NAME:
            return _hold("HOLD_RUNTIME_GPU_IDENTITY", gpu_id=device_id,
                         verifier_boundary=VERIFIER_BOUNDARY)
        total = row.get("total_bytes")
        free = row.get("free_bytes")
        if (not _strict_nonnegative_int(total) or not _strict_nonnegative_int(free)
                or total < MIN_GPU_TOTAL_BYTES or free <= 0 or free > total):
            return _hold("HOLD_RUNTIME_GPU_MEMORY_READING", gpu_id=device_id,
                         verifier_boundary=VERIFIER_BOUNDARY)
        by_id[device_id] = row
    if set(by_id) != set(GPU_IDS):
        return _hold("HOLD_RUNTIME_GPU_INVENTORY", verifier_boundary=VERIFIER_BOUNDARY)

    cgroup = observation.get("cgroup")
    if not isinstance(cgroup, dict) or cgroup.get("source") != "cgroup-v2":
        return _hold("HOLD_RUNTIME_CGROUP_SOURCE", verifier_boundary=VERIFIER_BOUNDARY)
    if not _is_fresh(cgroup.get("captured_at"), now):
        return _hold("HOLD_RUNTIME_CGROUP_TELEMETRY_STALE",
                     verifier_boundary=VERIFIER_BOUNDARY)
    current = cgroup.get("current_bytes")
    limit = cgroup.get("max_bytes")
    if (not _strict_nonnegative_int(current) or not _strict_nonnegative_int(limit)
            or limit <= 0 or current > limit):
        return _hold("HOLD_RUNTIME_CGROUP_MEMORY_READING",
                     verifier_boundary=VERIFIER_BOUNDARY)
    cgroup_free = limit - current

    if requested_budget.get("gpu_ids") != [0, 1]:
        return _hold("HOLD_RUNTIME_BUDGET_GPU_MAP", verifier_boundary=VERIFIER_BOUNDARY)
    if type(requested_budget.get("context_tokens")) is not int or requested_budget["context_tokens"] != 4096:
        return _hold("HOLD_RUNTIME_BUDGET_CONTEXT", verifier_boundary=VERIFIER_BOUNDARY)
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
            return _hold("HOLD_RUNTIME_BUDGET_INCOMPLETE", field=field,
                         verifier_boundary=VERIFIER_BOUNDARY)
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
            return _hold("HOLD_RUNTIME_BUDGET_INCOMPLETE", field=field,
                         verifier_boundary=VERIFIER_BOUNDARY)
        host[field] = raw

    if not any(values["model_resident_bytes_by_gpu"]) and not host["host_model_resident_bytes"]:
        return _hold("HOLD_RUNTIME_MODEL_RESIDENCY_UNKNOWN",
                     verifier_boundary=VERIFIER_BOUNDARY)
    if (not any(values["kv_cache_bytes_by_gpu"]) and
            not host["host_kv_cache_bytes"]):
        return _hold("HOLD_RUNTIME_KV_BUDGET_UNKNOWN",
                     verifier_boundary=VERIFIER_BOUNDARY)
    if any(reserve <= 0 for reserve in values["gpu_reserve_bytes_by_gpu"]) or host["host_reserve_bytes"] <= 0:
        return _hold("HOLD_RUNTIME_RESERVE_REQUIRED",
                     verifier_boundary=VERIFIER_BOUNDARY)

    gpu_estimates = {}
    overcommit = None
    for device_id in GPU_IDS:
        required = sum(values[field][device_id] for field in list_fields)
        free = by_id[device_id]["free_bytes"]
        gpu_estimates[str(device_id)] = {
            "reported_free_bytes": free,
            "estimated_required_bytes": required,
            "estimated_headroom_bytes": free - required,
        }
        if required > free and overcommit is None:
            overcommit = {
                "resource": "gpu",
                "gpu_id": device_id,
                "deficit_bytes": required - free,
            }

    host_required = sum(host.values())
    if host_required > cgroup_free and overcommit is None:
        overcommit = {
            "resource": "cgroup",
            "deficit_bytes": host_required - cgroup_free,
        }

    arithmetic_state = "WITHIN_REPORTED_CAPACITY" if overcommit is None else "OVERCOMMITTED"
    return _hold(
        "HOLD_UNVERIFIED_PROVENANCE",
        arithmetic_state=arithmetic_state,
        arithmetic_overcommit=overcommit,
        estimated_gpu_budget=gpu_estimates,
        estimated_cgroup_free_bytes=cgroup_free,
        estimated_host_required_bytes=host_required,
        context_tokens=requested_budget["context_tokens"],
        untrusted_readback_id=readback_id,
        verifier_boundary=VERIFIER_BOUNDARY,
    )
