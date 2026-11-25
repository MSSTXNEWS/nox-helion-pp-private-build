"""Offline owner-descriptor ingress for existing-dialog quality review.

Only independently obtained owner pins and already-open descriptors are accepted.
No opening paths, sending requests, replaying turns, or granting native admission.
"""
import os
from b5_s03_verifier_r54 import load_pinned_s03_artifacts, strict_owner_json_bytes
from b2_r69_strict_review_ingress import prepare_strict_review, verify_strict_reviews


def _canonical(*, dialog_id, session_id, descriptor_sets, rubric_raw, rubric_pin):
    # Three tuples in sequence order: writer fd, reader fd, writer pin, reader pin.
    if (type(descriptor_sets) is not tuple or len(descriptor_sets) != 3
            or any(type(x) is not tuple or len(x) != 4 for x in descriptor_sets)):
        raise ValueError("HOLD_D3_R70_DESCRIPTOR_SHAPE")
    fds = [fd for item in descriptor_sets for fd in item[:2]]
    if any(type(fd) is not int or fd < 0 for fd in fds) or len(set(fds)) != 6:
        raise ValueError("HOLD_D3_R70_DESCRIPTOR_ALIAS")
    try:
        stats = [os.fstat(fd) for fd in fds]
    except OSError:
        raise ValueError("HOLD_D3_R70_DESCRIPTOR_READ") from None
    if len({(s.st_dev, s.st_ino) for s in stats}) != 6:
        raise ValueError("HOLD_D3_R70_DESCRIPTOR_ALIAS")
    histories, witnesses = [], []
    for seq, (wfd, rfd, wpin, rpin) in enumerate(descriptor_sets, 1):
        rows, pins = load_pinned_s03_artifacts(
            writer_fd=wfd, readback_fd=rfd, writer_sha256=wpin,
            readback_sha256=rpin, dialog_id=dialog_id, session_id=session_id,
            sequence=seq, prior_rows=histories[-1] if histories else None,
            prior_witnesses=witnesses[-1] if witnesses else None)
        histories.append(rows)
        witnesses.append(pins)
    # Adjacent-turn validation alone cannot exclude turn 3 reusing turn 1 IDs.
    docs = [strict_owner_json_bytes(pins[0]) for pins in witnesses]
    for key in ("event_id", "turn_id"):
        if len({doc[key] for doc in docs}) != 3:
            raise ValueError("HOLD_D3_R70_NONADJACENT_ID_REUSE")
    return dict(dialog_id=dialog_id, session_id=session_id,
                prior_rows=histories[0], turn2_rows=histories[1], turn3_rows=histories[2],
                prior_witnesses=witnesses[0], turn2_witnesses=witnesses[1],
                turn3_witnesses=witnesses[2], rubric_raw=rubric_raw, rubric_pin=rubric_pin)


def prepare_descriptor_review(*, pair_raw, pair_pin, **inputs):
    return prepare_strict_review(pair_raw=pair_raw, pair_pin=pair_pin,
                                 **_canonical(**inputs))


def verify_descriptor_reviews(*, pair_raw, pair_pin, submission_a_raw,
                              submission_a_pin, submission_b_raw, submission_b_pin,
                              **inputs):
    return verify_strict_reviews(
        pair_raw=pair_raw, pair_pin=pair_pin, submission_a_raw=submission_a_raw,
        submission_a_pin=submission_a_pin, submission_b_raw=submission_b_raw,
        submission_b_pin=submission_b_pin, **_canonical(**inputs))
