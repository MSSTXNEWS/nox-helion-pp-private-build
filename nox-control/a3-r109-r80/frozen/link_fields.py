"""S03-only fields for the owner-authenticated per-turn terminal link.
Inputs are independently opened and pinned retained checkpoint descriptors.
Does not construct terminal/build evidence, authenticate caller, or permit ACK/POST.
"""
from b5_retained_ingress import load_retained_chain
from b5_r55_pinned import strict_owner_json_bytes
from canonical_text import token

def derive_link_fields(*, dialog_id, session_id, sequence, artifacts):
    if type(sequence) is not int or sequence not in (2, 3):
        raise ValueError("HOLD_LINK_FIELDS_SEQUENCE")
    if type(artifacts) is not tuple or len(artifacts) != sequence:
        raise ValueError("HOLD_LINK_FIELDS_CHAIN")
    rows, (w, r, ws, rs) = load_retained_chain(
        dialog_id=dialog_id, session_id=session_id, artifacts=artifacts)[-1]
    writer, reader = strict_owner_json_bytes(w), strict_owner_json_bytes(r)
    result = {}
    for key in ("dialog_id", "session_id", "event_id", "turn_id"):
        value = reader.get(key)
        if not token(value) or writer.get(key) != value:
            raise ValueError("HOLD_LINK_FIELDS_SCOPE:" + key)
        result["s03_" + key] = value
    for key, row in (("user_message_id", rows[-2]),
                     ("assistant_message_id", rows[-1])):
        value = row["message_id"]
        if not token(value):
            raise ValueError("HOLD_LINK_FIELDS_MESSAGE:" + key)
        result[key] = value
    return dict(result, writer_sha256=ws, readback_sha256=rs)
