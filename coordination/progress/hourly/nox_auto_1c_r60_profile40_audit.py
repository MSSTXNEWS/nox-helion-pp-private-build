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


def _trusted(cb, *args):
    """Original owner-native callbacks only: unknown, exception or integer 1 is never proof."""
    if not callable(cb):
        return False
    try:
        return cb(*args) is True
    except Exception:
        return False


def reconcile(master: Mapping, snapshot: Mapping, *, verify_job=None,
              verify_s03=None, verify_worker=None, verify_dependency=None) -> dict:
    """Read-only source audit. 3 actual OS PIDs != 6 threads != 40/60 task IDs."""
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
    if len(workers) > 3:
        raise ValueError("HOLD_THREE_NATIVE_OS_PROCESS_BOUND")
    threads = snapshot.get("internal_threads")
    if threads is not None and (type(threads) is not int or not 0 <= threads <= 6):
        raise ValueError("HOLD_INTERNAL_THREADS_BOUND")
    seen, verified_workers = set(), 0
    for worker in workers:
        if not isinstance(worker, Mapping):
            raise ValueError("HOLD_WORKER_IDENTITIES")
        wid, pid, start = worker.get("id"), worker.get("pid"), worker.get("process_starttime")
        if (not isinstance(wid, str) or not JOB.fullmatch(wid)
                or type(pid) is not int or pid <= 1
                or type(start) is not int or start <= 0
                or (wid, pid, start) in seen
                or any(x[1] == pid for x in seen)):
            raise ValueError("HOLD_WORKER_IDENTITIES")
        seen.add((wid, pid, start))
        shape = (worker.get("instance_id") == 60509551
                 and worker.get("origin") == "existing_onehost"
                 and worker.get("native_pid_verified") is True
                 and worker.get("state") == "RUNNING")
        if shape and _trusted(verify_worker, worker, snapshot):
            verified_workers += 1
    if len(jobs) > 60:
        raise ValueError("HOLD_JOB_LIST_BOUNDS")
    job_ids, task_ids, queue_verified, s03_verified = set(), set(), [], []
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
        hashes = (isinstance(job.get("registry_sha256"), str)
                  and SHA.fullmatch(job["registry_sha256"]) is not None
                  and isinstance(job.get("s03_sha256"), str)
                  and SHA.fullmatch(job["s03_sha256"]) is not None)
        if hashes and _trusted(verify_job, by_id[tid], job, snapshot):
            queue_verified.append(tid)
            if _trusted(verify_s03, by_id[tid], job, snapshot):
                s03_verified.append(tid)
    profile = {f"R60-{i:03}" for i in range(1, 41)}
    verified = sorted(profile.intersection(s03_verified))
    queue_profile = sorted(profile.intersection(queue_verified))
    external = sorted({dep for tid in profile for dep in by_id[tid]["depends_on"] if dep not in profile})
    external_unknown = [d for d in external if not _trusted(verify_dependency, d, snapshot)]
    return {
        "schema": "NOX_1C_R60_PROFILE40_EVIDENCE_V2",
        "scope": "READ_ONLY_EXISTING_ONEHOST",
        "source_tasks": 60,
        "working_profile_source_tasks": 40,
        "os_process_target": 3,
        "workers_observed_untrusted": len(workers),
        "workers_callback_verified": verified_workers,
        "internal_threads_observed_untrusted": threads,
        "jobs_observed_untrusted": len(jobs),
        "profile_queue_jobs_callback_verified": len(queue_profile),
        "profile_s03_receipts_independently_verified": len(verified),
        "profile_verified_task_ids": verified,
        "outside_profile_dependencies": external,
        "outside_dependencies_unverified": external_unknown,
        "native_state": "CALLBACK_VERIFIED_PARTIAL" if verified and verified_workers == 3 else "HOLD_NO_INDEPENDENT_NATIVE_PROOF",
        "source_only": not bool(verified and verified_workers == 3),
        "note": "Three OS PIDs, six internal threads, forty profile tasks and sixty logical tasks are distinct",
    }


