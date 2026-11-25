"""Read-only S03 post-failure evidence. All outcomes HOLD; never retry a POST.
The independent owner supplies the post-attempt snapshot, its external digest
and attempt identity. No claim of freshness/authenticity from JSON alone.
A pending user row is not a completed turn and is never silently discarded.
"""
import hashlib
import re
from b5_r55_pinned import strict_owner_json_bytes, canonical_s03_firstturn_prefix_valid
from b5_chain_guard import verify_existing_chain

def classify_failed_turn(*, dialog_id, session_id, attempt_id, prompt,
                         prior_chain, snapshot_raw, snapshot_sha256):
    if (type(attempt_id) is not str or not attempt_id or attempt_id.strip() != attempt_id
            or type(prompt) is not str or not prompt.strip()
            or type(snapshot_raw) is not bytes or not 0 < len(snapshot_raw) <= 200000
            or type(snapshot_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", snapshot_sha256) is None
            or hashlib.sha256(snapshot_raw).hexdigest() != snapshot_sha256):
        return "HOLD_S03_FAILURE_INPUT"
    try:
        if type(prior_chain) is not tuple or len(prior_chain) not in (1, 2):
            return "HOLD_S03_FAILURE_PREFIX"
        rows, pins = prior_chain[-1]
        if len(prior_chain) == 1:
            valid = canonical_s03_firstturn_prefix_valid(
                *pins, dialog_id, rows, expected_session_id=session_id)
        else:
            valid = verify_existing_chain(dialog_id=dialog_id, session_id=session_id,
                                          chain=prior_chain)
        if not valid or any(snapshot_sha256 in c[1][2:] for c in prior_chain):
            return "HOLD_S03_FAILURE_PREFIX"
        doc = strict_owner_json_bytes(snapshot_raw)
        if (type(doc) is not dict or doc.get("source") != "canonical_s03"
                or doc.get("independent") is not True
                or doc.get("dialog_id") != dialog_id or doc.get("session_id") != session_id
                or doc.get("attempt_id") != attempt_id
                or type(doc.get("messages")) is not list):
            return "HOLD_S03_FAILURE_SCOPE"
        observed = doc["messages"]
        if any(type(row) is not dict for row in observed):
            return "HOLD_S03_FAILURE_SCOPE"
        if observed[:len(rows)] != rows:
            return "HOLD_S03_FAILURE_PREFIX_CHANGED"
        if len(observed) == len(rows):
            return "HOLD_S03_FAILURE_PREFIX_INTACT"
        if len(observed) == len(rows) + 1:
            pending = observed[-1]
            mid = pending.get("message_id")
            if (pending.get("role") == "user" and pending.get("content") == prompt
                    and pending.get("dialog_id") == dialog_id
                    and pending.get("session_id") == session_id
                    and type(mid) is str and mid and mid.strip() == mid
                    and mid not in {row["message_id"] for row in rows}):
                return "HOLD_S03_FAILURE_PENDING_USER"
        return "HOLD_S03_FAILURE_UNEXPECTED_ROWS"
    except (ValueError, TypeError, KeyError, RuntimeError, UnicodeError, RecursionError):
        return "HOLD_S03_FAILURE_INVALID"
