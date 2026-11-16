#!/usr/bin/env python3
"""NOX AUTO 1C: read-only R60/40 profile vs six native worker evidence gate.

No enqueue, scheduler, GPU call, STOP, S03 write or server mutation.
Untrusted JSON never confirms native jobs: ONLY trusted existing OneHost
verify_job/verify_worker callbacks may prove individual rows. An independent
S03 event must be checked by verify_job, not inferred from a nonempty hash.
instructions_version=0.0.6
error_id=NOX-P0-R60-PROFILE40-WORKER-EQUIVALENCE-20261116
lesson=Six worker IDs, 40 profile tasks and 60 logical tasks are different.
next_action=Owner-native read-only callback must reconcile R60-020->R60-056
dependency and exact queue/job/S03/lease evidence before any enrollment.
"""
from __future__ import annotations
import argparse
import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path

TASK = re.compile(r"R60-(00[1-9]|0[1-5][0-9]|060)\Z")
JOB = re.compile(r"[A-Za-z0-9._:@/-]{1,128}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")


def reconcile(master: Mapping, snapshot: Mapping, *, verify_job: Callable | None = None,
              verify_worker: Callable | None = None) -> dict:
    """All callback claims must be independently verified by original OneHost."""
    if not isinstance(master, Mapping) or master.get("schema") != "NOX_R60_SOURCE_PLAN_V1":
        raise ValueError("HOLD_R60_MASTER_SCHEMA")
    tasks = master.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 60:
        raise ValueError("HOLD_R60_MASTER_60_ROWS")
    ids = {f"R60-{i:03}" for i in range(1, 61)}
    by_id = {}
    for row in tasks:
        if not isinstance(row, dict):
            raise ValueError("HOLD_R60_TASK_ROW")
        tid = row.get("task_id")
        if not isinstance(tid, str) or not TASK.fullmatch(tid) or tid in by_id:
            raise ValueError("HOLD_R60_TASK_ID_OR_DUPLICATE")
        n = int(tid[-3:])
        if row.get("legacy_task_id") != f"NOX-V46-{n:02}":
            raise ValueError("HOLD_R60_V46_ALIAS")
        deps = row.get("depends_on")
        if (not isinstance(deps, list) or len(deps) != len(set(deps)) or
                any(not isinstance(d, str) or d not in ids or d == tid for d in deps)):
            raise ValueError("HOLD_R60_DEPENDENCIES")
        by_id[tid] = row
    if set(by_id) != ids:
        raise ValueError("HOLD_R60_INCOMPLETE")
    if not isinstance(snapshot, Mapping):
        raise ValueError("HOLD_NATIVE_SNAPSHOT_SCHEMA")
    workers, jobs = snapshot.get("workers", []), snapshot.get("jobs", [])
    if not isinstance(workers, list) or not isinstance(jobs, list):
        raise ValueError("HOLD_NATIVE_SNAPSHOT_LISTS")
    if len(workers) > 6:
        raise ValueError("HOLD_SIX_NATIVE_WORKER_BOUND")
    worker_ids = [w.get("id") for w in workers if isinstance(w, dict)]
    if (len(worker_ids) != len(workers) or
            any(not isinstance(x, str) or not JOB.fullmatch(x) for x in worker_ids) or
            len(set(worker_ids)) != len(worker_ids)):
        raise ValueError("HOLD_WORKER_IDENTITIES")
    verified_workers = sum(verify_worker(w, snapshot) is True for w in workers) if callable(verify_worker) else 0
    if len(jobs) > 60:
        raise ValueError("HOLD_JOB_LIST_BOUNDS")
    job_ids, task_ids, verified_tasks = set(), set(), []
    for job in jobs:
        if not isinstance(job, Mapping):
            raise ValueError("HOLD_JOB_ROW")
        tid, jid = job.get("task_id"), job.get("job_id")
        if not isinstance(tid, str) or tid not in by_id or not isinstance(jid, str) or not JOB.fullmatch(jid):
            raise ValueError("HOLD_UNKNOWN_OR_INVALID_JOB")
        if tid in task_ids or jid in job_ids:
            raise ValueError("HOLD_DUPLICATED_JOB_OR_TASK")
        task_ids.add(tid)
        job_ids.add(jid)
        if (callable(verify_job) and
                isinstance(job.get("registry_sha256"), str) and SHA.fullmatch(job["registry_sha256"]) and
                isinstance(job.get("s03_sha256"), str) and SHA.fullmatch(job["s03_sha256"]) and
                verify_job(by_id[tid], job, snapshot) is True):
            verified_tasks.append(tid)
    profile = {f"R60-{i:03}" for i in range(1, 41)}
    verified = sorted(profile.intersection(verified_tasks))
    external = sorted({dep for tid in profile for dep in by_id[tid]["depends_on"] if dep not in profile})
    return {
        "schema": "NOX_1C_R60_PROFILE40_EVIDENCE_V1",
        "scope": "READ_ONLY_EXISTING_ONEHOST",
        "source_tasks": 60,
        "working_profile_source_tasks": 40,
        "workers_observed_untrusted": len(workers),
        "workers_callback_verified": verified_workers,
        "jobs_observed_untrusted": len(jobs),
        "profile_jobs_callback_verified": len(verified),
        "profile_verified_task_ids": verified,
        "outside_profile_dependencies": external,
        "native_state": "CALLBACK_VERIFIED_PARTIAL" if verified else "HOLD_NO_INDEPENDENT_NATIVE_PROOF",
        "source_only": not bool(verified),
        "note": "6 workers, 40 working tasks and 60 logical jobs are not interchangeable",
    }


