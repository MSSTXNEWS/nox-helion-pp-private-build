"""NOX PRIME Cold Vault offload admission inside the existing OneHost.

Never delete live student weights, S03, optimizer or checkpoints to regain
space. Trigger below the owner's 10GB free-disk threshold; prefer existing
encrypted Drive/PC offsite with full SHA and owner-key restoration verification.
This module does not copy, delete, fork or open network.
"""
from __future__ import annotations
from collections.abc import Mapping

FLOOR_BYTES=10_000_000_000
PROTECTED=frozenset({"active_student","s03","checkpoint","optimizer","genesis","chat","onehost"})
REGEN=frozenset({"pip_cache","rebuildable_download_cache","temporary_compilation_cache"})


def plan_offload(status:Mapping)->dict:
    base={"schema":"NOX_PRIME_OFFLOAD_PLAN_V1","performed":False,
          "queue_owner":"EXISTING_NOX_ONEHOST","chat_allowed":True,
          "s03_canonical_preserved":True,"source_deleted":False,
          "no_second_scheduler":True,"minimum_free_bytes":FLOOR_BYTES,
          "actions":[]}
    if not isinstance(status,Mapping) or type(status.get("disk_free_bytes")) is not int:
        return {**base,"state":"HOLD_NATIVE_DISK_TELEMETRY"}
    free=status["disk_free_bytes"]
    if free<0:
        return {**base,"state":"HOLD_NATIVE_DISK_TELEMETRY"}
    if free>=FLOOR_BYTES:
        return {**base,"state":"NO_CLEANUP_NEEDED","available_bytes":free}
    if status.get("stop_active") is not False:
        return {**base,"state":"HOLD_STOP_OR_UNVERIFIED"}
    if status.get("native_owner_authorized") is not True:
        return {**base,"state":"HOLD_OWNER_APPROVAL"}
    result={**base,"state":"OFFLOAD_REQUIRED","available_bytes":free,
            "missing_to_floor_bytes":FLOOR_BYTES-free,
            "actions":["CHAT_P0_UNINTERRUPTED","CPU_READONLY_STORAGE_INVENTORY"]}
    candidates=status.get("candidates")
    if not isinstance(candidates,list):
        return {**result,"state":"HOLD_CANDIDATE_INVENTORY"}
    for row in candidates[:100]:
        if not isinstance(row,Mapping):continue
        kind=row.get("kind")
        if kind in PROTECTED:
            continue
        if (kind in REGEN and row.get("native_verified") is True
                and row.get("not_open") is True
                and row.get("not_used_by_running_process") is True
                and row.get("allowlisted_root") is True):
            result["actions"].append("OWNER_NATIVE_REGENERABLE_CACHE_CLEANUP_PROPOSAL")
            continue
        # Cold files need a real encrypted offsite copy, full SHA compare,
        # independent download, owner-key restoration proof and owner lease.
        if kind=="cold_model" and row.get("active_student") is False:
            if all(row.get(k) is True for k in (
                "original_full_sha_verified","offsite_cipher_sha_verified",
                "offsite_download_roundtrip_verified",
                "owner_key_restore_verified","native_restore_readback_verified",
                "source_inode_not_open","source_not_hardlinked_to_active_model",
                "owner_delete_scope_verified")):
                result["actions"].append("OWNER_NATIVE_VERIFIED_COLD_COPY_CLEANUP_PROPOSAL")
            else:
                result["actions"].append("VERIFY_COLD_MODEL_OFFSITE_AND_RESTORE_BEFORE_CLEANUP")
    if status.get("drive_destination_authorized") is True:
        result["actions"].append("ENCRYPTED_DRIVE_COPY_THROUGH_EXISTING_OFFLOAD")
    elif status.get("pc_cold_destination_authorized") is True:
        result["actions"].append("ENCRYPTED_PC_COPY_THROUGH_EXISTING_OFFLOAD")
    else:
        result["actions"].append("HOLD_EXTERNAL_DESTINATION")
    result["actions"]=list(dict.fromkeys(result["actions"]))
    return result
