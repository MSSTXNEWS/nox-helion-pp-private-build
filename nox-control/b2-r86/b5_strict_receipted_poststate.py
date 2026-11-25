"""Strict R68 boundary: admission identity must only come from the pinned receipt.
Read-only diagnostics; never authorizes a retry or accepts a turn.
"""
from b5_receipted_failed_poststate import classify_receipted_failed_turn

_EVIDENCE_KEYS = frozenset({
    "dialog_id", "session_id", "attempt_id", "prompt", "prior_chain",
    "snapshot_raw", "snapshot_sha256",
})

def classify_strict_receipted_failed_turn(*, admission_raw=None,
                                          admission_sha256=None, **evidence):
    # R68 forwards arbitrary kwargs into R67 before checking the receipt.
    # Reject caller-controlled identity and all unexpected/missing keys.
    if evidence.keys() != _EVIDENCE_KEYS:
        return "HOLD_S03_FAILURE_EVIDENCE_SCHEMA"
    return classify_receipted_failed_turn(
        admission_raw=admission_raw, admission_sha256=admission_sha256, **evidence)
