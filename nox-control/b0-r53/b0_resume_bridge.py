"""B0 R54: pure bridge between the pinned owner GET and independent B5 evidence.
No network, POST, native admission, or production acceptance. Call only with
pins obtained from independent trusted receipts, not from the candidate GET.
"""
import hashlib
import json
import re
from b5_r55_pinned import BrowserResumeEvidence

def owner_prefix_sha(dialog_id, rows):
    return hashlib.sha256(json.dumps(
        {"dialog_id": dialog_id, "messages": rows}, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()

def bind_existing_resume(*, preflight, expected_owner_sha, dialog_id, session_id,
                         owner_rows, canonical_rows, prior_witnesses,
                         browser_calls, admitted_calls):
    """Return a one-shot B5 evidence object, NOT permission to send a POST."""
    if (type(preflight) is not dict or not isinstance(dialog_id, str)
            or not re.fullmatch(r"[a-f0-9]{32}", dialog_id)
            or not isinstance(expected_owner_sha, str)
            or not re.fullmatch(r"[a-f0-9]{64}", expected_owner_sha)
            or type(owner_rows) is not list or len(owner_rows) not in (2, 4)
            or type(preflight.get("prefix_rows")) is not int
            or preflight["prefix_rows"] != len(owner_rows)
            or preflight.get("scope") != "EXISTING_OWNER_DIALOG_PREFIX_ONLY_NOT_INDEPENDENT_S03"
            or preflight.get("prefix_pin_matched") is not True
            or preflight.get("prefix_sha256") != expected_owner_sha
            or preflight.get("dialog_id_sha256") != hashlib.sha256(dialog_id.encode("ascii")).hexdigest()
            or any(preflight.get(k) is not False for k in
                   ("model_post_issued", "dialog_created", "browser_multiturn_accepted",
                    "native_s03_independently_verified", "production_accepted"))):
        raise ValueError("HOLD_B0_RESUME_PREFLIGHT")
    try:
        actual = owner_prefix_sha(dialog_id, owner_rows)
    except (TypeError, ValueError, UnicodeError):
        raise ValueError("HOLD_B0_RESUME_OWNER_PIN") from None
    if actual != expected_owner_sha:
        raise ValueError("HOLD_B0_RESUME_OWNER_PIN")
    if any(type(row) is not dict or
           ("dialogId" in row and row["dialogId"] != dialog_id)
           for row in owner_rows):
        raise ValueError("HOLD_B0_RESUME_OWNER_SCOPE")
    return BrowserResumeEvidence(
        dialog_id=dialog_id, session_id=session_id, prior_rows=canonical_rows,
        prior_witnesses=prior_witnesses, browser_rows=owner_rows,
        browser_calls=browser_calls, admitted_calls=admitted_calls)
