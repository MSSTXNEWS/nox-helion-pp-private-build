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
# Must match the original V47 enqueue/recovery native queue-ID contract.
JOBID=re.compile(r"^[A-Za-z0-9._:@/-]{1,128}$")
RUNNING=frozenset(("RUNNING","PENDING","CLAIMED"))
STATES=RUNNING | {"COMPLETED","FAILED","CANCELLED","PAUSED","BLOCKED"}

def _valid_native_job_id(value) -> bool:
    """Opaque owner job IDs are canonical; padding/control aliases are unsafe."""
    return type(value) is str and JOBID.fullmatch(value) is not None



# Source-only passive audit: does not restart a PID or impersonate owner telemetry.
# Signed native OneHost must supply a complete inventory and two samples.
def audit_process_progress(current, previous, *, now_unix: int, grace_seconds: int = 1800) -> dict:
    """Compare useful *verified* progress, not CPU/GPU activity or a heartbeat alone."""
    report = {"schema": "NOX_NATIVE_PROGRESS_AUDIT_V1",
              "state": "HOLD_PROGRESS_SAMPLES_UNAVAILABLE",
              "advancing": [], "suspected_stalls": [], "holds": [],
              "restart_permitted": False, "mutations": 0}
    if (type(now_unix) is not int or now_unix <= 0
            or type(grace_seconds) is not int or not 600 <= grace_seconds <= 43200
            or not isinstance(current, Mapping) or not isinstance(previous, Mapping)
            or len(current) > 512 or len(previous) > 512):
        return report
    report["state"] = "PROGRESS_AUDITED_ADVISORY_ONLY"
    for identity, sample in current.items():
        if (not isinstance(identity, str)
                or re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", identity) is None):
            report["holds"].append({"id": "UNKNOWN", "reason": "HOLD_PROGRESS_ID"})
            continue
        old = previous.get(identity)
        if not isinstance(sample, Mapping):
            report["holds"].append({"id": identity, "reason": "HOLD_PROGRESS_FORMAT"})
            continue
        def valid(x):
            return (isinstance(x, Mapping)
                and x.get("native_verified") is True
                and isinstance(x.get("receipt_sha256"), str)
                and SHA.fullmatch(x["receipt_sha256"]) is not None
                and type(x.get("pid")) is int and x["pid"] > 0
                and type(x.get("start_ticks")) is int and x["start_ticks"] > 0
                and type(x.get("counter")) is int and x["counter"] >= 0
                and type(x.get("observed_unix")) is int
                and 0 < x["observed_unix"] <= now_unix + 30
                and x.get("metric") in
                    ("optimizer_updates", "verified_bytes", "native_jobs_done",
                     "s03_recall_done", "stream_completions", "accepted_improvements")
                and type(x.get("active")) is bool)
        if not valid(sample):
            report["holds"].append({"id": identity, "reason": "HOLD_UNVERIFIED_PROGRESS"})
            continue
        if not sample["active"]:
            report["holds"].append({"id": identity, "reason": "IDLE_NOT_STALLED"})
            continue
        if not valid(old):
            report["holds"].append({"id": identity, "reason": "NEED_TWO_NATIVE_SAMPLES"})
            continue
        if (old["pid"] != sample["pid"]
                or old["start_ticks"] != sample["start_ticks"]
                or old["metric"] != sample["metric"]):
            report["holds"].append({"id": identity, "reason": "NEW_PROCESS_BASELINE"})
            continue
        # A cached observation cannot diagnose a *current* stall. Match each
        # exact revision, when emitted, to avoid mistaking a model upgrade for
        # zero progress on the previous training run.
        if now_unix - sample["observed_unix"] > max(120, grace_seconds // 3):
            report["holds"].append({"id": identity, "reason": "STALE_NATIVE_PROGRESS_READBACK"})
            continue
        rev_new, rev_old = sample.get("revision_sha256"), old.get("revision_sha256")
        if rev_new is not None or rev_old is not None:
            if not (isinstance(rev_new, str) and SHA.fullmatch(rev_new)
                    and isinstance(rev_old, str) and SHA.fullmatch(rev_old)):
                report["holds"].append({"id": identity, "reason": "HOLD_PROGRESS_REVISION_PROOF"})
                continue
            if rev_new != rev_old:
                report["holds"].append({"id": identity, "reason": "NEW_WORK_REVISION_BASELINE"})
                continue
        elapsed = sample["observed_unix"] - old["observed_unix"]
        if elapsed <= 0 or sample["counter"] < old["counter"]:
            report["holds"].append({"id": identity, "reason": "HOLD_STALE_OR_RESET_COUNTER"})
        elif sample["counter"] > old["counter"]:
            report["advancing"].append({"id": identity, "metric": sample["metric"],
                                          "delta": sample["counter"] - old["counter"]})
        elif elapsed >= grace_seconds:
            report["suspected_stalls"].append({
                "id": identity, "pid": sample["pid"], "metric": sample["metric"],
                "no_progress_seconds": elapsed, "action": "DIAGNOSE_AND_CHANGE_APPROACH",
                "restart_permitted": False, "owner_lease_required": True})
        else:
            report["holds"].append({"id": identity, "reason": "NORMAL_LONG_STEP_GRACE"})
    return report


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
             "native_job_ids_verified":0,
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
                or not isinstance(obs.get("state"),str) or obs["state"] not in STATES
                or ("job_id" in obs and (
                    not _valid_native_job_id(obs["job_id"])
                    or job_counts.get(obs["job_id"],0)!=1))):
            result["untrusted_count"]+=1
            protected.add(tid)
            continue
        result["native_registered_verified"]+=1
        # A legacy signed status WITHOUT a concrete native job ID is only
        # telemetry; it cannot attest any of the owner's 60 real queue jobs.
        # This count is strict and must not be confused with S03 receipts.
        if "job_id" in obs:
            result["native_job_ids_verified"]+=1
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
            # A legacy signed FAILED status protects work, but owner recovery
            # cannot reclaim a specific native worker without its unique ID.
            eligible=(obs.get("terminal_verified") is True
                and obs.get("owner_lease_released") is True
                and _valid_native_job_id(obs.get("job_id"))
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
                    "task_id":tid,"job_id":obs["job_id"],
                    "next_attempt":tries+1,
                    "owner_approval_required":True,"duplicate_check_required":True,
                    "may_enqueue_via_generic_plan":False})
        else:
            protected.add(tid)
    result["process_progress_audit"] = audit_process_progress(
        observations.get("process_progress_current"),
        observations.get("process_progress_previous"),
        now_unix=now_unix)
    result["protected_task_ids"]=sorted(protected)
    result["state"]="NATIVE_QUEUE_RECONCILED_PROPOSALS_ONLY"
    return result



