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
    return isinstance(p, str) and bool(p) and "\\" not in p and "\x00" not in p and not p.startswith("/") and all(x not in ("", ".", "..") for x in p.split("/"))

def read_archive(parts, folder, expected):
    """Stream all source parts, verify Git blob SHA-1 + reconstructed SHA-256."""
    if not folder:
        return False
    root = Path(folder)
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
    outcomes[GATES[2]] = "PASS" if len(prs) >= 15 and all(
        type(p["number"]) is int and H40.fullmatch(p["head"]) and H40.fullmatch(p["base"])
        and all(safe_path(path) for path in p["paths"]) for p in prs
    ) else "HOLD"
    owners = data["owner_map"]
    all_paths = {path for pr in prs for path in pr["paths"]}
    outcomes[GATES[3]] = "PASS" if set(owners) == all_paths and all(
        safe_path(p) and type(owner) is int and 1 <= owner <= 6 for p, owner in owners.items()
    ) else "HOLD"
    occurrences = defaultdict(list)
    for pr in prs:
        for path in pr["paths"]:
            occurrences[path].append(pr["number"])
    collisions = {path: sorted(ids) for path, ids in occurrences.items() if len(ids) > 1}
    declared = {row["path"]: sorted(row["pr_numbers"]) for row in data["conflicts"]}
    outcomes[GATES[4]] = "PASS" if declared == collisions else "HOLD"

    receipts = receipts or {}
    def valid_receipt(path):
        record = receipts.get(path, {})
        return (record.get("path") == path and record.get("owner") == owners[path]
                and record.get("run_id") == data["run_id"]
                and H64.fullmatch(record.get("pre_sha256", ""))
                and H64.fullmatch(record.get("post_sha256", ""))
                and H64.fullmatch(record.get("patch_sha256", ""))
                and H40.fullmatch(record.get("base_commit_sha1", ""))
                and record.get("tests_passed") is True)
    outcomes[GATES[5]] = "PASS" if all_paths and all(valid_receipt(path) for path in all_paths) else "HOLD"

    mismatches = data["quarantine"]
    donor_manifest = data["donors"]
    outcomes[GATES[6]] = "PASS" if len(mismatches) == 2 and len(donor_manifest) >= 3 and all(
        H64.fullmatch(row["expected_sha256"]) and H64.fullmatch(row["observed_sha256"])
        and row["expected_sha256"] != row["observed_sha256"] for row in mismatches
    ) and all(H64.fullmatch(row["declared_sha256"]) and row["drive_id"] for row in donor_manifest) else "HOLD"
    outcomes[GATES[7]] = "PASS" if data.get("sourcelock") == "VERIFIED" and data.get("host_merge") is True and data.get("events_bridge_test") == "PASS" else "HOLD"
    lanes = data["lanes"]
    outcomes[GATES[8]] = "PASS" if len(lanes) == 7 and sorted(x["owner"] for x in lanes) == list(range(1,8)) and all(
        x["progress"] is None or (type(x["progress"]) in (float,int) and 0 <= x["progress"] <= 100)
        for x in lanes
    ) else "HOLD"
    exe, e07 = data.get("exe_sha256"), data.get("e07_exe_sha256")
    release = (all(x["accepted"] is True and x["progress"] == 100 for x in lanes[:5])
               and all(outcomes[g] == "PASS" for g in GATES[:9])
               and bool(exe) and H64.fullmatch(exe) and exe == e07
               and bool(data.get("build_id")) and data.get("build_id") == data.get("e07_build_id")
               and data.get("e07_runtime") == "PASS")
    outcomes[GATES[9]] = "PASS" if release else "HOLD"
    return {
        "run_id": data["run_id"], "release": "ELIGIBLE" if release else "BLOCKED",
        "gates": outcomes, "preflight_pass": sum(x == "PASS" for x in outcomes.values()),
        "preflight_hold": sum(x == "HOLD" for x in outcomes.values()),
        "path_conflicts": collisions, "lanes": lanes, "weighted_product_progress": data["weighted_progress"]
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
