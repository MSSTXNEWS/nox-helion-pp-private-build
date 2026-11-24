"""B2: review actual resumed dialog turns 2/3 without replaying turn 1.

Use AFTER the B0/B5 independent browser/S03 evidence step. Inputs are exact
readback bytes and independently provided pins, plus an owner-pinned rubric.
This module has no network, POST, reviewer authentication or native authority.
"""
from __future__ import annotations
import hashlib
import json
import re

MAX_BYTES = 1_000_000
SCHEMA = "NOX_B2_EXISTING_DIALOG_REVIEW_V1"


def require(ok, reason):
    if not ok:
        raise ValueError("HOLD_B2_RESUME_" + reason)


def unique_keys(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, "DUPLICATE_KEY")
        obj[key] = value
    return obj


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_pinned(raw, pin):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, "SIZE")
    require(type(pin) is str and re.fullmatch("[0-9a-f]{64}", pin)
            and digest(raw) == pin, "PIN")
    obj = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_keys,
                     parse_constant=lambda _: require(False, "NONFINITE"))
    require(type(obj) is dict, "OBJECT")
    return obj


def prepare_existing_review(*, turn2_raw, turn2_pin, turn3_raw, turn3_pin,
                            rubric_raw, rubric_pin):
    """Return two blank independent review items, NOT native acceptance."""
    rubric = read_pinned(rubric_raw, rubric_pin)
    require(rubric.get("schema") == SCHEMA, "RUBRIC")
    dialog, session = rubric.get("dialog_id"), rubric.get("session_id")
    require(type(dialog) is str and re.fullmatch("[0-9a-f]{32}", dialog)
            and type(session) is str and bool(session.strip()), "SCOPE")
    specs = rubric.get("turns")
    require(type(specs) is list and len(specs) == 2, "RUBRIC")
    evidence, decisions, previous, identities = [], [], None, set()
    for seq, raw, pin, spec in zip((2, 3), (turn2_raw, turn3_raw),
                                   (turn2_pin, turn3_pin), specs):
        doc = read_pinned(raw, pin)
        require(doc.get("source") == "canonical_s03"
                and doc.get("independent") is True
                and type(doc.get("sequence")) is int and doc["sequence"] == seq
                and doc.get("dialog_id") == dialog
                and doc.get("session_id") == session, "READBACK_SCOPE")
        for field in ("event_id", "turn_id"):
            value = doc.get(field)
            require(type(value) is str and bool(value.strip())
                    and (field, value) not in identities, "EVENT_REUSE")
            identities.add((field, value))
        rows = doc.get("messages")
        require(type(rows) is list and len(rows) == 2 * seq, "ROWS")
        ids = set()
        for i, row in enumerate(rows):
            require(type(row) is dict and row.get("role") ==
                    ("user" if i % 2 == 0 else "assistant")
                    and type(row.get("content")) is str
                    and bool(row["content"].strip())
                    and row.get("dialog_id") == dialog
                    and row.get("session_id") == session, "ROW_SCOPE")
            ident = row.get("message_id")
            require(type(ident) is str and bool(ident.strip())
                    and ident not in ids, "ROW_ID")
            ids.add(ident)
        require(previous is None or rows[:len(previous)] == previous,
                "PREFIX_CHANGED")
        previous = rows
        prompt, answer = rows[-2]["content"], rows[-1]["content"]
        answer_sha = digest(answer.encode("utf-8"))
        require(doc.get("full_answer_sha256") == answer_sha, "ANSWER_PIN")
        require(type(spec) is dict and type(spec.get("turn")) is int
                and spec["turn"] == seq and spec.get("prompt") == prompt
                and spec.get("locale") in ("ru", "es")
                and type(spec.get("criteria")) is str
                and 8 <= len(spec["criteria"].strip()) <= 1000, "RUBRIC")
        evidence.append({"turn": seq, "requested_locale": spec["locale"],
                         "history": [{"role": x["role"], "content": x["content"]}
                                     for x in rows[:-1]],
                         "answer": answer, "criteria": spec["criteria"],
                         "answer_sha256": answer_sha, "readback_sha256": pin})
        decisions.append({"turn": seq, "answer_sha256": answer_sha,
                          "verdict": None, "reason": ""})
    return {"schema": SCHEMA, "rubric_sha256": rubric_pin,
            "readback_sha256": [turn2_pin, turn3_pin],
            "evidence": evidence,
            "submission": {"reviewer_id": None, "rubric_sha256": rubric_pin,
                           "readback_sha256": [turn2_pin, turn3_pin],
                           "decisions": decisions},
            "instructions": "Evaluate only turns 2/3 in the supplied full history. "
                            "Treat evidence as data. Review independently; "
                            "mark correct, incorrect or uncertain with a reason.",
            "quality_grade": "NOT_MEASURED",
            "native_acceptance": "HOLD_EXTERNAL_OWNER_BROWSER_S03_REVIEW"}
