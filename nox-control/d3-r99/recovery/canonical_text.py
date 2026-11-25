"""Exact retained S03 assistant text for GET-only terminal recovery.
Owner authenticates terminal scope, served build, link bytes/pin and retained
descriptors independently before invoking. Never authorizes ACK or POST.
"""
import hashlib
import re
from b5_retained_ingress import load_retained_chain
from b5_r55_pinned import strict_owner_json_bytes

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def token(x):
    return (type(x) is str and 0 < len(x) <= 160 and x == x.strip()
            and not any(ord(c) < 32 or ord(c) == 127 for c in x))

def pin(x):
    return type(x) is str and re.fullmatch(r"[0-9a-f]{64}", x) is not None and len(set(x)) > 1

def recover_text(*, dialog_id, session_id, sequence, artifacts, terminal,
                 served_sha256, link_bytes, link_sha256):
    if type(sequence) is not int or sequence not in (2, 3):
        raise ValueError("HOLD_RECOVERY_SEQUENCE")
    if type(artifacts) is not tuple or len(artifacts) != sequence:
        raise ValueError("HOLD_RECOVERY_CHAIN")
    if not pin(served_sha256) or not pin(link_sha256) or type(link_bytes) is not bytes or digest(link_bytes) != link_sha256:
        raise ValueError("HOLD_RECOVERY_LINK_PIN")
    link = strict_owner_json_bytes(link_bytes)
    if type(link) is not dict or link.get("schema") != "NOX_B3_S03_TERMINAL_LINK_V1" or type(terminal) is not dict:
        raise ValueError("HOLD_RECOVERY_LINK")
    if terminal.get("status") != "STREAM_ENDED_READBACK_REQUIRED" or type(terminal.get("sequence")) is not int or terminal["sequence"] != sequence or type(link.get("sequence")) is not int or link["sequence"] != sequence:
        raise ValueError("HOLD_RECOVERY_TERMINAL")
    scope = {}
    for k in ("conversation_id", "exchange_id", "physical_dialog_id", "request_id", "attempt_id"):
        v = terminal.get(k)
        if not token(v) or link.get(k) != v:
            raise ValueError("HOLD_RECOVERY_SCOPE:" + k)
        scope[k] = v
    if link.get("served_sha256") != served_sha256:
        raise ValueError("HOLD_RECOVERY_BUILD")
    rows, (w, r, ws, rs) = load_retained_chain(dialog_id=dialog_id, session_id=session_id, artifacts=artifacts)[-1]
    writer, reader = strict_owner_json_bytes(w), strict_owner_json_bytes(r)
    for k in ("dialog_id", "session_id", "event_id", "turn_id"):
        v = link.get("s03_" + k)
        if not token(v) or writer.get(k) != v or reader.get(k) != v:
            raise ValueError("HOLD_RECOVERY_S03:" + k)
    if link.get("writer_sha256") != ws or link.get("readback_sha256") != rs or link_sha256 in (ws, rs):
        raise ValueError("HOLD_RECOVERY_WITNESS")
    if link.get("user_message_id") != rows[-2]["message_id"] or link.get("assistant_message_id") != rows[-1]["message_id"]:
        raise ValueError("HOLD_RECOVERY_MESSAGE")
    text = rows[-1]["content"]
    if type(text) is not str or not text:
        raise ValueError("HOLD_RECOVERY_TEXT")
    answer_sha = digest(text.encode("utf-8", errors="strict"))
    if reader.get("full_answer_sha256") != answer_sha:
        raise ValueError("HOLD_RECOVERY_ANSWER")
    return dict(schema="NOX_B5_CANONICAL_ASSISTANT_TEXT_V1", **scope,
                sequence=sequence, served_sha256=served_sha256,
                s03_dialog_id=dialog_id, s03_session_id=session_id,
                s03_event_id=reader["event_id"], s03_turn_id=reader["turn_id"],
                assistant_message_id=rows[-1]["message_id"], assistant_text=text,
                answer_sha256=answer_sha, writer_sha256=ws, readback_sha256=rs,
                link_sha256=link_sha256, authentication_verified=False,
                native_accepted=False, ack_allowed=False, next_post_allowed=False)
