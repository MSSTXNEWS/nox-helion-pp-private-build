#!/usr/bin/env python3
"""NOX HELION candidate-source staging downloader.
READ-ONLY to NOX product tree. Default is plan mode. Does not install, execute, merge or train.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

GITHUB_RE = re.compile(r"^https://github\\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/?$")
PIN_RE = re.compile(r"^[0-9a-fA-F]{40}$")

def read_manifest(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def candidate(row):
    url = (row.get("url") or "").strip()
    return row.get("type") == "GIT_CLONE_CANDIDATE" and bool(GITHUB_RE.fullmatch(url))

def run(cmd, cwd=None, timeout=300):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True,
                          timeout=timeout, check=True)

def disk_mb(path):
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) / (1024*1024)

def main():
    ap = argparse.ArgumentParser(description="Staged clone of reviewed NOX code candidates")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--staging", default="NOX_QUARANTINE_STAGING")
    ap.add_argument("--execute", action="store_true", help="Perform source checkout (default dry-run)")
    ap.add_argument("--allow-unpinned", action="store_true",
                    help="Allow discovery clone; actual checkout SHA is recorded before review")
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--max-total-mb", type=int, default=500)
    args = ap.parse_args()
    if args.limit < 1 or args.limit > 100 or args.max_total_mb < 1:
        ap.error("invalid safety limits")
    rows = [r for r in read_manifest(args.manifest) if candidate(r)]
    targets = rows[:args.limit]
    print(f"Candidates in manifest: {len(rows)}; selected: {len(targets)}")
    print(f"MODE: {'STAGE ONLY' if args.execute else 'PLAN — NO DOWNLOAD'}")
    for r in targets:
        print(f" - {r['url']}  pin={r.get('version_pin','UNPINNED')}")
    if not args.execute:
        return 0
    if not shutil.which("git"):
        print("git is required; no download performed", file=sys.stderr)
        return 2
    if any(not PIN_RE.fullmatch(r.get("version_pin","")) for r in targets) and not args.allow_unpinned:
        print("Unpinned candidates blocked. Pin SHA or explicitly set --allow-unpinned for sandbox discovery.",file=sys.stderr)
        return 2
    staging = Path(args.staging).expanduser().resolve()
    staging.mkdir(parents=True, exist_ok=True)
    receipt = {"timestamp": datetime.now(timezone.utc).isoformat(), "mode":"STAGING_ONLY",
               "manifest_sha256":hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest(),
               "items":[]}
    for r in targets:
        if disk_mb(staging) > args.max_total_mb:
            print("Budget reached; stopping further clones",file=sys.stderr)
            break
        match = GITHUB_RE.fullmatch(r["url"])
        target = staging / (match.group(1)+"__"+match.group(2))
        if target.exists():
            receipt["items"].append({"url":r["url"],"status":"SKIPPED_EXISTS"})
            continue
        print("STAGING:",r["url"])
        item={"url":r["url"],"target":str(target),"status":"FAILED"}
        try:
            run(["git","clone","--depth","1","--filter=blob:none","--no-tags","--no-recurse-submodules",
                 r["url"]+".git",str(target)], timeout=240)
            sha=run(["git","rev-parse","HEAD"],cwd=target).stdout.strip()
            pin=r.get("version_pin","")
            if PIN_RE.fullmatch(pin) and pin.lower()!=sha.lower():
                item["status"]="PIN_MISMATCH"
            else:
                item.update({"status":"STAGED_UNREVIEWED","commit_sha":sha,
                             "bytes_approx_mb":round(disk_mb(target),2),
                             "license_status":"NOT_REVIEWED",
                             "executed_code":False})
        except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as e:
            item["error"]=str(e)[:500]
        receipt["items"].append(item)
    path=staging/"fetch_receipt.json"
    path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Receipt:",path)
    print("No dependencies installed; no source code executed, no product changes.")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
