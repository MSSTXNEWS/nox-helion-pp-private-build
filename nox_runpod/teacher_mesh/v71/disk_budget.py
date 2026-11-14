"""Shared NOX PRIME evidence-based disk gate.

Never use a historical 20GB constant to block an otherwise healthy chat.
Actual *new writes* (checkpoint, temp, optimizer, output) need a verified
worst-case size and space for rollback. This pure function never writes.
"""
from __future__ import annotations

from collections.abc import Mapping

# Small nonzero filesystem headroom, not a fixed requirement of 20GB.
SAFETY_FLOOR_BYTES = 512 * 1024 * 1024


def verify_new_write_space(snapshot: Mapping, *, checkpoint_key: str =
                           "estimated_new_checkpoint_bytes") -> dict:
    out = {
        "schema": "NOX_PRIME_DISK_ADMISSION_V1",
        "state": "HOLD_DISK_BUDGET_UNVERIFIED",
        "performed": False,
        "chat_allowed": True,
        "training_allowed_by_disk_alone": False,
        "required_bytes": None,
    }
    if not isinstance(snapshot, Mapping):
        return out
    free = snapshot.get("disk_free_bytes")
    checkpoint = snapshot.get(checkpoint_key)
    temp = snapshot.get("estimated_temp_bytes")
    floor = snapshot.get("min_free_after_bytes", SAFETY_FLOOR_BYTES)
    if (snapshot.get("disk_write_estimate_verified") is not True or
        any(type(x) is not int for x in (free, checkpoint, temp, floor)) or
        free < 0 or checkpoint <= 0 or temp < 0 or floor < SAFETY_FLOOR_BYTES):
        return out
    required = checkpoint + temp + floor
    out["required_bytes"] = required
    out["available_bytes"] = free
    out["margin_after_write_bytes"] = free - checkpoint - temp
    if required > free:
        out["state"] = "HOLD_INSUFFICIENT_SPACE_FOR_NEW_WRITE"
        return out
    out["state"] = "READY_FOR_OTHER_NATIVE_GATES"
    out["training_allowed_by_disk_alone"] = True
    return out
