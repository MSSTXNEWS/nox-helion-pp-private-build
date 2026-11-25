"""Explicit retained S03 / transport identity join. Offline evidence only.
All pins must arrive via independent authenticated owner channels. This module
cannot authenticate those channels, authorize POST, or accept native work.
"""
import hashlib
import re
from b5_r55_pinned import strict_owner_json_bytes
from b5_retained_ingress import load_retained_chain

_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_HASH = re.compile(r"[0-9a-f]{64}")
_FIELDS = {"turn", "exchange_id", "request_id", "attempt_id",
           "user_message_id", "assistant_message_id", "event_id", "turn_id",
           "writer_sha256", "readback_sha256"}
_SCOPE = {"conversation_id", "dialog_id", "session_id", "served_sha256",
          "server_sha256", "owner_admission_receipt_sha256"}

def _require(condition, reason):
    if not condition:
        raise ValueError("HOLD_R89_" + reason)

def _pin(raw, pin):
    _require(type(raw) is bytes and 0 < len(raw) <= 16384
             and type(pin) is str and _HASH.fullmatch(pin)
             and hashlib.sha256(raw).hexdigest() == pin, "PIN")
    doc = strict_owner_json_bytes(raw)
    _require(type(doc) is dict, "SCHEMA")
    return doc

def verify_join(*, owner_raw, owner_pin, terminal_pairs, descriptor_sets,
                expected_scope):
    """Compare independently pinned transport terminals to real B5 chain.
    expected_scope originates in authorized orchestration, not owner_raw.
    No native/quality authority follows from a matched join.
    """
    _require(type(expected_scope) is dict and set(expected_scope) == _SCOPE, "SCOPE")
    for key, val in expected_scope.items():
        pat = _HASH if key.endswith("sha256") else _ID
        _require(type(val) is str and pat.fullmatch(val), "SCOPE")
    owner = _pin(owner_raw, owner_pin)
    _require(set(owner) == _SCOPE | {"schema", "bindings"}
             and owner["schema"] == "nox.owner.s03-transport-join.v1"
             and all(owner[k] == expected_scope[k] for k in _SCOPE), "OWNER_SCOPE")
    bindings = owner["bindings"]
    _require(type(bindings) is list and len(bindings) == 2
             and type(terminal_pairs) is tuple and len(terminal_pairs) == 2
             and type(descriptor_sets) is tuple and len(descriptor_sets) == 3, "TURN_COUNT")
    chain = load_retained_chain(dialog_id=expected_scope["dialog_id"],
                                session_id=expected_scope["session_id"],
                                artifacts=descriptor_sets)
    seen = {k: set() for k in ("request_id", "exchange_id", "attempt_id")}
    seen_pins = {owner_pin, *(p for pair in descriptor_sets for p in pair[2:])}
    for n, binding, terminal in zip((2, 3), bindings, terminal_pairs):
        _require(type(binding) is dict and set(binding) == _FIELDS
                 and type(binding["turn"]) is int and binding["turn"] == n, "BINDING")
        for k in _FIELDS - {"turn"}:
            pat = _HASH if k.endswith("sha256") else _ID
            _require(type(binding[k]) is str and pat.fullmatch(binding[k]), "BINDING")
        for k in seen:
            _require(binding[k] not in seen[k], "IDENTITY_REUSE")
            seen[k].add(binding[k])
        _require(type(terminal) is tuple and len(terminal) == 2, "TERMINAL")
        raw, pin = terminal
        doc = _pin(raw, pin)
        _require(pin not in seen_pins, "PIN_REUSE")
        seen_pins.add(pin)
        _require(set(doc) == _SCOPE | _FIELDS | {"schema", "state", "eof",
                    "prompt_sha256", "answer_sha256"}
                 and doc["schema"] == "nox.transport.terminal-readback.v1"
                 and doc["state"] == "TERMINAL_SAVED" and doc["eof"] is True
                 and all(doc[k] == expected_scope[k] for k in _SCOPE)
                 and all(type(doc[k]) is type(binding[k]) and doc[k] == binding[k]
                         for k in _FIELDS), "TERMINAL_SCOPE")
        rows, witnesses = chain[n-1]
        writer = strict_owner_json_bytes(witnesses[0])
        user, assistant = rows[-2:]
        actual = dict(user_message_id=user["message_id"],
                      assistant_message_id=assistant["message_id"],
                      event_id=writer["event_id"], turn_id=writer["turn_id"],
                      writer_sha256=witnesses[2], readback_sha256=witnesses[3])
        _require(all(binding[k] == v for k, v in actual.items()), "CANONICAL_IDENTITY")
        _require(doc["prompt_sha256"] == hashlib.sha256(user["content"].encode()).hexdigest()
                 and doc["answer_sha256"] == hashlib.sha256(assistant["content"].encode()).hexdigest(),
                 "CANONICAL_TEXT")
    return {"status": "SCOPE_MATCHED_OFFLINE", "native_accepted": False,
            "authentication_verified": False, "training_admitted": False,
            "next_post_allowed": False, "retry_allowed": False}

def review_joined(*, outcome, review_inputs=None, failed_attempt=None, join_inputs=None):
    from receipted_outcome import review_attempt
    from outcome_review import _hold
    if outcome != "completed":
        return review_attempt(outcome=outcome, review_inputs=None, failed_attempt=failed_attempt)
    try:
        _require(type(review_inputs) is dict and type(join_inputs) is dict, "MISSING")
        _require(set(join_inputs) == {"owner_raw", "owner_pin", "terminal_pairs", "expected_scope"},
                 "JOIN_SCHEMA")
        scope = join_inputs["expected_scope"]
        _require(all(review_inputs[k] == scope[k] for k in ("dialog_id", "session_id")), "REVIEW_SCOPE")
        verify_join(**join_inputs, descriptor_sets=review_inputs["descriptor_sets"])
    except (TypeError, ValueError, KeyError, RuntimeError, OSError, UnicodeError) as exc:
        return _hold(str(exc) if str(exc).startswith("HOLD_") else "HOLD_R89_INVALID")
    return review_attempt(outcome=outcome, review_inputs=review_inputs, failed_attempt=failed_attempt)
