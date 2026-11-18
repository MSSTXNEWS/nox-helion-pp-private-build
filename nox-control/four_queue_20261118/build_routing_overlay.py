#!/usr/bin/env python3
"""Build a routing-only overlay from exact existing NOX registry snapshots.

This script does not import tasks into a runtime, claim tasks, set READY, or
invent executable handlers. The native reviewed catalog remains authoritative.
"""
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = "handoff/20261117/nox-v15-kit/server"
COMMIT = "e4a2fc6c5ec2e707e44896aecaa0377cee2ad3cc"
PROJECT = "https://gitlab.com/s-grouptwet/nox-helion-pp-private-build"
EXPECTED_BLOBS = {
    "work_tasks.json": "ca8f24491de0fa5fcfec12fead78fd22999f521f",
    "work_ideas.json": "6f84f315d9792cb43f08b72b062dc2f71ce1d4a6",
    "work_receipts.json": "6a9c71393735dbc4b5c1577272f22cef38ab6338",
    "NOX_SERVER_OPTIMIZATION_STAGING_20261118.json": "39c5acbcad70475ba8d3f5d78c9fce097a4cce3f",
}

def load_exact(name):
    raw = (ROOT / name).read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    assert blob == EXPECTED_BLOBS[name], (name, "source blob changed", blob)
    return json.loads(raw), {
        "path": f"{REPO_ROOT}/{name}",
        "ref": COMMIT,
        "git_blob_sha1": blob,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "url": f"{PROJECT}/-/blob/{COMMIT}/{REPO_ROOT}/{name}",
    }

