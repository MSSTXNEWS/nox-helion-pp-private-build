#!/usr/bin/env python3
"""E06 EXPRESS FINISH: mandatory truthful per-run report (never release approval).

All technical statuses default to HOLD/NOT_RUN. Source/installer readiness is NOT
product acceptance; only independent E07 is authorized to accept the release.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, pathlib, re, sys

LANES = (
    ("E01", "D02/NSIS", 0.20),
    ("E02", "Ollama/SQLite/Voice", 0.25),
    ("E03", "ModelCenter", 0.20),
    ("E04", "RAG/GPU", 0.25),
    ("E05", "events.v3/SPACE", 0.10),
    ("E06", "one-host integration", None),
    ("E07", "same-SHA independent Windows QA", None),
)
GATES = ("CI_EXECUTED", "SOURCELOCK_729_ACCEPTED",
         "COMBINED_NSIS_INSTALLED", "ONE_HOST_FUNCTIONS_ACCEPTED",
         "E07_SAME_SHA_ACCEPTED")
ALLOWED = {"PASS", "HOLD", "FAIL", "NOT_RUN"}
def digest(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--event", default="CI_FINAL")
    ap.add_argument("--gate", action="append", default=[],
                    help="NAME=PASS/HOLD/FAIL/NOT_RUN; unmentioned gates default HOLD")
    ap.add_argument("--installer", type=pathlib.Path)
    ap.add_argument("--installer-receipt", type=pathlib.Path)
    args = ap.parse_args()
    run = os.getenv("GITHUB_RUN_ID", "LOCAL-UNVERIFIED")
    attempt = os.getenv("GITHUB_RUN_ATTEMPT", "0")
    commit = os.getenv("GITHUB_SHA", "UNKNOWN")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", run):
        raise SystemExit("INVALID_RUN_ID")
    statuses = {name: "HOLD" for name in GATES}
    for item in args.gate:
        if "=" not in item:
            raise SystemExit("INVALID_GATE_ARGUMENT")
        k, v = item.split("=", 1)
        if k not in statuses or v not in ALLOWED:
            raise SystemExit("UNKNOWN_GATE_OR_STATUS")
        statuses[k] = v
    # Actual runner execution is proved only by reaching this script in CI.
    if os.getenv("GITHUB_ACTIONS") == "true":
        statuses["CI_EXECUTED"] = "PASS"
    if statuses["E07_SAME_SHA_ACCEPTED"] == "PASS":
        raise SystemExit("INDEPENDENT_E07_ONLY_NO_SELF_ACCEPTANCE")
    receipt = None
    if args.installer_receipt is not None and args.installer_receipt.is_file():
        receipt = json.loads(args.installer_receipt.read_text(encoding="utf-8-sig"))
    installer = None
    if args.installer is not None and args.installer.is_file():
        installer = {"path": str(args.installer), "bytes": args.installer.stat().st_size,
                     "sha256": digest(args.installer)}
        if receipt and receipt.get("installer_sha256") != installer["sha256"]:
            statuses["COMBINED_NSIS_INSTALLED"] = "HOLD"
            installer["receipt_match"] = False
        elif receipt:
            installer["receipt_match"] = True
    # No installer compilation alone can credit combined install acceptance.
    if installer is None:
        statuses["COMBINED_NSIS_INSTALLED"] = "HOLD"
    accepted = sum(v == "PASS" for v in statuses.values())
    lanes = [{"owner": name, "scope": scope, "weight": weight,
              "accepted_tasks": None, "total_tasks": None,
              "accepted_percent": None, "integrated": "HOLD",
              "windows_accepted": "NOT_RUN"} for name, scope, weight in LANES]
    result = {
        "schema": "NOX_V16_E06_EXPRESS_PER_RUN_V1",
        "run_id": run, "attempt": attempt, "commit": commit,
        "event": args.event, "time_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "task_id": "NOX-V16-E06-EXPRESS",
        "gates": statuses, "accepted_gates": accepted,
        "total_gates": len(GATES), "remaining_gates": len(GATES) - accepted,
        "gate_completion_percent": round(100 * accepted/len(GATES), 2),
        "development_percent": None, "weighted_product_percent": None,
        "product_formula": "0.20*E01 + 0.25*E02 + 0.20*E03 + 0.25*E04 + 0.10*E05",
        "seven_indicators": lanes, "installer_evidence": installer,
        "release_accepted": False, "e07_accepted": False,
        "source_no_loss": "UNCHANGED_BY_REPORT",
        "note": "This receipt is a per-run observation, not E07 acceptance.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    summary = "\n".join([
        "## NOX E06 EXPRESS · mandatory per-run report",
        f"RunID: {run}, attempt {attempt}, commit {commit}",
        f"Accepted stages: {accepted}/{len(GATES)} ({result['gate_completion_percent']}%); remaining {len(GATES)-accepted}",
        "Final product acceptance: HOLD; weighted readiness: N/D.",
        "Seven lanes E01-E07: N/D until accepted canonical TaskID receipts.",
        "Gates: " + "; ".join(f"{k}={v}" for k,v in statuses.items()),
        ("Installer SHA256: " + installer["sha256"]) if installer else "Installer: not observed on this run",
    ]) + "\n"
    print(summary)
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(summary)
if __name__ == "__main__":
    main()
