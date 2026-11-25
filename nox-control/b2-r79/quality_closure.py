"""Source-only final quality boundary; never grants native admission."""
import os
import retained_snapshot_review as r78

def _signatures(artifacts):
    if type(artifacts) is not tuple or len(artifacts) != 3:
        raise ValueError("HOLD_B2_QUALITY_CHAIN_SHAPE")
    descriptors = []
    for pair in artifacts:
        if type(pair) is not tuple or len(pair) != 4:
            raise ValueError("HOLD_B2_QUALITY_CHAIN_SHAPE")
        for fd in pair[:2]:
            if type(fd) is not int or fd < 0:
                raise ValueError("HOLD_B2_QUALITY_CHAIN_FD")
            descriptors.append(fd)
    try:
        result = []
        for fd in descriptors:
            st = os.fstat(fd)
            result.append((st.st_dev, st.st_ino, st.st_size,
                           st.st_mtime_ns, st.st_ctime_ns))
        return tuple(result)
    except OSError:
        raise ValueError("HOLD_B2_QUALITY_CHAIN_READ") from None

def _guard(operation, inputs):
    descriptors = inputs["descriptor_sets"]
    before = _signatures(descriptors)
    result = operation(**inputs)
    if _signatures(descriptors) != before:
        raise ValueError("HOLD_B2_QUALITY_CLOSURE_DRIFT")
    return result

def prepare_joint_review(**inputs):
    return _guard(r78.prepare_joint_review, inputs)

def verify_joint_reviews(**inputs):
    return _guard(r78.verify_joint_reviews, inputs)
