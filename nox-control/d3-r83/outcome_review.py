"""Source-only joint outcome router; no POST, retry, training or native authority.

The authorized caller must supply independent attempt and S03 evidence. A route
label is not authenticated state. The complete path still requires R80's full
retained chain, browser continuity and independently pinned reviewer inputs.
"""
from b5_bound_failed_poststate import classify_bound_failed_turn
from review_feedback import verify_with_feedback

def _hold(reason):
    return dict(route="HOLD", reason=reason, quality_sample=None,
                retry_allowed=False, next_post_allowed=False,
                training_admitted=False, native_accepted=False)

def route_review(*, outcome, review_inputs=None, failed_attempt=None):
    if type(outcome) is not str:
        return _hold("HOLD_D3_OUTCOME_UNPROVEN")
    if outcome in ("failed", "uncertain"):
        if type(failed_attempt) is not dict:
            return _hold("HOLD_D3_FAILED_ATTEMPT_EVIDENCE_MISSING")
        try:
            reason = classify_bound_failed_turn(**failed_attempt)
        except (TypeError, ValueError, KeyError, RuntimeError):
            reason = "HOLD_D3_FAILED_ATTEMPT_EVIDENCE_INVALID"
        # A stale review envelope must never override a failed attempt.
        return _hold(reason)
    if outcome != "completed":
        return _hold("HOLD_D3_OUTCOME_UNPROVEN")
    if failed_attempt is not None:
        return _hold("HOLD_D3_CONTRADICTORY_ATTEMPT")
    if type(review_inputs) is not dict:
        return _hold("HOLD_D3_COMPLETE_EVIDENCE_MISSING")
    try:
        sample = verify_with_feedback(**review_inputs)
    except (TypeError, ValueError, KeyError, RuntimeError, OSError) as exc:
        reason = str(exc)
        return _hold(reason if reason.startswith("HOLD_") else
                     "HOLD_D3_COMPLETE_EVIDENCE_INVALID")
    return dict(route="REVIEW_DATA_ONLY", quality_sample=sample,
                retry_allowed=False, next_post_allowed=False,
                training_admitted=False, native_accepted=False)
