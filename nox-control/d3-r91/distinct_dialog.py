"""R91: distinct physical and canonical dialogue provenance; offline only.

All detached digests MUST come from independent authenticated orchestration.
Derived R89 compatibility digests are not authority. No network or writes.
"""
import hashlib
import json
import subprocess
from pathlib import Path
from s03_identity_join import _pin, _SCOPE, _FIELDS, review_joined
from terminal_canonical import terminal_canonical
from receipted_outcome import review_attempt
from outcome_review import _hold

SCOPE = (_SCOPE - {"dialog_id"}) | {"physical_dialog_id", "s03_dialog_id"}
BINDING = _FIELDS | {"transport_sha256"}
NODE = Path(__file__).resolve().parent / "r70_check.cjs"

def need(value, reason):
    if not value:
        raise ValueError("HOLD_R91_" + reason)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def encode(doc):
    return json.dumps(doc, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")

def pair(doc):
    raw = encode(doc)
    return raw, digest(raw)

def prepare(*, owner_pair, terminal_pairs, transport_pairs, expected_scope,
            descriptor_sets):
    need(type(expected_scope) is dict and set(expected_scope) == SCOPE, "SCOPE")
    need(type(descriptor_sets) is tuple and len(descriptor_sets) == 3, "CHAIN")
    need(type(owner_pair) is tuple and len(owner_pair) == 2, "OWNER_PAIR")
    for pairs in (terminal_pairs, transport_pairs):
        need(type(pairs) is tuple and len(pairs) == 2 and
             all(type(p) is tuple and len(p) == 2 for p in pairs), "PAIRS")
    owner = _pin(*owner_pair)
    need(set(owner) == SCOPE | {"schema", "bindings"} and
         owner["schema"] == "nox.owner.s03-transport-join.v2" and
         all(owner[k] == expected_scope[k] for k in SCOPE), "OWNER")
    bindings = owner["bindings"]
    need(type(bindings) is list and len(bindings) == 2, "BINDINGS")
    pins = [owner_pair[1], *(p[1] for p in terminal_pairs),
            *(p[1] for p in transport_pairs), *(p for d in descriptor_sets for p in d[2:])]
    need(len(set(pins)) == len(pins), "PIN_REUSE")
    old_scope = {k: expected_scope[k] for k in _SCOPE - {"dialog_id"}}
    old_scope["dialog_id"] = expected_scope["s03_dialog_id"]
    old_bindings, old_terminals = [], []
    for n, binding, saved_pair, wire_pair in zip((2, 3), bindings, terminal_pairs, transport_pairs):
        need(type(binding) is dict and set(binding) == BINDING and
             type(binding["turn"]) is int and binding["turn"] == n and
             binding["transport_sha256"] == wire_pair[1], "BINDING")
        saved = _pin(*saved_pair)
        need(set(saved) == SCOPE | BINDING | {"schema","state","eof","prompt_sha256","answer_sha256"}
             and saved["schema"] == "nox.transport.terminal-readback.v2"
             and saved["state"] == "TERMINAL_SAVED" and saved["eof"] is True
             and all(saved[k] == expected_scope[k] for k in SCOPE)
             and all(type(saved[k]) is type(binding[k]) and saved[k] == binding[k]
                     for k in BINDING), "SAVED_RECEIPT")
        wire = _pin(*wire_pair)
        need(set(wire) == {"wire","physical","mapping","scope","expectedTurn","terminal","link"}
             and type(wire["expectedTurn"]) is int and wire["expectedTurn"] == n, "WIRE_SCHEMA")
        physical, link = wire["physical"], wire["link"]
        need(physical["dialog_id"] == expected_scope["physical_dialog_id"] and
             physical["owner_admission_receipt_sha256"] == expected_scope["owner_admission_receipt_sha256"] and
             wire["wire"]["served_sha256"] == expected_scope["served_sha256"] and
             wire["wire"]["server_sha256"] == expected_scope["server_sha256"] and
             wire["scope"]["conversation_id"] == expected_scope["conversation_id"], "PHYSICAL_SCOPE")
        expected_link = dict(physical_dialog_id=expected_scope["physical_dialog_id"],
             s03_dialog_id=expected_scope["s03_dialog_id"], s03_session_id=expected_scope["session_id"],
             conversation_id=expected_scope["conversation_id"], s03_event_id=binding["event_id"],
             s03_turn_id=binding["turn_id"], sequence=n)
        for k in ("exchange_id","request_id","attempt_id","user_message_id",
                  "assistant_message_id","writer_sha256","readback_sha256"):
            expected_link[k] = binding[k]
        need(all(link[k] == v for k,v in expected_link.items()), "LINK_SCOPE")
        canonical = terminal_canonical(dialog_id=expected_scope["s03_dialog_id"],
            session_id=expected_scope["session_id"], expected_turn=n, artifacts=descriptor_sets[:n])
        # Fixed, locally bundled pinned R70/R69/R68; no shell or dynamic user path.
        checked = subprocess.run(["node", str(NODE)], input=encode(dict(wire, canonical=canonical)),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, check=True)
        result = json.loads(checked.stdout)
        need(result.get("status") == "CONSISTENT_TERMINAL_LINK_ONLY" and
             result.get("consistent") is True and all(result.get(k) is False for k in
             ("native_accepted","authentication_verified","next_post_allowed")), "R70")
        old_binding = {k:binding[k] for k in _FIELDS}
        old_bindings.append(old_binding)
        old_terminals.append(pair(dict(old_scope, **old_binding,
            schema="nox.transport.terminal-readback.v1", state=saved["state"], eof=saved["eof"],
            prompt_sha256=saved["prompt_sha256"], answer_sha256=saved["answer_sha256"])))
    raw, pin = pair(dict(old_scope, schema="nox.owner.s03-transport-join.v1", bindings=old_bindings))
    return dict(owner_raw=raw, owner_pin=pin, terminal_pairs=tuple(old_terminals),
                expected_scope=old_scope)

def review_distinct(*, outcome, review_inputs=None, failed_attempt=None, provenance=None):
    if outcome != "completed":
        return review_attempt(outcome=outcome, review_inputs=None, failed_attempt=failed_attempt)
    try:
        need(type(provenance) is dict and set(provenance) ==
             {"owner_pair","terminal_pairs","transport_pairs","expected_scope"}, "PROVENANCE")
        need(type(review_inputs) is dict, "REVIEW")
        join = prepare(**provenance, descriptor_sets=review_inputs["descriptor_sets"])
        result = review_joined(outcome=outcome, review_inputs=review_inputs,
                               failed_attempt=failed_attempt, join_inputs=join)
        if result.get("route") == "REVIEW_DATA_ONLY":
            need(result.get("native_accepted") is False and result.get("training_admitted") is False, "AUTHORITY")
            # Retain ORIGINAL independent digests, never the derived v1 pins.
            result = dict(result, dialog_provenance=dict(
                physical_dialog_id=provenance["expected_scope"]["physical_dialog_id"],
                s03_dialog_id=provenance["expected_scope"]["s03_dialog_id"],
                owner_sha256=provenance["owner_pair"][1],
                terminal_sha256=[p[1] for p in provenance["terminal_pairs"]],
                transport_sha256=[p[1] for p in provenance["transport_pairs"]],
                authentication_verified=False))
        return result
    except (TypeError, ValueError, KeyError, RuntimeError, OSError, UnicodeError, subprocess.SubprocessError):
        return _hold("HOLD_R91_DIALOG_PROVENANCE")
