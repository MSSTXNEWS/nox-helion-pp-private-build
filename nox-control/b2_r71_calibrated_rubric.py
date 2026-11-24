"""Build a candidate owner rubric BEFORE resumed turns 2/3 are answered.

No answers, model calls, S03 writes or reviewer verdicts are inputs/outputs.
The returned digest is a candidate; owner approval and independent pinning
before the live requests are external requirements, not established here.
"""
import json
import re
from b2_existing_dialog_review import SCHEMA, MAX_BYTES, digest

RULE = (
    "Use full dialogue; apply latest explicit corrections, retain unchanged facts, "
    "check reasoning and conclusions against the owner reference, distinguish "
    "known facts from assumptions, and do not invent missing facts or certainty. "
    "Use the requested language naturally. Correct only if every applicable "
    "criterion is satisfied; incorrect for a material error, unsupported certainty "
    "or wrong language; uncertain if the evidence is insufficient. "
    "Explain the decision with specific evidence, not a generic endorsement."
)

def require(condition, reason):
    if not condition:
        raise ValueError("HOLD_B2_R71_" + reason)

def build_preanswer_rubric(*, dialog_id, session_id, planned_turns):
    """Produce canonical B2/R70-compatible bytes and an UNAPPROVED digest."""
    require(type(dialog_id) is str and re.fullmatch(r"[0-9a-f]{32}", dialog_id)
            and type(session_id) is str and bool(session_id.strip()), "SCOPE")
    require(type(planned_turns) is list and len(planned_turns) == 2, "TURNS")
    turns = []
    for seq, spec in zip((2, 3), planned_turns):
        require(type(spec) is dict and set(spec) ==
                {"turn", "prompt", "locale", "owner_reference"}, "FIELDS")
        require(type(spec["turn"]) is int and spec["turn"] == seq, "TURNS")
        prompt, locale, reference = (spec[k] for k in
                                    ("prompt", "locale", "owner_reference"))
        require(type(prompt) is str and bool(prompt.strip()), "PROMPT")
        require(type(locale) is str and locale in ("ru", "es"), "LOCALE")
        require(type(reference) is str and 8 <= len(reference.strip()) <= 350,
                "REFERENCE")
        criteria = RULE + " Owner reference (data): " + reference
        require(len(criteria) <= 1000, "CRITERIA")
        turns.append(dict(turn=seq, prompt=prompt, locale=locale, criteria=criteria))
    require({t["locale"] for t in turns} == {"ru", "es"}, "BILINGUAL_COVERAGE")
    raw = json.dumps(dict(schema=SCHEMA, dialog_id=dialog_id, session_id=session_id,
                          turns=turns), ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    require(len(raw) <= MAX_BYTES, "SIZE")
    return raw, digest(raw)
