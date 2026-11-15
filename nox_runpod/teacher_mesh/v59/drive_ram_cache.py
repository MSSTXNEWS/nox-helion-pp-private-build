#!/usr/bin/env python3
"""NOX Drive -> RAM on-demand model cache. Source-only; NOT a live deployment.

Prerequisites: a *pre-authorized* rclone remote and a reviewed manifest.
No credential capture, no remote deletion, no training restarts, no SSD writes.
Use only a dedicated tmpfs mount, never a plain directory on the SSD.
"""
import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_ROOT = Path("/dev/shm/nox-model-cache")
ALLOWED_SUFFIX = {".gguf", ".safetensors", ".bin", ".json", ".model"}
GIB = 1024 ** 3


def fatal(message):
    raise RuntimeError(message)


def assert_tmpfs(root):
    root = root.resolve()
    if not root.is_dir():
        fatal("RAM_CACHE_NOT_PRESENT: create a dedicated tmpfs mount first")
    mounts = []
    for raw in Path("/proc/self/mountinfo").read_text().splitlines():
        left, _, right = raw.partition(" - ")
        fields = left.split()
        rhs = right.split()
        if len(fields) >= 5 and rhs:
            mounts.append((fields[4].replace("\\040", " "), rhs[0]))
    applicable = [(len(p), t) for p, t in mounts
                  if str(root) == p or str(root).startswith(p.rstrip("/") + "/")]
    if not applicable or max(applicable)[1] != "tmpfs":
        fatal("FAIL_CLOSED_NOT_TMPFS: refusing SSD cache")
    if root == Path("/dev/shm"):
        fatal("Use dedicated subdirectory, not entire shared-memory root")
    return root


def load_manifest(path):
    obj = json.loads(path.read_text(encoding="utf-8"))
    if obj.get("schema") != "NOX_RAM_TIER_V1":
        fatal("unsupported manifest schema")
    models = obj.get("models")
    if not isinstance(models, dict):
        fatal("manifest models must be a map")
    for name, item in models.items():
        if not name or not all(c.isalnum() or c in "-_" for c in name):
            fatal("unsafe model id")
        if not isinstance(item, dict):
            fatal("malformed model entry")
        remote = item.get("remote", "")
        sha = item.get("sha256", "")
        size = item.get("bytes")
        if (not isinstance(remote, str) or not remote.startswith("noxdrive:")
            or ".." in remote.split("/") or remote.count(":") != 1):
            fatal("remote must use preconfigured noxdrive: with no traversal")
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            fatal("invalid sha256")
        if not isinstance(size, int) or size <= 0:
            fatal("invalid file length")
        if Path(remote).suffix.lower() not in ALLOWED_SUFFIX:
            fatal("unsupported model suffix")
    return models


def free_memory():
    data = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            data[parts[0].rstrip(":")] = int(parts[1]) * 1024
    return data.get("MemAvailable", 0)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cache_path(root, name, entry):
    return root / (name + Path(entry["remote"]).suffix.lower())


def verified(path, entry):
    return path.is_file() and path.stat().st_size == entry["bytes"] and sha256(path) == entry["sha256"]


def ensure_cached(root, name, entry, minimum_available_gib):
    root = assert_tmpfs(root)
    target = cache_path(root, name, entry)
    # Serializes downloads and eviction even across concurrent NOX requests.
    with (root / ".nox-tier.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if verified(target, entry):
            os.utime(target, None)
            print(json.dumps({"status": "RAM_CACHE_HIT", "path": str(target)}))
            return
        if target.exists():
            fatal("existing unverified cache file: manual investigation required")
        need = entry["bytes"]
        fs_free = shutil.disk_usage(root).free
        mem_avail = free_memory()
        reserve = int(minimum_available_gib * GIB)
        if fs_free < need + 128 * 1024 * 1024 or mem_avail < need + reserve:
            fatal("HOLD_INSUFFICIENT_RAM: leave running workloads untouched")
        partial = root / ("." + name + "." + str(os.getpid()) + ".partial")
        try:
            args = ["rclone", "copyto", "--retries", "3", "--low-level-retries", "5",
                    "--transfers", "1", "--checkers", "2",
                    entry["remote"], str(partial)]
            subprocess.run(args, check=True, timeout=7200, capture_output=True)
            if not verified(partial, entry):
                fatal("HOLD_INTEGRITY: SHA256 or byte length mismatch")
            os.replace(partial, target)
            print(json.dumps({"status": "RAM_CACHE_READY", "path": str(target)}))
        finally:
            partial.unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser(description="NOX read-only remote -> verified RAM lazy loader")
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    p.add_argument("--minimum-available-gib", type=float, default=8)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    get = sub.add_parser("get")
    get.add_argument("model_id")
    args = p.parse_args()
    if args.minimum_available_gib < 2:
        fatal("minimum available RAM must be at least 2 GiB")
    models = load_manifest(args.manifest)
    if args.cmd == "list":
        print(json.dumps({k: {"bytes": v["bytes"], "tier": v.get("tier", "cold")}
                          for k, v in models.items()}, indent=2))
        return
    if args.model_id not in models:
        fatal("unknown model: no fallback to unverified downloads")
    ensure_cached(args.root, args.model_id, models[args.model_id], args.minimum_available_gib)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        print("NOX_DRIVE_RAM_HOLD: " + str(error), file=sys.stderr)
        sys.exit(2)
