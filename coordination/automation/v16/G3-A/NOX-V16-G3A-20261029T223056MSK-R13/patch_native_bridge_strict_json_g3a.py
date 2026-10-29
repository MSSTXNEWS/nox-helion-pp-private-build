"""G3-A R13: exact-PRE owner handoff patch for the existing PACK01 loader.

This patch generator does NOT write PR162 or start Windows/CPU/GPU workers.
Only T06 may integrate its proposed bytes into the real owner source tree.
"""
from __future__ import annotations

import difflib
import hashlib
from pathlib import Path

TARGET_PATH = "proposals/NOX-PACK01-50/native_bridge.py"
OBSERVED_PRE_GIT_BLOB_SHA1 = "1cd8f2d49a440775401e4ad0a3721d2ef36c8b62"

REPLACEMENTS = (
    (
        'class HostDenied(PermissionError):\n    """Native host refused permission, consent or session."""',
        'class HostDenied(PermissionError):\n    """Native host refused permission, consent or session."""'
        '\n\n\ndef _reject_duplicate_native_json_members(pairs):'
        '\n    """Reject lossy JSON member collisions before approval or owner call."""'
        '\n    result = {}'
        '\n    for key, value in pairs:'
        '\n        if key in result:'
        '\n            raise HostDenied("Duplicate native JSON property")'
        '\n        result[key] = value'
        '\n    return result'
    ),
    (
        'frozen_payload = json.loads(raw)',
        'frozen_payload = json.loads(raw, object_pairs_hook=_reject_duplicate_native_json_members)'
    ),
    (
        'self.native_approve(session,route,json.loads(raw)) is not True):',
        'self.native_approve(session,route,json.loads(raw, object_pairs_hook=_reject_duplicate_native_json_members)) is not True):'
    ),
)


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\x00" + data).hexdigest()


def propose_bytes(preimage: bytes, *, expected_git_blob_sha1: str = OBSERVED_PRE_GIT_BLOB_SHA1) -> bytes:
    if git_blob_sha1(preimage) != expected_git_blob_sha1:
        raise ValueError("STALE_OR_UNAUTHORIZED_PACK01_PREIMAGE")
    source = preimage.decode("utf-8", "strict")
    if ('assert len(ALLOWED_ROUTES) == 50' not in source or
            'APPROVED_NATIVE_POLICY' not in source or
            'session.private_approved' not in source):
        raise ValueError("PACK01_NOLOSS_SECURITY_CONTRACT_NOT_FOUND")
    for original, updated in REPLACEMENTS:
        if source.count(original) != 1:
            raise ValueError("PACK01_ANCHOR_NONUNIQUE_OR_DRIFT")
        source = source.replace(original, updated, 1)
    return source.encode("utf-8", "strict")


def proposed_unified_diff(preimage: bytes, *, expected_git_blob_sha1: str = OBSERVED_PRE_GIT_BLOB_SHA1) -> str:
    result = propose_bytes(preimage, expected_git_blob_sha1=expected_git_blob_sha1)
    return "".join(difflib.unified_diff(
        preimage.decode("utf-8").splitlines(True), result.decode("utf-8").splitlines(True),
        fromfile="a/" + TARGET_PATH, tofile="b/" + TARGET_PATH,
    ))


def preview_file(path: str | Path) -> tuple[str, str, str]:
    """Read only: T06 must use separate CAS to apply the preview."""
    original = Path(path).read_bytes()
    candidate = propose_bytes(original)
    return (git_blob_sha1(original), git_blob_sha1(candidate), proposed_unified_diff(original))
