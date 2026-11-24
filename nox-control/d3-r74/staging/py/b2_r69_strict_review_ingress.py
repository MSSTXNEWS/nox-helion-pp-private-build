"""B2 strict canonical ingress for the D3 existing-dialog quality review.
Offline only: all expected pins, rows and scope must come from independently
authenticated owner/verifier inputs. No POST, first-turn replay or admission.
"""
from b5_s03_verifier_r54 import (
    canonical_s03_resumed_second_turn_valid,
    canonical_s03_pinned_evidence_valid,
)
from d3_r68_review_binding import prepare_bound_review, verify_bound_reviews


def _strict_evidence(*, dialog_id, session_id, prior_rows, turn2_rows, turn3_rows,
                     prior_witnesses, turn2_witnesses, turn3_witnesses,
                     rubric_raw, rubric_pin):
    # Each tuple: writer raw, independent reader raw, writer pin, reader pin.
    # The prior tuple refers to the existing turn 1, never a new request.
    witnesses = (prior_witnesses, turn2_witnesses, turn3_witnesses)
    if any(type(w) is not tuple or len(w) != 4 for w in witnesses):
        raise ValueError("HOLD_B2_R69_WITNESS_SHAPE")
    if not canonical_s03_resumed_second_turn_valid(
        *turn2_witnesses, dialog_id, turn2_rows,
        expected_session_id=session_id, prior_messages=prior_rows,
        prior_witnesses=prior_witnesses,
    ):
        raise ValueError("HOLD_B2_R69_CANONICAL_TURN2")
    if not canonical_s03_pinned_evidence_valid(
        *turn3_witnesses, dialog_id, turn3_rows,
        expected_session_id=session_id, expected_sequence=3,
        expected_prior_messages=turn2_rows, prior_witnesses=turn2_witnesses,
    ):
        raise ValueError("HOLD_B2_R69_CANONICAL_TURN3")
    # Pass the very same immutable reader bytes/pins checked by B5.
    return dict(turn2_raw=turn2_witnesses[1], turn2_pin=turn2_witnesses[3],
                turn3_raw=turn3_witnesses[1], turn3_pin=turn3_witnesses[3],
                rubric_raw=rubric_raw, rubric_pin=rubric_pin)


def prepare_strict_review(*, pair_raw, pair_pin, **canonical_inputs):
    return prepare_bound_review(pair_raw=pair_raw, pair_pin=pair_pin,
                                **_strict_evidence(**canonical_inputs))


def verify_strict_reviews(*, pair_raw, pair_pin, submission_a_raw,
                          submission_a_pin, submission_b_raw, submission_b_pin,
                          **canonical_inputs):
    return verify_bound_reviews(
        pair_raw=pair_raw, pair_pin=pair_pin, submission_a_raw=submission_a_raw,
        submission_a_pin=submission_a_pin, submission_b_raw=submission_b_raw,
        submission_b_pin=submission_b_pin, **_strict_evidence(**canonical_inputs))
