#!/usr/bin/env python3
"""Read-only optimization hints for the EXISTING NOX dispatcher.
Never submits a job, never changes training weights, never disables STOP.
Input is locally collected evidence: metrics, queue and trainer receipts.
"""
import argparse
import datetime as dt
import json
import math
from pathlib import Path


def _finite_nonnegative(value):
    # Owner telemetry may contain JSON booleans, NaN/Infinity, or strings.
    # They must never authorize progress or crash read-only diagnostics.
    if type(value) not in (int, float) or value < 0:
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _owner_snapshot_attested(snapshot, verifier):
    """Only an injected, trusted owner-side verifier can attest JSON evidence.

    A JSON 'age', lease or CAS flag alone is never proof of provenance.
    The command-line advisor deliberately has no verifier and fails closed.
    """
    if not callable(verifier):
        return False
    try:
        return verifier(snapshot) is True
    except Exception:
        return False


def assess(snapshot, *, owner_snapshot_verifier=None):
    issues = []
    def add(code, urgency, advice, question=None):
        item = {"code": code, "urgency": urgency, "advice": advice}
        if question:
            item["question"] = question
        issues.append(item)
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot must be a JSON object")
    stop_state = snapshot.get("stop_active")
    if stop_state is True:
        add("STOP_ACTIVE", "safety", "Keep training and automatic mutations paused.")
        return issues
    if stop_state is not False:
        add("STOP_STATE_UNVERIFIED", "hold",
            "Do not advise optimization, training or native publication until "
            "a current authenticated owner STOP reading is explicitly false.")
        return issues
    required = ("onehost", "s03", "trainer", "gpu", "disk")
    missing = [x for x in required if not isinstance(snapshot.get(x), dict)]
    if missing:
        add("TELEMETRY_MISSING", "hold", "Do not infer healthy services from missing metrics.",
            "Provide authenticated current metrics for: " + ", ".join(missing))
        return issues
    onehost, s03, trainer, gpu, disk = [snapshot[x] for x in required]
    native = snapshot.get("native_queue")
    if isinstance(native, dict):
        workers = native.get("workers")
        state = native.get("admission_state")
        if (state == "NATIVE_QUEUE_REVIEWED_CATALOG_EXHAUSTED"
                and type(native.get("jobs_started")) is int
                and native["jobs_started"] == 0
                and isinstance(workers, list) and 0 < len(workers) <= 3
                and all(isinstance(w, dict)
                        and w.get("state") == "RUNNING"
                        and w.get("current_task") is None for w in workers)):
            # Original 6A02: idle workers are *not* an owner lease, task claim,
            # atomic registry snapshot, or sufficient resource admission.
            headroom = native.get("resource_headroom_bytes")
            # The verifier must check this SAME snapshot's owner provenance,
            # timestamp and lease/CAS; it cannot be supplied through JSON.
            owner_attested = _owner_snapshot_attested(
                snapshot, owner_snapshot_verifier)
            reviewable = (
                owner_attested
                and native.get("maintenance_busy") is False
                and native.get("active_claims") is False
                and type(headroom) is int and headroom >= 2*1024**3
                # A previously true lease/source flag is not a current owner
                # admission. Require a bounded age from the same snapshot.
                and type(native.get("owner_evidence_age_sec")) is int
                and 0 <= native["owner_evidence_age_sec"] <= 30
                and native.get("owner_lease_cas_verified") is True
                and native.get("immutable_task_source_verified") is True
            )
            if reviewable:
                add("NATIVE_REFILL_OWNER_REVIEW_REQUIRED", "review",
                    "Candidate only: revalidate current STOP, owner lease/CAS, exact "
                    "TaskID dedup, resource floor and pinned source at the native "
                    "publisher immediately before ONE action. This advice is not admission.")
            else:
                add("NATIVE_REFILL_OWNER_HOLD", "hold",
                    "Idle workers/catalog exhaustion do not authorize publication. "
                    "Await independently attested owner snapshot, age-bounded lease/CAS evidence, immutable source, zero active claims, "
                    "explicit maintenance clearance and >=2 GiB raw cgroup headroom; "
                    "do not duplicate queues or overwrite a pending run.")
        if native.get("maintenance_busy") is True or native.get("active_claims") is True:
            add("NATIVE_OWNER_LEASE_BUSY", "hold",
                "Do not cancel/replace a live claim or force a second publisher. Reconcile the existing owner lease and exact TaskID receipt, then retry once on new owner state.")
        headroom = native.get("resource_headroom_bytes")
        if type(headroom) is not int or headroom < 0:
            add("NATIVE_CGROUP_MEMORY_UNVERIFIED", "hold",
                "No verified raw cgroup headroom; deny extra native admission until current owner evidence.")
        elif headroom < 2*1024**3:
            add("NATIVE_CGROUP_MEMORY_PRESSURE", "urgent",
                "Keep the serving model, S03 and STOP intact. Native CPU work only with fresh low-memory admission; defer extra model/worker/RAM staging until measured headroom recovers.")
    if onehost.get("healthy") is not True:
        add("ONEHOST_DEGRADED", "urgent", "Inspect OneHost health and preserve single dispatcher; repair only by local allowlist.")
    if s03.get("readback_verified") is not True:
        add("S03_NOT_VERIFIED", "hold", "Do not claim persistent memory; verify SQLite integrity and restart readback.")
    temp = gpu.get("temperature_c")
    if "temperature_c" in gpu and not _finite_nonnegative(temp):
        add("GPU_THERMAL_READING_INVALID", "safety",
            "Invalid GPU temperature measurement; refuse new training until an authenticated sensor readback.")
    elif _finite_nonnegative(temp) and temp >= 70:
        add("GPU_THERMAL_LIMIT", "safety", "Hold new training admission; use existing host SAFE70 and sensor policy.")
    if gpu.get("temperature_sensor_valid") is not True:
        add("GPU_SENSOR_MISSING", "safety", "Do not train until trusted thermal telemetry is restored.")
    free_gib = disk.get("free_gib")
    reserve_gib = disk.get("checkpoint_reserve_gib", 10)
    if free_gib is None:
        add("DISK_UNKNOWN", "hold", "Inspect free disk and checkpoint reserve before training.")
    elif not _finite_nonnegative(free_gib) or not _finite_nonnegative(reserve_gib):
        add("DISK_TELEMETRY_UNVERIFIED", "hold",
            "Non-finite, negative or wrongly typed disk/reserve telemetry; no downloads or training admission.")
    elif free_gib < max(5, reserve_gib):
        add("DISK_CHECKPOINT_RESERVE", "urgent", "Pause new downloads and training admission; preserve existing weights, S03 and checkpoints.")
    if trainer.get("running") is True and trainer.get("checkpoint_recent") is not True:
        add("TRAIN_CHECKPOINT_STALE", "urgent", "Inspect trainer heartbeat and checkpoint write/readback; avoid blind restart.")
    if trainer.get("running") is False and trainer.get("ready_for_resume") is True:
        add("TRAIN_RESUME_CANDIDATE", "review", "Queue verified resume through existing OneHost admission; never launch another scheduler.")
    if onehost.get("chat_waiting") is True and trainer.get("running") is True:
        add("CHAT_PRIORITY", "optimize", "Request cooperative trainer yield at next safe checkpoint; do not kill process.")
    if trainer.get("running") is True:
        # Original TaskID 6A04: missing/malformed utilization is a HOLD,
        # not silent evidence of capacity or an unhandled huge-int overflow.
        util = gpu.get("utilization_pct")
        if not _finite_nonnegative(util) or util > 100:
            add("GPU_UTILIZATION_UNVERIFIED", "hold",
                "Missing, invalid or out-of-range GPU utilization; do not "
                "infer spare GPU capacity or admit additional work.")
        elif util < 35:
            # Low compute utilization alone is NOT spare accelerator capacity
            # without fresh VRAM, host I/O and chat latency.
            host = snapshot.get("cpu_io")
            values = (
                (gpu.get("vram_used_mib"), 0, 1048576),
                (gpu.get("vram_total_mib"), 1, 1048576),
                (gpu.get("age_sec"), 0, 30),
                ((host or {}).get("cpu_busy_pct") if isinstance(host,dict) else None, 0, 100),
                ((host or {}).get("io_wait_pct") if isinstance(host,dict) else None, 0, 100),
                ((host or {}).get("age_sec") if isinstance(host,dict) else None, 0, 30),
                (onehost.get("chat_p95_ms"), 0, 300000),
                (onehost.get("chat_budget_ms"), 1, 300000),
                (onehost.get("chat_metrics_age_sec"), 0, 30),
            )
            # Owner telemetry can contain JSON integers too large for
            # math.isfinite(int); keep those on the existing HOLD path.
            known = (all(_finite_nonnegative(v) and lo <= v <= hi
                         for v,lo,hi in values)
                     and type(onehost.get("chat_waiting")) is bool)
            if not known or gpu["vram_used_mib"] >= gpu["vram_total_mib"]:
                add("GPU_RESIDUAL_UNVERIFIED", "hold",
                    "GPU utilization alone cannot justify more work: require fresh "
                    "VRAM, CPU, I/O and chat latency measurements. Admit no GPU job.")
            elif onehost["chat_waiting"] or onehost["chat_p95_ms"] >= onehost["chat_budget_ms"]:
                # CHAT_PRIORITY was already emitted for a waiting chat above.
                if not onehost["chat_waiting"]:
                    add("GPU_CHAT_PRIORITY", "hold",
                        "Chat latency at its budget takes priority; no GPU spare allocation.")
            elif host["cpu_busy_pct"] >= 85 or host["io_wait_pct"] >= 10:
                add("GPU_HOST_PIPELINE_PRESSURE", "hold",
                    "Host CPU/I/O pressure blocks further GPU work despite low compute utilization.")
            else:
                cap = round(85 - util, 2)
                add("GPU_RESIDUAL_OBSERVED_NOT_ADMITTED", "observe",
                    f"Measured utilization-only upper bound to the 85% limit: {cap} percentage points. "
                    "VRAM is not a per-job allocation; no admission, trainer restart or new queue authorized.")
    if not issues:
        add("NO_UNVERIFIED_TUNING", "observe", "No changes recommended without measured before/after and readback.")
    return issues

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    data = json.loads(Path(args.snapshot).read_text(encoding="utf8"))
    report = {"schema_version":1,"observed_at":dt.datetime.now(dt.timezone.utc).isoformat(),
              "mode":"read_only", "advice": assess(data)}
    path = Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(json.dumps(report,ensure_ascii=False))

if __name__ == "__main__":
    main()
