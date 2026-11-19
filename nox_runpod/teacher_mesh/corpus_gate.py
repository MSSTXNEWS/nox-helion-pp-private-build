#!/usr/bin/env python3
"""NOX night SFT corpus gate. Converts APPROVED teacher answers to train/holdout.

This tool does NOT access teachers, train an adapter, or create a second memory DB.
The existing NOX/S03 owner supplies already-vetted samples. No unsafe data gets
automatically promoted to model weights. Local-only, one-way, versioned exports.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import tempfile
import os
from typing import Any

SCHEMA="nox-teacher-approved-sft-v1"
MAX_EXAMPLES=50000
MAX_PROMPT=8000
MAX_COMPLETION=14000
LOCAL_ROOTS=(Path("/root/nox"),Path("/tmp/nox"),Path("/dev/shm/nox"))
SAFE_LICENSES={"apache-2.0","mit","cc-by-4.0","cc0-1.0","owner-original"}
ALLOWED_SOURCE_KINDS={"local_open_weights","internal_human_review"}
FORBIDDEN_KEYS={"secret","password","api_key","token","private_key"}


def canonical_hash(text: str) -> str:
    normalized=re.sub(r"\s+"," ",text.strip().casefold())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def quality_gate(record: Any) -> tuple[bool,str]:
    """Fail closed. Assertions/quality must be supplied by an independent evaluator.
    A teacher reply alone does not constitute independent correctness evidence.
    """
    if not isinstance(record,dict):
        return False,"NOT_OBJECT"
    required={"task_id","cluster_id","prompt","completion","teacher_model",
              "model_card_url","source_kind","license","quality_score",
              "quality_verified","rights_verified","privacy_verified",
              "owner_approved","review_evidence"}
    if not required.issubset(record):return False,"MISSING_FIELDS"
    if any(k in record for k in FORBIDDEN_KEYS):return False,"UNSAFE_FIELDS"
    if not all(record.get(k) is True for k in (
        "quality_verified","rights_verified","privacy_verified","owner_approved"
    )):return False,"NOT_APPROVED"
    if record["source_kind"] not in ALLOWED_SOURCE_KINDS:
        return False,"HOSTED_TRAINING_PERMISSION_NOT_VERIFIED"
    if record["license"].lower() not in SAFE_LICENSES:
        return False,"LICENSE_NOT_ALLOWLISTED"
    if (not isinstance(record["model_card_url"],str)
            or not record["model_card_url"].startswith("https://huggingface.co/")):
        return False,"SOURCE_NOT_ATTRIBUTED"
    if not (isinstance(record["cluster_id"],str)
            and re.fullmatch(r"[A-Za-z0-9_-]{12,100}",record["cluster_id"])):
        return False,"MISSING_SEMANTIC_CLUSTER_ID"
    if not (isinstance(record["task_id"],str)
            and re.fullmatch(r"[A-Za-z0-9_-]{8,100}",record["task_id"])):
        return False,"BAD_TASK_ID"
    if not all(isinstance(record[k],str) and record[k].strip() for k in
        ("prompt","completion","teacher_model","review_evidence")):
        return False,"EMPTY_EXAMPLE_OR_REVIEW"
    if len(record["prompt"])>MAX_PROMPT or len(record["completion"])>MAX_COMPLETION:
        return False,"EXAMPLE_TOO_LONG"
    if len(record["review_evidence"])>1000:
        return False,"REVIEW_TOO_LONG"
    score=record["quality_score"]
    if isinstance(score,bool) or not isinstance(score,(int,float)) or not 0.0<=score<=1.0:
        return False,"BAD_SCORE"
    if score<0.8:return False,"LOW_QUALITY_SCORE"
    # No arbitrary prose-based PII classifier is claimed. Independent approval
    # is mandatory; never infer privacy clearance just from a regex.
    return True,"ACCEPTED"


def _split_by_cluster(cluster_id: str, holdout_rate: int=15) -> str:
    """Entire semantic source cluster stays in one split, not per sentence."""
    bucket=int(hashlib.sha256(cluster_id.encode()).hexdigest()[:8],16)%100
    return "holdout" if bucket<holdout_rate else "train"


def build_approved_sft(records:list[dict],holdout_rate:int=15) -> dict:
    if not 1<=len(records)<=MAX_EXAMPLES:
        return {"status":"HOLD_BATCH_SIZE","accepted":[]}
    if not 5<=holdout_rate<=30:
        return {"status":"HOLD_HOLDOUT_RATE","accepted":[]}
    accepted=[]
    rejected={}
    seen=set()
    for r in records:
        good,code=quality_gate(r)
        if not good:
            rejected[code]=rejected.get(code,0)+1
            continue
        key=(canonical_hash(r["prompt"]),canonical_hash(r["completion"]))
        if key in seen:
            rejected["DUPLICATE"]=rejected.get("DUPLICATE",0)+1
            continue
        seen.add(key)
        selected=_split_by_cluster(r["cluster_id"],holdout_rate)
        # TRL prompt/completion dataset: completion-only loss.
        sft={"prompt":[{"role":"user","content":r["prompt"]}],
             "completion":[{"role":"assistant","content":r["completion"]}]}
        accepted.append({
            "split":selected,"sft":sft,"task_id":r["task_id"],
            "group_id":r["cluster_id"],"teacher_model":r["teacher_model"],
            "model_card_url":r["model_card_url"],"license":r["license"],
            "answer_sha256":hashlib.sha256(r["completion"].encode()).hexdigest(),
            "score":r["quality_score"]
        })
    return {"status":"ACCEPTED_CANDIDATES_NOT_TRAINED",
            "accepted":accepted,"rejected":rejected,
            "train":sum(1 for x in accepted if x["split"]=="train"),
            "holdout":sum(1 for x in accepted if x["split"]=="holdout")}


def export_versioned(local_output_root:str, corpus:dict) -> dict:
    """No overwrite/deletion. Existing S03 remains authoritative metadata DB."""
    if corpus.get("status")!="ACCEPTED_CANDIDATES_NOT_TRAINED" or not corpus.get("accepted"):
        return {"status":"HOLD_NO_APPROVED_DATA"}
    raw_path=Path(local_output_root)
    if not raw_path.is_absolute() or raw_path.exists() and raw_path.is_symlink():
        return {"status":"HOLD_OUTPUT_PATH"}
    resolved=raw_path.resolve(strict=False)
    if not any(root==resolved or root in resolved.parents for root in LOCAL_ROOTS):
        return {"status":"HOLD_OUTPUT_NOT_LOCAL"}
    if "/workspace" in str(resolved):
        return {"status":"HOLD_NETWORK_VOLUME"}
    resolved.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(resolved,0o700)
    # Name content-addressed corpus, not mutable 'last.jsonl'.
    entries=corpus["accepted"]
    identity=json.dumps(
        [{"task":r["task_id"],"sha256":r["answer_sha256"],"split":r["split"]}
         for r in entries],sort_keys=True).encode()
    key=hashlib.sha256(identity).hexdigest()[:20]
    dest=resolved/("corpus-"+key)
    if dest.exists():return {"status":"HOLD_ALREADY_EXPORTED","id":key}
    temp=Path(tempfile.mkdtemp(prefix=".nox_sft_",dir=resolved))
    try:
        for kind in ("train","holdout"):
            target=temp/(kind+".jsonl")
            with target.open("w",encoding="utf-8") as out:
                for x in entries:
                    if x["split"]==kind:
                        out.write(json.dumps(x["sft"],ensure_ascii=False)+"\n")
                out.flush();os.fsync(out.fileno())
            os.chmod(target,0o600)
        manifest={
            "schema":SCHEMA,"id":key,"status":"REVIEWED_NOT_OPTIMIZER_TRAINED",
            "counts":{"train":corpus["train"],"holdout":corpus["holdout"]},
            "splitting":"SEMANTIC_GROUP_STABLE_SHA256",
            "response_only_loss_required":True,
            "teacher_weights_copied":False,
            "source_attribution":[{
                "task_id":x["task_id"],"teacher_model":x["teacher_model"],
                "model_card_url":x["model_card_url"],"answer_sha256":x["answer_sha256"]
            } for x in entries],
        }
        for kind in ("train","holdout"):
            name=kind+".jsonl"
            manifest[name+"_sha256"]=hashlib.sha256((temp/name).read_bytes()).hexdigest()
        with (temp/"manifest.json").open("w",encoding="utf-8") as out:
            json.dump(manifest,out,ensure_ascii=False,indent=2)
            out.flush();os.fsync(out.fileno())
        os.chmod(temp/"manifest.json",0o600)
        os.rename(temp,dest)
        return {"status":"CORPUS_EXPORTED_NO_TRAINING","id":key,
                "path":str(dest),"counts":manifest["counts"],
                "manifest_sha256":hashlib.sha256((dest/"manifest.json").read_bytes()).hexdigest()}
    except Exception:
        # Deliberately leave temp artifacts in place on failure for inspection.
        return {"status":"HOLD_EXPORT_FAILED_TEMP_PRESERVED"}
