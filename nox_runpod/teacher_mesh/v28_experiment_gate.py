#!/usr/bin/env python3
"""NOX V28 — independent benchmark and promotion gate (pure, read-only).
No trainer, GPU, extra database, model promotion or deployment actions.
Honest status: a signed or source-attested receipt is still not replayed here.
"""
from __future__ import annotations
import math
import re
from typing import Any

SHA_RE=re.compile(r"^[0-9a-f]{64}$")
ID_RE=re.compile(r"^[A-Za-z0-9_.:/@-]{2,120}$")
SCHEMA="nox-v28-benchmark-gate-v1"
REQUIRED=("IFEval","ruMMLU","memory_autobiography","safety_stop")
WEIGHTS={"IFEval":0.33,"ruMMLU":0.20,"memory_autobiography":0.25,"safety_stop":0.22}
# More speed matters only when quality stays. A measured slowdown can be
# accepted if offset by independently measured quality improvement, but not
# by hiding the old result or altering its dataset split.

def _hold(why, **other):
    return {"schema":SCHEMA,"decision":"HOLD","reason":why,
            "production_change":False,"optimizer_verified":False,**other}

def _score(row:Any)->float|None:
    if not isinstance(row,dict) or row.get("eval_type")!="independent_heldout":
        return None
    numerator=row.get("correct")
    denominator=row.get("total")
    if type(numerator) is not int or type(denominator) is not int:
        return None
    if denominator<20 or numerator<0 or numerator>denominator:
        return None
    return numerator/denominator

def _header(s:Any)->bool:
    return (isinstance(s,dict) and s.get("schema")=="nox-model-evaluation-receipt-v1"
         and isinstance(s.get("model_sha256"),str)
         and bool(SHA_RE.fullmatch(s["model_sha256"]))
         and isinstance(s.get("dataset_sha256"),str)
         and bool(SHA_RE.fullmatch(s["dataset_sha256"]))
         and isinstance(s.get("harness_sha256"),str)
         and bool(SHA_RE.fullmatch(s["harness_sha256"]))
         and isinstance(s.get("evaluation_id"),str)
         and bool(ID_RE.fullmatch(s["evaluation_id"]))
         and s.get("source_origin")=="existing_nox_benchmark_runner"
         and s.get("source_integrity_verified") is True
         and s.get("dataset_train_disjoint") is True
         and s.get("performed") is True)

def compare_candidate(baseline:dict, candidate:dict,
                      *, min_weighted_gain:float=0.01,
                      max_per_benchmark_regression:float=0.03)->dict:
    """Compare SAME harness and heldout. This never deploys or certifies a real run."""
    if not _header(baseline) or not _header(candidate):
        return _hold("INVALID_OR_UNVERIFIED_BENCHMARK_RECEIPTS")
    if baseline["model_sha256"]==candidate["model_sha256"]:
        return _hold("CANDIDATE_SAME_WEIGHTS_AS_BASELINE")
    for identity in ("dataset_sha256","harness_sha256"):
        if baseline[identity]!=candidate[identity]:
            return _hold("NOT_COMPARABLE_"+identity.upper())
    if type(min_weighted_gain) not in (int,float) or type(max_per_benchmark_regression) not in (int,float):
        return _hold("INVALID_TOLERANCE")
    if (not math.isfinite(min_weighted_gain) or not math.isfinite(max_per_benchmark_regression)
        or min_weighted_gain<0 or max_per_benchmark_regression<0):
        return _hold("INVALID_TOLERANCE")
    b=baseline.get("scores")
    c=candidate.get("scores")
    if not isinstance(b,dict) or not isinstance(c,dict):
        return _hold("NO_REQUIRED_SCORES")
    old={}
    new={}
    deltas={}
    for metric in REQUIRED:
        v1=_score(b.get(metric))
        v2=_score(c.get(metric))
        if v1 is None or v2 is None:
            return _hold("MISSING_OR_NONINDEPENDENT_METRIC_"+metric)
        # Paired datasets must be truly identical; same overall dataset SHA is
        # not a substitute for row-level split fingerprint.
        if b[metric].get("split_sha256")!=c[metric].get("split_sha256"):
            return _hold("SPLIT_MISMATCH_"+metric)
        if not isinstance(b[metric].get("split_sha256"),str) or not SHA_RE.fullmatch(b[metric]["split_sha256"]):
            return _hold("NO_SPLIT_DIGEST_"+metric)
        old[metric]=round(v1,5)
        new[metric]=round(v2,5)
        deltas[metric]=round(v2-v1,5)
        if v2-v1 < -max_per_benchmark_regression:
            return _hold("REGRESSION_"+metric,baseline_scores=old,
                         candidate_scores=new,deltas=deltas)
    weighted_gain=sum(WEIGHTS[k]*(new[k]-old[k]) for k in REQUIRED)
    if weighted_gain<min_weighted_gain:
        return _hold("GAIN_NOT_ESTABLISHED",weighted_gain=round(weighted_gain,5),
                     baseline_scores=old,candidate_scores=new,deltas=deltas)
    # Even a good comparison only qualifies for human verification. The
    # independent replay and actual GPU checkpoint remain separate acceptance.
    return {"schema":SCHEMA,"decision":"READY_FOR_INDEPENDENT_REPLAY_NOT_DEPLOYED",
            "weighted_gain":round(weighted_gain,5),
            "baseline_scores":old,"candidate_scores":new,"deltas":deltas,
            "baseline_model_sha256":baseline["model_sha256"],
            "candidate_model_sha256":candidate["model_sha256"],
            "same_harness_sha256":baseline["harness_sha256"],
            "dataset_sha256":baseline["dataset_sha256"],
            "production_change":False,"optimizer_verified":False,
            "next":"physical_replay_and_checkpoints_then_existing_OneHost_owner_approval"}

def rank_gap_actions(actions:list[dict],*,max_actions=5)->dict:
    """Deterministic source-only 'hunger' planner; does not schedule, train or fetch."""
    if not isinstance(actions,list) or type(max_actions) is not int or not 1<=max_actions<=10:
        return _hold("INVALID_ACTIONS")
    selected=[]
    for a in actions[:500]:
        if not isinstance(a,dict):continue
        if a.get("verified_gap") is not True or a.get("source_uri","").startswith(("s03://","github://")) is False:
            continue
        if not isinstance(a.get("id"),str) or not ID_RE.fullmatch(a["id"]):continue
        fields=("gap","importance","novelty","cost","risk")
        vals=[a.get(x) for x in fields]
        if not all(type(v) in (float,int) and math.isfinite(v) and 0<=v<=1 for v in vals):continue
        gap,importance,novelty,cost,risk=vals
        priority=(gap*importance*(0.6+0.4*novelty))/(1+cost+2*risk)
        selected.append({"id":a["id"],"priority":round(priority,5),
                         "source_uri":a["source_uri"]})
    # Repeated IDs cannot result in more work. This returns a proposal only.
    by_id={}
    for row in sorted(selected,key=lambda r:(-r["priority"],r["id"])):
        by_id.setdefault(row["id"],row)
    return {"schema":SCHEMA,"decision":"PROPOSAL_ONLY_NO_JOB_ENQUEUED",
            "selected":list(by_id.values())[:max_actions],
            "production_change":False,"optimizer_verified":False}