def build():
    docs = {}
    sources = {}
    for name in EXPECTED_BLOBS:
        docs[name], sources[name] = load_exact(name)
    rules = json.loads((ROOT / "routing_rules.json").read_text())
    specs = docs["work_tasks.json"]["tasks"] + docs["work_ideas.json"]["ideas"]
    spec_by_id = {s["id"]: s for s in specs}
    assert len(specs) == len(spec_by_id) == 295
    plan = docs["NOX_SERVER_OPTIMIZATION_STAGING_20261118.json"]
    staged = {s["task_id"]: s for s in plan["tasks"]}
    deferred = {s["id"]: s for s in plan["deferred_external"]}
    assert not set(staged) & set(deferred)
    assert set(staged) | set(deferred) == set(spec_by_id)
    receipts = docs["work_receipts.json"]["tasks"]
    assert set(receipts) <= set(spec_by_id)
    assert set(rules["task_overrides"]) <= set(spec_by_id)
    names = {
        "Q1_RUNTIME_CHAT": "Runtime, chat, voice, UI, media and dispatcher",
        "Q2_MEMORY_KNOWLEDGE": "S03, C01-C08, knowledge, tools and retrieval",
        "Q3_TRAINING_WEIGHTS": "FORGE, model delivery, training and weights",
        "Q4_INTEGRATION_ACCEPTANCE": "Engineering integration, proof, QA and release",
    }
    tasks = []
    for s in specs:
        tid = s["id"]
        p = staged.get(tid, {})
        receipt = receipts.get(tid)
        queue = rules["task_overrides"].get(tid, rules["group_defaults"][str(s["group"])] )
        assert queue in names
        priority = p.get("priority", s.get("priority", "P2"))
        if isinstance(priority, int):
            priority = f"P{priority}"
        assert priority in ("P0", "P1", "P2", "P3"), (tid, priority)
        row = {
            "task_id": tid,
            "queue_id": queue,
            "priority": priority,
            "priority_origin": "existing_staging_plan" if "priority" in p else ("original_registry" if "priority" in s else "routing_default_P2"),
            "registry": "work_ideas.json" if tid.startswith("I-") else "work_tasks.json",
            "required_evidence": s["evidence"],
            "recorded_status": p.get("recorded_status", "DEFERRED_EXTERNAL_IN_PRIOR_PLAN"),
            "snapshot_receipt_state": receipt.get("state") if receipt else None,
            "snapshot_receipt_scope": receipt.get("scope") if receipt else None,
            "native_binding": "UNBOUND_PENDING_NATIVE_CATALOG",
        }
        if tid in deferred:
            row["prior_external_scope"] = deferred[tid]["owner"]
            row["prior_deferral_reason"] = deferred[tid]["reason"]
        tasks.append(row)
    queues = []
    for queue, title in names.items():
        rows = [r for r in tasks if r["queue_id"] == queue]
        queues.append({
            "queue_id": queue,
            "title": title,
            "task_count": len(rows),
            "priority_counts": dict(sorted(collections.Counter(r["priority"] for r in rows).items())),
            "historical_verified_receipts": sum(r["snapshot_receipt_state"] == "verified" for r in rows),
            "recorded_blocked_receipts": sum(r["snapshot_receipt_state"] == "blocked" for r in rows),
            "no_receipt_in_snapshot": sum(r["snapshot_receipt_state"] is None for r in rows),
        })
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    out = {
        "schema": "NOX_FOUR_QUEUE_ROUTING_OVERLAY_V1",
        "instructions_version": "0.0.6",
        "date": "2026-11-18",
        "generated_at": now,
        "state": "SOURCE_ROUTING_OVERLAY_NATIVE_IMPORT_NOT_PROVEN",
        "routing_only": True,
        "dispatch_cap": 3,
        "max_concurrent_workers": 3,
        "queue_count": 4,
        "coordinator": "existing OneHost",
        "worker_policy": {
            "workers": ["W1", "W2", "W3"],
            "universal_workers": True,
            "affinity": "soft_only_all_three_workers_may_claim_from_any_queue",
            "fairness": "bounded_fair_selection_from_ready_admitted_queues_with_priority_and_resource_gates",
            "idle": "wait_for_event_or_cursor_change_no_busy_spin",
            "per_task_restart": False,
            "cycle": "claim -> exact patch -> affected-risk check -> durable receipt -> release -> next",
            "historical_six_worker_specs": "retain_original_text_but_current_dispatch_cap_3_takes_precedence",
        },
        "admission_contract": {
            "routing_is_not_ready": True,
            "join_key": "task_id == canonical_registry.id == reviewed_native_catalog.id",
            "required_existing_catalog_fields": ["id", "handler", "deps", "source_sha256"],
            "binding_source": "existing native read_reviewed_catalog; no invented handlers or hashes",
            "live_state_sources": ["existing native task statuses", "existing fenced claims", "existing receipts", "owner STOP and lease"],
            "no_receipt_meaning": "no proof in this snapshot, neither a confirmed defect nor READY",
            "verified_receipt_handling": "preserve original state, scope and evidence; no automatic redispatch or native promotion",
            "existing_claim_handling": "preserve active claims; no duplicate import or takeover",
            "dependency_handling": "preserve live reviewed catalog deps; empty deps are not synthesized from missing metadata",
            "resource_handling": "existing measured CPU RAM GPU VRAM and checkpoint gates remain authoritative",
            "external_scope_handling": "include all IDs for ownership visibility; retain prior WEB release scope; routing does not authorize publication deletion or paid compute",
        },
        "coverage": {
            "canonical_task_ids": 230,
            "canonical_idea_ids": 65,
            "unique_ids": 295,
            "prior_in_scope_ids": 287,
            "prior_deferred_external_ids_included": 8,
            "duplicate_ids": 0,
            "missing_ids": 0,
            "snapshot_receipt_rows": len(receipts),
            "snapshot_verified_receipts": 11,
            "snapshot_verified_source_scope": 7,
            "snapshot_verified_native_scope": 4,
            "snapshot_blocked_receipts": 48,
            "snapshot_source_ci_pass_native_hold_receipts": 1,
            "without_receipt_in_snapshot": 235,
            "verified_executable_bindings_in_inspected_sources": 0,
            "live_native_ready_count": None,
        },
        "sources": sources,
        "source_freshness": {
            "checked_branch": "source/nox-server-fast-hot-queue-20261118",
            "method": "branch repository tree blob IDs match all four pinned source files",
            "live_native_queue_and_claim_freshness": "not_observed_by_inventory_agent",
        },
        "queues": queues,
        "tasks": tasks,
    }
    assert sum(q["task_count"] for q in queues) == 295
    assert {r["task_id"] for r in tasks} == set(spec_by_id)
    assert sum(r["snapshot_receipt_state"] == "verified" for r in tasks) == 11
    assert all(r["priority"] == staged[r["task_id"]]["priority"] for r in tasks if r["task_id"] in staged)
    path = ROOT / "NOX_FOUR_QUEUE_ROUTING_20261118.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"path":str(path), "coverage":out["coverage"], "queues":queues}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    build()
