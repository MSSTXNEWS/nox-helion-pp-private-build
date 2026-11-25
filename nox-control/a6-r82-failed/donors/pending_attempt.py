"""Pending S03 row consistency with the independently pinned failed attempt.

Optional legacy row attempt metadata may be absent. Explicit conflicting
metadata must never be classified as the admitted pending user. All HOLD.
"""
import json
from b5_r55_pinned import strict_owner_json_bytes
from pending_wire import classify_wire_failed_turn

def classify_pending_attempt(*, admission_raw=None, admission_sha256=None, **evidence):
    state = classify_wire_failed_turn(
        admission_raw=admission_raw, admission_sha256=admission_sha256, **evidence)
    if state != "HOLD_S03_FAILURE_PENDING_USER":
        return state
    try:
        row = strict_owner_json_bytes(evidence["snapshot_raw"])["messages"][-1]
        if "attempt_id" in row and (type(row["attempt_id"]) is not str
                                    or row["attempt_id"] != evidence["attempt_id"]):
            return "HOLD_S03_FAILURE_PENDING_ATTEMPT_MISMATCH"
        # Text is already checked by R83. Check the complete pending row,
        # including extension keys and values, just like R82's typed prefix.
        json.dumps(row, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, KeyError, RuntimeError, UnicodeError, RecursionError):
        return "HOLD_S03_FAILURE_PENDING_METADATA_INVALID"
    return state
