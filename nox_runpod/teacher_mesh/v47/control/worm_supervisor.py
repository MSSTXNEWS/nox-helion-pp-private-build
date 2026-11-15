"""Owner-verified V46 worm supervisor for the existing OneHost queue.

A tick only reconciles native receipts and proposes next actions. No new daemon,
second scheduler, GPU process, root shell or unapproved restart is created.
"""
from __future__ import annotations
from collections.abc import Mapping
from hashlib import sha256
import json
import re

TASKID=re.compile(r"^NOX-V46-(0[1-9]|[1-5][0-9]|60)$")
R60ID=re.compile(r"^R60-(00[1-9]|0[1-5][0-9]|060)$")
SHA=re.compile(r"^[a-f0-9]{64}$")
RUNNING=frozenset(("RUNNING","PENDING","CLAIMED"))
STATES=RUNNING | {"COMPLETED","FAILED","CANCELLED","PAUSED","BLOCKED"}

def _valid_native_job_id(value) -> bool:
    """Opaque owner job IDs are canonical; padding/control aliases are unsafe."""
    return (type(value) is str and 1 <= len(value) <= 128
            and value == value.strip() and value.isprintable())



def audit_native_queue(matrix, observations, *, now_unix: int, heartbeat_s: int=600,
                       max_attempts: int=3) -> dict:
    """Fail-closed task heartbeat, completion and bounded restart proposals.

    A stale heartbeat is not proof that the process died or released its lease.
    A failed task is retry-eligible only if OneHost has independently verified
    terminal state, backoff, released owner lease and (for GPU) restored checkpoint.
    """
    result={"schema":"NOX_V175_WORM60_AUDIT_V1",
            "state":"HOLD_NATIVE_QUEUE_BINDINGS",
            "tasks_expected":60,"native_registered_verified":0,
            "native_completed_verified":0,"native_running_verified":0,
            "unregistered_count":0,"untrusted_count":0,
            "stale_heartbeat_holds":[],"retry_eligible_proposals":[],
            "protected_task_ids":[],"native_jobs_started":0,
            "native_jobs_restarted":0,"trainer_started":False}
    if not isinstance(matrix,dict) or not isinstance(observations,Mapping):
        return result
    if (type(now_unix) is not int or now_unix<=0
            or type(heartbeat_s) is not int or not 60<=heartbeat_s<=3600
            or type(max_attempts) is not int or not 1<=max_attempts<=3):
        result["state"]="HOLD_INVALID_SUPERVISOR_LIMITS";return result
    if (observations.get("native_verified") is not True
            or observations.get("s03_native_verified") is not True
            or observations.get("native_queue_verified") is not True
            or observations.get("stop_active") is not False
            or observations.get("student_serving") is not True):
        result["state"]="HOLD_NATIVE_OWNER_STOP_S03_OR_CHAT";return result
    rows=matrix.get("tasks")
    status=observations.get("task_status")
    # Source V46 and canonical coordination/R60 are two IDs for the SAME
    # 60 logical tasks, not two queues. Reject mixed/duplicate/incomplete
    # matrices before counting even one native registration.
    if not isinstance(rows,list) or len(rows)!=60 or not isinstance(status,Mapping):
        result["state"]="HOLD_NATIVE_QUEUE_SCHEMA";return result
    allowed=set()
    family=None
    for task in rows:
        if not isinstance(task,dict):
            result["state"]="HOLD_NATIVE_QUEUE_SCHEMA";return result
        tid=task.get("task_id")
        if isinstance(tid,str) and TASKID.fullmatch(tid):
            kind="V46"
        elif isinstance(tid,str) and R60ID.fullmatch(tid):
            kind="R60"
            if task.get("legacy_task_id")!=f"NOX-V46-{int(tid[-3:]):02d}":
                result["state"]="HOLD_NATIVE_QUEUE_SCHEMA";return result
        else:
            result["state"]="HOLD_NATIVE_QUEUE_SCHEMA";return result
        if family is not None and family!=kind or tid in allowed:
            result["state"]="HOLD_NATIVE_QUEUE_SCHEMA";return result
        family=kind
        allowed.add(tid)
    expected=({f"R60-{i:03d}" for i in range(1,61)} if family=="R60"
              else {f"NOX-V46-{i:02d}" for i in range(1,61)})
    if allowed!=expected:
        result["state"]="HOLD_NATIVE_QUEUE_SCHEMA";return result
    if any(k not in allowed for k in status):
        result["state"]="HOLD_FOREIGN_TASK_IDS";return result
    # Two logical tasks must never be counted as two native registrations
    # when owner readback identifies the same native job for both. A missing
    # job_id is legacy telemetry (handled by existing receipt gates); an
    # explicitly supplied invalid or duplicated ID is untrusted.
    job_counts={}
    for obs in status.values():
        if isinstance(obs,Mapping) and "job_id" in obs:
            jid=obs["job_id"]
            if _valid_native_job_id(jid):
                job_counts[jid]=job_counts.get(jid,0)+1
    protected=set()
    for task in rows:
        tid=task["task_id"]
        obs=status.get(tid)
        if obs is None:
            result["unregistered_count"]+=1
            continue
        if (not isinstance(obs,Mapping) or obs.get("task_id")!=tid
                or obs.get("native_verified") is not True
                or not isinstance(obs.get("receipt_sha256"),str)
                or SHA.fullmatch(obs["receipt_sha256"]) is None
                or obs.get("state") not in STATES
                or ("job_id" in obs and (
                    not _valid_native_job_id(obs["job_id"])
                    or job_counts.get(obs["job_id"],0)!=1))):
            result["untrusted_count"]+=1
            protected.add(tid)
            continue
        result["native_registered_verified"]+=1
        state=obs["state"]
        if state in RUNNING:
            protected.add(tid)
            result["native_running_verified"]+=1
            stamp=obs.get("heartbeat_unix")
            if state=="RUNNING" and (type(stamp) is not int
                    or stamp>now_unix+30 or now_unix-stamp>heartbeat_s):
                result["stale_heartbeat_holds"].append({"task_id":tid,
                    "state":"HOLD_OWNER_LEASE_INSPECTION","kill_permitted":False,
                    "restart_permitted":False})
        elif state=="COMPLETED":
            protected.add(tid)
            if obs.get("independent_test_passed") is True:
                result["native_completed_verified"]+=1
            else:result["untrusted_count"]+=1
        elif state=="FAILED":
            tries=obs.get("attempt_count")
            when=obs.get("retry_after_unix")
            eligible=(obs.get("terminal_verified") is True
                and obs.get("owner_lease_released") is True
                and type(tries) is int and 0<=tries<max_attempts
                and type(when) is int and 0<=when<=now_unix)
            # R60 uses resource_class / backup_restore_required / checkpoint,
            # whereas V46 uses resource / requires_backup_restore. Ignoring
            # these canonical fields previously admitted an unsafe GPU1 retry.
            checkpoint=task.get("checkpoint")
            backup_required=(task.get("requires_backup_restore") is True
                or task.get("backup_restore_required") is True
                or isinstance(checkpoint,Mapping) and checkpoint.get("required") is True)
            gpu1=(task.get("resource")=="GPU1_EXCLUSIVE"
                  or task.get("resource_class")=="GPU1_EXCLUSIVE")
            if backup_required or gpu1:
                eligible=eligible and obs.get("checkpoint_restorable") is True
            # A native FAILED job is NEVER another fresh NEW job.
            # Even when retry-eligible, only a separate owner-approved
            # recovery can claim its prior worker ID and next attempt.
            protected.add(tid)
            if eligible:
                result["retry_eligible_proposals"].append({
                    "task_id":tid,"next_attempt":tries+1,
                    "owner_approval_required":True,"duplicate_check_required":True,
                    "may_enqueue_via_generic_plan":False})
        else:
            protected.add(tid)
    result["protected_task_ids"]=sorted(protected)
    result["state"]="NATIVE_QUEUE_RECONCILED_PROPOSALS_ONLY"
    return result


def release_evidence(*,old_source_sha:str,new_source_sha:str,
                     native_web_e2e:bool,quality_holdout_improved:bool,
                     backup_restorable:bool)->dict:
    """Three-hour time elapsing or new code SHA never means 'smarter'."""
    source_changed=(isinstance(old_source_sha,str) and SHA.fullmatch(old_source_sha)
        and isinstance(new_source_sha,str) and SHA.fullmatch(new_source_sha)
        and old_source_sha!=new_source_sha)
    success=bool(source_changed and native_web_e2e is True
                 and quality_holdout_improved is True and backup_restorable is True)
    return {"schema":"NOX_V175_THREE_HOUR_RELEASE_GATE_V1",
            "state":"VERIFIED_RELEASE_IMPROVEMENT" if success else "HOLD_NO_VERIFIED_IMPROVEMENT",
            "source_changed":bool(source_changed),"release_accepted":success,
            "subjective_consciousness_proven":False}
