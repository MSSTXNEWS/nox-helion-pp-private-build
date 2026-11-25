"""Opt-in R65 -> B3 R70 canonical evidence projection, not admission."""
from b5_retained_ingress import load_retained_chain
from b5_r55_pinned import strict_owner_json_bytes

def terminal_canonical(*, dialog_id, session_id, expected_turn, artifacts):
    """Use only owner-opened original descriptors and detached authenticated pins.
    No candidate canonical object, no POST, no write, no authentication claim.
    The caller must separately authenticate the scope, link and pins.
    """
    if type(expected_turn) is not int or expected_turn not in (2, 3):
        raise ValueError("HOLD_TERMINAL_TURN")
    if type(artifacts) is not tuple or len(artifacts) != expected_turn:
        raise ValueError("HOLD_TERMINAL_CHAIN_LENGTH")
    chain = load_retained_chain(dialog_id=dialog_id, session_id=session_id,
                                artifacts=artifacts)
    rows, (writer, reader, ws, rs) = chain[-1]
    return dict(writer=strict_owner_json_bytes(writer),
                readback=strict_owner_json_bytes(reader), rows=rows,
                writer_sha256=ws, readback_sha256=rs)
