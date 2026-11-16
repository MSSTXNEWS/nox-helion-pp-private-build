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
import unicodedata
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
    normalized=unicodedata.normalize("NFKC",text.strip().casefold())
    normalized="".join(ch for ch in normalized if unicodedata.category(ch)!="Cf")
    normalized=re.sub(r"\s+"," ",normalized)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def reviewed_payload_sha256(record: dict) -> str:
    """Exact sample attestation supplied independently by the existing owner callback.

    Bind the original task/job, independently reviewed quality evidence, rights,
    teacher identity and training text to one owner-pinned source receipt.
    This changes the digest contract: old owner approval hashes must be reissued
    by the authenticated owner after review, never guessed from teacher output.
    """
    fields=("task_id","prompt","completion","teacher_model","model_card_url",
            "source_kind","license","quality_score","review_evidence")
    payload={key:record[key] for key in fields}
    encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True,
                       separators=(",",":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    if (not isinstance(record["source_kind"],str)
            or record["source_kind"] not in ALLOWED_SOURCE_KINDS):
        return False,"HOSTED_TRAINING_PERMISSION_NOT_VERIFIED"
    if (not isinstance(record["license"],str)
            or record["license"].lower() not in SAFE_LICENSES):
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



def _split_by_owner_source_sha(source_group_sha256: str,
                               *, dev_rate: int=10, holdout_rate: int=15) -> str:
    """Deterministic *source-family* partition, not a user-provided cluster."""
    bucket=int(hashlib.sha256(source_group_sha256.encode("ascii")).hexdigest()[:8],16)%100
    return ("holdout" if bucket < holdout_rate
            else "dev" if bucket < holdout_rate + dev_rate else "train")


