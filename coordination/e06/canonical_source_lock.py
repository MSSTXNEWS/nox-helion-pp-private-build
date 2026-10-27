"""E06 R03: byte-proven NOX original Python application SourceLock, no extraction.

This is an ORIGINAL BASELINE SEAL, not a merged-application seal or release attestation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile
from pathlib import Path

EXPECTED_ARCHIVE = "ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a"
EXPECTED_BYTES = 60364346
EXPECTED_FILES = 729
MAX_UNCOMPRESSED = 1024 * 1024 * 1024
MAX_MEMBER = 200 * 1024 * 1024
HOST_FILES = ("run_helion.py", "helion/app.py", "helion/desktop_routes.py", "helion/e06_route_adapter.py")
CRITICAL = {
    "D02_APPROVED": ("assets/HOME_OWNER_APPROVED.png", "assets/asset_manifest.json",
                     "assets/approved_ui/NOX_HELION_MENU_OWNER_APPROVED_20261019.png"),
    "PERSONAS": ("assets/personas_5.json", "helion/personas.py"),
    "CORE_CHAT": ("helion/ai_core_runtime.py", "helion/core_chat_bridge.py"),
    "VOICE": ("helion_voice/service.py", "helion_voice/integration.py"),
    "ROUTES": ("helion/desktop_routes.py", "helion/e06_route_adapter.py"),
    "WEIGHTS": ("helion/ai_weights/weights/MODEL_FEATURE_CONTRACT.json",),
    "WINDOWS_BUILD": ("build_windows.ps1", "C_RELEASE_SPRINT_BUILD.ps1",
                      "tools/windows_candidate_v23/build_windows_candidate.ps1"),
    "SECURITY": ("helion_security.py", "helion_scoped_capabilities.py"),
}
NO_RELEASE = "ORIGINAL_BASELINE_ONLY_NOT_INTEGRATED"

def safe_member(info):
    """Reject nonportable/colliding ZIP members before even reading their bytes."""
    name = info.filename
    if not isinstance(name, str) or not name or name.startswith(("/", "\\")) or "\\" in name:
        raise ValueError("ZIP_UNSAFE_PATH")
    if any(ord(c) < 32 or c == ":" for c in name):
        raise ValueError("ZIP_UNSAFE_CHAR")
    pieces = name.rstrip("/").split("/")
    if not pieces or any(x in ("", ".", "..") or x.endswith((" ", ".")) for x in pieces):
        raise ValueError("ZIP_TRAVERSAL")
    if any(re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", x)
           for x in pieces):
        raise ValueError("ZIP_WINDOWS_DEVICE")
    mode = info.external_attr >> 16
    if stat.S_IFMT(mode) == stat.S_IFLNK:
        raise ValueError("ZIP_SYMLINK")
    if info.flag_bits & 0x1:
        raise ValueError("ZIP_ENCRYPTED")
    return "/".join(pieces)

def digest_archive(root, meta, target):
    """Stream exact 3 source pieces to a temporary file with Git object and SHA256 proof."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("ROOT_UNTRUSTED")
    parts = meta["archive"]["parts"]
    if [x["path"] for x in parts] != ["source_00.part", "source_01.part", "source_02.part"]:
        raise ValueError("PARTS_OUT_OF_ORDER")
    total = 0
    archive_sha = hashlib.sha256()
    for entry in parts:
        source = root / entry["path"]
        if source.is_symlink() or not source.is_file() or source.stat().st_size != entry["size_bytes"]:
            raise ValueError("SOURCE_PART_MISSING_OR_CHANGED")
        git_sha = hashlib.sha1(f"blob {entry['size_bytes']}\0".encode())
        with source.open("rb") as fp:
            while buf := fp.read(1024 * 1024):
                git_sha.update(buf)
                archive_sha.update(buf)
                target.write(buf)
                total += len(buf)
        if git_sha.hexdigest() != entry["git_blob_sha1"]:
            raise ValueError("SOURCE_GIT_BLOB_SHA_MISMATCH")
    if total != EXPECTED_BYTES or archive_sha.hexdigest() != EXPECTED_ARCHIVE:
        raise ValueError("SOURCE_ARCHIVE_SHA_MISMATCH")
    return archive_sha.hexdigest(), total

