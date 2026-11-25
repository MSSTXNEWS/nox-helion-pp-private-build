"""Immutable B5→B3 handoff. Offline evidence, never native/ACK authority."""
import copy
import hashlib
import json
from bind_retained_pair import bind_retained_pair
from b5_r55_pinned import strict_owner_json_bytes

def freeze_consumer_payload(candidates, *, dialog_id, session_id, artifacts, turns, physical_bytes):
    """Accept immutable JSON bytes, validate a private snapshot and return exact
    Node arguments as immutable UTF-8 bytes plus their SHA256.
    Caller must pass these bytes unchanged and independently authenticate pins.
    """
    if type(physical_bytes) is not bytes:
        raise ValueError("HOLD_PHYSICAL_BYTES_REQUIRED")
    physical = strict_owner_json_bytes(physical_bytes, limit=2_000_000)
    candidates, turns = copy.deepcopy((candidates, turns))
    pair, links = bind_retained_pair(candidates, dialog_id=dialog_id,
        session_id=session_id, artifacts=artifacts, turns=turns, physical_input=physical)
    for flag in ("native_accepted", "authentication_verified", "ack_allowed", "next_post_allowed"):
        if pair.get(flag) is not False:
            raise ValueError("HOLD_OFFLINE_AUTHORITY")
    payload = json.dumps([physical, pair, links], ensure_ascii=False,
        allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8", errors="strict")
    return payload, hashlib.sha256(payload).hexdigest()
