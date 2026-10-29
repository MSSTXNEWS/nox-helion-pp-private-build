#!/usr/bin/env python3
"""NOX R29 — compile truthful executor inventory from authorized scheduler export.

Inputs:
  roster.json: owner-approved role membership / authorizations
  scheduler.json: normalized, complete authenticated Automations.list + peek results
  control_data.js: existing NOX_CONTROL_DATA (preserve all product history)
No network, no writes to services; emits two updated JS files after validation.
Never changes task status to QA_ACCEPTED or archives an ID just for being disabled.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime


def read_js(path, variable):
    raw = Path(path).read_text(encoding="utf-8")
    prefix = "window." + variable + "="
    if prefix not in raw:
        raise ValueError("EXPECTED_DATA_BINDING_MISSING")
    return json.loads(raw.split(prefix, 1)[1].strip().rstrip(";"))


def positive_iso(value):
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def reconcile(roster, exported, data):
    if roster.get("schema") != "NOX_R29_EXECUTOR_ROSTER_V1":
        raise ValueError("UNKNOWN_ROSTER_SCHEMA")
    if exported.get("schema") != "NOX_R29_AUTHENTICATED_SCHEDULER_EXPORT_V1" or exported.get("complete") is not True:
        raise ValueError("INCOMPLETE_OR_UNAUTHENTICATED_SCHEDULER_EXPORT")
    if not positive_iso(exported.get("observed_at")):
        raise ValueError("OBSERVATION_TIME_REQUIRED")
    if data.get("schema") != "NOX_CONTROL_CENTER_R26_SNAPSHOT_V1":
        raise ValueError("UNSUPPORTED_CONTROL_SNAPSHOT")
    roles = roster.get("owner_manual_roles")
    if not isinstance(roles, list) or any(not isinstance(r, dict) or not r.get("id") for r in roles):
        raise ValueError("INVALID_MANUAL_ROSTER")
    mid = [str(r["id"]) for r in roles if r.get("scope") == "current"]
    if len(set(mid)) != len(mid):
        raise ValueError("DUPLICATE_MANUAL_ROLE")
    manual_before = {str(m.get("id")): m for m in data.get("manuals", [])}
    data["manuals"] = [
        dict(manual_before.get(rid, {}), id=rid,
             role=next(r["role"] for r in roles if str(r["id"]) == rid),
             registry_scope="current")
        for rid in mid
    ]
    mapped = roster.get("automation_roles")
    if not isinstance(mapped, list):
        raise ValueError("AUTOMATION_ROSTER_REQUIRED")
    role_ids = [str(x.get("id")) for x in mapped]
    if len(set(role_ids)) != len(role_ids) or any(not x for x in role_ids):
        raise ValueError("DUPLICATE_OR_MISSING_AUTOMATION_ID")
    approved = {str(x["id"]): x["scope"] for x in mapped}
    if any(x not in ("current", "historical", "unassigned") for x in approved.values()):
        raise ValueError("INVALID_AUTOMATION_SCOPE")
    records = exported.get("automations")
    if not isinstance(records, list):
        raise ValueError("AUTOMATIONS_ARRAY_REQUIRED")
    seen = set()
    before = {x["id"]: x for x in data.get("automations", []) if x.get("id")}
    by_run = {}
    for raw in records:
        if not isinstance(raw, dict):
            raise ValueError("INVALID_SCHEDULER_RECORD")
        rid = raw.get("id")
        if not isinstance(rid, str) or not rid or rid in seen:
            raise ValueError("DUPLICATE_SCHEDULER_RECORD")
        seen.add(rid)
        enabled = raw.get("is_enabled")
        if type(enabled) is not bool:
            raise ValueError("SCHEDULER_ENABLED_STATUS_REQUIRED")
        run = raw.get("last_run")
        if run is not None:
            if not isinstance(run, dict) or run.get("status") not in ("completed", "failed", "in_progress", "no_update"):
                raise ValueError("INVALID_LAST_RUN_STATUS")
            if not positive_iso(run.get("started_at")):
                raise ValueError("RUN_STARTED_AT_REQUIRED")
            if run.get("completed_at") and not positive_iso(run["completed_at"]):
                raise ValueError("RUN_COMPLETED_AT_INVALID")
        scope = approved.get(rid, "unassigned")
        record = dict(before.get(rid, {}), id=rid, title=str(raw.get("title") or rid),
                      enabled=enabled,
                      kind="source_support" if scope == "current" else "legacy_or_future",
                      registry_scope=scope)
        before[rid] = record
        by_run[rid] = {"id": rid, "title": record["title"], "enabled": enabled,
                       "scope": scope, "schedule": raw.get("schedule"),
                       "last_run": run}
    missing = sorted(set(approved) - seen)
    # Never silently delete historical ID; keep its last-known status but mark missing.
    for rid in missing:
        old = before.get(rid, {"id": rid, "title": rid, "enabled": False})
        old["registry_scope"] = approved[rid]
        old["kind"] = "source_support" if approved[rid] == "current" else "legacy_or_future"
        old["scheduler_observation"] = "MISSING_FROM_COMPLETE_EXPORT_UNVERIFIED"
        before[rid] = old
        by_run[rid] = {"id": rid, "title": old["title"], "enabled": None,
                       "scope": approved[rid], "schedule": None, "last_run": None}
    data["automations"] = list(before.values())
    data["automation_counts"] = {
        "defined_in_scheduler": len(seen),
        "current_roster": sum(x.get("registry_scope") == "current" for x in data["automations"]),
        "current_enabled_confirmed": sum(x.get("registry_scope") == "current" and x.get("id") in seen and x.get("enabled") is True for x in data["automations"]),
        "historical": sum(x.get("registry_scope") == "historical" for x in data["automations"]),
        "unassigned": sum(x.get("registry_scope") == "unassigned" for x in data["automations"]),
        "missing_in_scheduler": len(missing),
    }
    data["manual_count"] = len(mid)
    data["snapshot_type"] = "AUTHENTICATED_EXECUTOR_INVENTORY_ONLY_NOT_PRODUCT_QA"
    data["executor_inventory_observed_at"] = exported["observed_at"]
    data["executor_registry_notice"] = "Scheduler confirms existence, enabled and last-run. Journal/independent QA confirms product results."
    schedule = {
        "schema": "NOX_R29_SCHEDULE_SNAPSHOT_V1",
        "observed_at": exported["observed_at"],
        "last_run_observed_at": exported["observed_at"],
        "source": "authenticated Automations.list + Automations.peek export",
        "tasks": list(by_run.values()),
        "missing_ids": missing,
        "complete": not missing,
    }
    return data, schedule


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("roster")
    ap.add_argument("scheduler_export")
    ap.add_argument("control_data_js")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    roster = json.loads(Path(args.roster).read_text(encoding="utf-8"))
    observed = json.loads(Path(args.scheduler_export).read_text(encoding="utf-8"))
    original = read_js(args.control_data_js, "NOX_CONTROL_DATA")
    data, runs = reconcile(roster, observed, original)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "nox-control-data.js").write_text("window.NOX_CONTROL_DATA=" + json.dumps(data, ensure_ascii=False, indent=2) + ";\n", encoding="utf-8")
    (out / "nox-schedule-r29.js").write_text("window.NOX_SCHEDULE_SNAPSHOT=" + json.dumps(runs, ensure_ascii=False, indent=2) + ";\n", encoding="utf-8")
    print(json.dumps({"current": data["automation_counts"]["current_roster"],
                      "enabled": data["automation_counts"]["current_enabled_confirmed"],
                      "historical": data["automation_counts"]["historical"],
                      "unassigned": data["automation_counts"]["unassigned"],
                      "missing": runs["missing_ids"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
