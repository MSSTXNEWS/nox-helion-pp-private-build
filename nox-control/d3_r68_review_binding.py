"""D3: bind the independently pinned B4 browser pair to B2's S03 review.
Offline only. Caller must authenticate the provenance of every expected pin,
including the B4 pair produced by bindExistingTurnPair. No native admission,
POST, reviewer authentication, or first-turn replay is performed here.
"""
from b2_existing_dialog_review import (
    prepare_existing_review, read_pinned, verify_existing_reviews,
)

def _require(condition, reason):
    if not condition:
        raise ValueError("HOLD_D3_R68_" + reason)

def prepare_bound_review(*, pair_raw, pair_pin, **evidence):
    """Preserve the B2 packet schema; bind its answers to the B4 pair first."""
    pair = read_pinned(pair_raw, pair_pin)
    packet = prepare_existing_review(**evidence)
    rubric = read_pinned(evidence["rubric_raw"], evidence["rubric_pin"])
    _require(pair.get("status") == "B4_PAIR_INPUTS_MATCHED"
             and pair.get("dialog_id") == rubric["dialog_id"], "PAIR_SCOPE")
    _require(all(pair.get(key) is False for key in (
        "browser_authenticated", "native_verified", "canonical_s03_verified"))
        and "model_tokens_per_second" in pair
        and pair["model_tokens_per_second"] is None, "PAIR_AUTHORITY")
    turns = pair.get("turns")
    _require(type(turns) is list and len(turns) == 2, "PAIR_COVERAGE")
    exchanges = set()
    for seq, turn, item in zip((2, 3), turns, packet["evidence"]):
        _require(type(turn) is dict and type(turn.get("turn")) is int
                 and turn["turn"] == item["turn"] == seq, "PAIR_SEQUENCE")
        exchange = turn.get("exchange_id")
        _require(type(exchange) is str and 6 <= len(exchange) <= 160
                 and exchange not in exchanges, "PAIR_EXCHANGE")
        exchanges.add(exchange)
        _require(turn.get("visible_text_sha256") == item["answer_sha256"],
                 "BROWSER_S03_ANSWER_MISMATCH")
    return {"pair_sha256": pair_pin, "review_packet": packet,
            "native_acceptance": packet["native_acceptance"]}

def verify_bound_reviews(*, pair_raw, pair_pin, submission_a_raw,
                         submission_a_pin, submission_b_raw,
                         submission_b_pin, **evidence):
    """Rebind the same pair/readbacks before verifying original review submissions."""
    bound = prepare_bound_review(pair_raw=pair_raw, pair_pin=pair_pin, **evidence)
    summary = verify_existing_reviews(
        submission_a_raw=submission_a_raw, submission_a_pin=submission_a_pin,
        submission_b_raw=submission_b_raw, submission_b_pin=submission_b_pin,
        **evidence)
    return {"pair_sha256": bound["pair_sha256"], "review_summary": summary,
            "native_acceptance": bound["native_acceptance"]}
