"""NOX V16 E06: executable fail-closed, no-loss intake and release gate."""
import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

H40 = re.compile(r"^[0-9a-f]{40}$")
H64 = re.compile(r"^[0-9a-f]{64}$")
GATES = (
    "01_main_tree", "02_source_archive", "03_candidate_pins", "04_owner_map",
    "05_path_conflicts", "06_receipts", "07_preservation", "08_single_event_bridge",
    "09_progress_ledger", "10_release_same_exe"
)

def safe_path(p):
    """Reject cross-platform traversal, Windows ADS/devices and ambiguous names."""
    if not isinstance(p, str) or not p or p.startswith("/") or "\\\\" in p:
        return False
    if any(ord(c) < 32 or c in "\\\\:" for c in p):
        return False
    for component in p.split("/"):
        if component in ("", ".", "..") or component.endswith((" ", ".")):
            return False
        device = component.split(".")[0].upper()
        if device in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(?:COM|LPT)[1-9]", device):
            return False
    return True

def read_archive(parts, folder, expected):
    """Stream all source parts, verify Git blob SHA-1 + reconstructed SHA-256."""
    if not folder:
        return False
    root = Path(folder)
    if root.is_symlink() or not root.is_dir():
        return False
    combined = hashlib.sha256()
    for entry in parts:
        path = root / entry["path"]
        if path.is_symlink() or not path.is_file() or path.stat().st_size != entry["size_bytes"]:
            return False
        blob = hashlib.sha1()
        blob.update(b"blob " + str(entry["size_bytes"]).encode("ascii") + b"\0")
        with path.open("rb") as stream:
            while chunk := stream.read(1048576):
                combined.update(chunk)
                blob.update(chunk)
        if blob.hexdigest() != entry["git_blob_sha1"]:
            return False
    return combined.hexdigest() == expected