def canonical_tree(files):
    """Unambiguous, domain-separated original-file tree SHA256, NOT a Git tree SHA1."""
    h = hashlib.sha256(b"NOX-SOURCELOCK-V2\x00")
    for item in files:
        line = json.dumps([item["path"], item["bytes"], item["sha256"]],
                          ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        h.update(len(line).to_bytes(8, "big") + line)
    return h.hexdigest()

def analyze_zip(archive, *, enforce_baseline=True):
    seen = set()
    total = 0
    rows = []
    for info in archive.infolist():
        path = safe_member(info)
        key = path.casefold()
        if key in seen:
            raise ValueError("ZIP_CASE_COLLISION")
        seen.add(key)
        if info.is_dir():
            continue
        if info.file_size < 0 or info.file_size > MAX_MEMBER:
            raise ValueError("ZIP_MEMBER_OVERSIZE")
        total += info.file_size
        if total > MAX_UNCOMPRESSED:
            raise ValueError("ZIP_UNCOMPRESSED_OVERSIZE")
        if info.file_size > 1048576 and (info.compress_size == 0 or
                                       info.file_size > info.compress_size * 10000):
            raise ValueError("ZIP_COMPRESSION_BOMB")
        sha = hashlib.sha256()
        length = 0
        with archive.open(info) as fp:
            while buf := fp.read(1048576):
                sha.update(buf)
                length += len(buf)
                if length > info.file_size:
                    raise ValueError("ZIP_UNEXPECTED_LENGTH")
        if length != info.file_size:
            raise ValueError("ZIP_TRUNCATED")
        rows.append({"path": path, "bytes": length, "sha256": sha.hexdigest()})
    rows.sort(key=lambda x: x["path"])
    if enforce_baseline and len(rows) != EXPECTED_FILES:
        raise ValueError("ORIGINAL_MEMBER_COUNT_DRIFT")
    return rows, total

def verify_json_assets(archive, rows):
    checks = {}
    for path in ("assets/asset_manifest.json", "assets/personas_5.json",
                 "assets/visual_pack/manifest.json", "assets/release_visual_pack.json",
                 "helion/ai_weights/weights/MODEL_FEATURE_CONTRACT.json"):
        entry = next((x for x in rows if x["path"] == path), None)
        if entry is None:
            checks[path] = "MISSING"
            continue
        if entry["bytes"] > 1024 * 1024:
            checks[path] = "OVERSIZED"
            continue
        try:
            item = json.loads(archive.read(path).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError, KeyError):
            checks[path] = "INVALID"
        else:
            checks[path] = "STRUCTURAL_JSON_PASS" if type(item) in (dict, list) else "INVALID"
    return checks

def attest_routes(map_doc):
    """Validate the 50 owner-proposal routes WITHOUT pretending to bind Python host."""
    if not isinstance(map_doc, dict) or map_doc.get("schema") != "NOX_PACK01_NATIVE_BINDING_MAP_V1":
        raise ValueError("ROUTE_MAP_SCHEMA")
    rows = map_doc.get("routes", [])
    if len(rows) != 50 or len({x.get("routeId") for x in rows}) != 50 or len({x.get("taskId") for x in rows}) != 50:
        raise ValueError("ROUTE_MAP_CARDINALITY")
    bound = 0
    for row in rows:
        if row.get("taskId") not in {f"NIP01-{n:02d}" for n in range(1, 51)}:
            raise ValueError("ROUTE_UNKNOWN_TASK")
        if type(row.get("owner")) is not int or row["owner"] not in range(1,7):
            raise ValueError("ROUTE_OWNER_INVALID")
        if any(row.get(k) is not False for k in ("exeIntegrated", "hardwareAccepted", "releaseAccepted")):
            raise ValueError("ROUTE_ACCEPTANCE_UNVERIFIED")
        if row.get("sourceBinding") is not None:
            if not isinstance(row["sourceBinding"], str) or not row["sourceBinding"].startswith("proposals/NOX-PACK01-50/"):
                raise ValueError("ROUTE_BINDING_NOT_PINNED_OWNER")
            bound += 1
    if bound != map_doc.get("counts", {}).get("sourceOwnerMethodBound"):
        raise ValueError("ROUTE_BINDING_COUNT_MISMATCH")
    return {"route_count": len(rows), "source_method_candidates": bound,
            "canonical_host_bound": 0, "release_accepted": 0,
            "state": "CANDIDATE_SOURCE_ONLY", "unbound": 50 - bound}

def create_lock(parts_root, intake, *, route_map=None):
    """No extraction, no code execution; originals remain immutable."""
    meta = json.loads(Path(intake).read_text(encoding="utf-8"))
    if meta.get("main", {}).get("commit_sha1") != "eb46b49fb8a022cefa679afb8606877016808db1":
        raise ValueError("BASE_MAIN_UNEXPECTED")
    if meta.get("main", {}).get("tree_sha1") != "bedea674b77d14d94028ba86251d8f4d690353c1":
        raise ValueError("BASE_TREE_UNEXPECTED")
    with tempfile.TemporaryFile() as scratch:
        archive_sha, archive_bytes = digest_archive(Path(parts_root), meta, scratch)
        scratch.flush()
        scratch.seek(0)
        with zipfile.ZipFile(scratch) as archive:
            files, bytes_unpacked = analyze_zip(archive)
            json_status = verify_json_assets(archive, files)
    names = {x["path"] for x in files}
    critical = {group: {"state": "PRESENT" if all(x in names for x in paths) else "MISSING",
                        "missing": [x for x in paths if x not in names],
                        "file_sha256": {r["path"]: r["sha256"] for r in files if r["path"] in paths}}
                for group, paths in CRITICAL.items()}
    if any(group["state"] == "MISSING" for group in critical.values()):
        raise ValueError("CRITICAL_ORIGINAL_FEATURE_MISSING")
    if any(v != "STRUCTURAL_JSON_PASS" for v in json_status.values()):
        raise ValueError("ORIGINAL_MANIFEST_INVALID")
    topology = {
        "python_original_host_paths": [x for x in HOST_FILES if x in names],
        "wpf_mainwindow_present": "MainWindow.xaml" in names or
                                  "MainWindow.xaml.cs" in names,
        "canonical_python_host_binding_test": "NOT_RUN",
        "routeid_coreid_persona_asset_mapping": "HOLD_PENDING_CANONICAL_RUNTIME_CONTRACT"
    }
    if len(topology["python_original_host_paths"]) != len(HOST_FILES):
        raise ValueError("HOST_CANONICAL_FILES_MISSING")
    route_state = None
    if route_map:
        route_state = attest_routes(json.loads(Path(route_map).read_text(encoding="utf-8")))
    lock = {
        "schema": "NOX-E06-ORIGINAL-BASELINE-SOURCELOCK-v2",
        "run_id": "NOX-V16-E06-TURBO10-20261028-R03", "owner": 6,
        "git_main_commit_sha1": meta["main"]["commit_sha1"],
        "git_main_tree_sha1": meta["main"]["tree_sha1"],
        "source_archive_sha256": archive_sha, "source_archive_bytes": archive_bytes,
        "original_tree_sha256": canonical_tree(files),
        "total_members": len(files), "uncompressed_bytes": bytes_unpacked,
        "critical_preservation": critical, "original_json_manifests": json_status,
        "topology": topology, "route_candidate_admission": route_state,
        "files": files, "source_modified": False, "product_integrated": False,
        "component_acceptance_complete": False, "e07_accepted": False,
        "release": "BLOCKED", "status": NO_RELEASE
    }
    return lock

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-root", default=".")
    ap.add_argument("--intake", default="coordination/e06/intake.json")
    ap.add_argument("--route-map")
    ap.add_argument("--out", default="e06-original-baseline-sourcelock.json")
    args = ap.parse_args()
    lock = create_lock(args.source_root, args.intake, route_map=args.route_map)
    path = Path(args.out)
    path.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    verify = json.loads(path.read_text(encoding="utf-8"))
    if verify != lock:
        raise ValueError("SOURCELOCK_READBACK_MISMATCH")
    print("E06_SOURCELOCK_ORIGINAL_BASELINE_PASS", lock["original_tree_sha256"],
          "MEMBERS", lock["total_members"], "APP_BYTES", lock["uncompressed_bytes"],
          "ARCHIVE", lock["source_archive_sha256"])
    print("E06_SOURCELOCK_STATUS", lock["status"], "RELEASE", lock["release"],
          "ROUTE_COUNTS", lock["route_candidate_admission"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
