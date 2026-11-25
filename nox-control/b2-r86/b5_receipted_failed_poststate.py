"""Read-only consistency gate for independently authenticated owner receipts.
The caller supplies a trusted detached receipt digest, never a digest derived
from the candidate snapshot. This gate cannot authenticate the owner or
authorize another POST. All outcomes remain HOLD.
"""
import hashlib
import re
from b5_r55_pinned import strict_owner_json_bytes
from b5_bound_failed_poststate import classify_bound_failed_turn

def classify_receipted_failed_turn(*, admission_raw=None, admission_sha256=None,
                                    **evidence):
    baseline = classify_bound_failed_turn(**evidence)
    if baseline != "HOLD_S03_FAILURE_PENDING_ID_UNPROVEN":
        return baseline
    if (type(admission_raw) is not bytes or not 0 < len(admission_raw) <= 16384
            or type(admission_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", admission_sha256) is None
            or hashlib.sha256(admission_raw).hexdigest() != admission_sha256
            or admission_sha256 == evidence["snapshot_sha256"]):
        return "HOLD_S03_FAILURE_ADMISSION_PIN"
    try:
        receipt = strict_owner_json_bytes(admission_raw)
        keys = {"schema", "dialog_id", "session_id", "attempt_id",
                "snapshot_sha256", "user_message_id"}
        if type(receipt) is not dict or set(receipt) != keys:
            return "HOLD_S03_FAILURE_ADMISSION_SCOPE"
        if receipt["schema"] != "nox.s03.failed-attempt-binding.v1":
            return "HOLD_S03_FAILURE_ADMISSION_SCOPE"
        for key in ("dialog_id", "session_id", "attempt_id", "snapshot_sha256"):
            if type(receipt[key]) is not str or receipt[key] != evidence[key]:
                return "HOLD_S03_FAILURE_ADMISSION_SCOPE"
        return classify_bound_failed_turn(
            expected_user_message_id=receipt["user_message_id"], **evidence)
    except (ValueError, TypeError, KeyError, RuntimeError, UnicodeError, RecursionError):
        return "HOLD_S03_FAILURE_ADMISSION_INVALID"
