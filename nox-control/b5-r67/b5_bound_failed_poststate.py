"""Bind pending S03 row to independently admitted attempt identity.
All outcomes remain HOLD. The owner must authenticate the admission and snapshot.
This module never sends, retries, or accepts a turn.
"""
from b5_failed_poststate import classify_failed_turn
from b5_r55_pinned import strict_owner_json_bytes

def classify_bound_failed_turn(*, expected_user_message_id=None, **evidence):
    result = classify_failed_turn(**evidence)
    if result != "HOLD_S03_FAILURE_PENDING_USER":
        return result
    if (type(expected_user_message_id) is not str or not expected_user_message_id
            or expected_user_message_id.strip() != expected_user_message_id):
        return "HOLD_S03_FAILURE_PENDING_ID_UNPROVEN"
    # R66 validated the immutable bytes, scope, prefix, prompt and unique ID.
    pending = strict_owner_json_bytes(evidence["snapshot_raw"])["messages"][-1]
    if pending["message_id"] != expected_user_message_id:
        return "HOLD_S03_FAILURE_PENDING_ID_MISMATCH"
    return "HOLD_S03_FAILURE_PENDING_USER"
