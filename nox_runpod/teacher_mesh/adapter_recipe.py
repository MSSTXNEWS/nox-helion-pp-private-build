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
import math
import re
import unicodedata

SCHEMA="nox-mycelium-sft-recipe-v1"
SUPPORTED_PRECISIONS={"fp16"}  # Existing 2x V100 SM70: never silently request BF16.
ALLOWED_ROOTS=(Path("/root/nox"),Path("/tmp/nox"),Path("/dev/shm/nox"))
ALLOWED_RANKS={8,16,32,64,128}
KNOWN_MODULES={
  "q_proj","k_proj","v_proj","o_proj",
  "gate_proj","up_proj","down_proj",
  "in_proj","out_proj","qkv_proj","gate_up_proj"
}
MAX_EXPERT_PATTERNS=80

def _under_allowed_root(path):
    try:
        p=Path(path).resolve(strict=False)
    except (OSError, TypeError, ValueError):
        return False
    return p.is_absolute() and any(root==p or root in p.parents for root in ALLOWED_ROOTS)

def _file_sha256_streamed(file:Path)->str:
    """Bounded RAM hashing: do not load entire training JSONL into memory."""
    hasher=sha256()
    with file.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def _reject_duplicate_json_keys(pairs):
    """A rehashed corpus must not hide conflicting JSON property values."""
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError("duplicate JSON property")
        result[key]=value
    return result

def _reject_nonfinite_json_constant(value):
    raise ValueError("nonfinite JSON constant: "+value)

def _strict_json_loads(value):
    """Use one unambiguous JSON interpretation for manifest and TRL rows."""
    return json.loads(value,object_pairs_hook=_reject_duplicate_json_keys,
                      parse_constant=_reject_nonfinite_json_constant)

MAX_CORPUS_ROW_BYTES=65536
MAX_CORPUS_ROWS=50000
# Hard bound even if owner receipt metadata is tampered; max ~150k row proofs.
MAX_MANIFEST_BYTES=96*1024*1024

def _prompt_fingerprint(row:object)->str|None:
    """Check the intended TRL message shape, not merely a hash of arbitrary JSONL."""
    if not isinstance(row,dict) or set(row)!={"prompt","completion"}:
        return None
    prompt=row["prompt"]
    completion=row["completion"]
    if (not isinstance(prompt,list) or len(prompt)!=1
            or not isinstance(completion,list) or len(completion)!=1):
        return None
    for message,role in ((prompt[0],"user"),(completion[0],"assistant")):
        if (not isinstance(message,dict) or set(message)!={"role","content"}
                or message["role"]!=role or not isinstance(message["content"],str)
                or not message["content"].strip()):
            return None
    # Invisible format-controls can disguise a train/holdout collision.
    # Fail closed rather than treating different hashes as disjoint evidence.
    if any(unicodedata.category(ch) == "Cf"
           for msg in (prompt[0],completion[0]) for ch in msg["content"]):
        return None
    normalized=unicodedata.normalize("NFKC",prompt[0]["content"]).casefold()
    normalized=" ".join(normalized.split())
    return sha256(normalized.encode("utf-8")).hexdigest()

def _source_row_sha256(value:str)->str:
    """Match the original V28 canonical_hash used for owner-pinned row proofs."""
    normalized=unicodedata.normalize("NFKC",value.strip().casefold())
    normalized="".join(ch for ch in normalized if unicodedata.category(ch)!="Cf")
    return sha256(re.sub(r"\s+"," ",normalized).encode("utf-8")).hexdigest()