def build_owner_pinned_threeway_sft(records: list[dict], policy: dict,
                                    *, dev_rate: int=10, holdout_rate: int=15) -> dict:
    """Prepare a candidate; NEVER enqueue training or export without native 2D.

    The source-group, exact reviewed-payload, privacy source-pair bindings and
    privacy allowlist must be supplied by authenticated owner-native callbacks,
    NOT records, teachers or downloaded sites.
    This function checks their shape but does not verify a cryptographic signature.
    No fixture can establish actual OneHost auth or a live Hunter/S03 receipt.
    """
    def hold(reason, **details):
        return {"status":reason,"accepted":[],"train":0,"dev":0,"holdout":0,
                "optimizer_updates_verified":0,"native_queue_modified":False,**details}
    if (not isinstance(policy,dict)
            or policy.get("signed_by_native_owner") is not True
            or policy.get("allow_source_disjoint_corpus") is not True
            or policy.get("stop_requested") is not False):
        return hold("HOLD_NATIVE_OWNER_POLICY_OR_STOP")
    if (not isinstance(records,list) or not 3 <= len(records) <= MAX_EXAMPLES):
        return hold("HOLD_BATCH_SIZE")
    if (type(dev_rate) is not int or type(holdout_rate) is not int
            or not 5 <= dev_rate <= 25 or not 5 <= holdout_rate <= 30
            or dev_rate + holdout_rate >= 50):
        return hold("HOLD_THREEWAY_SPLIT_POLICY")
    group_map=policy.get("source_group_sha_by_receipt")
    privacy_shas=policy.get("accepted_privacy_receipt_shas")
    sha_pattern=re.compile(r"^[a-f0-9]{64}$")
    if (not isinstance(group_map,dict) or not 1 <= len(group_map) <= MAX_EXAMPLES
            or any(not isinstance(k,str) or not sha_pattern.fullmatch(k)
                   or not isinstance(v,str) or not sha_pattern.fullmatch(v)
                   for k,v in group_map.items())):
        return hold("HOLD_OWNER_SOURCE_GROUP_RECEIPTS")
    if (not isinstance(privacy_shas,list) or not 1 <= len(privacy_shas) <= MAX_EXAMPLES
            or any(not isinstance(x,str) or not sha_pattern.fullmatch(x)
                   for x in privacy_shas)):
        return hold("HOLD_OWNER_PRIVACY_RECEIPTS")
    # An approved source SHA by itself cannot certify arbitrary substituted
    # answers, and an unrelated approved privacy receipt cannot clear this row.
    # Both mappings are owner-provided and bound to the very same source receipt.
    reviewed=policy.get("approved_content_sha_by_source_receipt")
    privacy_pairs=policy.get("privacy_receipt_sha_by_source_receipt")
    if (not isinstance(reviewed,dict) or not isinstance(privacy_pairs,dict)
            or set(reviewed)!=set(group_map) or set(privacy_pairs)!=set(group_map)
            or any(not isinstance(value,str) or not sha_pattern.fullmatch(value)
                   for value in reviewed.values())
            or any(not isinstance(value,str) or not sha_pattern.fullmatch(value)
                   for value in privacy_pairs.values())):
        return hold("HOLD_OWNER_SOURCE_CONTENT_PRIVACY_BINDINGS")
    privacy_allow=set(privacy_shas)
    seen_prompts,seen_completions=set(),set()
    accepted,rejected=[],{}
    for record in records:
        valid,code=quality_gate(record)
        if not valid:
            rejected[code]=rejected.get(code,0)+1
            continue
        source_sha=record.get("source_receipt_sha256")
        privacy_sha=record.get("privacy_receipt_sha256")
        if (not isinstance(source_sha,str) or source_sha not in group_map
                or record.get("source_provenance_verified") is not True):
            rejected["UNPINNED_SOURCE_RECEIPT"]=rejected.get("UNPINNED_SOURCE_RECEIPT",0)+1
            continue
        if reviewed_payload_sha256(record)!=reviewed[source_sha]:
            rejected["UNPINNED_REVIEWED_PAYLOAD"]=rejected.get("UNPINNED_REVIEWED_PAYLOAD",0)+1
            continue
        if (not isinstance(privacy_sha,str) or privacy_sha not in privacy_allow
                or privacy_sha!=privacy_pairs[source_sha]
                or record.get("pii_review") != "PASS"):
            rejected["UNPINNED_PRIVACY_RECEIPT"]=rejected.get("UNPINNED_PRIVACY_RECEIPT",0)+1
            continue
        prompt_sha,answer_sha=canonical_hash(record["prompt"]),canonical_hash(record["completion"])
        # Conservative leak prevention: overlapping prompts OR answers are
        # excluded even when a row claims a distinct family/cluster.
        if prompt_sha in seen_prompts or answer_sha in seen_completions:
            rejected["CROSS_SOURCE_DUPLICATE"]=rejected.get("CROSS_SOURCE_DUPLICATE",0)+1
            continue
        seen_prompts.add(prompt_sha);seen_completions.add(answer_sha)
        owner_group=group_map[source_sha]
        accepted.append({
            "split":_split_by_owner_source_sha(owner_group,
                                              dev_rate=dev_rate,holdout_rate=holdout_rate),
            "source_group_sha256":owner_group,
            "source_receipt_sha256":source_sha,
            "privacy_receipt_sha256":privacy_sha,
            "prompt_sha256":prompt_sha,"answer_sha256":answer_sha,
            "task_id":record["task_id"],"teacher_model":record["teacher_model"],
            "license":record["license"],
            "sft":{"prompt":[{"role":"user","content":record["prompt"]}],
                   "completion":[{"role":"assistant","content":record["completion"]}]},
        })
    counts={kind:sum(r["split"]==kind for r in accepted)
            for kind in ("train","dev","holdout")}
    if not all(counts.values()):
        return hold("HOLD_THREEWAY_SOURCE_COVERAGE",
                    rejected=rejected,verified_candidate_counts=counts)
    if any({r["split"] for r in accepted if r["source_group_sha256"]==g}!={s}
           for g,s in {(r["source_group_sha256"],r["split"]) for r in accepted}):
        return hold("HOLD_SOURCE_SPLIT_COLLISION")
    return {"status":"OWNER_PINNED_THREEWAY_CANDIDATES_NOT_TRAINED",
            "accepted":accepted,"rejected":rejected,**counts,
            "splitting":"OWNER_RECEIPT_SOURCE_GROUP_DISJOINT_SHA256",
            "optimizer_updates_verified":0,"native_queue_modified":False,
            "source_data_is_not_new_deepseek_distillation":True}


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


