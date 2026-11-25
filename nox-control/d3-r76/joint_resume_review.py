"""Offline composition of existing B0/B5 resume and R72 calibrated review.
No model call, transport, native authority or production acceptance.
All observations and pins must originate independently at an authorized caller.
"""
from b5_browser_prefix_gate import bind_observed_browser_prefix
from d3_r70_owner_fd_review_ingress import _canonical
from d3_r72_calibrated_descriptor_gate import (
    prepare_calibrated_review, verify_calibrated_reviews,
)

def _distinct(rows, *others):
    return type(rows) is list and all(type(peer) is list and rows is not peer
        and not any(r is p for r in rows for p in peer) for peer in others)

def _check_resume(observations, inputs):
    if type(observations) is not tuple or len(observations) != 2:
        raise ValueError("HOLD_R76_OBSERVATION_COUNT")
    canonical = _canonical(**{k: inputs[k] for k in (
        "dialog_id", "session_id", "descriptor_sets", "rubric_raw", "rubric_pin")})
    expected = {"preflight", "expected_owner_sha", "owner_rows", "browser_before",
                "browser_after", "calls_before", "calls_after", "admitted_before",
                "admitted_after", "prompt", "stream_answer", "terminal_saved", "dom_matches"}
    previous = None
    for obs, before, after in zip(observations, ("prior", "turn2"), ("turn2", "turn3")):
        if type(obs) is not dict or set(obs) != expected:
            raise ValueError("HOLD_R76_OBSERVATION_SHAPE")
        old, new = canonical[before+"_rows"], canonical[after+"_rows"]
        if not _distinct(obs["browser_before"], obs["owner_rows"], old) or not _distinct(
                obs["browser_after"], obs["owner_rows"], obs["browser_before"], new):
            raise ValueError("HOLD_R76_OBSERVATION_ALIAS")
        if previous is not None and (obs["calls_before"] != previous["calls_after"]
                or obs["admitted_before"] != previous["admitted_after"]
                or obs["browser_before"] != previous["browser_after"]):
            raise ValueError("HOLD_R76_RESUME_CONTINUITY")
        bridge = bind_observed_browser_prefix(
            observed_browser_rows=obs["browser_before"], observed_browser_calls=obs["calls_before"],
            preflight=obs["preflight"], expected_owner_sha=obs["expected_owner_sha"],
            dialog_id=inputs["dialog_id"], session_id=inputs["session_id"],
            owner_rows=obs["owner_rows"], canonical_rows=old,
            prior_witnesses=canonical[before+"_witnesses"], browser_calls=obs["calls_before"],
            admitted_calls=obs["admitted_before"])
        result = bridge.finish(browser_rows=obs["browser_after"], canonical_rows=new,
            witnesses=canonical[after+"_witnesses"], browser_calls=obs["calls_after"],
            admitted_calls=obs["admitted_after"], prompt=obs["prompt"],
            stream_answer=obs["stream_answer"], terminal_saved=obs["terminal_saved"],
            dom_matches=obs["dom_matches"])
        if result != "RESUME_EVIDENCE_MATCHED":
            raise ValueError(result)
        previous = obs

def prepare_joint_review(*, observations, **inputs):
    _check_resume(observations, inputs)
    result = prepare_calibrated_review(**inputs)
    return dict(result, resume_evidence="TURNS_2_3_MATCHED_OFFLINE")

def verify_joint_reviews(*, observations, submission_a_raw, submission_a_pin,
                         submission_b_raw, submission_b_pin, **inputs):
    _check_resume(observations, inputs)
    result = verify_calibrated_reviews(submission_a_raw=submission_a_raw,
        submission_a_pin=submission_a_pin, submission_b_raw=submission_b_raw,
        submission_b_pin=submission_b_pin, **inputs)
    return dict(result, resume_evidence="TURNS_2_3_MATCHED_OFFLINE")
