#!/usr/bin/env python3
"""NOX: publish bounded read-only diagnostic receipts to a PRIVATE GitHub repository.
No shell, no remote command execution, no trainer/scheduler/STOP manipulation.
Requires an explicitly configured fine-grained repository-scoped GitHub token.
"""
import argparse
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

NODES = {
    "vast-60254538": Path("/root/nox/remote_control/vast_60254538"),
    "runpod-5f3j8hwyicc0bp": Path("/workspace/nox/remote_control/runpod_5f3j8hwyicc0bp"),
}
STATE = Path("/root/.local/state/nox-private-receipts")
CONFIG = Path("/root/.config/nox-control/private-receipts.json")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ALLOWED_OPS = {"gpu", "disk", "processes", "checkpoints", "health"}

def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def load_config():
    if not CONFIG.is_file() or CONFIG.is_symlink():
        raise ValueError("HOLD_PRIVATE_CONFIG_ABSENT")
    mode = CONFIG.stat().st_mode & 0o777
    if mode & 0o077:
        raise ValueError("HOLD_PRIVATE_CONFIG_PERMISSIONS")
    obj = json.loads(CONFIG.read_text(encoding="utf-8"))
    repo, token = obj.get("private_repo"), obj.get("token")
    if not isinstance(repo, str) or not REPO_RE.fullmatch(repo):
        raise ValueError("HOLD_PRIVATE_REPOSITORY")
    if not isinstance(token, str) or not token.startswith(("github_pat_", "ghp_")):
        raise ValueError("HOLD_TOKEN_ABSENT")
    return repo, token

def safe_data(receipt):
    """Allowlisted metrics only; never export arbitrary logs, commands or prompt data."""
    op = receipt.get("operation")
    data = receipt.get("data")
    if op not in ALLOWED_OPS:
        return {}
    if not isinstance(data, dict):
        return {}
    if op == "gpu":
        raw = str(data.get("stdout", "")).strip()[:400] if data.get("exit") == 0 else ""
        # GPU name, numbers, units only; prevent carrying arbitrary process output.
        return {"exit": data.get("exit"), "nvidia_smi": raw if re.fullmatch(r"[\w .,%/+-]{0,400}", raw) else ""}
    if op == "disk":
        out = {}
        for key in ("/workspace", "/root/nox"):
            v = data.get(key)
            if isinstance(v, dict):
                out[key] = {k: v[k] for k in ("free_gib", "total_gib") if type(v.get(k)) in (int, float)}
        return out
    if op == "processes":
        # Do not export arguments, paths or arbitrary executable names publicly/privately.
        return {"count": data.get("count") if type(data.get("count")) is int else None}
    if op == "checkpoints":
        items = data.get("items")
        if not isinstance(items, list):
            return {}
        return {"count": min(len(items), 100)}
    if op == "health":
        return {"gpu": safe_data({"operation": "gpu", "data": data.get("gpu")}),
                "disk": safe_data({"operation": "disk", "data": data.get("disk")}),
                "processes": safe_data({"operation": "processes", "data": data.get("processes")})}
    return {}

def compact_receipt(obj, node):
    if not isinstance(obj, dict) or obj.get("node") != node:
        raise ValueError("NODE_MISMATCH")
    ident = obj.get("id")
    if not isinstance(ident, str) or not ID_RE.fullmatch(ident):
        raise ValueError("INVALID_RECEIPT_ID")
    status = obj.get("status")
    if status not in ("READ_ONLY", "HOLD_EXPIRED"):
        raise ValueError("INVALID_RECEIPT_STATUS")
    op = obj.get("operation")
    if op not in ALLOWED_OPS:
        raise ValueError("INVALID_RECEIPT_OP")
    return {"schema": "nox-private-receipt-v1", "node": node, "id": ident,
            "op": op, "status": status, "source_utc": str(obj.get("utc", ""))[:40],
            "published_utc": utc(), "data": safe_data(obj)}

def request(url, token, method="GET", data=None):
    req = urllib.request.Request(url, data=data, method=method,
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "NOX-private-receipts/1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        result = r.read(32769)
    if len(result) > 32768:
        raise ValueError("OVERSIZED_GITHUB_RESPONSE")
    return json.loads(result)

def publish(repo, token, node, record):
    owner, name = repo.split("/")
    key = f"receipts/{node}/{record['id']}.json"
    url = f"https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(name)}/contents/{key}"
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2).encode()
    if len(payload) > 4096:
        raise ValueError("RECEIPT_TOO_LARGE")
    try:
        existing = request(url, token)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        existing = None
    if existing is not None:
        old = base64.b64decode(existing.get("content", "").replace("\n", ""))
        if json.loads(old).get("id") == record["id"]:
            return "ALREADY_EXISTS"  # Never overwrite an existing receipt.
        raise ValueError("RECEIPT_COLLISION")
    body = json.dumps({"message": f"NOX read-only receipt {node}/{record['id']}",
                       "content": base64.b64encode(payload).decode()}).encode()
    request(url, token, "PUT", body)
    return "CREATED"

def tick(node):
    repo, token = load_config()
    root = NODES[node]
    if not root.is_dir():
        raise ValueError("HOLD_OBSERVER_FOLDER_MISSING")
    STATE.mkdir(parents=True, exist_ok=True)
    sent = 0
    for p in sorted(root.glob("receipt_*.json"))[:100]:
        if p.is_symlink() or not p.is_file() or p.stat().st_size > 16384:
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            record = compact_receipt(obj, node)
            marker = STATE / (node + "_" + record["id"] + ".sent")
            if marker.exists():
                continue
            result = publish(repo, token, node, record)
            marker.write_text(result + "\n", encoding="utf-8")
            sent += 1
        except (OSError, ValueError, KeyError, urllib.error.URLError) as e:
            print("HOLD_RECEIPT", p.name, type(e).__name__, flush=True)
    print("NOX_PRIVATE_RECEIPTS", node, "count", sent, "utc", utc(), flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", choices=tuple(NODES), required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    while True:
        try:
            tick(args.node)
        except (OSError, ValueError, urllib.error.URLError) as e:
            # Never log the token, response bodies, or server data.
            print("HOLD_PRIVATE_CHANNEL", type(e).__name__, flush=True)
        if args.once:
            break
        time.sleep(180)

if __name__ == "__main__":
    main()
