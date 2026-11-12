#!/usr/bin/env python3
"""NOX MYCELIUM: zero-side-effect adapter training recipe and checkpoint gate.

A recipe for integration with the single existing NOX trainer (not a trainer).
No weights are downloaded, copied, merged or overwritten here.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import hashlib
import json
import re

SCHEMA="nox-mycelium-sft-recipe-v1"
SUPPORTED_PRECISIONS={"bf16","fp16"}
ALLOWED_ROOTS=(Path("/root/nox"),Path("/tmp/nox"),Path("/dev/shm/nox"))
ALLOWED_RANKS={8,16,32,64,128}
KNOWN_MODULES={
  "q_proj","k_proj","v_proj","o_proj",
  "gate_proj","up_proj","down_proj",
  "in_proj","out_proj","qkv_proj","gate_up_proj"
}
MAX_EXPERT_PATTERNS=80

def _under_allowed_root(path):
    p=Path(path).resolve(strict=False)
    return p.is_absolute() and any(root==p or root in p.parents for root in ALLOWED_ROOTS)

def verify_corpus(corpus_dir:str)->dict:
    p=Path(corpus_dir)
    if not _under_allowed_root(p):
        return {"state":"HOLD_NONLOCAL_CORPUS"}
    try:
        manifest=json.loads((p/"manifest.json").read_text("utf-8"))
        if manifest.get("schema")!="nox-teacher-approved-sft-v1":
            return {"state":"HOLD_CORPUS_SCHEMA"}
        if manifest.get("status")!="REVIEWED_NOT_OPTIMIZER_TRAINED":
            return {"state":"HOLD_CORPUS_STATE"}
        for part in ("train","holdout"):
            filename=part+".jsonl"
            file=p/filename
            if not file.is_file() or file.is_symlink():
                return {"state":"HOLD_CORPUS_FILE"}
            if sha256(file.read_bytes()).hexdigest()!=manifest.get(filename+"_sha256"):
                return {"state":"HOLD_CORPUS_HASH"}
        if not manifest.get("response_only_loss_required"):
            return {"state":"HOLD_LOSS_MASK"}
        counts=manifest["counts"]
        if counts["train"]<1 or counts["holdout"]<1:
            return {"state":"HOLD_CORPUS_NO_HOLDOUT"}
        return {"state":"VERIFIED_SOURCE_CORPUS","counts":counts,
                "train_sha256":manifest["train.jsonl_sha256"],
                "holdout_sha256":manifest["holdout.jsonl_sha256"]}
    except (OSError,ValueError,KeyError,TypeError):
        return {"state":"HOLD_CORPUS_UNREADABLE"}

def plan_adapter(
    *,
    corpus_dir:str,
    base_model_id:str,
    base_model_sha256:str,
    checkpoint_sha256:str,
    target_modules:list[str],
    rank:int=32,
    alpha:int=64,
    learning_rate:float=0.00008,
    max_steps:int=500,
    precision:str="bf16",
    expert_target_parameters:list[str]|None=None
) -> dict:
    """The plan is *not* a proof the model's named modules exist.
    Actual architecture verification and memory fit precede any trainer launch.
    """
    if (not isinstance(base_model_id,str)
            or not re.fullmatch(r"[A-Za-z0-9._:/-]{4,160}",base_model_id)):
        return {"state":"HOLD_BASE_ID"}
    if not re.fullmatch(r"[a-f0-9]{64}",base_model_sha256) or not re.fullmatch(
       r"[a-f0-9]{64}",checkpoint_sha256
    ):
        return {"state":"HOLD_PROVENANCE_HASH"}
    if rank not in ALLOWED_RANKS or not 1<=alpha<=512:
        return {"state":"HOLD_LORA_RANK"}
    if precision not in SUPPORTED_PRECISIONS or not 0.0<learning_rate<0.001:
        return {"state":"HOLD_PRECISION_OR_LR"}
    if not 1<=max_steps<=100000:
        return {"state":"HOLD_STEP_BUDGET"}
    if not isinstance(target_modules,list) or not target_modules or any(
       t not in KNOWN_MODULES for t in target_modules
    ):
        return {"state":"HOLD_TARGET_MODULES"}
    if expert_target_parameters:
        if (len(expert_target_parameters)>MAX_EXPERT_PATTERNS
             or any(not re.fullmatch(r"[A-Za-z0-9._*]{3,200}",x)
                    for x in expert_target_parameters)):
            return {"state":"HOLD_EXPERT_TARGETS"}
    corpus=verify_corpus(corpus_dir)
    if corpus["state"]!="VERIFIED_SOURCE_CORPUS":
        return corpus
    payload={
      "schema":SCHEMA,
      "state":"RECIPE_ONLY_NOT_TRAINED",
      "base_model_id":base_model_id,
      "base_model_sha256":base_model_sha256,
      "resume_checkpoint_sha256":checkpoint_sha256,
      "corpus":corpus_dir,
      "training_data_sha256":corpus["train_sha256"],
      "holdout_data_sha256":corpus["holdout_sha256"],
      "precision":precision,
      "peft":{
        "type":"LORA", "target_modules":sorted(set(target_modules)),
        "rank":rank,"alpha":alpha,"dropout":0.05,
        "use_rslora":True,
        "target_parameters":sorted(set(expert_target_parameters or []))
      },
      "trl":{
        "dataset_format":"prompt_completion_messages",
        "completion_only_loss":True,
        "packing":False,
        "learning_rate":learning_rate,
        "max_steps":max_steps
      },
      "acceptance_gates":[
        "model_architecture_matches_target_modules",
        "expert_target_parameters_supported_by_installed_peft",
        "VRAM_BUDGET_MEASURED",
        "ONLY_ONE_NOX_TRAINER",
        "checkpoint_model_optimizer_rng_verified",
        "train_vs_holdout_no_semantic_cluster_overlap",
        "eval_before_promotion_and_lossless_rollback"
      ],
      "teacher_weights_copied":False,
      "model_weights_updated":False,
      "optimizer_steps_verified":0
    }
    return payload
