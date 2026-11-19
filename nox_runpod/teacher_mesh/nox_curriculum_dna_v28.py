#!/usr/bin/env python3
"""NOX V28 Curriculum DNA + Proof of Growth.

Converts independent benchmark failures into source-only learning proposals.
Does NOT train, create S03 tables, promote checkpoints, or use a model as its
own unverified judge. One active NOX model, verified source-separated holdouts.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from math import sqrt
import math,re

SCHEMA="nox-curriculum-dna-v28"
SHA=re.compile(r"^[a-f0-9]{64}$")
DOMAINS=("instruction","reasoning","coding","ru_knowledge","es_knowledge",
         "tool_use","long_memory","emotion_tone","self_history","computer_use")
METHODS={
 "instruction":"RESPONSE_ONLY_SFT_THEN_VERIFIED_DPO",
 "reasoning":"VERIFIED_SFT_OR_GKD_IF_TEACHER_APPROVED",
 "coding":"UNIT_TEST_CONFIRMED_SFT",
 "ru_knowledge":"GROUND_TO_SOURCE_AND_RAG_BEFORE_WEIGHT_TRAINING",
 "es_knowledge":"GROUND_TO_SOURCE_AND_RAG_BEFORE_WEIGHT_TRAINING",
 "tool_use":"TOOL_AST_VALIDATED_SFT",
 "long_memory":"FIX_S03_RETRIEVAL_FIRST_NO_WEIGHT_JOB",
 "emotion_tone":"HUMAN_REVIEWED_EMPATHY_PAIRS_NO_CLAIM_OF_FEELINGS",
 "self_history":"VERIFY_GENESIS_M7_FIRST_NO_WEIGHT_JOB",
 "computer_use":"SANDBOX_ENVIRONMENT_TRAJECTORIES_AFTER_APPROVAL",
}
NO_WEIGHT_FIRST=frozenset(("long_memory","self_history"))
def _timestamp(x):
    if not isinstance(x,str):return None
    try:
        t=datetime.fromisoformat(x.replace("Z","+00:00"))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except (TypeError,ValueError,OverflowError):
        return None

def _valid_record(r,student_sha,now):
    if not isinstance(r,dict) or r.get("domain") not in DOMAINS:return False
    if not isinstance(r.get("model_sha256"),str) or r["model_sha256"]!=student_sha:return False
    if any(not (isinstance(r.get(key),str) and SHA.fullmatch(r[key]))
           for key in ("harness_sha256","dataset_split_sha256","source_receipt_sha256")):
        return False
    if (r.get("independent_replay") is not True
            or r.get("heldout") is not True
            or r.get("source_separated") is not True
            or r.get("contamination_review")!="PASS"):
        return False
    if (type(r.get("correct")) is not int or type(r.get("total")) is not int
            or not 0<=r["correct"]<=r["total"]<=100000 or r["total"]<50):
        return False
    t=_timestamp(r.get("observed_at_utc"))
    return bool(t and t<=now+timedelta(seconds=30) and now-t<timedelta(days=30))

def build_curriculum(records:list[dict], policy:dict, *, now:datetime|None=None)->dict:
    now=now or datetime.now(timezone.utc)
    if (not isinstance(policy,dict) or policy.get("signed_by_native_owner") is not True
            or not isinstance(policy.get("active_student_sha256"),str)
            or not SHA.fullmatch(policy["active_student_sha256"])):
        return {"schema":SCHEMA,"state":"HOLD_NATIVE_OWNER_AND_STUDENT_SHA","proposals":[]}
    student_sha=policy["active_student_sha256"]
    if not isinstance(records,list) or len(records)>400:
        return {"schema":SCHEMA,"state":"HOLD_BENCHMARK_INPUT","proposals":[]}
    if policy.get("stop_requested") is not False:
        return {"schema":SCHEMA,"state":"HOLD_NATIVE_STOP","proposals":[]}
    total_budget=policy.get("max_proposals",3)
    if type(total_budget) is not int or not 1<=total_budget<=5:
        return {"schema":SCHEMA,"state":"HOLD_CURRICULUM_BUDGET","proposals":[]}
    verified=[r for r in records if _valid_record(r,student_sha,now)]
    latest_by_domain={}
    for r in verified:
        domain=r["domain"];t=_timestamp(r["observed_at_utc"])
        if domain not in latest_by_domain or t>_timestamp(latest_by_domain[domain]["observed_at_utc"]):
            latest_by_domain[domain]=r
    proposals=[]
    for domain,r in latest_by_domain.items():
        score=r["correct"]/r["total"]
        # Deficiency estimate with sample caution; no novelty without evidence.
        uncertainty=min(0.2,1/sqrt(r["total"]))
        importance=float(policy.get("domain_importance",{}).get(domain,1.0))
        if not math.isfinite(importance) or not 0<=importance<=3:continue
        severity=round((1-score)*(1-uncertainty)*importance,6)
        if severity<=0.05:continue
        strategy=METHODS[domain]
        proposals.append({
            "domain":domain,"method_template":strategy,"student_sha256":student_sha,
            "harness_sha256":r["harness_sha256"],
            "heldout_split_sha256":r["dataset_split_sha256"],
            "sample_count":r["total"],"measured_accuracy":round(score,6),
            "priority":severity,
            "stage":"MEMORY_OR_EVIDENCE_ENGINEERING_FIRST" if domain in NO_WEIGHT_FIRST
                else "NEEDS_APPROVED_TRAINING_CORPUS",
            "requires_new_training_source_not_benchmark_answers":True,
            "catastrophic_forgetting_regression_required":True,
            "optimizer_steps_verified":0,
        })
    proposals.sort(key=lambda x:(-x["priority"],x["domain"]))
    return {
        "schema":SCHEMA,
        "state":"CURRICULUM_PROPOSED_NOT_TRAINED" if proposals else "HOLD_NO_INDEPENDENT_BENCHMARK_GAPS",
        "proposals":proposals[:total_budget],
        "evaluation_records_accepted":len(verified),
        "gpu_job_started":False,
        "student_sha256":student_sha,
        "must_preserve_existing_s03":True,
    }

def promotion_gate(*,baseline:list[dict],candidate:list[dict],policy:dict,now:datetime|None=None)->dict:
    """Never automatically deploy: returns 'ready for owner review' at best."""
    now=now or datetime.now(timezone.utc)
    if not isinstance(policy,dict) or policy.get("signed_by_native_owner") is not True:
        return {"schema":SCHEMA,"state":"HOLD_NATIVE_OWNER_POLICY"}
    base_sha=policy.get("baseline_sha256");candidate_sha=policy.get("candidate_sha256")
    if not all(isinstance(v,str) and SHA.fullmatch(v) for v in (base_sha,candidate_sha)):
        return {"schema":SCHEMA,"state":"HOLD_MODEL_SHA"}
    if base_sha==candidate_sha:return {"schema":SCHEMA,"state":"HOLD_IDENTICAL_WEIGHTS"}
    if not isinstance(baseline,list) or not isinstance(candidate,list):
        return {"schema":SCHEMA,"state":"HOLD_EVAL_DATA"}
    required=policy.get("required_domains")
    if not isinstance(required,list) or not required or not all(x in DOMAINS for x in required):
        return {"schema":SCHEMA,"state":"HOLD_REQUIRED_DOMAINS"}
    def by_domain(seq,sha):
        out={}
        for r in seq:
            if _valid_record(r,sha,now):out[r["domain"]]=r
        return out
    b=by_domain(baseline,base_sha);c=by_domain(candidate,candidate_sha)
    if any(x not in b or x not in c for x in required):
        return {"schema":SCHEMA,"state":"HOLD_MISSING_SAME_DOMAIN_RESULTS"}
    regressions=[];improvements=[]
    for domain in required:
        left,right=b[domain],c[domain]
        if (left["harness_sha256"]!=right["harness_sha256"] or
            left["dataset_split_sha256"]!=right["dataset_split_sha256"] or
            left["total"]!=right["total"]):
            return {"schema":SCHEMA,"state":"HOLD_DIFFERENT_HARNESS_SPLIT_OR_SAMPLE_COUNT"}
        delta=(right["correct"]-left["correct"])/left["total"]
        if delta < -0.01:regressions.append({"domain":domain,"delta":round(delta,5)})
        elif delta>0.01:improvements.append({"domain":domain,"delta":round(delta,5)})
    if regressions:return {"schema":SCHEMA,"state":"REJECT_MEASURED_REGRESSION",
                           "regressions":regressions}
    if not improvements:return {"schema":SCHEMA,"state":"HOLD_NO_MEASURED_GAIN"}
    if policy.get("checkpoint_reloaded_and_sha_verified") is not True:
        return {"schema":SCHEMA,"state":"HOLD_CHECKPOINT_RELOAD_NOT_PROVEN"}
    if policy.get("real_optimizer_receipt_verified") is not True:
        return {"schema":SCHEMA,"state":"HOLD_OPTIMIZER_NOT_VERIFIED"}
    return {"schema":SCHEMA,"state":"READY_FOR_OWNER_REVIEW_NOT_PROMOTED",
            "measured_improvements":improvements,"production_modified":False,
            "rollback_required":True}
