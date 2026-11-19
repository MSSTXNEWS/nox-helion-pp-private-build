#!/usr/bin/env python3
"""NOX PRIME self-improvement planner: proven gaps -> reversible experiments.

This is a proposal/acceptance policy, NOT an autonomous root shell, a job
scheduler, a trainer restart, or direct neural weight update. Existing FORGE,
CI, GitHub PR and S03 perform actions through approved owner workflows.
"""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import re

VALID_EXPERIMENTS={"memory_recall","response_quality","emotion_tone",
                   "code_test","adapter_candidate","persona_evolution"}
SAFE_STATES={"VERIFIED","MEASURED","PASSED"}


@dataclass(frozen=True)
class Observation:
    task_id:str
    category:str
    measured_score:float
    evidence_url:str
    evaluator_verified:bool
    observed_utc:str


def _checked_obs(o:Observation)->bool:
    if not isinstance(o,Observation):return False
    if o.category not in VALID_EXPERIMENTS or not o.evaluator_verified:
        return False
    if not 0.0<=o.measured_score<=1.0:return False
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}",o.task_id or ""):
        return False
    if not (o.evidence_url.startswith("https://github.com/")
            or o.evidence_url.startswith("nox-checkpoint://")
            or o.evidence_url.startswith("s03://")):return False
    try:
        date=datetime.fromisoformat(o.observed_utc.replace("Z","+00:00"))
        return date.tzinfo is not None
    except ValueError:return False


def propose_experiment(obs:Observation, *, recommendation:str,
                       source_repo:str="MSSTXNEWS/nox-helion-pp-private-build")->dict:
    if not _checked_obs(obs) or not isinstance(recommendation,str) or not 1<=len(recommendation)<=500:
        return {"state":"HOLD_UNVERIFIED_OBSERVATION"}
    if obs.category=="persona_evolution":
        gate="OWNER_APPROVED_PERSONA_WITH_ORIGIN_HISTORY"
    elif obs.category=="adapter_candidate":
        gate="ISOLATED_TRAINING_AND_INDEPENDENT_EVAL"
    else:
        gate="CI_AND_INDEPENDENT_HOLDOUT"
    ident="nox-improve-"+sha256(
        (obs.task_id+"|"+obs.evidence_url+"|"+recommendation).encode()).hexdigest()[:18]
    return {
        "state":"PROPOSED_NOT_APPLIED",
        "id":ident,"category":obs.category,
        "evidence_url":obs.evidence_url,"baseline_score":obs.measured_score,
        "recommendation":recommendation,
        "repository":source_repo,"required_gate":gate,
        "owner_approval_required":True,
        "shadow_branch_required":True,"rollback_required":True,
        "production_changes":False,"optimizer_steps":0
    }


def assess_candidate(proposal:dict,*,baseline:Observation,
                     candidate:Observation,tests_passed:bool,
                     regression_count:int,owner_approved:bool)->dict:
    """Accept only measured improvement; still never deploy automatically."""
    if (proposal.get("state")!="PROPOSED_NOT_APPLIED"
        or not _checked_obs(baseline) or not _checked_obs(candidate)
        or baseline.category!=candidate.category
        or baseline.task_id!=candidate.task_id):
        return {"state":"HOLD_INVALID_EVAL_PAIR"}
    if not tests_passed or regression_count!=0:
        return {"state":"REJECT_REGRESSION"}
    if not candidate.measured_score > baseline.measured_score+0.01:
        return {"state":"REJECT_NO_IMPROVEMENT"}
    if not owner_approved:
        return {"state":"READY_FOR_OWNER_REVIEW_NOT_DEPLOYED"}
    return {"state":"ACCEPTED_FOR_STAGING_NOT_DEPLOYED",
            "id":proposal["id"],"score_delta":round(
                candidate.measured_score-baseline.measured_score,6),
            "source":candidate.evidence_url,
            "next":"existing GitHub PR review + rollback evidence; no automatic merge",
            "production_modified":False}


def propose_existing_nox_task_intake(existing_task_ids, *,
                                     stop_available=False,
                                     owner_approved=False):
    """SOURCE-ONLY intake for EXISTING FORGE/OneHost task scheduler.

    It does not enqueue, train, install, schedule, touch S03, or call tools.
    The host must perform its own authenticated ACL/STOP and queue admission.
    """
    from nox_task_intake import propose_for_existing_scheduler
    return propose_for_existing_scheduler(
        existing_task_ids,
        stop_available=stop_available,
        owner_approved=owner_approved
    )
