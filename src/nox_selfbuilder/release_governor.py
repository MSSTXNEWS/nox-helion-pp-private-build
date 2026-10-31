"""One owner release director; only candidate admission and immutable evidence.

NO runner, second task DB, self-merging code, or hidden CI retries here.
The existing S03 task ledger and a single authorized owner #1 remain authoritative.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping
import re

_SHA = re.compile(r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,120}$")
OWNER = "1"
INDEPENDENT_QA = "2"

@dataclass(frozen=True)
class Gate:
    status: str
    reasons: tuple[str, ...]
    next_action: str
    author: str = OWNER
    independent_acceptor: str = INDEPENDENT_QA
    release_ready: bool = False


def inspect_release_task(ticket:Mapping, *, current_head:str, seen_task_ids:frozenset[str]=frozenset()) -> Gate:
    """Hard gate > learned priorities, independent of model output."""
    if not isinstance(ticket,Mapping) or not _SHA.fullmatch(current_head or ""):
        return Gate("HOLD",("CURRENT_SOURCE_HEAD_UNKNOWN",),"Find exact source HEAD")
    tid=ticket.get("task_id")
    if not isinstance(tid,str) or not _ID.fullmatch(tid):
        return Gate("HOLD",("TASK_ID_MISSING_OR_INVALID",),"Resolve existing TaskID")
    if tid in seen_task_ids:
        return Gate("HOLD",("DUPLICATE_TASK_ID",),"Reuse prior receipt")
    if ticket.get("owner_id") != OWNER:
        return Gate("HOLD",("SINGLE_OWNER_1_REQUIRED",),"Handoff to owner #1")
    if ticket.get("head") != current_head:
        return Gate("HOLD",("EXACT_HEAD_DRIFT",),"Reconcile before patch")
    if ticket.get("existing_code_checked") is not True:
        return Gate("HOLD",("REUSE_FIRST_NOT_PROVEN",),"Review approved ready-code registry")
    if ticket.get("critical_sources_complete") is not True:
        return Gate("HOLD",("SOURCE_COVERAGE_HOLD",),"Resolve missing required sources")
    if ticket.get("overlapping_owner_paths",False) is not False:
        return Gate("HOLD",("OWNER_FILE_COLLISION",),"Serial integrator path ownership")
    if ticket.get("required_scope_fixed",False) is not True:
        return Gate("HOLD",("SCOPE_CREEP",),"Freeze exact acceptance criterion")
    if ticket.get("code_preimage_sha") not in ("ABSENT",) and not _SHA.fullmatch(ticket.get("code_preimage_sha") or ""):
        return Gate("HOLD",("PREIMAGE_UNKNOWN",),"Read exact preimage SHA")
    return Gate("PATCH_CANDIDATE_ALLOWED",(),"One minimal source patch, one targeted test; owner #1 integrates")


def source_ready(*, mandatory_total:int|None, source_verified:int, patch_tests_passed:int,
                 integration_receipts:int, windows_runner_ready:bool) -> dict:
    """Separates SOURCE_READY from actual Windows build ability."""
    if not isinstance(mandatory_total,int) or mandatory_total <= 0:
        return {"status":"HOLD","reason":"UNKNOWN_DENOMINATOR","windows_release":False}
    for n in (source_verified,patch_tests_passed,integration_receipts):
        if not isinstance(n,int) or n<0:
            return {"status":"HOLD","reason":"INVALID_EVIDENCE_COUNTER","windows_release":False}
    if source_verified != mandatory_total or patch_tests_passed != mandatory_total or integration_receipts != mandatory_total:
        return {"status":"HOLD","reason":"INCOMPLETE_SOURCE_READY","windows_release":False}
    return {"status":"SOURCE_READY", "windows_runner":"READY" if windows_runner_ready else "HOLD",
            "windows_release":False,"next":"One owner-controlled Windows build; independent same-SHA E07"}


def choose_next(tickets:list[dict], *, head:str, seen:frozenset[str]=frozenset(),
                learned_weights:dict|None=None) -> tuple[dict|None,list[dict]]:
    """Deterministic release path, optional *ranking* only; no authorizing via model weights."""
    decisions=[]
    for t in tickets:
        g=inspect_release_task(t,current_head=head,seen_task_ids=seen)
        entry={"task_id":t.get("task_id"), "gate":g.status,"reason":list(g.reasons), "next_action":g.next_action}
        decisions.append(entry)
    ready=[t for t in tickets if any(x["task_id"]==t.get("task_id") and x["gate"]=="PATCH_CANDIDATE_ALLOWED" for x in decisions)]
    def score(t):
        # Hard critical path dominates optional learnt tie-breaker.
        critical=1000 if t.get("blocks_onehost",False) else 0
        dependencies=int(t.get("dependency_unblocks",0))
        dependencies=max(0,min(dependencies,10))
        reuse=100 if t.get("ready_patch_found",False) else 0
        learned=0.0
        if isinstance(learned_weights,dict) and learned_weights.get("status")=="SIMULATED_ADVISORY_ONLY":
            features=(int(bool(t.get("ready_patch_found",False))),int(bool(t.get("blocks_onehost",False))),dependencies/10)
            ws=learned_weights.get("weights")
            if isinstance(ws,list) and len(ws)==3 and all(isinstance(x,(float,int)) and -8<=x<=8 for x in ws):
                learned=sum(a*b for a,b in zip(ws,features))
        return (critical+dependencies*10+reuse+max(-1,min(1,learned)),t.get("task_id",""))
    ready.sort(key=lambda t:(-score(t)[0],score(t)[1]))
    return (ready[0] if ready else None),decisions
