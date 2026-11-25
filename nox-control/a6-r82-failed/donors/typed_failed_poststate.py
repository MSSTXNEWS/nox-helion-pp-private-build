"""Type-exact diagnostic fence for failed S03 turns; no retry or ACK authority."""
import json
from b5_r55_pinned import strict_owner_json_bytes
from b5_strict_receipted_poststate import classify_strict_receipted_failed_turn

def _wire(rows):
    return json.dumps(rows, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")

def classify_typed_failed_turn(*, admission_raw=None, admission_sha256=None, **evidence):
    state = classify_strict_receipted_failed_turn(
        admission_raw=admission_raw, admission_sha256=admission_sha256, **evidence)
    if state not in ("HOLD_S03_FAILURE_PREFIX_INTACT", "HOLD_S03_FAILURE_PENDING_USER"):
        return state
    # The original gate checked detached pins, scope, and admitted pending ID.
    # Compare exact JSON types from the pinned readback, not caller row equality.
    try:
        previous = None
        for rows, pins in evidence["prior_chain"]:
            canonical = strict_owner_json_bytes(pins[1])["messages"]
            if _wire(rows) != _wire(canonical):
                return "HOLD_S03_FAILURE_TYPED_PREFIX_CHANGED"
            if previous is not None and _wire(previous) != _wire(canonical[:len(previous)]):
                return "HOLD_S03_FAILURE_TYPED_PREFIX_CHANGED"
            previous = canonical
        observed = strict_owner_json_bytes(evidence["snapshot_raw"])["messages"]
        if _wire(previous) != _wire(observed[:len(previous)]):
            return "HOLD_S03_FAILURE_TYPED_PREFIX_CHANGED"
        return state
    except (ValueError, TypeError, KeyError, RuntimeError, UnicodeError, RecursionError):
        return "HOLD_S03_FAILURE_INVALID"
