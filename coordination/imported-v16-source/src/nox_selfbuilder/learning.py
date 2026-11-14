"""Existing S03 and FORGE contracts: no second learning database or trainer."""
from datetime import datetime, timezone
import hashlib
import json
import re

SHA256 = re.compile(r"^[0-9a-f]{64}$")


def make_learning_record(*, run_id:str, receipt:dict, outcome:str,
                         reviewer_source_id:str, native_approve:bool) -> dict:
    if not native_approve or outcome not in ("ACCEPTED", "REJECTED", "NO_GAIN"):
        raise PermissionError("LEARNING_REQUIRES_VERIFIED_OWNER_OUTCOME")
    if receipt.get("status") != "SOURCE_CANDIDATE_REVIEW_REQUIRED_NOT_EXECUTED":
        raise ValueError("INVALID_PROPOSAL_RECEIPT")
    if not reviewer_source_id or not isinstance(reviewer_source_id,str):
        raise ValueError("REVIEW_EVIDENCE_REQUIRED")
    return {"schema":"NOX-SELFBUILDER-LESSON-v1", "run_id":run_id,
            "proposal_sha256":receipt["code_sha256"], "outcome":outcome,
            "reviewer_source_id":reviewer_source_id,
            "created_utc":datetime.now(timezone.utc).isoformat(),
            "destination":"existing S03 append-only owner ledger",
            "S03_WRITE_PERFORMED":False, "weights_updated":False}


def make_forge_handoff(*, dataset_manifest_sha256:str, base_model_snapshot_sha256:str,
                       rights_receipt_id:str, approved:bool, gpu_preflight:dict) -> dict:
    if not approved or not rights_receipt_id:
        raise PermissionError("FORGE_TRAINING_OWNER_CONSENT_REQUIRED")
    if (not SHA256.fullmatch(dataset_manifest_sha256) or
        not SHA256.fullmatch(base_model_snapshot_sha256)):
        raise ValueError("FORGE_IMMUTABLE_INPUT_HASH_REQUIRED")
    if gpu_preflight.get("status") != "HARDWARE_READY_ONLY":
        raise ValueError("FORGE_NATIVE_GPU_HOLD")
    return {"schema":"NOX-SELFBUILDER-FORGE-HANDOFF-v1",
            "existing_trainer":"Packages/P04/train_qlora.py",
            "dataset_manifest_sha256":dataset_manifest_sha256,
            "base_model_snapshot_sha256":base_model_snapshot_sha256,
            "rights_receipt_id":rights_receipt_id,
            "training":"NOT_EXECUTED", "learning_gain":"NOT_MEASURED",
            "next_step":"existing P04 trainer preflight+independent holdout, checkpoint/rollback", "release_accepted":False}
