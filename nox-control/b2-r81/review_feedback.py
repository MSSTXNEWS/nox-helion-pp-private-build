"""B2 review feedback for D3 R80; evidence only, never a model instruction."""
from b2_existing_dialog_review import read_pinned
import review_release as r80

def verify_with_feedback(**inputs):
    """Retain exact review reasons after the existing complete R80 check."""
    result = r80.verify_joint_reviews(**inputs)
    summary = result["review_summary"]
    pins = [inputs["submission_a_pin"], inputs["submission_b_pin"]]
    if summary["submission_sha256"] != pins or summary["decisions_bound"] != 4:
        raise ValueError("HOLD_B2_FEEDBACK_BINDING")
    feedback = []
    for side, pin in zip(("a", "b"), pins):
        doc = read_pinned(inputs["submission_" + side + "_raw"], pin)
        for row in sorted(doc["decisions"], key=lambda d: d["turn"]):
            feedback.append(dict(turn=row["turn"], answer_sha256=row["answer_sha256"],
                                 verdict=row["verdict"], reason=row["reason"],
                                 submission_sha256=pin, reviewer_slot=side))
    return dict(result, correction_evidence=dict(
        status="REPORTED_REVIEW_DATA_ONLY", reviewer_identity_verified=False,
        rubric_sha256=summary["rubric_sha256"], readback_sha256=summary["readback_sha256"],
        entries=feedback, model_instruction=False, training_admitted=False))
