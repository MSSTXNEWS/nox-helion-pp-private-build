"""Provider-side S03 projection comparison for B1 R81.
The host must authenticate the independent input source and browser scope.
This function is not host.verifyCanonicalText and grants no ACK authority.
"""
from canonical_text import recover_text

def compare_projection(candidate, *, dialog_id, session_id, sequence, artifacts,
                       terminal, served_sha256, link_bytes, link_sha256):
    # Never derive independent evidence inputs from candidate.
    expected = recover_text(dialog_id=dialog_id, session_id=session_id,
        sequence=sequence, artifacts=artifacts, terminal=terminal,
        served_sha256=served_sha256, link_bytes=link_bytes, link_sha256=link_sha256)
    if type(candidate) is not dict or candidate.keys() != expected.keys():
        raise ValueError("HOLD_S03_PROJECTION_SCHEMA")
    for key, value in expected.items():
        # Python bool/int equality must not authorize changed flags.
        if type(candidate[key]) is not type(value) or candidate[key] != value:
            raise ValueError("HOLD_S03_PROJECTION_MISMATCH:" + key)
    return dict(status="S03_PROJECTION_MATCHED_OFFLINE",
                sequence=sequence, answer_sha256=expected["answer_sha256"],
                link_sha256=expected["link_sha256"],
                writer_sha256=expected["writer_sha256"],
                readback_sha256=expected["readback_sha256"],
                authentication_verified=False, native_accepted=False,
                ack_allowed=False, next_post_allowed=False)