# Owner's newest rule: the 60 V46/R60 tasks are background obligations,
# NOT 60 daemons and NEVER a reason to delay conversation or direct commands.
# This is a pure admission decision. It starts/stops NOTHING and modifies
# neither the canonical queue nor its STOP/lease/worker owner.
BACKGROUND_POLICY = "NOX_CHAT_FIRST_BACKGROUND_V18"

def recommend_background_admission(observations:Mapping)->dict:
    """Propose a capacity ceiling for existing native queue workers.

    On an active chat/direct request, reduce or suspend NEW background claims;
    cooperative release of already running work remains the original OneHost's
    responsibility. New optimizer jobs need an accepted replacement model,
    exact resource lease, restorable checkpoint and no quality hold.
    Missing evidence is a HOLD, not an invitation to silently resume Qwen.
    """
    base={"schema":BACKGROUND_POLICY, "native_mutations":0,
          "new_worm_cpu_claims_max":0, "new_worm_gpu_claims_max":0,
          "background_training_allowed":False, "chat_priority":"P0",
          "direct_tasks_priority":"P0", "worm_priority":"P2",
          "new_training_priority":"P3", "gpu0_reserved_for_chat":True,
          "existing_jobs_killed":0, "stop_overridden":False}
    if not isinstance(observations,Mapping):
        return {**base,"state":"HOLD_BACKGROUND_NATIVE_OBSERVATIONS"}
    if (observations.get("native_verified") is not True
        or observations.get("s03_native_verified") is not True
        or observations.get("stop_active") is not False
        or observations.get("student_serving") is not True):
        return {**base,"state":"HOLD_BACKGROUND_STOP_OR_MODEL_NOT_SERVING"}
    chat=observations.get("chat_state")
    recent=observations.get("chat_recent")
    direct=observations.get("direct_tasks_pending",False)
    if (chat not in ("idle","generating","streaming","thinking","connecting",
                     "error","offline")
        or type(recent) is not bool or type(direct) is not bool):
        return {**base,"state":"HOLD_BACKGROUND_CHAT_OR_DIRECT_STATE"}
    if direct:
        return {**base,"state":"DIRECT_TASKS_FIRST","yield_background":True}
    if chat!="idle":
        # One very light pre-existing CPU monitor may continue; no new media
        # or GPU work while the owner talks with NOX.
        return {**base,"state":"CHAT_ACTIVE_LIGHT_BACKGROUND",
                "new_worm_cpu_claims_max":1,"yield_background":True}
    if recent:
        return {**base,"state":"CHAT_RECENT_LOW_BACKGROUND",
                "new_worm_cpu_claims_max":2,"yield_background":True}
    # Chat is idle. Background knowledge/research can continue; user can
    # interrupt. Explicit new-model release evidence gates weight training.
    accepted=observations.get("new_model_release_verified") is True
    learning=(accepted
              and observations.get("quality_hold_active") is False
              and observations.get("checkpoint_restorable") is True
              and observations.get("gpu1_owner_lease") is True
              and observations.get("gpu1_peak_verified") is True
              and observations.get("gpu1_teacher_active") is False
              and observations.get("gpu1_trainer_active") is False)
    sleep=observations.get("owner_sleep_mode") is True
    return {**base,
       "state":("SLEEP_BACKGROUND_ADMITTED" if sleep else "IDLE_BACKGROUND_ADMITTED")
               if accepted else "HOLD_NEW_MODEL_TRAINING_BACKGROUND_CPU_ONLY",
       "new_worm_cpu_claims_max":6 if sleep else 4,
       "new_worm_gpu_claims_max":1 if learning else 0,
       "background_training_allowed":bool(learning),
       "gpu_training_utilization_ceiling_percent":85 if learning else 0,
       "yield_background":False,
       "reason":"new_main_model_accepted" if accepted else "NEW_MAIN_NOT_ACCEPTED"}


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
