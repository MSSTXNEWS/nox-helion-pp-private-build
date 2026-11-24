"""Owner-opened retained S03 checkpoint pairs; evidence only, no admission.

Supply original independent pins and descriptors for turns 1/2 before turn 3,
and all three at terminal. Never recreate historical receipts from current rows.
"""
import os
from b5_r55_pinned import load_pinned_s03_artifacts
from b5_chain_guard import verify_existing_chain


def _signature(fd):
    st = os.fstat(fd)
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def load_retained_chain(*, dialog_id, session_id, artifacts):
    """Return verified checkpoints, or raise HOLD. Each pair is
    (writer_fd, readback_fd, externally pinned writer SHA256, reader SHA256).
    Does not open paths, move offsets, close descriptors, POST or write.
    """
    if type(artifacts) is not tuple or len(artifacts) not in (2, 3):
        raise ValueError("HOLD_RETAINED_CHAIN_LENGTH")
    descriptors, pins = [], []
    for pair in artifacts:
        if type(pair) is not tuple or len(pair) != 4:
            raise ValueError("HOLD_RETAINED_CHAIN_PAIR")
        w, r, ws, rs = pair
        if any(type(fd) is not int or fd < 0 for fd in (w, r)):
            raise ValueError("HOLD_RETAINED_CHAIN_FD")
        if any(type(pin) is not str for pin in (ws, rs)):
            raise ValueError("HOLD_RETAINED_CHAIN_PIN")
        descriptors.extend((w, r))
        pins.extend((ws, rs))
    if len(set(descriptors)) != len(descriptors) or len(set(pins)) != len(pins):
        raise ValueError("HOLD_RETAINED_CHAIN_REUSE")
    try:
        signatures = tuple(_signature(fd) for fd in descriptors)
        if len({s[:2] for s in signatures}) != len(signatures):
            raise ValueError("HOLD_RETAINED_CHAIN_ALIAS")
        chain = []
        for sequence, (w, r, ws, rs) in enumerate(artifacts, 1):
            previous = chain[-1] if chain else (None, None)
            chain.append(load_pinned_s03_artifacts(
                writer_fd=w, readback_fd=r, writer_sha256=ws,
                readback_sha256=rs, dialog_id=dialog_id, session_id=session_id,
                sequence=sequence, prior_rows=previous[0],
                prior_witnesses=previous[1]))
        if tuple(_signature(fd) for fd in descriptors) != signatures:
            raise ValueError("HOLD_RETAINED_CHAIN_CHANGED")
    except OSError:
        raise ValueError("HOLD_RETAINED_CHAIN_READ") from None
    result = tuple(chain)
    if not verify_existing_chain(dialog_id=dialog_id, session_id=session_id,
                                 chain=result):
        raise ValueError("HOLD_RETAINED_CHAIN_INVALID")
    return result