def selftest():
    rows = [{"task_id": f"R60-{i:03}", "legacy_task_id": f"NOX-V46-{i:02}",
             "depends_on": [f"R60-{i-1:03}"] if i > 1 else []} for i in range(1, 61)]
    master = {"schema": "NOX_R60_SOURCE_PLAN_V1", "tasks": rows}
    workers = [{"id": f"worker{i}"} for i in range(6)]
    one = {"task_id": "R60-001", "job_id": "job-1",
           "registry_sha256": "a"*64, "s03_sha256": "b"*64}
    n = 0
    def check(value, label):
        nonlocal n
        assert value, label
        n += 1
    a = reconcile(master, {"workers": workers, "jobs": [one]})
    check(a["profile_jobs_callback_verified"] == 0 and a["workers_callback_verified"] == 0, "no callback no pass")
    check(a["working_profile_source_tasks"] == 40 and a["source_tasks"] == 60, "count identities")
    check(a["workers_observed_untrusted"] == 6 and a["jobs_observed_untrusted"] == 1, "distinct sources")
    b = reconcile(master, {"workers": workers, "jobs": [one]},
                  verify_job=lambda t,j,s: True, verify_worker=lambda w,s: True)
    check(b["profile_jobs_callback_verified"] == 1 and b["workers_callback_verified"] == 6, "genuine callbacks")
    check(reconcile(master, {"jobs": [one]}, verify_job=lambda t,j,s: 1)["profile_jobs_callback_verified"] == 0, "strict true")
    check(reconcile(master, {"jobs": [{**one, "s03_sha256": "bad"}]}, verify_job=lambda t,j,s: True)["profile_jobs_callback_verified"] == 0, "S03 input")
    def blocked(fn, expected):
        try: fn()
        except ValueError as exc: check(str(exc) == expected, expected)
        else: raise AssertionError("missing gate " + expected)
    blocked(lambda: reconcile(master, {"workers": workers + [{"id":"worker6"}]}), "HOLD_SIX_NATIVE_WORKER_BOUND")
    blocked(lambda: reconcile(master, {"workers": [{"id":"x"},{"id":"x"}]}), "HOLD_WORKER_IDENTITIES")
    blocked(lambda: reconcile(master, {"jobs": [one,{**one, "job_id":"job2"}]}), "HOLD_DUPLICATED_JOB_OR_TASK")
    blocked(lambda: reconcile(master, {"jobs": [{**one, "task_id":"R60-061"}]}), "HOLD_UNKNOWN_OR_INVALID_JOB")
    blocked(lambda: reconcile({**master, "tasks": rows[:-1]}, {}), "HOLD_R60_MASTER_60_ROWS")
    bad = rows.copy(); bad[0] = {**rows[0], "legacy_task_id":"NOX-V46-02"}
    blocked(lambda: reconcile({**master,"tasks":bad}, {}), "HOLD_R60_V46_ALIAS")
    bad = rows.copy(); bad[0] = {**rows[0], "depends_on":["R60-001"]}
    blocked(lambda: reconcile({**master,"tasks":bad}, {}), "HOLD_R60_DEPENDENCIES")
    print(f"NOX_1C_R60_PROFILE40_SELFTEST_PASS {n}/{n}; no native operation")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--master-json", type=Path)
    p.add_argument("--snapshot-json", type=Path)
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()
    if a.selftest:
        selftest(); return
    if not a.master_json or not a.snapshot_json:
        p.error("--master-json and --snapshot-json required")
    result = reconcile(json.loads(a.master_json.read_text()),
                       json.loads(a.snapshot_json.read_text()))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
