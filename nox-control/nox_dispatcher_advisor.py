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
    if snapshot.get("stop_active") is True:
        add("STOP_ACTIVE", "safety", "Keep training and automatic mutations paused.")
        return issues
    required = ("onehost", "s03", "trainer", "gpu", "disk")
    missing = [x for x in required if not isinstance(snapshot.get(x), dict)]
    if missing:
        add("TELEMETRY_MISSING", "hold", "Do not infer healthy services from missing metrics.",
            "Provide authenticated current metrics for: " + ", ".join(missing))
        return issues
    onehost, s03, trainer, gpu, disk = [snapshot[x] for x in required]
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
