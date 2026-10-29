#!/usr/bin/env python3
"""NOX V16: strict read-only progress monitor for THREE primary manual owners.

Input is a separately verified evidence snapshot, never a claimed release receipt.
No external dependencies; never alters Git/GitLab/Drive or authorizes CI.
"""
import argparse
import json
import re
import sys
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")
ROLES = ("1", "3", "2")
GATES = ("A", "B", "C", "D", "E")
STAGES = ("SOURCE_PREPARED", "SOURCE_VERIFIED", "INTEGRATED", "QA_ACCEPTED")
STATES = ("PASS", "PARTIAL", "BLOCKED", "NOT_RUN")


def bar(value, total, width=10):
    if not isinstance(value, int) or not isinstance(total, int) or total <= 0 or value < 0 or value > total:
        return "N/D"
    filled = value * width // total
    return "█" * filled + "░" * (width - filled) + " " + str(value) + "/" + str(total)


def sha(value):
    return type(value) is str and SHA.fullmatch(value) is not None


def proof_gate(gate):
    return (isinstance(gate, dict) and gate.get("status") == "PASS"
            and isinstance(gate.get("proof"), str) and len(gate["proof"].strip()) >= 12)


def validate_snapshot(snapshot, expected_head=None):
    errors = []
    if type(snapshot) is not dict or snapshot.get("schema") != "NOX_V16_R25_MANUAL_FIRST_OTCH1_V1":
        return ["SCHEMA_INVALID"]
    head = snapshot.get("head")
    if not sha(head):
        errors.append("INVALID_HEAD")
    if expected_head is not None and head != expected_head:
        errors.append("STALE_HEAD")
    reports = snapshot.get("manuals")
    if type(reports) is not list or len(reports) != 3:
        return errors + ["EXACTLY_THREE_MANUALS_REQUIRED"]
    role_ids = [r.get("role") for r in reports if isinstance(r, dict)]
    if sorted(role_ids) != sorted(ROLES):
        errors.append("MANUAL_ROLES_MISSING_OR_DUPLICATED")
    for r in reports:
        if not isinstance(r, dict):
            errors.append("BAD_MANUAL_REPORT")
            continue
        role = str(r.get("role"))
        gates = r.get("gates")
        if type(gates) is not dict or set(gates) != set(GATES):
            errors.append("GATES_INCOMPLETE_ROLE_" + role)
            continue
        for key in GATES:
            g = gates[key]
            if type(g) is not dict or g.get("status") not in STATES:
                errors.append("INVALID_GATE_" + role + "_" + key)
            elif g["status"] == "PASS" and not proof_gate(g):
                errors.append("UNPROVEN_PASS_" + role + "_" + key)
        approaches = r.get("approaches")
        if not isinstance(approaches, list) or len(approaches) > 10:
            errors.append("INVALID_APPROACHES_" + role)
        else:
            numbered = [a.get("number") for a in approaches if isinstance(a, dict)]
            if numbered != list(range(1, len(approaches) + 1)):
                errors.append("APPROACH_ORDER_INVALID_" + role)
        tasks = r.get("tasks", [])
        if type(tasks) is not list:
            errors.append("INVALID_TASKS_" + role)
            continue
        seen = set()
        for task in tasks:
            if type(task) is not dict or not isinstance(task.get("task_id"), str) or not task["task_id"]:
                errors.append("INVALID_TASK_" + role)
                continue
            tid = task["task_id"]
            if tid in seen:
                errors.append("DUPLICATE_TASK_" + role + "_" + tid)
            seen.add(tid)
            if task.get("stage") not in STAGES:
                errors.append("INVALID_STAGE_" + role + "_" + tid)
            if task.get("stage") == "QA_ACCEPTED":
                evidence = task.get("qa", {})
                if not (role == "2" and isinstance(evidence, dict)
                        and evidence.get("reviewer") == "manual-2"
                        and evidence.get("pass") is True
                        and evidence.get("head") == head
                        and sha(evidence.get("receipt_blob"))):
                    errors.append("QA_ACCEPTED_WITHOUT_INDEPENDENT_PROOF_" + role + "_" + tid)
    if snapshot.get("product_percent") is not None:
        errors.append("PRODUCT_PERCENT_UNSUPPORTED_WITHOUT_FROZEN_LEDGER")
    return errors


def render(snapshot, issues):
    head = snapshot.get("head", "UNKNOWN")
    lines = ["# NOX V16 · ОТЧ-1 · MANUAL FIRST",
             "HEAD: \`" + str(head) + "\` | verification: " + ("CHECK_INPUT" if issues else "INPUT_CONSISTENT"),
             "These bars represent *evidence in this snapshot*, not verified product acceptance unless independently signed.",
             ""]
    for role in ROLES:
        matches = [r for r in snapshot.get("manuals", []) if isinstance(r, dict) and r.get("role") == role]
        if not matches:
            lines.append("Manual №" + role + ": NOT_REPORTED")
            continue
        r = matches[0]
        gates = r.get("gates", {})
        pass_count = sum(proof_gate(gates.get(k)) for k in GATES)
        approaches = r.get("approaches", []) if isinstance(r.get("approaches"), list) else []
        complete = sum(isinstance(a, dict) and a.get("status") == "DONE" and
                       isinstance(a.get("proof"), str) and len(a["proof"].strip()) >= 12
                       for a in approaches)
        tasks = r.get("tasks", [])
        prepared = sum(t.get("stage") == "SOURCE_PREPARED" for t in tasks)
        verified = sum(t.get("stage") == "SOURCE_VERIFIED" for t in tasks)
        integrated = sum(t.get("stage") == "INTEGRATED" for t in tasks)
        accepted = sum(t.get("stage") == "QA_ACCEPTED" and
                       isinstance(t.get("qa"), dict) and t["qa"].get("reviewer") == "manual-2"
                       and t["qa"].get("pass") is True and t["qa"].get("head") == head
                       and sha(t["qa"].get("receipt_blob")) for t in tasks)
        d = r.get("frozen_denominator")
        lines += ["## Manual №" + role + " — " + str(r.get("role_name", "UNNAMED")),
                  "Approaches: " + (bar(complete, 10) if r.get("approaches_logged") is True else "N/D (legacy report lacks 10-step evidence)"),
                  "Gates A–E: " + bar(pass_count, 5),
                  "Accepted fixed criteria: " + bar(accepted, d),
                  "Stages (reported, not additive): PREPARED " + str(prepared) +
                  "; VERIFIED " + str(verified) + "; INTEGRATED " + str(integrated) +
                  "; QA_ACCEPTED " + str(accepted),
                  "Run status: " + str(r.get("run_status", "UNKNOWN")) +
                  "; source proof: " + str(r.get("proof_ref", "MISSING")), ""]
    lines += ["Shared journal: " + json.dumps(snapshot.get("journal", {}), ensure_ascii=False),
              "Error register: " + json.dumps(snapshot.get("error_register", {}), ensure_ascii=False),
              "Pre-build stage: STALE_NOT_RECHECKED unless independently revalidated at this HEAD.",
              "PRODUCT: N/D (full frozen accepted functional TaskID ledger unavailable)."]
    if issues:
        lines += ["", "## CONTROL FAILURES", *["- " + x for x in issues]]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--current-head", help="40-char source PR HEAD from fresh authorized GitHub read")
    args = parser.parse_args(argv)
    data = json.loads(args.snapshot.read_text(encoding="utf-8"))
    failures = validate_snapshot(data, expected_head=args.current_head)
    print(render(data, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
