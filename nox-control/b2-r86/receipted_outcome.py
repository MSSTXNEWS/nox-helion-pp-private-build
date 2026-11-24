"""Route failed attempts through B5 R69; completed review stays on R85."""
from integrated_outcome import review_attempt as review_r85
from b5_strict_receipted_poststate import classify_strict_receipted_failed_turn
from outcome_review import _hold


def review_attempt(*, outcome, review_inputs=None, failed_attempt=None):
    if type(outcome) is str and outcome in ("failed", "uncertain"):
        if type(failed_attempt) is not dict:
            return _hold("HOLD_D3_FAILED_ATTEMPT_EVIDENCE_MISSING")
        try:
            reason = classify_strict_receipted_failed_turn(**failed_attempt)
        except (TypeError, ValueError, KeyError, RuntimeError, OSError):
            reason = "HOLD_D3_FAILED_ATTEMPT_EVIDENCE_INVALID"
        return _hold(reason)
    return review_r85(outcome=outcome, review_inputs=review_inputs,
                      failed_attempt=failed_attempt)
