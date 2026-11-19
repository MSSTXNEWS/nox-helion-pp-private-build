#!/usr/bin/env python3
"""NOX V30: prevent invalid cross-family weight absorption and fabricated learning.

Pure source-only gate: does not load untrusted model weights or torch pickle,
does not execute teacher source, alter ONE NOX, copy sensitive data, download,
start GPU or create a competing model server.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from typing import Any

SHA256=re.compile(r"^[a-f0-9]{64}$")
SHA40=re.compile(r"^[a-f0-9]{40}$")
ID=re.compile(r"^[A-Za-z0-9_./-]{3,140}$")
SCHEMA="nox-v30-model-admission-v1"

def _sha(value:Any)->bool:
    return isinstance(value,str) and bool(SHA256.fullmatch(value))

def _deny(reason:str)->dict:
    return {"schema":SCHEMA,"state":"HOLD","reason":reason,
            "student_weights_changed":False,"gpu_training_launched":False,
            "active_nox_switched":False,"untrusted_code_executed":False}

def admit_teacher(student:dict,teacher:dict,owner_policy:dict)->dict:
    """Frozen teacher = data source ONLY, never raw weights merge across architectures."""
    if not all(isinstance(x,dict) for x in (student,teacher,owner_policy)):
        return _deny("INVALID_NATIVE_METADATA")
    if owner_policy.get("signed_by_native_owner") is not True or owner_policy.get("stop_active") is not False:
        return _deny("SIGNED_OWNER_AND_STOP_REQUIRED")
    if not _sha(student.get("active_model_sha256")):
        return _deny("STUDENT_SHA_MISSING")
    if not isinstance(teacher.get("model_id"),str) or not ID.fullmatch(teacher["model_id"]):
        return _deny("BAD_TEACHER_ID")
    if teacher.get("model_id") not in owner_policy.get("allowed_teacher_ids",[]):
        return _deny("TEACHER_NOT_APPROVED")
    if not isinstance(teacher.get("revision"),str) or not SHA40.fullmatch(teacher["revision"]):
        return _deny("UNPINNED_TEACHER_REVISION")
    if not _sha(teacher.get("weights_sha256")):
        return _deny("TEACHER_WEIGHTS_UNVERIFIED")
    if teacher.get("license_review")!="APPROVED" or teacher.get("training_rights") is not True:
        return _deny("LICENSE_OR_DISTILLATION_RIGHTS_HOLD")
    if teacher.get("model_family") not in ("qwen","deepseek","mistral","llama","other_frozen_teacher"):
        return _deny("UNKNOWN_TEACHER_FAMILY")
    if teacher.get("source")!="trusted_model_registry" or teacher.get("frozen_in_isolated_vm") is not True:
        return _deny("TEACHER_VM_ISOLATION_NOT_VERIFIED")
    if teacher.get("sends_private_s03_to_teacher") is not False:
        return _deny("PRIVATE_S03_EXFILTRATION_HOLD")
    if (type(teacher.get("max_bytes")) is not int or
        teacher["max_bytes"]>owner_policy.get("max_source_bytes",0) or
        teacher["max_bytes"]<1000):
        return _deny("TEACHER_SIZE_OR_QUOTA")
    return {"schema":SCHEMA,"state":"FROZEN_TEACHER_CANDIDATE_ONLY",
            "method":"GENERATE_VERIFIED_EXAMPLES_THEN_SFT_DPO_NOT_WEIGHT_AVERAGING",
            "student_model_sha256":student["active_model_sha256"],
            "teacher_id":teacher["model_id"],"teacher_revision":teacher["revision"],
            "teacher_weights_sha256":teacher["weights_sha256"],
            "trainer_launch_allowed":False,
            "student_weights_changed":False,"gpu_training_launched":False,
            "active_nox_switched":False,"untrusted_code_executed":False}

def admit_student_update(base:dict,candidate:dict,evals:dict,owner_policy:dict)->dict:
    """Review a purported full-weight merge. Does not promote or rewrite on disk."""
    if not all(isinstance(x,dict) for x in (base,candidate,evals,owner_policy)):
        return _deny("INVALID_UPDATE_METADATA")
    if owner_policy.get("signed_by_native_owner") is not True or owner_policy.get("stop_active") is not False:
        return _deny("NATIVE_OWNER_STOP_HOLD")
    if not all(_sha(base.get(k)) for k in ("weights_sha256","tokenizer_sha256","architecture_sha256")):
        return _deny("BASE_FINGERPRINT_MISSING")
    if not all(_sha(candidate.get(k)) for k in ("weights_sha256","base_model_sha256",
            "tokenizer_sha256","architecture_sha256","optimizer_receipt_sha256",
            "dataset_sha256","checkpoint_sha256")):
        return _deny("CANDIDATE_FINGERPRINTS_MISSING")
    if (candidate["base_model_sha256"]!=base["weights_sha256"] or
        candidate["tokenizer_sha256"]!=base["tokenizer_sha256"] or
        candidate["architecture_sha256"]!=base["architecture_sha256"]):
        return _deny("MODEL_ABI_OR_BASE_SHA_MISMATCH")
    if candidate["weights_sha256"]==base["weights_sha256"]:
        return _deny("NO_STUDENT_WEIGHT_CHANGE")
    if (type(candidate.get("optimizer_steps")) is not int or candidate["optimizer_steps"]<1
        or candidate.get("checkpoint_readback_verified") is not True
        or candidate.get("optimizer_state_readback_verified") is not True
        or candidate.get("rng_state_readback_verified") is not True
        or candidate.get("safe70_verified") is not True
        or candidate.get("production_mutated") is not False):
        return _deny("OPTIMIZER_CHECKPOINT_SAFE70_EVIDENCE_HOLD")
    if (evals.get("same_harness_sha") is None or not _sha(evals["same_harness_sha"])
        or evals.get("independent_heldout") is not True
        or evals.get("source_disjoint") is not True
        or evals.get("anti_forgetting_passed") is not True
        or evals.get("stop_and_s03_regression_passed") is not True):
        return _deny("INDEPENDENT_EVAL_OR_ANTIFORGET_HOLD")
    return {"schema":SCHEMA,"state":"STUDENT_CHANGE_EVIDENCE_REVIEW_CANDIDATE_NOT_PROMOTED",
            "source_weight_sha256":base["weights_sha256"],
            "candidate_weight_sha256":candidate["weights_sha256"],
            "optimizer_steps_reported":candidate["optimizer_steps"],
            "replay_required":True,"independent_windows_e07_required":True,
            "student_weights_changed":False,"gpu_training_launched":False,
            "active_nox_switched":False,"untrusted_code_executed":False}
