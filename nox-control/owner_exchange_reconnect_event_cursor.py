"""B1 source-only signed readback cursor for one *verified* S03 exchange.

Not connected to serving, model calls, or live S03. A caller must obtain the
owner-verified immutable S03 proof AND assert durable exchange READBACK_ONLY.
This module never issues a model POST, never mutates a database, and does not
claim that source-only witnesses represent native acceptance.

The single terminal event has an immutable id so clients can deduplicate a
retry after a lost ACK. Cursor '1' means that event was consumed; an old cursor
can redeliver the same event id, but can never create a new assistant turn.
"""
import base64
import hashlib
import hmac
import json
import re


class HoldReconnect(RuntimeError):
    """Fail-closed hold; callers must NOT fall back to a new inference POST."""


_CURSOR_SCHEMA = "NOX_B1_S03_RECONNECT_CURSOR_V1"
_CANDIDATE_SCHEMA = "NOX_B1_SOURCE_S03_WRITER_CANDIDATE_V1"
_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9_-]{1,1200}\Z")


def _id(value):
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise HoldReconnect("HOLD_RECONNECT_IDENTITY")
    return value


def _sha(value):
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise HoldReconnect("HOLD_RECONNECT_DIGEST")
    return value


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=True,
                      allow_nan=False, separators=(",", ":")).encode("ascii")


def _snapshot(candidate, receipt):
    if type(candidate) is not dict or type(receipt) is not dict:
        raise HoldReconnect("HOLD_RECONNECT_PROOF")
    if candidate.get("schema") != _CANDIDATE_SCHEMA:
        raise HoldReconnect("HOLD_RECONNECT_CANDIDATE_SCHEMA")
    claim = {k: _id(candidate.get(k)) for k in (
        "owner", "request_id", "conversation_id", "exchange_id", "s03_record_id")}
    for key in ("request_sha256", "s03_proof_sha256", "s03_item_sha256",
                "user_sha256", "response_sha256"):
        claim[key] = _sha(candidate.get(key))
    pair = candidate.get("pair_row_ids")
    if (type(pair) is not list or len(pair) != 2 or
            any(type(v) is not int or v <= 0 for v in pair) or pair[0] >= pair[1]):
        raise HoldReconnect("HOLD_RECONNECT_PAIR")
    claim["assistant_row_id"] = pair[1]
    claim["writer_blob_sha1"] = candidate.get("writer_blob_sha1")
    if (type(claim["writer_blob_sha1"]) is not str or
            re.fullmatch(r"[0-9a-f]{40}\Z", claim["writer_blob_sha1"]) is None):
        raise HoldReconnect("HOLD_RECONNECT_WRITER")
    # Strict envelope only: authenticity needs owner/immutable-verifier callback.
    if receipt.get("native_verified") is not True:
        raise HoldReconnect("HOLD_RECONNECT_NATIVE_PROOF")
    for key in ("owner", "request_id", "conversation_id", "exchange_id",
                "s03_record_id", "request_sha256", "s03_proof_sha256",
                "response_sha256"):
        if receipt.get(key) != claim[key]:
            raise HoldReconnect("HOLD_RECONNECT_PROOF_SCOPE")
    # Freeze technical envelope before invoking untrusted callbacks.
    proof = {k: receipt[k] for k in (
        "owner", "request_id", "conversation_id", "exchange_id",
        "s03_record_id", "request_sha256", "s03_proof_sha256",
        "response_sha256")}
    proof["native_verified"] = True
    return claim, proof


def _sign(payload, secret):
    msg = _canonical(payload)
    digest = hmac.new(secret, msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(msg + digest).decode("ascii").rstrip("=")


def _decode(token, secret):
    if type(token) is not str or _TOKEN.fullmatch(token) is None:
        raise HoldReconnect("HOLD_RECONNECT_CURSOR_FORMAT")
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        if len(raw) <= 32:
            raise ValueError("short")
        msg, sig = raw[:-32], raw[-32:]
        if not hmac.compare_digest(sig, hmac.new(secret, msg, hashlib.sha256).digest()):
            raise ValueError("bad signature")
        obj = json.loads(msg.decode("ascii"))
        if type(obj) is not dict or _canonical(obj) != msg:
            raise ValueError("not canonical")
        return obj
    except (ValueError, UnicodeError, TypeError, OverflowError) as exc:
        raise HoldReconnect("HOLD_RECONNECT_CURSOR_AUTH") from exc


def resume_terminal(candidate, receipt, *, cursor, secret, permit,
                    durable_claim, immutable_verifier):
    """Return readback-only terminal metadata and next cursor, never content.

    permit() must check fresh owner/STOP/lease/resource scope. durable_claim()
    must check a preexisting durable exchange is READBACK_ONLY, not IN_FLIGHT.
    immutable_verifier must verify a real owner-signed receipt independently;
    a test stub returning True is NEVER native acceptance.

    cursor=None requests the one terminal event; the returned next_cursor
    ACKs that event. A second invocation with next_cursor returns no events.
    Client must deduplicate by immutable event_id if an ACK is lost.
    """
    if type(secret) is not bytes or len(secret) < 32:
        raise HoldReconnect("HOLD_RECONNECT_SIGNING_KEY")
    if not all(callable(f) for f in (permit, durable_claim, immutable_verifier)):
        raise HoldReconnect("HOLD_RECONNECT_OWNER_GATE")
    claim, verified = _snapshot(candidate, receipt)
    if permit() is not True or durable_claim() != "READBACK_ONLY":
        raise HoldReconnect("HOLD_RECONNECT_DURABILITY")
    # Callbacks receive copies; neither can alter the snapshot to be signed.
    if immutable_verifier(dict(claim), dict(verified)) is not True:
        raise HoldReconnect("HOLD_RECONNECT_IMMUTABLE_VERIFIER")
    scope = {"v": _CURSOR_SCHEMA, "owner": claim["owner"],
             "conversation_id": claim["conversation_id"],
             "exchange_id": claim["exchange_id"],
             "request_sha256": claim["request_sha256"],
             "s03_proof_sha256": claim["s03_proof_sha256"],
             "assistant_row_id": claim["assistant_row_id"]}
    expected = dict(scope)
    if cursor is None:
        offset = 0
    else:
        parsed = _decode(cursor, secret)
        offset = parsed.get("after")
        if (type(offset) is not int or offset not in (0, 1) or
                parsed != dict(expected, after=offset)):
            raise HoldReconnect("HOLD_RECONNECT_CURSOR_SCOPE")
    # No callback or external persistence can occur after final gate.
    if permit() is not True or durable_claim() != "READBACK_ONLY":
        raise HoldReconnect("HOLD_RECONNECT_OWNER_REVOKED")
    event_id = hashlib.sha256(_canonical(scope)).hexdigest()
    next_cursor = _sign(dict(expected, after=1), secret)
    return {"readback_only": True, "emit_terminal": offset == 0,
            "event_id": event_id, "next_cursor": next_cursor,
            "conversation_id": claim["conversation_id"],
            "exchange_id": claim["exchange_id"],
            "response_sha256": claim["response_sha256"],
            "s03_proof_sha256": claim["s03_proof_sha256"]}
