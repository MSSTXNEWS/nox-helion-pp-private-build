#!/usr/bin/env python3
"""Read-only NOX tasks intake: prepare tasks for existing trusted FORGE scheduler.

No network, file mutations, GPU execution, automated schedules or enqueuing.
The real OneHost scheduler must re-check ACL, STOP, owner consent, and state.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "nox_onepass_task_intake.json"
LANES = {"PRIME", "S03", "COGNITIVE", "FORGE", "AUTOPILOT", "WEB"}
STATES = {"TODO", "HOLD", "DONE"}
PRIORITIES = {"P0", "P1", "P2"}

def load_tasks(path=MANIFEST):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != "nox-existing-task-intake-v1":
        raise ValueError("Unknown task manifest schema")
    ids = set()
    for row in data["tasks"]:
        if row["id"] in ids or row["lane"] not in LANES or row["state"] not in STATES or row["priority"] not in PRIORITIES:
            raise ValueError("Invalid or repeated task ID/state/lane")
        ids.add(row["id"])
        if row["execution"] != "DISCOVERY_OR_PROPOSAL_ONLY" or row["runtime_accepted"] is not False:
            raise ValueError("Runtime completion or execution was not verified")
        if not row["sources"] or any(not u.startswith("https://") for u in row["sources"]):
            raise ValueError("Task lacks provenance")
    if data["mode"] != "SOURCE_ONLY_NOT_ENQUEUED":
        raise ValueError("Task enqueue must be a separate authorized action")
    return data

def propose_for_existing_scheduler(existing_task_ids, *, stop_available=False, owner_approved=False):
    """Return structured proposal, NEVER invoke the scheduler itself."""
    data = load_tasks()
    if not stop_available or not owner_approved:
        return {"state":"HOLD_STOP_OR_OWNER_APPROVAL", "jobs_enqueued":0, "manifest_tasks":len(data["tasks"])}
    existing = set(existing_task_ids)
    proposed = [dict(row, state="PROPOSED_NOT_ENQUEUED") for row in data["tasks"] if row["id"] not in existing]
    return {"state":"PROPOSAL_ONLY", "jobs_enqueued":0, "candidate_tasks":proposed, "skipped_existing":len(data["tasks"])-len(proposed)}
