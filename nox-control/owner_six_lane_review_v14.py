#!/usr/bin/env python3
"""Six real, separate CPU subagents advising the ORIGINAL NOX OneHost dispatcher.

This is a REVIEW/owner-queue adapter, not a second scheduler, backend, trainer
or direct code runner. All candidates must pass native owner admission, reviewed
handlers, source tests, rollback and trusted native proof before promotion.
Never creates a worker under MODEL_UPDATE/STOP or an unverified owner lease.
"""
from __future__ import annotations

from collections.abc import Mapping

SCHEMA = "NOX_SIX_LANE_REVIEW_V14"
ROLES = ("safety", "storage", "maya", "memory", "web", "media")
INSTANCE = 60509551
# Separate work, within-lane order; first task from every lane is independent.
REVIEW_TASKS = {
 "safety": (
    "Read original NOX STOP, PID/start_ticks, services, watchdog, leases; propose an exact no-loss stop fix.",
    "Verify S03 WAL-consistent restore, Genesis, history, checkpoint+optimizer/scaler/RNG and approved deletion allowlist.",
    "Propose reversible cleanup of obsolete files only where original inode, SHA and no open handles are proven.",
 ),
 "storage": (
    "Verify current Drive starter 4 parts and training wheelhouse 39 parts against manifests without duplicate downloads.",
    "Verify full-model >=248834257920-byte seekable capacity, quota, real auth and safe storage lease.",
    "Review five missing DeepSeek GGUF (four backbone + one Engram) Range/resume/full SHA receipt and single writer.",
 ),
 "maya": (
    "Compare pinned Maya CUDA12.4 sm70 ELF and native GPU0/GPU1 FP16 smoke with existing installed ABI.",
    "Review isolated compatible PyTorch/TRL/PEFT/DeepSpeed and caching dependencies; reject unsupported V100 kernels.",
    "Review TP2/KV/VRAM expert storage, benchmark and rollback after actual DeepSeek files are verified.",
 ),
 "memory": (
    "Verify existing S03 SQLite/FTS/BGE index, exact owner permissions and protected fact provenance.",
    "Review C01-C08/M0-M7/Reflection/self-model and skill-memory callbacks in the existing OneHost.",
    "Propose verified RU/ES recall and evaluation tasks, prevent imaginary autobiographical memories.",
 ),
 "web": (
    "Identify actual serving web/UI by HTTP/process/files, not WEB29 by archive name.",
    "Review original D02/14 worlds web asset preservation and Maya stdio-to-original SSE adapter.",
    "Check first-token streaming, complete response, STOP/cancel, tools, history, ACL and browser E2E.",
 ),
 "media": (
    "Check historical SDXL-Lightning and Wan2.1/UMT5/VAE SHA and ComfyUI post-STOP file residency.",
    "Review original ComfyUI PNG/video request graph, GPU on-demand lease, cancellation and provenance.",
    "Prepare photo/video quality metrics, short 480p video and no-overlap with primary chat GPU use.",
 ),
}

# Only tasks in this exact source-reviewed DAG belong to this reviewer.
REVIEW_IDS = frozenset(
    "V14-" + role + "-" + str(index)
    for role in ROLES for index in range(1, len(REVIEW_TASKS[role]) + 1)
)

def make_review_batch():
    """Typed DAG for the existing owner_subagent_processes.Subagents IPC pool."""
    tasks = []
    for role in ROLES:
        previous = None
        for idx, description in enumerate(REVIEW_TASKS[role], 1):
            task_id = "V14-" + role + "-" + str(idx)
            tasks.append({"id": task_id, "subagent": role, "task": description,
                          "depends_on": [previous] if previous else []})
            previous = task_id
    batch = {"schema": "NOX_OWNER_SUBAGENTS_BATCH_V1",
             "subagents": list(ROLES), "tasks": tasks}
    # One consistent, independently validated schema; no arbitrary shell/code.
    from owner_subagent_processes import validate
    validate(batch)
    return batch

def _authorized(native):
    """Only an authenticated original OneHost object can supply these callbacks.

    This code cannot authenticate or mint owner leases. Missing evidence => HOLD.
    """
    if native is None or not all(callable(getattr(native, key, None)) for key in
        ("owner_allowed", "stop_active", "writer_lease",
         "read_resource_snapshot")):
        return False
    try:
        snapshot = native.read_resource_snapshot()
        return (isinstance(snapshot, Mapping)
                and snapshot.get("native_verified") is True
                and snapshot.get("instance_id") == INSTANCE
                and snapshot.get("owner_scope_verified") is True
                and snapshot.get("source_sha_verified") is True
                and snapshot.get("stop_active") is False
                and native.owner_allowed() is True
                and native.stop_active() is False
                and native.writer_lease() is True)
    except Exception:
        return False

