#!/usr/bin/env python3
"""NOX Future V28 Neural Matchmaker.

Pure deterministic candidate selection for independent teacher *evidence*.
It NEVER changes the sole user-facing NOX model, downloads weights, executes
remote tools, sends private prompts, or claims a new model is better absent a
verified same-harness capability comparison. Use within EXISTING OneHost.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any
import math
import re

SCHEMA="nox-future-matchmaker-v28"
SHA=re.compile(r"^[a-f0-9]{64}$")
REV=re.compile(r"^[a-f0-9]{40}$")
TASKS=frozenset(("reasoning","code","math","memory","vision","tool_use","language_ru","language_es","emotion_tone","research"))
ROUTES={
    "reasoning":"REASONING","code":"REASONING","math":"REASONING",
    "memory":"S03","vision":"VISION","tool_use":"TOOLS",
    "language_ru":"NOX","language_es":"NOX","emotion_tone":"SOUL",
    "research":"TOOLS",
}

def _finite(x):
    return type(x) in (int,float) and math.isfinite(x)

def _valid_verified_score(entry:Any):
    if not isinstance(entry,dict):return False
    if not (entry.get("verified") is True and entry.get("same_harness") is True
            and entry.get("heldout") is True and entry.get("contamination_review")=="PASS"):
        return False
    if not (isinstance(entry.get("harness_sha256"),str) and SHA.fullmatch(entry["harness_sha256"])):
        return False
    total=entry.get("total")
    if type(total) is not int or not 30<=total<=100000:return False
    if not (_finite(entry.get("student_score")) and _finite(entry.get("teacher_score"))):
        return False
    if not (0<=entry["student_score"]<=1 and 0<=entry["teacher_score"]<=1):
        return False
    return True

def match_advisors(task:dict, registry:list[dict], policy:dict, *, now:datetime|None=None)->dict:
    """Rank 0..3 pinned frozen advisors. Output is a proposal, not a tool call."""
    now=now or datetime.now(timezone.utc)
    if not isinstance(task,dict) or task.get("kind") not in TASKS:
        return {"schema":SCHEMA,"status":"HOLD_TASK","advisors":[]}
    domain=task["kind"]
    scope=task.get("scope")
    if not isinstance(scope,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",scope):
        return {"schema":SCHEMA,"status":"HOLD_SCOPE","advisors":[]}
    if not isinstance(policy,dict) or policy.get("signed_by_native_owner") is not True or policy.get("scope")!=scope:
        return {"schema":SCHEMA,"status":"HOLD_NATIVE_OWNER_POLICY","advisors":[]}
    if policy.get("allow_teacher_comparison") is not True:
        return {"schema":SCHEMA,"status":"NO_COMPARE_BY_POLICY","advisors":[]}
    student_sha=task.get("active_student_sha256")
    if not isinstance(student_sha,str) or not SHA.fullmatch(student_sha):
        return {"schema":SCHEMA,"status":"HOLD_ACTIVE_STUDENT_SHA","advisors":[]}
    if not isinstance(registry,list) or len(registry)>100:
        return {"schema":SCHEMA,"status":"HOLD_REGISTRY","advisors":[]}
    max_count=policy.get("max_advisors",1)
    if type(max_count) is not int or not 1<=max_count<=3:
        return {"schema":SCHEMA,"status":"HOLD_ADVISOR_BUDGET","advisors":[]}
    if task.get("chat_busy") is True or task.get("stop_requested") is not False:
        return {"schema":SCHEMA,"status":"DEFER_CHAT_OR_STOP","advisors":[]}
    # NOX is the only agent allowed to generate the immediate user-visible answer.
    if task.get("user_data_private") is True and policy.get("allow_private_local_vm_teacher") is not True:
        return {"schema":SCHEMA,"status":"HOLD_PRIVATE_COMPARISON","advisors":[]}
    allowed=policy.get("allowed_model_ids")
    if not isinstance(allowed,list):return {"schema":SCHEMA,"status":"HOLD_ALLOWLIST","advisors":[]}
    budget=policy.get("available_teacher_vram_mb",0)
    if type(budget) is not int or budget<0:
        return {"schema":SCHEMA,"status":"HOLD_GPU_BUDGET","advisors":[]}
    result=[]
    for m in registry:
        if not isinstance(m,dict):continue
        if m.get("role")!="FROZEN_TEACHER_ONLY" or m.get("id") not in allowed:continue
        if (m.get("local_isolated_vm") is not True or m.get("owner_approved") is not True
                or m.get("license_verified") is not True or m.get("weights_sha256")==task.get("active_student_sha256")):
            continue
        if not (isinstance(m.get("revision"),str) and REV.fullmatch(m["revision"]) and
                isinstance(m.get("weights_sha256"),str) and SHA.fullmatch(m["weights_sha256"])):
            continue
        vram=m.get("required_vram_mb")
        if type(vram) is not int or not 1<=vram<=budget:continue
        profiles=m.get("verified_benchmarks")
        if not isinstance(profiles,dict) or not _valid_verified_score(profiles.get(domain)):continue
        ev=profiles[domain]
        if ev.get("student_model_sha256")!=student_sha:
            continue
        allowed_harnesses=policy.get("accepted_harness_shas",[])
        if (not isinstance(allowed_harnesses,list) or
                ev["harness_sha256"] not in allowed_harnesses):
            continue
        improvement=ev["teacher_score"]-ev["student_score"]
        # Do not pay additional latency for same-family/no-measured-benefit teachers.
        if improvement<=0.02:continue
        delay=m.get("p95_ms")
        if type(delay) is not int or not 0<delay<=policy.get("max_adviser_p95_ms",10000):
            continue
        family=m.get("family","")
        if not isinstance(family,str) or not 1<=len(family)<=60:continue
        score=round(0.8*improvement + 0.2*min(ev["total"]/500,1) - 0.000005*delay,6)
        result.append({
            "id":m["id"],"family":family,"revision":m["revision"],
            "weights_sha256":m["weights_sha256"],"evidence_harness_sha256":ev["harness_sha256"],
            "measured_domain_gain":round(improvement,6),"bench_total":ev["total"],
            "estimated_p95_ms_from_registry":delay,
            "selection_score":score,
            "teacher_response_can_control_NOX":False,
        })
    # Prefer independent families when scores are near; count is bounded.
    result.sort(key=lambda x:(-x["selection_score"],x["id"]))
    selected=[];seen_families=set()
    for item in result:
        if item["family"] in seen_families:continue
        selected.append(item);seen_families.add(item["family"])
        if len(selected)>=max_count:break
    return {
        "schema":SCHEMA,
        "status":"ADVISOR_PROPOSAL_NOT_EXECUTED" if selected else "NO_PROVEN_ADVISOR_GAIN",
        "user_visible_model":"CURRENT_NOX_STUDENT_ONLY",
        "task_kind":domain,
        "skill_lane":ROUTES[domain],
        "advisors":selected,
        "separate_user_facing_personas":0,
        "prompt_sent":False,
        "weight_updates":0,
        "requires_existing_onehost_admission":True,
    }
