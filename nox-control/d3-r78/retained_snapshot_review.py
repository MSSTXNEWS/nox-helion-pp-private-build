"""Offline composition of existing B0/B5 resume and R72 calibrated review.
No model call, transport, native authority or production acceptance.
All observations and pins must originate independently at an authorized caller.
"""
from b5_browser_prefix_gate import bind_observed_browser_prefix
from b5_retained_ingress import load_retained_chain
from d3_r72_calibrated_descriptor_gate import _gate
from b2_r69_strict_review_ingress import prepare_strict_review, verify_strict_reviews

def _snapshot(inputs):
    scope = {k: inputs[k] for k in ("dialog_id", "session_id")}
    chain = load_retained_chain(artifacts=inputs["descriptor_sets"], **scope)
    if len(chain) != 3:
        raise ValueError("HOLD_R78_TERMINAL_CHAIN")
    result = dict(scope, rubric_raw=inputs["rubric_raw"], rubric_pin=inputs["rubric_pin"])
    for name, (rows, witnesses) in zip(("prior", "turn2", "turn3"), chain):
        result[name+"_rows"] = rows
        result[name+"_witnesses"] = witnesses
    return result

def _review_inputs(inputs):
    _gate(inputs["plan_raw"], inputs["plan_pin"], inputs)
    return _snapshot(inputs)

def _distinct(rows, *others):
    return type(rows) is list and all(type(peer) is list and rows is not peer
        and not any(r is p for r in rows for p in peer) for peer in others)

def _check_resume(observations, inputs, canonical):
    if type(observations) is not tuple or len(observations) != 2:
        raise ValueError("HOLD_R76_OBSERVATION_COUNT")
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
    canonical = _review_inputs(inputs)
    _check_resume(observations, inputs, canonical)
    result = prepare_strict_review(pair_raw=inputs["pair_raw"], pair_pin=inputs["pair_pin"], **canonical)
    return dict(result, resume_evidence="TURNS_2_3_MATCHED_OFFLINE")

def verify_joint_reviews(*, observations, submission_a_raw, submission_a_pin,
                         submission_b_raw, submission_b_pin, **inputs):
    canonical = _review_inputs(inputs)
    _check_resume(observations, inputs, canonical)
    result = verify_strict_reviews(submission_a_raw=submission_a_raw,
        submission_a_pin=submission_a_pin, submission_b_raw=submission_b_raw,
        submission_b_pin=submission_b_pin, pair_raw=inputs["pair_raw"],
        pair_pin=inputs["pair_pin"], **canonical)
    return dict(result, resume_evidence="TURNS_2_3_MATCHED_OFFLINE")