def review_with_six_processes(native, *, model_url="http://127.0.0.1:8081/v1/chat/completions",
                               timeout=60):
    """Start exactly six OS processes AFTER owner STOP release.

    Each calls the same existing local model; returned ideas are candidates,
    NOT deployed patches or native TaskID completions.
    """
    if not _authorized(native):
        return {"schema": SCHEMA, "state": "HOLD_OWNER_MODEL_UPDATE_OR_NATIVE_LEASE",
                "actual_processes": 0, "native_changes": 0}
    from owner_subagent_processes import Subagents
    batch = make_review_batch()
    try:
        # Gate is checked BEFORE process creation, as well as by Subagents.run
        with Subagents(list(ROLES), model_url=model_url, timeout=timeout) as pool:
            if not _authorized(native):
                return {"schema": SCHEMA, "state": "HOLD_OWNER_GATE_CHANGED",
                        "actual_processes": 0, "native_changes": 0}
            result = pool.run(batch, stop_active=native.stop_active,
                              authorize=native.owner_allowed,
                              lease_current=native.writer_lease)
        pids = result.get("processes", {})
        if (not isinstance(pids, Mapping) or set(pids) != set(ROLES)
            or len(set(pids.values())) != 6
            or any(type(pid) is not int or pid < 2 for pid in pids.values())):
            return {"schema": SCHEMA, "state": "HOLD_UNVERIFIED_SIX_PID",
                    "actual_processes": 0, "native_changes": 0}
        return {"schema": SCHEMA, "state": "SIX_REVIEW_CANDIDATES_ONLY",
                "actual_processes": 6, "pids": dict(pids),
                "tasks_reviewed": result["task_count"],
                "candidate_count": sum(
                    row.get("state") == "CANDIDATE_NOT_APPLIED"
                    for row in result["results"].values()),
                "native_changes": 0, "new_model_loaded": False,
                "native_implementation_proven": False}
    except Exception as exc:
        # A STOP/lease transition is NEVER a reason to retry blindly.
        from owner_subagent_processes import GateError
        code = str(exc) if isinstance(exc, GateError) else "HOLD_SIX_REVIEW_UNVERIFIED"
        return {"schema": SCHEMA, "state": code,
                "actual_processes": 0, "native_changes": 0}

def dispatch_reviewed_native_six(native):
    """Existing original native dispatcher: asks its reviewed callback for six.

    This is the ONLY optional action path to actual native queue claims.
    A three-role installed binder must safely HOLD, not lie about six agents.
    """
    if not _authorized(native):
        return {"schema": SCHEMA, "state": "HOLD_OWNER_MODEL_UPDATE_OR_NATIVE_LEASE",
                "jobs_started": 0}
    import owner_autonomy_pool as pool
    # Existing catalog/role allowlists, resource pressure, owner queue, S03,
    # unique PID+startticks, and lease are all verified inside this call.
    out = pool.tick_existing_dispatcher(
        {"_nox_owner_autonomy_native": native}, {}, mode="FORSAZH")
    return {"schema": SCHEMA, "native_result": out,
            "state": out.get("state", "HOLD_NATIVE_RESULT_UNKNOWN"),
            "jobs_started": out.get("jobs_started", 0),
            "jobs_completed_verified": out.get("jobs_completed_verified", 0)}

def coordinator_reconcile(review, native_receipts):
    """Coordinator never turns a model suggestion into a PASS.

    Native receipt collection MUST originate from an independent owner reader
    (not the candidate/model response); no mutations are performed here.
    """
    if not isinstance(review, Mapping) or review.get("schema") != SCHEMA:
        return {"state": "HOLD_REVIEW_SCHEMA", "done": 0}
    if review.get("state") != "SIX_REVIEW_CANDIDATES_ONLY":
        return {"state": "HOLD_NO_SIX_REVIEW", "done": 0}
    if not isinstance(native_receipts, (list, tuple)):
        return {"state": "HOLD_NATIVE_RECEIPTS", "done": 0}
    pids = review.get("pids")
    if (review.get("actual_processes") != len(ROLES)
        or review.get("tasks_reviewed") != len(REVIEW_IDS)
        or not isinstance(pids, Mapping) or set(pids) != set(ROLES)
        or len(set(pids.values())) != len(ROLES)
        or any(type(pid) is not int or pid < 2 for pid in pids.values())):
        return {"state": "HOLD_REVIEW_IDENTITY", "done": 0}
    approved = []
    seen = set()
    for row in native_receipts:
        if not isinstance(row, Mapping):
            continue
        task_id, sha = row.get("task_id"), row.get("result_sha256")
        if (not isinstance(task_id, str) or task_id not in REVIEW_IDS
            or task_id in seen or not isinstance(sha, str) or len(sha) != 64
            or any(c not in "0123456789abcdef" for c in sha)
            or row.get("native_verified") is not True
            or row.get("terminal_state") != "COMPLETED"
            or row.get("source_tests_passed") is not True
            or row.get("installed_and_readback") is not True
            or row.get("rollback_verified") is not True):
            continue
        seen.add(task_id)
        approved.append(task_id)
    return {"state": "NATIVE_EVIDENCE_READBACK" if approved else "HOLD_NO_NATIVE_COMPLETIONS",
            "done": len(approved), "task_ids": approved}

if __name__ == "__main__":
    print("NOX_V14_SOURCE_ONLY_NOT_INSTALLED_OR_STARTED")