def audit(data, root=None, receipts=None):
    """Returns ten evidence gates. Missing evidence means HOLD, never implicit PASS."""
    outcomes = {}
    head = data["main"]
    outcomes[GATES[0]] = "PASS" if H40.fullmatch(head.get("commit_sha1", "")) and H40.fullmatch(head.get("tree_sha1", "")) and head.get("tree_truncated") is False else "HOLD"
    source = data["archive"]
    parts = source["parts"]
    structural = (len(parts) == 3 and [p["path"] for p in parts] == ["source_00.part", "source_01.part", "source_02.part"]
                  and all(H40.fullmatch(p["git_blob_sha1"]) and p["size_bytes"] > 0 for p in parts)
                  and sum(p["size_bytes"] for p in parts) == source["bytes"])
    outcomes[GATES[1]] = "PASS" if structural and read_archive(parts, root, source["expected_sha256"]) else "HOLD"
    prs = data["prs"]
    numbers = [p["number"] for p in prs]
    outcomes[GATES[2]] = "PASS" if len(prs) >= 15 and len(set(numbers)) == len(prs) and all(
        type(p["number"]) is int and p["number"] > 0
        and H40.fullmatch(p["head"]) and H40.fullmatch(p["base"])
        and p["paths"] and len(p["paths"]) == len(set(p["paths"]))
        and all(safe_path(path) for path in p["paths"]) for p in prs
    ) else "HOLD"
    owners = data["owner_map"]
    all_paths = {path for pr in prs for path in pr["paths"]}
    outcomes[GATES[3]] = "PASS" if (
        set(owners) == all_paths
        and len({p.casefold() for p in all_paths}) == len(all_paths)
        and all(safe_path(p) and type(owner) is int and 1 <= owner <= 6
                for p, owner in owners.items())
    ) else "HOLD"
    occurrences = defaultdict(list)
    for pr in prs:
        for path in pr["paths"]:
            occurrences[path].append(pr["number"])
    collisions = {path: sorted(ids) for path, ids in occurrences.items() if len(ids) > 1}
    conflict_rows = data["conflicts"]
    declared = {row["path"]: sorted(row["pr_numbers"]) for row in conflict_rows}
    outcomes[GATES[4]] = "PASS" if (
        len(declared) == len(conflict_rows)
        and all(safe_path(r["path"]) and r["path"] in owners and
                len(set(r["pr_numbers"])) == len(r["pr_numbers"]) and
                all(type(n) is int for n in r["pr_numbers"]) for r in conflict_rows)
        and declared == collisions
    ) else "HOLD"

    receipts = receipts or {}
    def valid_receipt(path):
        record = receipts.get(path, {})
        return (record.get("path") == path and record.get("owner") == owners[path]
                and record.get("run_id") == data["run_id"]
                and H64.fullmatch(record.get("pre_sha256", ""))
                and H64.fullmatch(record.get("post_sha256", ""))
                and H64.fullmatch(record.get("patch_sha256", ""))
                and H40.fullmatch(record.get("base_commit_sha1", ""))
                and record.get("tests_passed") is True
                and type(record.get("source_pr_number")) is int
                and any(p["number"] == record.get("source_pr_number")
                        and p["head"] == record.get("source_pr_head_sha1")
                        and path in p["paths"] for p in prs)
                and record.get("bytes_verified") is True)
    outcomes[GATES[5]] = "PASS" if all_paths and all(valid_receipt(path) for path in all_paths) else "HOLD"

    mismatches = data["quarantine"]
    donor_manifest = data["donors"]
    outcomes[GATES[6]] = "PASS" if (
        len(mismatches) == 2 and len({r["path"].casefold() for r in mismatches}) == 2
        and all(safe_path(r["path"]) and H64.fullmatch(r["expected_sha256"])
                and H64.fullmatch(r["observed_sha256"])
                and r["expected_sha256"] != r["observed_sha256"] for r in mismatches)
        and len(donor_manifest) >= 3
        and len({r["drive_id"] for r in donor_manifest}) == len(donor_manifest)
        and all(type(r.get("owner")) is int and 1 <= r["owner"] <= 6
                and type(r.get("size")) is int and r["size"] > 0
                and H64.fullmatch(r["declared_sha256"]) and r["drive_id"]
                for r in donor_manifest)
    ) else "HOLD"
    outcomes[GATES[7]] = "PASS" if (
        data.get("sourcelock") == "VERIFIED"
        and H64.fullmatch(data.get("source_lock_sha256") or "")
        and H64.fullmatch(data.get("canonical_bridge_sha256") or "")
        and data.get("host_merge") is True
        and data.get("host_implementation_count") == 1
        and data.get("events_bridge_test") == "PASS"
        and data.get("webview2_origin_test") == "PASS"
    ) else "HOLD"
    lanes = data["lanes"]
    def measured_lane(x):
        value = x.get("progress")
        if value is None:
            return x.get("accepted") is False
        if type(value) not in (int, float) or not 0 <= value <= 100:
            return False
        criteria = x.get("criteria")
        if not isinstance(criteria, list) or not criteria:
            return False
        ids = [r.get("task_id") for r in criteria]
        if any(not isinstance(k, str) or not k for k in ids) or len(set(ids)) != len(ids):
            return False
        if any(type(r.get("weight")) not in (int, float) or r["weight"] <= 0
               or r.get("passed") not in (True, False)
               or (r["passed"] and not H64.fullmatch(r.get("evidence_sha256") or ""))
               for r in criteria):
            return False
        if abs(sum(r["weight"] for r in criteria) - 100) > 1e-8:
            return False
        achieved = sum(r["weight"] for r in criteria if r["passed"])
        return (abs(achieved - value) < 1e-8
                and (x.get("accepted") is True) == (achieved == 100))
    lane_ok = (len(lanes) == 7 and sorted(x["owner"] for x in lanes) == list(range(1,8))
               and all(type(x["owner"]) is int and measured_lane(x) for x in lanes))
    values = {x["owner"]: x.get("progress") for x in lanes}
    expected_weighted = None
    if lane_ok and all(values.get(n) is not None for n in range(1,6)):
        expected_weighted = sum(values[n] * w for n,w in ((1,.20),(2,.25),(3,.20),(4,.25),(5,.10)))
    reported_weighted = data.get("weighted_progress")
    weighted_ok = ((expected_weighted is None and reported_weighted is None)
                   or (expected_weighted is not None and
                       type(reported_weighted) in (int,float) and
                       abs(reported_weighted - expected_weighted) < 1e-8))
    outcomes[GATES[8]] = "PASS" if lane_ok and weighted_ok else "HOLD"
    exe, e07 = data.get("exe_sha256"), data.get("e07_exe_sha256")
    release = (all(x["accepted"] is True and x["progress"] == 100 for x in lanes[:5])
               and all(outcomes[g] == "PASS" for g in GATES[:9])
               and bool(exe) and H64.fullmatch(exe) and exe == e07
               and bool(data.get("build_id")) and data.get("build_id") == data.get("e07_build_id")
               and data.get("e07_runtime") == "PASS"
               and data.get("e07_independent_owner") == 7
               and data.get("e07_acceptance") == "ACCEPTED"
               and H64.fullmatch(data.get("e07_report_sha256") or "")
               and H64.fullmatch(data.get("source_lock_sha256") or "")
               and data.get("signed_no_loss_matrix") is True)
    outcomes[GATES[9]] = "PASS" if release else "HOLD"
    return {
        "run_id": data["run_id"], "release": "ELIGIBLE" if release else "BLOCKED",
        "gates": outcomes, "preflight_pass": sum(x == "PASS" for x in outcomes.values()),
        "preflight_hold": sum(x == "HOLD" for x in outcomes.values()),
        "path_conflicts": collisions, "lanes": lanes,
        "weighted_product_progress": expected_weighted if outcomes[GATES[8]] == "PASS" else None
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", default="coordination/e06/intake.json")
    p.add_argument("--source-root", default=None, help="Local checked-out main containing exact source parts")
    p.add_argument("--receipts", default=None, help="Exact owner/path receipts JSON (do not infer)")
    p.add_argument("--out", default=None)
    a = p.parse_args()
    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    receipts = json.loads(Path(a.receipts).read_text(encoding="utf-8")) if a.receipts else None
    report = audit(manifest, a.source_root, receipts)
    body = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if a.out:
        Path(a.out).write_text(body, encoding="utf-8")
    print(body)
    return 0 if report["release"] == "ELIGIBLE" else 2

if __name__ == "__main__":
    raise SystemExit(main())