def selftest():
    rows = [{"task_id": f"R60-{i:03}", "legacy_task_id": f"NOX-V46-{i:02}",
             "depends_on": [f"R60-{i-1:03}"] if i > 1 else []} for i in range(1, 61)]
    rows[19]["depends_on"] = ["R60-056"]
    master = {"schema": "NOX_R60_SOURCE_PLAN_V1", "tasks": rows}
    workers = [{"id": f"w{i}", "pid": 120+i, "process_starttime": 800+i,
                "instance_id": 60509551, "origin": "existing_onehost",
                "native_pid_verified": True, "state": "RUNNING"} for i in range(3)]
    job = {"task_id": "R60-001", "job_id": "job1",
           "registry_sha256": "a"*64, "s03_sha256": "b"*64}
    snapshot = {"workers": workers, "internal_threads": 6, "jobs": [job]}
    n = 0
    def check(value):
        nonlocal n
        assert value
        n += 1
    none = reconcile(master, snapshot)
    check(none["source_only"] and none["os_process_target"] == 3)
    check(none["internal_threads_observed_untrusted"] == 6 and none["workers_callback_verified"] == 0)
    check(none["outside_dependencies_unverified"] == ["R60-056"])
    native = dict(verify_worker=lambda w,s: True, verify_job=lambda t,j,s: True,
                  verify_s03=lambda t,j,s: True)
    good = reconcile(master, snapshot, **native)
    check(good["profile_s03_receipts_independently_verified"] == 1 and good["workers_callback_verified"] == 3)
    check(good["native_state"] == "CALLBACK_VERIFIED_PARTIAL")
    check(reconcile(master, {"jobs":[job]}, verify_job=lambda *a: True)["profile_s03_receipts_independently_verified"] == 0)
    check(reconcile(master, {"jobs":[job]}, verify_job=lambda *a: True,
                    verify_s03=lambda *a: 1)["profile_s03_receipts_independently_verified"] == 0)
    check(reconcile(master, {"workers":[{"id":"w","pid":3,"process_starttime":1}]},
                    verify_worker=lambda *a: True)["workers_callback_verified"] == 0)
    check(reconcile(master, {"jobs":[job]}, verify_job=lambda *a: 1,
                    verify_s03=lambda *a: True)["profile_queue_jobs_callback_verified"] == 0)
    def explode(*args): raise RuntimeError("synthetic failure")
    check(reconcile(master, {"jobs":[job]}, verify_job=explode)["profile_queue_jobs_callback_verified"] == 0)
    check(reconcile(master, {"jobs":[job]}, verify_job=lambda *a: True,
                    verify_s03=lambda *a: True,
                    verify_dependency=lambda d,s: d == "R60-056")["outside_dependencies_unverified"] == [])
    def blocked(fn, expected):
        try: fn()
        except ValueError as exc: check(str(exc) == expected)
        else: raise AssertionError("missing gate " + expected)
    blocked(lambda: reconcile(master, {"workers": workers + [{"id":"w4"}]}), "HOLD_THREE_NATIVE_OS_PROCESS_BOUND")
    blocked(lambda: reconcile(master, {"internal_threads": 7}), "HOLD_INTERNAL_THREADS_BOUND")
    blocked(lambda: reconcile(master, {"workers": [workers[0], workers[0]]}), "HOLD_WORKER_IDENTITIES")
    blocked(lambda: reconcile(master, {"workers": [workers[0], {**workers[1], "pid": workers[0]["pid"]}]}), "HOLD_WORKER_IDENTITIES")
    blocked(lambda: reconcile(master, {"jobs": [job,job]}), "HOLD_DUPLICATED_JOB_OR_TASK")
    blocked(lambda: reconcile(master, {"jobs": [{**job, "task_id":"R60-061"}]}), "HOLD_UNKNOWN_OR_INVALID_JOB")
    blocked(lambda: reconcile({**master, "tasks":rows[:-1]}, {}), "HOLD_R60_MASTER_60_ROWS")
    bad = rows.copy(); bad[0] = {**rows[0], "legacy_task_id":"NOX-V46-02"}
    blocked(lambda: reconcile({**master, "tasks":bad}, {}), "HOLD_R60_V46_ALIAS")
    bad = rows.copy(); bad[0] = {**rows[0], "depends_on":["R60-001"]}
    blocked(lambda: reconcile({**master, "tasks":bad}, {}), "HOLD_R60_DEPENDENCIES")
    print(f"NOX_1C_POOL3_PROFILE40_SELFTEST_PASS {n}/{n}; synthetic only, no native operation")


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
