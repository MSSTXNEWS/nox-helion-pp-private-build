"""Final quality sample fence for R83, not native admission or model execution."""
from outcome_review import route_review, _hold
from quality_closure import _signatures


def route_closed_review(*, outcome, review_inputs=None, failed_attempt=None):
    args = dict(outcome=outcome, review_inputs=review_inputs, failed_attempt=failed_attempt)
    if type(outcome) is not str or outcome != "completed" or failed_attempt is not None or type(review_inputs) is not dict:
        return route_review(**args)
    try:
        descriptors = review_inputs["descriptor_sets"]
        before = _signatures(descriptors)
    except (KeyError, TypeError, ValueError, OSError):
        return _hold("HOLD_B2_FINAL_FEEDBACK_FD_UNPROVEN")
    result = route_review(**args)
    if result["route"] != "REVIEW_DATA_ONLY":
        return result
    try:
        if review_inputs["descriptor_sets"] != descriptors or _signatures(descriptors) != before:
            return _hold("HOLD_B2_FINAL_FEEDBACK_FD_DRIFT")
    except (KeyError, TypeError, ValueError, OSError):
        return _hold("HOLD_B2_FINAL_FEEDBACK_FD_DRIFT")
    return result
