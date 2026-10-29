"""NOX V16/T06: immutable evidence-driven closeout gate.
A report, commit, archive SHA or DONE string is never acceptance.
This script cannot keep a ChatGPT response running; it blocks dishonest DONE.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

CRITERIA = ("base", "P01", "P02", "P03", "P04", "P05", "common_integration", "accepted_head_manifest")
HEX40 = re.compile(r"[0-9a-f]{40}\\Z")
HEX_PROOF = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\\Z")
PROOF = ("owner_receipt", "preimage_sha", "postimage_sha", "test_receipt")

def valid_owner_and_proof(row: dict, evidence: dict) -> bool:
    # This checks evidence format, NOT the Git object's existence or its owner's
    # authority. The sole integrator must separately obtain CAS/readback proof.
    return (type(row.get("owner")) is str and bool(row["owner"].strip())
            and row["owner"] != "UNASSIGNED"
            and all(type(evidence.get(k)) is str and
                    bool(HEX_PROOF.fullmatch(evidence[k])) for k in PROOF))

def decide(receipt: dict) -> dict:
    if not isinstance(receipt, dict) or not isinstance(receipt.get("criteria"), dict):
        raise ValueError("FIXED_T06_CRITERIA_MISSING")
    if set(receipt["criteria"]) != set(CRITERIA):
        raise ValueError("T06_MUST_HAVE_EXACTLY_EIGHT_CRITERIA")
    accepted, remaining = [], []
    for name in CRITERIA:
        row = receipt["criteria"][name]
        if not isinstance(row, dict):
            raise ValueError("INVALID_CRITERION_" + name)
        evidence = row.get("evidence")
        if name == "base":
            # A pinned source base needs a real head and source-choice receipt,
            # not imaginary PRE/POST changes or a test for an unchanged baseline.
            ok = (row.get("status") == "DONE" and isinstance(evidence, dict)
                  and isinstance(evidence.get("canonical_head_sha"), str)
                  and bool(HEX40.fullmatch(evidence["canonical_head_sha"]))
                  and type(row.get("owner")) is str and bool(row["owner"].strip())
                  and type(evidence.get("source_choice_receipt")) is str
                  and bool(HEX_PROOF.fullmatch(evidence["source_choice_receipt"])))
        else:
            ok = (row.get("status") == "DONE" and isinstance(evidence, dict)
                  and valid_owner_and_proof(row, evidence))
        if name == "accepted_head_manifest" and ok:
            ok = all(isinstance(receipt.get(key), str) and bool(HEX40.fullmatch(receipt[key]))
                     for key in ("head_sha", "tree_sha", "manifest_blob_sha"))
            # T10 independently verifies SOURCE_READY *after* T09 freezes T06's
            # accepted source. Making T10 a T06 prerequisite deadlocks the
            # canonical T06 -> T08 -> T09 -> T10 pipeline.
            ok = ok and receipt.get("owner_acceptance") is True
        if ok:
            accepted.append(name)
        else:
            remaining.append({"criterion": name, "owner": row.get("owner", "UNASSIGNED"),
                              "action": row.get("next_action", "VERIFY_EXACT_SHA_AND_RECEIPT")})
    done = len(accepted) == len(CRITERIA)
    count = len(accepted)
    return {"schema": "NOX_V16_T06_CLOSEOUT_GATE_V1", "run_id": receipt.get("run_id"),
            "status": "DONE" if done else "HOLD_INCOMPLETE", "done": done,
            "premature_closeout_rejected": not done and receipt.get("claimed_status") in
                ("DONE", "COMPLETE", "SOURCE_READY", "100%"),
            "completed": count, "total": 8, "progress_pct": count*12.5,
            "progress_bar": "█"*round(count*10/8) + "░"*(10-round(count*10/8)),
            "remaining": remaining, "continuation_required": not done,
            "T10_source_ready": "INDEPENDENT_PASS_REQUIRED_AFTER_T09_FREEZE",
            "limitations": "No script controls assistant turn lifetime or proves native Windows behavior"}

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("receipt", type=Path)
    p.add_argument("--output", type=Path)
    a=p.parse_args()
    out=decide(json.loads(a.receipt.read_text(encoding="utf-8")))
    result=json.dumps(out, ensure_ascii=False, indent=2)+"\n"
    if a.output:
        if a.output.exists(): raise RuntimeError("APPEND_ONLY_RECEIPT_ALREADY_EXISTS")
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(result,encoding="utf-8")
    print(result,end="")
    return 0 if out["done"] else 2

if __name__=="__main__":
    sys.exit(main())
