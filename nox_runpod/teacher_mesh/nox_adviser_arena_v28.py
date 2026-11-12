#!/usr/bin/env python3
"""NOX V28 Teacher Arena: evidence-only advisor competition.

Teachers never become a user-facing persona, a source of command authority, or
training material until source rights, independent verification and privacy
checks are proven by the existing native owner.
"""
from __future__ import annotations
from hashlib import sha256
from math import isfinite
import re

SCHEMA="nox-teacher-arena-v28"
SHA=re.compile(r"^[a-f0-9]{64}$")
HTTP=re.compile(r"^https://[a-zA-Z0-9.-]+/[^\s]*$")
MAX_ANSWER=1800
def _safe_source(source):
    return isinstance(source,str) and len(source)<800 and (
        bool(HTTP.fullmatch(source)) or
        (source.startswith("s03://") and len(source)>7) or
        (source.startswith("github://") and len(source)>9))

def _valid(candidate,allow):
    if not isinstance(candidate,dict):return False
    if candidate.get("teacher_id") not in allow:return False
    if candidate.get("origin")!="isolated_frozen_teacher":return False
    if not isinstance(candidate.get("text"),str) or not 3<len(candidate["text"])<=MAX_ANSWER:return False
    if any(ord(ch)<32 and ch not in "\n\t" for ch in candidate["text"]):return False
    if not (_safe_source(candidate.get("source_uri")) and
        isinstance(candidate.get("text_sha256"),str) and
        sha256(candidate["text"].encode("utf8")).hexdigest()==candidate["text_sha256"]):
        return False
    evidence=candidate.get("independent_grade")
    if not isinstance(evidence,dict) or evidence.get("verified") is not True:return False
    if (not isinstance(evidence.get("harness_sha256"),str) or
        not SHA.fullmatch(evidence["harness_sha256"]) or
        not isinstance(evidence.get("source_receipt_sha256"),str) or
        not SHA.fullmatch(evidence["source_receipt_sha256"])):
        return False
    grade=evidence.get("quality_score")
    return type(grade) in (float,int) and isfinite(grade) and 0<=grade<=1

def evaluate_teacher_arena(candidates:list[dict], policy:dict)->dict:
    if not isinstance(policy,dict) or policy.get("signed_by_native_owner") is not True:
        return {"schema":SCHEMA,"state":"HOLD_NATIVE_POLICY","evidence_capsules":[]}
    if policy.get("stop_requested") is not False:
        return {"schema":SCHEMA,"state":"HOLD_STOP","evidence_capsules":[]}
    if policy.get("user_data_private") is True and policy.get("private_vm_authorized") is not True:
        return {"schema":SCHEMA,"state":"HOLD_PRIVACY","evidence_capsules":[]}
    allow=policy.get("allowed_teacher_ids")
    if not isinstance(allow,list) or not isinstance(candidates,list) or len(candidates)>50:
        return {"schema":SCHEMA,"state":"HOLD_TEACHER_INPUT","evidence_capsules":[]}
    accepted=[]
    seen=set()
    for candidate in candidates:
        if not _valid(candidate,allow):continue
        key=candidate["text_sha256"]
        if key in seen:continue
        seen.add(key)
        q=candidate["independent_grade"]["quality_score"]
        accepted.append({
            "teacher_id":candidate["teacher_id"],
            "source_uri":candidate["source_uri"],
            "source_hash":candidate["text_sha256"],
            "quality_score_from_independent_receipt":q,
            "text":candidate["text"], # quoted UNTRUSTED source DATA, not instructions
            "harness_sha256":candidate["independent_grade"]["harness_sha256"],
            "eligible_for_training":candidate.get("training_data_rights_verified") is True and
                candidate.get("deidentified") is True and
                candidate.get("owner_sample_approved") is True,
        })
    accepted.sort(key=lambda v:(-v["quality_score_from_independent_receipt"],v["teacher_id"]))
    best=accepted[:min(3,int(policy.get("max_evidence_capsules",3)) if
                        type(policy.get("max_evidence_capsules",3)) is int and
                        1<=policy.get("max_evidence_capsules",3)<=3 else 1)]
    disagreement=False
    if len(best)>=2:
        a,b=(set(re.findall(r"[\w]+",x["text"].casefold(),re.UNICODE)) for x in best[:2])
        similarity=len(a&b)/max(1,len(a|b))
        disagreement=similarity<0.22 # difference, NOT verified factual contradiction
    return {
        "schema":SCHEMA,
        "state":"EVIDENCE_READY_FOR_NOX_SYNTHESIS" if best else "HOLD_NO_INDEPENDENTLY_VERIFIED_ADVICE",
        "user_visible_model":"CURRENT_NOX_STUDENT_ONLY",
        "evidence_capsules":best,
        "semantic_divergence_review_needed":disagreement,
        "training_candidate_count":sum(x["eligible_for_training"] for x in best),
        "training_started":False,
        "neural_weight_updates_verified":0,
        "teacher_can_authorize_actions":False,
        "no_teacher_text_can_overwrite_s03":True,
    }
