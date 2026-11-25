"""Bind an independently pinned preanswer plan to the existing descriptor review.
This verifies content, not the identity of the owner or the time of approval.
Never opens a model request or grants native admission.
"""
import hashlib
import hmac
from b5_s03_verifier_r54 import strict_owner_json_bytes
from b2_r71_calibrated_rubric import build_preanswer_rubric
from d3_r70_owner_fd_review_ingress import (
    prepare_descriptor_review, verify_descriptor_reviews,
)


def _check(*, plan_raw, plan_pin, rubric_raw, rubric_pin, dialog_id, session_id):
    if (type(plan_raw) is not bytes or len(plan_raw) > 65536
            or type(plan_pin) is not str or len(plan_pin) != 64
            or not hmac.compare_digest(hashlib.sha256(plan_raw).hexdigest(), plan_pin)):
        raise ValueError("HOLD_D3_R72_PLAN_PIN")
    plan = strict_owner_json_bytes(plan_raw)
    if (type(plan) is not dict or set(plan) != {"dialog_id", "session_id", "planned_turns"}
            or plan["dialog_id"] != dialog_id or plan["session_id"] != session_id):
        raise ValueError("HOLD_D3_R72_PLAN_SCOPE")
    expected, expected_pin = build_preanswer_rubric(
        dialog_id=dialog_id, session_id=session_id, planned_turns=plan["planned_turns"])
    if (type(rubric_raw) is not bytes or type(rubric_pin) is not str
            or rubric_raw != expected or rubric_pin != expected_pin):
        raise ValueError("HOLD_D3_R72_RUBRIC_MISMATCH")


def _gate(plan_raw, plan_pin, inputs):
    _check(plan_raw=plan_raw, plan_pin=plan_pin,
           **{k: inputs[k] for k in ("rubric_raw", "rubric_pin", "dialog_id", "session_id")})


def prepare_calibrated_review(*, plan_raw, plan_pin, **inputs):
    _gate(plan_raw, plan_pin, inputs)
    return prepare_descriptor_review(**inputs)


def verify_calibrated_reviews(*, plan_raw, plan_pin, **inputs):
    _gate(plan_raw, plan_pin, inputs)
    return verify_descriptor_reviews(**inputs)
