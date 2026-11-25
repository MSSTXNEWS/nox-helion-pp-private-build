"""Read-only failed S03 diagnostic with canonical pending-row identity rules."""
from b5_r55_pinned import strict_owner_json_bytes
from typed_failed_poststate import classify_typed_failed_turn

def classify_wire_failed_turn(*, admission_raw=None, admission_sha256=None, **evidence):
    state = classify_typed_failed_turn(
        admission_raw=admission_raw, admission_sha256=admission_sha256, **evidence)
    if state not in ("HOLD_S03_FAILURE_PENDING_USER", "HOLD_S03_FAILURE_PREFIX_INTACT"):
        return state
    if not evidence["attempt_id"].isprintable():
        return "HOLD_S03_FAILURE_ATTEMPT_ID_INVALID"
    if state == "HOLD_S03_FAILURE_PENDING_USER":
        try:
            row = strict_owner_json_bytes(evidence["snapshot_raw"])["messages"][-1]
            if not row["message_id"].isprintable():
                return "HOLD_S03_FAILURE_PENDING_ID_INVALID"
            # Canonical completed history requires actual UTF-8 text, not lone
            # escaped UTF-16 surrogates that cannot be persisted as UTF-8.
            row["content"].encode("utf-8", errors="strict")
        except (ValueError, TypeError, KeyError, RuntimeError, UnicodeError, RecursionError):
            return "HOLD_S03_FAILURE_PENDING_TEXT_INVALID"
    return state
