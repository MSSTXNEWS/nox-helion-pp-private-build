"""B5 retained witness fence for the B3 R78 consumer; offline only."""
import json
from b5_retained_ingress import load_retained_chain
from b5_r55_pinned import strict_owner_json_bytes
from pair_projection import compare_pair

def _same(a, b):
    return json.dumps(a, sort_keys=True, ensure_ascii=False, allow_nan=False) == json.dumps(b, sort_keys=True, ensure_ascii=False, allow_nan=False)

def bind_retained_pair(candidates, *, dialog_id, session_id, artifacts, turns, physical_input):
    """Verify the independently retained raw witnesses against B3's row objects.
    No authentication, native acceptance, ACK or next POST authority.
    """
    pair = compare_pair(candidates, dialog_id=dialog_id, session_id=session_id,
                        artifacts=artifacts, turns=turns)
    chain = load_retained_chain(dialog_id=dialog_id, session_id=session_id, artifacts=artifacts)
    if type(physical_input) is not dict or type(physical_input.get("turns")) is not list or len(physical_input["turns"]) != 2:
        raise ValueError("HOLD_B3_PAIR_SHAPE")
    payloads = []
    for i, (provided, evidence) in enumerate(zip(physical_input["turns"], turns), 2):
        rows, (w, r, ws, rs) = chain[i-1]
        canonical = dict(writer=strict_owner_json_bytes(w), readback=strict_owner_json_bytes(r),
                         rows=rows, writer_sha256=ws, readback_sha256=rs)
        link = strict_owner_json_bytes(evidence["link_bytes"])
        if type(provided) is not dict or not _same(provided.get("canonical"), canonical):
            raise ValueError("HOLD_B3_CANONICAL_WITNESS:"+str(i))
        if not _same(provided.get("terminal"), evidence["terminal"]) or not _same(provided.get("link"), link):
            raise ValueError("HOLD_B3_TERMINAL_LINK:"+str(i))
        payloads.append(evidence["link_bytes"].decode("utf-8", errors="strict"))
    return pair, payloads