def _inspect_corpus_file(file:Path,expected_rows:int,train_fingerprints:set[str]|None,
                         owner_proofs:list[dict]|None=None,
                         seen_answers:set[str]|None=None)->dict:
    """Stream/hash/parse bounded JSONL. Exact-text disjointness, not semantic proof."""
    digest=sha256()
    seen=set()
    rows=0
    with file.open("rb") as stream:
        while True:
            raw=stream.readline(MAX_CORPUS_ROW_BYTES+1)
            if not raw:
                break
            if len(raw)>MAX_CORPUS_ROW_BYTES:
                return {"state":"HOLD_CORPUS_ROW_TOO_LARGE"}
            digest.update(raw)
            try:
                row=_strict_json_loads(raw)
            except (ValueError,UnicodeDecodeError):
                return {"state":"HOLD_CORPUS_JSONL_FORMAT"}
            fp=_prompt_fingerprint(row)
            if fp is None:
                return {"state":"HOLD_CORPUS_JSONL_FORMAT"}
            # Bind each exported source receipt to the exact on-disk JSONL row.
            # Matching file hashes alone do not authenticate the claimed group.
            if owner_proofs is not None:
                proof=owner_proofs[rows] if rows<len(owner_proofs) else None
                if (proof is None
                        or _source_row_sha256(row["prompt"][0]["content"])!=proof["prompt_sha256"]
                        or _source_row_sha256(row["completion"][0]["content"])!=proof["answer_sha256"]):
                    return {"state":"HOLD_CORPUS_ROW_PROVENANCE_MISMATCH"}
            if fp in seen:
                return {"state":"HOLD_CORPUS_DUPLICATE_PROMPT"}
            if train_fingerprints is not None and fp in train_fingerprints:
                return {"state":"HOLD_CORPUS_EXACT_HOLDOUT_LEAKAGE"}
            # The existing V28 three-way exporter forbids duplicate completions.
            # Mirror that rule in the independent FORGE importer, including
            # hash-consistent repacks with newly generated row receipts.
            if seen_answers is not None:
                answer_fp=_source_row_sha256(row["completion"][0]["content"])
                if answer_fp in seen_answers:
                    return {"state":"HOLD_CORPUS_DUPLICATE_ANSWER"}
                seen_answers.add(answer_fp)
            seen.add(fp)
            rows+=1
            if rows>MAX_CORPUS_ROWS or rows>expected_rows:
                return {"state":"HOLD_CORPUS_COUNT_MISMATCH"}
    if rows!=expected_rows:
        return {"state":"HOLD_CORPUS_COUNT_MISMATCH"}
    return {"state":"SOURCE_ROWS_PARSED","sha256":digest.hexdigest(),"prompts":seen}

