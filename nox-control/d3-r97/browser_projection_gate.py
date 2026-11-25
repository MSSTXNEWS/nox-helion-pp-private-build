"""R97: independently pinned rendered-text quality gate for R92.
Source only; the caller must authenticate the observer and detached pins.
No browser recovery, network, ACK, POST, training or native authority.
"""
import copy
import re
from s03_identity_join import _pin
from quality_physical_pair import review_physical_pair
from outcome_review import _hold

HASH = re.compile(r"[0-9a-f]{64}")
ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")
SCOPE = {"conversation_id", "physical_dialog_id", "s03_dialog_id", "session_id",
         "served_sha256", "server_sha256", "owner_admission_receipt_sha256"}
BIND = {"turn", "exchange_id", "request_id", "attempt_id", "event_id", "turn_id",
        "user_message_id", "assistant_message_id"}
EXTRA = {"schema", "observation_id", "browser_sha256", "terminal_receipt_sha256",
         "visible_text_sha256", "visible_row_count", "state", "ack_state"}

def need(ok):
    if not ok:
        raise ValueError("HOLD_B2_BROWSER_TEXT_UNVERIFIED")

def review_browser_projection(*, outcome, review_inputs=None, failed_attempt=None,
                              provenance=None, physical_receipt_pair=None,
                              browser_pairs=None, expected_browser_sha256=None):
    if outcome != "completed":
        return review_physical_pair(outcome=outcome, failed_attempt=failed_attempt)
    try:
        need(failed_attempt is None)
        need(type(provenance) is dict and type(review_inputs) is dict)
        p = copy.deepcopy(provenance)
        inputs = dict(review_inputs)
        need(type(expected_browser_sha256) is str and HASH.fullmatch(expected_browser_sha256))
        scope = p["expected_scope"]
        need(type(scope) is dict and set(scope) == SCOPE)
        terminals = p["terminal_pairs"]
        need(type(terminals) is tuple and len(terminals) == 2)
        need(type(browser_pairs) is tuple and len(browser_pairs) == 2)
        need(type(physical_receipt_pair) is tuple and len(physical_receipt_pair) == 2)
        seen = {p["owner_pair"][1], physical_receipt_pair[1],
                *(x[1] for x in terminals), *(x[1] for x in p["transport_pairs"]),
                *(v for d in inputs["descriptor_sets"] for v in d[2:])}
        observations = set()
        proofs = []
        for n, terminal, projection in zip((2, 3), terminals, browser_pairs):
            need(type(projection) is tuple and len(projection) == 2)
            doc = _pin(*projection)
            saved = _pin(*terminal)
            need(projection[1] not in seen)
            seen.add(projection[1])
            need(set(doc) == SCOPE | BIND | EXTRA)
            need(doc["schema"] == "nox.browser.projection-readback.v1")
            need(type(doc["turn"]) is int and doc["turn"] == n)
            need(all(type(doc[k]) is type(scope[k]) and doc[k] == scope[k] for k in SCOPE))
            need(all(type(doc[k]) is type(saved[k]) and doc[k] == saved[k] for k in BIND))
            need(saved["state"] == "TERMINAL_SAVED" and saved["eof"] is True)
            need(doc["terminal_receipt_sha256"] == terminal[1])
            need(doc["browser_sha256"] == expected_browser_sha256)
            need(doc["state"] == "TERMINAL_VISIBLE" and doc["ack_state"] == "NOT_SENT")
            need(type(doc["visible_row_count"]) is int and doc["visible_row_count"] == 1)
            oid = doc["observation_id"]
            need(type(oid) is str and ID.fullmatch(oid) and oid not in observations)
            observations.add(oid)
            need(type(doc["visible_text_sha256"]) is str and HASH.fullmatch(doc["visible_text_sha256"]))
            need(doc["visible_text_sha256"] == saved["answer_sha256"])
            proofs.append(projection[1])
        # R92 checks the same pinned terminal answer digests against the
        # independently loaded S03 rows, along with all physical identities.
        result = review_physical_pair(outcome=outcome, review_inputs=inputs,
                    provenance=p, physical_receipt_pair=physical_receipt_pair)
        if result.get("route") != "REVIEW_DATA_ONLY":
            return result
        need(result.get("native_accepted") is False and
             result.get("training_admitted") is False and
             result.get("next_post_allowed") is False and
             result.get("retry_allowed") is False)
        evidence = dict(result["dialog_provenance"], browser_projection_sha256=proofs,
                        browser_sha256=expected_browser_sha256,
                        browser_projection_status="MATCHED_OFFLINE",
                        authentication_verified=False)
        return dict(result, dialog_provenance=evidence, ack_allowed=False)
    except (TypeError, ValueError, KeyError, IndexError, AttributeError, RuntimeError, OSError):
        return dict(_hold("HOLD_B2_BROWSER_TEXT_UNVERIFIED"), ack_allowed=False)
