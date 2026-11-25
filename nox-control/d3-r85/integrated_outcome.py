"""R85 integrated review entrypoint; no runtime or training authority."""
from final_feedback import route_closed_review

def review_attempt(*, outcome, review_inputs=None, failed_attempt=None):
    return route_closed_review(outcome=outcome, review_inputs=review_inputs,
                               failed_attempt=failed_attempt)