def verify_corpus(corpus_dir:str)->dict:
    """Bounded local JSONL integrity gate, including optional owner threeway splits.

    Owner group hashes are checked for shape/disjointness only. The caller must
    obtain independent authenticated owner-native provenance before training.
    """
    try:
        p=Path(corpus_dir)
    except (OSError,TypeError,ValueError):
        return {"state":"HOLD_NONLOCAL_CORPUS"}
    if not _under_allowed_root(p):
        return {"state":"HOLD_NONLOCAL_CORPUS"}
    if p.is_symlink() or not p.is_dir():
        return {"state":"HOLD_CORPUS_DIRECTORY"}
    try:
        mf=p/"manifest.json"
        if not mf.is_file() or mf.is_symlink():
            return {"state":"HOLD_CORPUS_MANIFEST_FILE"}
        # read_text() was unbounded even though JSONL reads were capped.
        # Bound the manifest before JSON decoding/provenance inspection.
        with mf.open("rb") as manifest_stream:
            manifest_bytes=manifest_stream.read(MAX_MANIFEST_BYTES+1)
        if len(manifest_bytes)>MAX_MANIFEST_BYTES:
            return {"state":"HOLD_CORPUS_MANIFEST_TOO_LARGE"}
        manifest=_strict_json_loads(manifest_bytes.decode("utf-8"))
        if not isinstance(manifest,dict):
            return {"state":"HOLD_CORPUS_SCHEMA"}
        schema=manifest.get("schema")
        legacy=schema=="nox-teacher-approved-sft-v1"
        threeway=schema=="nox-teacher-owner-threeway-sft-v2"
        if not (legacy or threeway):
            return {"state":"HOLD_CORPUS_SCHEMA"}
        if manifest.get("status")!="REVIEWED_NOT_OPTIMIZER_TRAINED":
            return {"state":"HOLD_CORPUS_STATE"}
        if manifest.get("response_only_loss_required") is not True:
            return {"state":"HOLD_LOSS_MASK"}
        counts=manifest.get("counts")
        expected_splits=("train","dev","holdout") if threeway else ("train","holdout")
        if not isinstance(counts,dict) or set(counts)!=set(expected_splits):
            return {"state":"HOLD_CORPUS_SPLIT_SET"}
        if any(type(counts[k]) is not int or not 1<=counts[k]<=MAX_CORPUS_ROWS
               for k in expected_splits):
            return {"state":"HOLD_CORPUS_NO_HOLDOUT"}
        if legacy and (p/"dev.jsonl").exists():
            return {"state":"HOLD_CORPUS_UNDECLARED_SPLIT"}
        if threeway:
            if manifest.get("splitting")!="OWNER_RECEIPT_SOURCE_GROUP_DISJOINT_SHA256":
                return {"state":"HOLD_CORPUS_OWNER_SPLIT_POLICY"}
            owner_groups=manifest.get("source_group_shas_by_split")
            if not isinstance(owner_groups,dict) or set(owner_groups)!=set(expected_splits):
                return {"state":"HOLD_CORPUS_OWNER_GROUPS"}
            all_groups=set()
            for part in expected_splits:
                group_shas=owner_groups[part]
                if (not isinstance(group_shas,list) or not group_shas
                        or any(not isinstance(s,str) or re.fullmatch(r"[a-f0-9]{64}",s) is None
                               for s in group_shas)
                        or len(set(group_shas))!=len(group_shas)):
                    return {"state":"HOLD_CORPUS_OWNER_GROUPS"}
                if all_groups.intersection(group_shas):
                    return {"state":"HOLD_CORPUS_OWNER_GROUP_OVERLAP"}
                all_groups.update(group_shas)
            owner_proofs=manifest.get("source_receipts")
            if (not isinstance(owner_proofs,list)
                    or len(owner_proofs)!=sum(counts.values())):
                return {"state":"HOLD_CORPUS_SOURCE_RECEIPT_PROOF"}
            proof_fields={"part","task_id","group","source","privacy",
                          "prompt_sha256","answer_sha256"}
            proof_by_split={part:[] for part in expected_splits}
            seen_sources=set()
            for proof in owner_proofs:
                if not isinstance(proof,dict) or set(proof)!=proof_fields:
                    return {"state":"HOLD_CORPUS_SOURCE_RECEIPT_PROOF"}
                part=proof["part"]
                if (not isinstance(part,str) or part not in proof_by_split
                        or not isinstance(proof["task_id"],str)
                        or re.fullmatch(r"[A-Za-z0-9_-]{8,100}",proof["task_id"]) is None
                        or any(not isinstance(proof[k],str)
                               or re.fullmatch(r"[a-f0-9]{64}",proof[k]) is None
                               for k in ("group","source","privacy",
                                         "prompt_sha256","answer_sha256"))):
                    return {"state":"HOLD_CORPUS_SOURCE_RECEIPT_PROOF"}
                if proof["source"] in seen_sources:
                    return {"state":"HOLD_CORPUS_SOURCE_RECEIPT_REPLAY"}
                seen_sources.add(proof["source"])
                proof_by_split[part].append(proof)
            if any(len(proof_by_split[k])!=counts[k]
                   or {proof["group"] for proof in proof_by_split[k]}!=set(owner_groups[k])
                   for k in expected_splits):
                return {"state":"HOLD_CORPUS_SOURCE_RECEIPT_GROUPS"}
        all_prompts=set()
        all_answers=set() if threeway else None
        verified_shas={}
        for part in expected_splits:
            filename=part+".jsonl"
            file=p/filename
            if not file.is_file() or file.is_symlink():
                return {"state":"HOLD_CORPUS_FILE"}
            details=_inspect_corpus_file(file,counts[part],all_prompts if all_prompts else None,
                                         proof_by_split[part] if threeway else None,
                                         all_answers)
            if details["state"]!="SOURCE_ROWS_PARSED":
                return {"state":details["state"]}
            if details["sha256"]!=manifest.get(filename+"_sha256"):
                return {"state":"HOLD_CORPUS_HASH"}
            verified_shas[part]=details["sha256"]
            all_prompts.update(details["prompts"])
        result={"state":"VERIFIED_SOURCE_CORPUS","counts":counts,
                "train_sha256":verified_shas["train"],
                "holdout_sha256":verified_shas["holdout"],
                "owner_corpus_identity_native_verified":False,
                "split_evidence":"EXACT_PROMPT_THREEWAY_DISJOINT_SOURCE_ONLY_OWNER_RECEIPTS_NOT_NATIVE_VALIDATED"
                    if threeway else "EXACT_PROMPT_DISJOINT_SOURCE_ONLY_SEMANTIC_HOLDOUT_UNVERIFIED"}
        if threeway:
            result["dev_sha256"]=verified_shas["dev"]
        return result
    except (OSError,ValueError,KeyError,TypeError,AttributeError):
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
    precision:str="fp16",
    expert_target_parameters:list[str]|None=None,
    base_revision:str|None=None,
    base_architecture:str|None=None,
    base_config_sha256:str|None=None,
    tokenizer_sha256:str|None=None,
    base_weight_manifest_sha256:str|None=None,
    use_rslora:bool=False
) -> dict:
    """The plan is *not* a proof the model's named modules exist.
    Actual architecture verification and memory fit precede any trainer launch.
    """
    if (not isinstance(base_model_id,str)
            or not re.fullmatch(r"[A-Za-z0-9._:/-]{4,160}",base_model_id)):
        return {"state":"HOLD_BASE_ID"}
    if base_model_id.lower().endswith(".gguf"):
        return {"state":"HOLD_GGUF_NOT_TRAINABLE_HF_BASE"}
    if not isinstance(base_revision,str) or not re.fullmatch(r"[a-f0-9]{40}",base_revision):
        return {"state":"HOLD_IMMUTABLE_HF_REVISION"}
    if not isinstance(base_architecture,str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,127}",base_architecture):
        return {"state":"HOLD_HF_ARCHITECTURE"}
    if any(not isinstance(value,str) or re.fullmatch(r"[a-f0-9]{64}",value) is None
           for value in (base_model_sha256,checkpoint_sha256,base_config_sha256,
                         tokenizer_sha256,base_weight_manifest_sha256)):
        return {"state":"HOLD_PROVENANCE_HASH"}
    if type(use_rslora) is not bool:
        return {"state":"HOLD_RSLORA_MODE"}
    if type(rank) is not int or rank not in ALLOWED_RANKS or type(alpha) is not int or not 1<=alpha<=512:
        return {"state":"HOLD_LORA_RANK"}
    if (not isinstance(precision,str) or precision not in SUPPORTED_PRECISIONS
            or type(learning_rate) not in (int,float) or not math.isfinite(learning_rate)
            or not 0.0<learning_rate<0.001):
        return {"state":"HOLD_PRECISION_OR_LR"}
    if type(max_steps) is not int or not 1<=max_steps<=100000:
        return {"state":"HOLD_STEP_BUDGET"}
    if not isinstance(target_modules,list) or not target_modules or any(
       not isinstance(t,str) or t not in KNOWN_MODULES for t in target_modules
    ):
        return {"state":"HOLD_TARGET_MODULES"}
    if expert_target_parameters is not None:
        if (not isinstance(expert_target_parameters,list)
             or len(expert_target_parameters)>MAX_EXPERT_PATTERNS
             or any(not isinstance(x,str) or not re.fullmatch(r"[A-Za-z0-9._*]{3,200}",x)
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
      "base_revision":base_revision,
      "base_architecture":base_architecture,
      "base_config_sha256":base_config_sha256,
      "tokenizer_sha256":tokenizer_sha256,
      "base_weight_manifest_sha256":base_weight_manifest_sha256,
      "training_mode":"RSLORA_FP16" if use_rslora else "LORA_FP16",
      "hf_identity_native_verified":False,
      "native_writer_lease_verified":False,
      "original_optimizer_resume_allowed":False,
      "resume_checkpoint_sha256":checkpoint_sha256,
      "corpus":corpus_dir,
      "training_data_sha256":corpus["train_sha256"],
      "holdout_data_sha256":corpus["holdout_sha256"],
      "dev_data_sha256":corpus.get("dev_sha256"),
      "owner_corpus_identity_native_verified":False,
      "corpus_split_evidence":corpus["split_evidence"],
      "precision":precision,
      "peft":{
        "type":"LORA", "target_modules":sorted(set(target_modules)),
        "rank":rank,"alpha":alpha,"dropout":0.05,
        "use_rslora":use_rslora,
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
        "owner_native_original_HF_base_revision_config_tokenizer_shards_sha_readback",
        "signed_owner_GPU1_lease_STOP_S03_full_optimizer_offsite_restore",
        "one_optimizer_namespace_per_training_mode",
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
      "optimizer_steps_verified":0,
      "live_model_promoted":False
    }
    return payload
