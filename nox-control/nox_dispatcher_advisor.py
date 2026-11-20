#!/usr/bin/env python3
"""Read-only optimization hints for the EXISTING NOX dispatcher.
Never submits a job, never changes training weights, never disables STOP.
Input is locally collected evidence: metrics, queue and trainer receipts.
"""
import argparse
import datetime as dt
import json
from pathlib import Path

def assess(snapshot):
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
                and native.get("jobs_started") == 0 and isinstance(workers, list)
                and workers and all(isinstance(w,dict)
                                    and w.get("state") == "RUNNING"
                                    and w.get("current_task") is None for w in workers)):
            add("IDLE_NATIVE_CATALOG_EXHAUSTED", "urgent",
                "Keep healthy workers running. Publish one current exact TaskID through the existing owner/CAS reviewed publisher; a relay manifest is not executable. Do not duplicate old or terminal tasks.")
        if native.get("maintenance_busy") is True or native.get("active_claims") is True:
            add("NATIVE_OWNER_LEASE_BUSY", "hold",
                "Do not cancel/replace a live claim or force a second publisher. Reconcile the existing owner lease and exact TaskID receipt, then retry once on new owner state.")
        if type(native.get("resource_headroom_bytes")) is int and native["resource_headroom_bytes"] < 2*1024**3:
            add("NATIVE_CGROUP_MEMORY_PRESSURE", "urgent",
                "Keep the serving model, S03 and STOP intact. Native CPU work only with fresh low-memory admission; defer extra model/worker/RAM staging until measured headroom recovers.")
    if onehost.get("healthy") is not True:
        add("ONEHOST_DEGRADED", "urgent", "Inspect OneHost health and preserve single dispatcher; repair only by local allowlist.")
    if s03.get("readback_verified") is not True:
        add("S03_NOT_VERIFIED", "hold", "Do not claim persistent memory; verify SQLite integrity and restart readback.")
    temp = gpu.get("temperature_c")
    if isinstance(temp, (int, float)) and not isinstance(temp, bool) and temp >= 70:
        add("GPU_THERMAL_LIMIT", "safety", "Hold new training admission; use existing host SAFE70 and sensor policy.")
    if gpu.get("temperature_sensor_valid") is not True:
        add("GPU_SENSOR_MISSING", "safety", "Do not train until trusted thermal telemetry is restored.")
    if disk.get("free_gib") is None or not isinstance(disk.get("free_gib"), (int,float)):
        add("DISK_UNKNOWN", "hold", "Inspect free disk and checkpoint reserve before training.")
    elif disk["free_gib"] < max(5, float(disk.get("checkpoint_reserve_gib", 10))):
        add("DISK_CHECKPOINT_RESERVE", "urgent", "Pause new downloads and training admission; preserve existing weights, S03 and checkpoints.")
    if trainer.get("running") is True and trainer.get("checkpoint_recent") is not True:
        add("TRAIN_CHECKPOINT_STALE", "urgent", "Inspect trainer heartbeat and checkpoint write/readback; avoid blind restart.")
    if trainer.get("running") is False and trainer.get("ready_for_resume") is True:
        add("TRAIN_RESUME_CANDIDATE", "review", "Queue verified resume through existing OneHost admission; never launch another scheduler.")
    if onehost.get("chat_waiting") is True and trainer.get("running") is True:
        add("CHAT_PRIORITY", "optimize", "Request cooperative trainer yield at next safe checkpoint; do not kill process.")
    if trainer.get("running") is True and gpu.get("utilization_pct") is not None:
        util = gpu["utilization_pct"]
        if isinstance(util, (int,float)) and not isinstance(util,bool) and util < 35:
            add("LOW_GPU_UTILIZATION", "investigate", "Profile input pipeline, batching and context length; benchmark before tuning.")
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
