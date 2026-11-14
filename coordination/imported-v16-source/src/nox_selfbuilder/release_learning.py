"""Tiny advisory prioritization model, NOT a coding LLM or new trainer.
Trains in memory using synthetic unit fixtures. Actual lessons only accepted
from trusted existing S03 review, no autonomous alteration of release gates.
"""
from __future__ import annotations
import json,math
from pathlib import Path

def train_advisory(training:list[dict],holdout:list[dict],*,epochs:int=180,lr:float=.12)->dict:
    if not 1<=epochs<=400 or not 0<lr<=.25: raise ValueError("TRAIN_BUDGET_INVALID")
    def valid(r):
        return isinstance(r,dict) and isinstance(r.get("features"),list) and len(r["features"])==3 and all(type(x) in (int,float) and math.isfinite(x) and -1<=x<=1 for x in r["features"]) and r.get("label") in (0,1)
    if len(training)<8 or len(holdout)<4 or any(not valid(r) for r in training+holdout):
        raise ValueError("VERIFIED_FIXED_SHAPE_DATASET_REQUIRED")
    # disjoint source groups between training and evaluation
    if not all(isinstance(r.get("source_id"),str) and r["source_id"] for r in training+holdout):
        raise ValueError("SOURCE_PROVENANCE_REQUIRED")
    if {x["source_id"] for x in training}&{x["source_id"] for x in holdout}:
        raise ValueError("LEAKED_HOLDOUT_SOURCE")
    w=[0.,0.,0.]; bias=0.
    for _ in range(epochs):
        for row in training:
            z=sum(a*b for a,b in zip(row["features"],w))+bias
            sig=1/(1+math.exp(-max(-20,min(20,z))))
            e=sig-row["label"]
            for i,f in enumerate(row["features"]):
                w[i]=max(-8.,min(8.,w[i]-lr*e*f))
            bias=max(-8.,min(8.,bias-lr*e))
    def acc(rows):
        return sum(int((sum(a*b for a,b in zip(r["features"],w))+bias>=0)==bool(r["label"])) for r in rows)/len(rows)
    return {"schema":"NOX-RELEASE-GOVERNOR-ADVISORY-v1", "status":"SIMULATED_ADVISORY_ONLY",
            "weights":[round(x,6) for x in w],"bias":round(bias,6),
            "training_examples":len(training),"holdout_examples":len(holdout),
            "training_accuracy":round(acc(training),4),"holdout_accuracy":round(acc(holdout),4),
            "trained_llm_weights":False,"real_release_benchmark_verified":False,
            "note":"Never authorizes source, build, license, personal data or irreversible change"}
