"""One retained three-turn chain for both terminal projections. Offline only.
All scope, links, physical receipts and pins require independent authentication.
"""
import copy
from b5_retained_ingress import load_retained_chain
from b5_r55_pinned import strict_owner_json_bytes

def compose_pair(*, dialog_id, session_id, artifacts, receipts, turns):
    if type(artifacts) is not tuple or len(artifacts) != 3:
        raise ValueError("HOLD_PAIR_RETAINED_LENGTH")
    if type(turns) is not tuple or len(turns) != 2:
        raise ValueError("HOLD_PAIR_TURNS")
    keys = {"wire", "physical", "mapping", "scope", "expectedTurn", "terminal", "link"}
    payload = dict(receipts=copy.deepcopy(receipts), turns=copy.deepcopy(list(turns)))
    for n, item in enumerate(payload["turns"], 2):
        if type(item) is not dict or set(item) != keys or type(item["expectedTurn"]) is not int or item["expectedTurn"] != n:
            raise ValueError("HOLD_PAIR_INPUT")
    chain = load_retained_chain(dialog_id=dialog_id, session_id=session_id, artifacts=artifacts)
    for n, item in enumerate(payload["turns"], 2):
        rows, (w, r, ws, rs) = chain[n-1]
        item["canonical"] = dict(writer=strict_owner_json_bytes(w),
            readback=strict_owner_json_bytes(r), rows=rows,
            writer_sha256=ws, readback_sha256=rs)
    # Pass directly to pinned B3 R71; no POST, ACK or authority.
    return payload