def export_owner_pinned_threeway(local_output_root: str, corpus: dict) -> dict:
    """Immutable source-only handoff from owner-pinned V28 candidates to 2D.

    No queue/S03/model writes. Native caller must independently verify provenance
    and admission. This is deliberately separate from the legacy two-way export.
    """
    def hold(reason):
        return {"status":reason,"native_queue_modified":False,
                "optimizer_updates_verified":0}

    if (not isinstance(corpus,dict)
            or corpus.get("status")!="OWNER_PINNED_THREEWAY_CANDIDATES_NOT_TRAINED"
            or corpus.get("native_queue_modified") is not False
            or corpus.get("optimizer_updates_verified") != 0):
        return hold("HOLD_NOT_OWNER_PINNED_CANDIDATES")
    rows=corpus.get("accepted")
    splits=("train","dev","holdout")
    if (not isinstance(rows,list) or not 3<=len(rows)<=MAX_EXAMPLES
            or any(type(corpus.get(k)) is not int or corpus[k]<1 for k in splits)
            or sum(corpus[k] for k in splits)!=len(rows)):
        return hold("HOLD_THREEWAY_ROW_COUNTS")

    grouped={k:[] for k in splits}
    groups={k:set() for k in splits}
    seen_prompts,seen_answers=set(),set()
    sha_pattern=re.compile(r"^[a-f0-9]{64}$")
    proof=[]
    for row in rows:
        if not isinstance(row,dict):
            return hold("HOLD_MALFORMED_CANDIDATE_ROW")
        try:
            part=row["split"]
            if part not in grouped:
                return hold("HOLD_UNKNOWN_SPLIT")
            for field in ("source_group_sha256","source_receipt_sha256",
                          "privacy_receipt_sha256","prompt_sha256","answer_sha256"):
                if (not isinstance(row[field],str)
                        or not sha_pattern.fullmatch(row[field])):
                    return hold("HOLD_MALFORMED_PROVENANCE")
            if (not isinstance(row["task_id"],str) or not row["task_id"].strip()
                    or not isinstance(row["teacher_model"],str) or not row["teacher_model"].strip()
                    or row["license"] not in SAFE_LICENSES):
                return hold("HOLD_LICENSE_OR_TASK_PROVENANCE")
            sft=row["sft"]
            if not isinstance(sft,dict) or set(sft)!={"prompt","completion"}:
                return hold("HOLD_INVALID_SFT_SHAPE")
            values=[]
            for field,role in (("prompt","user"),("completion","assistant")):
                messages=sft[field]
                if (not isinstance(messages,list) or len(messages)!=1
                        or not isinstance(messages[0],dict)
                        or set(messages[0])!={"role","content"}
                        or messages[0]["role"]!=role
                        or not isinstance(messages[0]["content"],str)
                        or not messages[0]["content"].strip()):
                    return hold("HOLD_INVALID_SFT_SHAPE")
                values.append(messages[0]["content"])
            prompt,answer=values
            if any(unicodedata.category(ch)=="Cf" for ch in prompt+answer):
                return hold("HOLD_UNICODE_FORMAT_CONTROL")
            prompt_sha,answer_sha=canonical_hash(prompt),canonical_hash(answer)
            if (prompt_sha!=row["prompt_sha256"]
                    or answer_sha!=row["answer_sha256"]):
                return hold("HOLD_ROW_CONTENT_FINGERPRINT")
            if prompt_sha in seen_prompts or answer_sha in seen_answers:
                return hold("HOLD_CROSS_SPLIT_DUPLICATE")
            seen_prompts.add(prompt_sha);seen_answers.add(answer_sha)
            groups[part].add(row["source_group_sha256"])
            grouped[part].append(row)
            proof.append({"part":part,"task_id":row["task_id"],
                          "group":row["source_group_sha256"],
                          "source":row["source_receipt_sha256"],
                          "privacy":row["privacy_receipt_sha256"],
                          "prompt_sha256":prompt_sha,"answer_sha256":answer_sha})
        except (KeyError,TypeError,ValueError,AttributeError):
            return hold("HOLD_MALFORMED_CANDIDATE_ROW")
    if any(len(grouped[k])!=corpus[k] for k in splits):
        return hold("HOLD_THREEWAY_ROW_COUNTS")
    if any(groups[a]&groups[b] for a,b in
           (("train","dev"),("train","holdout"),("dev","holdout"))):
        return hold("HOLD_SOURCE_GROUP_OVERLAP")

    try:
        root=Path(local_output_root)
        if not root.is_absolute() or root.is_symlink():
            return hold("HOLD_OUTPUT_PATH")
        resolved=root.resolve(strict=False)
        if (not any(a==resolved or a in resolved.parents for a in LOCAL_ROOTS)
                or "/workspace" in str(resolved)):
            return hold("HOLD_OUTPUT_NOT_LOCAL")
        resolved.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(resolved,0o700)
        identity=json.dumps(sorted(proof,key=lambda x:(x["part"],x["source"],x["task_id"])),
                            ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
        key=hashlib.sha256(identity).hexdigest()[:20]
        dest=resolved/("owner-threeway-"+key)
        if dest.exists():
            return hold("HOLD_ALREADY_EXPORTED")
        temp=Path(tempfile.mkdtemp(prefix=".nox_threeway_",dir=resolved))
        try:
            checksums={}
            for part in splits:
                target=temp/(part+".jsonl")
                with target.open("x",encoding="utf-8") as out:
                    for row in sorted(grouped[part],
                                      key=lambda x:(x["source_receipt_sha256"],x["task_id"])):
                        out.write(json.dumps(row["sft"],ensure_ascii=False,sort_keys=True,
                                             allow_nan=False)+"\n")
                    out.flush();os.fsync(out.fileno())
                os.chmod(target,0o600)
                checksums[part+".jsonl_sha256"]=hashlib.sha256(target.read_bytes()).hexdigest()
            manifest={
                "schema":"nox-teacher-owner-threeway-sft-v2",
                "status":"REVIEWED_NOT_OPTIMIZER_TRAINED",
                "counts":{k:len(grouped[k]) for k in splits},
                "splitting":"OWNER_RECEIPT_SOURCE_GROUP_DISJOINT_SHA256",
                "source_group_shas_by_split":{k:sorted(groups[k]) for k in splits},
                "source_receipts":sorted(proof,key=lambda x:(x["part"],x["source"],x["task_id"])),
                "response_only_loss_required":True,
                "owner_corpus_identity_native_verified":False,
                "native_queue_modified":False,
                "optimizer_updates_verified":0,
                "teacher_weights_copied":False,
                "new_deepseek_distillation_claimed":False,
                **checksums,
            }
            mf=temp/"manifest.json"
            with mf.open("x",encoding="utf-8") as out:
                json.dump(manifest,out,ensure_ascii=False,sort_keys=True,
                          allow_nan=False,indent=2)
                out.write("\n");out.flush();os.fsync(out.fileno())
            os.chmod(mf,0o600)
            if dest.exists():
                return hold("HOLD_ALREADY_EXPORTED")
            os.rename(temp,dest)
            return {"status":"THREEWAY_SOURCE_CORPUS_EXPORTED_NOT_TRAINED",
                    "path":str(dest),"counts":manifest["counts"],
                    "manifest_sha256":hashlib.sha256((dest/"manifest.json").read_bytes()).hexdigest(),
                    "native_queue_modified":False,"optimizer_updates_verified":0}
        except (OSError,TypeError,ValueError):
            # Preserve partially written TEMP for explicit inspection; never delete data blindly.
            return hold("HOLD_EXPORT_FAILED_TEMP_PRESERVED")
    except (OSError,TypeError,ValueError):
        return hold("HOLD_OUTPUT_PATH")
