"""Failed/interrupted diagnostic only. No successful turn or mutation authority."""
from typed_failed_poststate import classify_typed_failed_turn
def review_failed(*, evidence):
    try:
        state=classify_typed_failed_turn(**evidence)
    except (TypeError, ValueError, KeyError, RuntimeError, UnicodeError, RecursionError):
        state="HOLD_S03_FAILURE_INVALID"
    if type(state) is not str or not state.startswith("HOLD_"):
        state="HOLD_S03_FAILURE_INVALID"
    return dict(state=state, native_accepted=False, ack_allowed=False,
                next_post_allowed=False, training_admitted=False,
                retry_allowed=False, successful_turn=False)
