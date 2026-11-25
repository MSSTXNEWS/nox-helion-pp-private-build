"""Pair recovery verifier for an existing RU/ES dialogue, offline only.
The owner must supply one independent retained chain and separately authenticated
terminal/build/link evidence. No network, ACK, POST, or authentication authority.
"""
from projection_match import compare_projection
from canonical_text import token

def compare_pair(candidates, *, dialog_id, session_id, artifacts, turns):
    if type(artifacts) is not tuple or len(artifacts) != 3:
        raise ValueError("HOLD_PAIR_CHAIN")
    if type(candidates) is not tuple or len(candidates) != 2 or type(turns) is not tuple or len(turns) != 2:
        raise ValueError("HOLD_PAIR_SHAPE")
    keys = {"terminal", "served_sha256", "link_bytes", "link_sha256"}
    for turn in turns:
        if type(turn) is not dict or set(turn) != keys or type(turn["terminal"]) is not dict:
            raise ValueError("HOLD_PAIR_INPUT")
    a, b = (t["terminal"] for t in turns)
    for k in ("conversation_id", "physical_dialog_id"):
        if not token(a.get(k)) or a[k] != b.get(k):
            raise ValueError("HOLD_PAIR_SCOPE:" + k)
    if turns[0]["served_sha256"] != turns[1]["served_sha256"]:
        raise ValueError("HOLD_PAIR_BUILD")
    for k in ("exchange_id", "request_id", "attempt_id"):
        if not token(a.get(k)) or not token(b.get(k)) or a[k] == b[k]:
            raise ValueError("HOLD_PAIR_REUSE:" + k)
    matches = tuple(compare_projection(candidate, dialog_id=dialog_id,
        session_id=session_id, sequence=n, artifacts=artifacts[:n], **turn)
        for n, (candidate, turn) in enumerate(zip(candidates, turns), 2))
    return dict(status="S03_PROJECTION_PAIR_MATCHED_OFFLINE",
        turns=matches, authentication_verified=False, native_accepted=False,
        ack_allowed=False, next_post_allowed=False)
