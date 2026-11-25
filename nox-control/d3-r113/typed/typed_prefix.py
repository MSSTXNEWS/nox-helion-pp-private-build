"""Type-exact retained prefix fence for R111/R80. Offline evidence only."""
import json
from b5_retained_ingress import load_retained_chain
from frozen_consumer import freeze_consumer_payload

def _canonical_rows(rows):
    return json.dumps(rows, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8", errors="strict")

def load_typed_chain(*, dialog_id, session_id, artifacts):
    chain = load_retained_chain(dialog_id=dialog_id, session_id=session_id, artifacts=artifacts)
    for previous, current in zip(chain, chain[1:]):
        if _canonical_rows(previous[0]) != _canonical_rows(current[0][:len(previous[0])]):
            raise ValueError("HOLD_S03_TYPED_PREFIX_CHANGED")
    return chain

def freeze_typed_payload(candidates, *, dialog_id, session_id, artifacts, turns, physical_bytes):
    # All rereads are bound to the same independently supplied raw SHA256 pins.
    load_typed_chain(dialog_id=dialog_id, session_id=session_id, artifacts=artifacts)
    return freeze_consumer_payload(candidates, dialog_id=dialog_id, session_id=session_id,
        artifacts=artifacts, turns=turns, physical_bytes=physical_bytes)
