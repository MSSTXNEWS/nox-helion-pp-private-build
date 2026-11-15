#!/usr/bin/env python3
"""NOX V59 — portable R2 model archive (Linux/Windows). No local/remote deletes.

Credentials must be injected by a secure runtime secret store:
RCLONE_CONFIG_NOXR2_ACCESS_KEY_ID
RCLONE_CONFIG_NOXR2_SECRET_ACCESS_KEY

Usage:
 python r2_archive.py --bucket ACTUAL_BUCKET probe
 python r2_archive.py --bucket ACTUAL_BUCKET upload /models/teacher.gguf --tier warm
 python r2_archive.py --bucket ACTUAL_BUCKET restore --object NOX/WEIGHTS/WARM/teacher.gguf --sha256 HASH /ram/cache/teacher.gguf
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ENDPOINT = "https://6ab1503ad55d0a429062ad470c448012.r2.cloudflarestorage.com"
BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
TIER_NAMES = {"warm": "WARM", "cold": "COLD"}
CHUNK = 8 * 1024 * 1024

def credentials():
    env = os.environ.copy()
    for k, value in {"TYPE": "s3", "PROVIDER": "Cloudflare", "REGION": "auto",
                     "ENDPOINT": ENDPOINT, "ENV_AUTH": "false"}.items():
        env["RCLONE_CONFIG_NOXR2_" + k] = value
    if not env.get("RCLONE_CONFIG_NOXR2_ACCESS_KEY_ID") or not env.get("RCLONE_CONFIG_NOXR2_SECRET_ACCESS_KEY"):
        raise ValueError("HOLD_NO_SECURE_R2_CREDENTIALS")
    return env

def object_name(name):
    if not name or name.startswith("/") or "\\" in name or ":" in name or any(p in ("", ".", "..") for p in name.split("/")):
        raise ValueError("HOLD_UNSAFE_OBJECT_PATH")
    return name

def command(args, env):
    try:
        p = subprocess.run(["rclone", *args], env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=14400)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise ValueError("HOLD_RCLONE_MISSING_OR_TIMEOUT") from None
    if p.returncode != 0:
        raise ValueError("HOLD_RCLONE_FAILED")
    return p.stdout

def file_hash(path):
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while True:
            block = source.read(CHUNK)
            if not block:
                break
            size += len(block)
            h.update(block)
    return h.hexdigest(), size

def remote_hash(remote, env):
    # Independent end-to-end readback, not an ETag or cached local checksum.
    try:
        process = subprocess.Popen(["rclone", "cat", remote], env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        raise ValueError("HOLD_RCLONE_MISSING") from None
    sha = hashlib.sha256()
    size = 0
    try:
        while True:
            block = process.stdout.read(CHUNK)
            if not block:
                break
            sha.update(block)
            size += len(block)
        if process.wait(timeout=60) != 0:
            raise ValueError("HOLD_REMOTE_READBACK_FAILED")
        return sha.hexdigest(), size
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()

def main():
    parser = argparse.ArgumentParser(description="NOX portable verified R2 archive")
    parser.add_argument("--bucket", required=True, help="Actual bucket name, not URL path")
    parser.add_argument("--prefix", default="NOX/WEIGHTS")
    sub = parser.add_subparsers(dest="op", required=True)
    sub.add_parser("probe")
    upload = sub.add_parser("upload")
    upload.add_argument("source", type=Path)
    upload.add_argument("--tier", choices=("warm", "cold"), required=True)
    restore = sub.add_parser("restore")
    restore.add_argument("--object", required=True)
    restore.add_argument("--sha256", required=True)
    restore.add_argument("destination", type=Path)
    args = parser.parse_args()
    if not BUCKET_RE.fullmatch(args.bucket):
        raise ValueError("HOLD_INVALID_BUCKET_NAME")
    prefix = object_name(args.prefix.strip("/"))
    env = credentials()
    if args.op == "probe":
        command(["lsf", "--max-depth", "1", "noxr2:" + args.bucket], env)
        print(json.dumps({"state": "READ_OK", "write": "NOT_TESTED"}))
        return
    if args.op == "upload":
        source = args.source.resolve(strict=True)
        if not source.is_file() or source.is_symlink():
            raise ValueError("HOLD_NOT_REGULAR_FILE")
        name = object_name(prefix + "/" + TIER_NAMES[args.tier] + "/" + source.name)
        remote = "noxr2:" + args.bucket + "/" + name
        local_sha, local_size = file_hash(source)
        # No overwrite: copies only if destination not present. If present, require exact same readback.
        current = subprocess.run(["rclone", "lsjson", remote, "--stat"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if current.returncode == 0:
            actual_sha, actual_size = remote_hash(remote, env)
            if (actual_sha, actual_size) != (local_sha, local_size):
                raise ValueError("HOLD_REMOTE_OBJECT_EXISTS_DIFFERENT")
        else:
            command(["copyto", "--immutable", "--retries", "3", str(source), remote], env)
            actual_sha, actual_size = remote_hash(remote, env)
            if (actual_sha, actual_size) != (local_sha, local_size):
                raise ValueError("HOLD_UPLOAD_READBACK_MISMATCH")
        print(json.dumps({"state": "VERIFIED_REMOTE_COPY", "remote": remote,
                          "sha256": local_sha, "bytes": local_size,
                          "source_deleted": False}))
        return
    name = object_name(args.object)
    expected = args.sha256.lower()
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("HOLD_INVALID_SHA256")
    destination = args.destination
    if destination.exists():
        raise ValueError("HOLD_DESTINATION_ALREADY_EXISTS")
    if not destination.parent.is_dir():
        raise ValueError("HOLD_DESTINATION_PARENT_MISSING")
    partial = destination.with_name(destination.name + ".nox-incomplete")
    if partial.exists():
        raise ValueError("HOLD_PARTIAL_ALREADY_EXISTS")
    try:
        command(["copyto", "noxr2:" + args.bucket + "/" + name, str(partial), "--retries", "3"], env)
        actual, size = file_hash(partial)
        if actual != expected:
            raise ValueError("HOLD_RESTORED_HASH_MISMATCH")
        os.replace(partial, destination)
        print(json.dumps({"state": "RESTORED_AND_VERIFIED", "bytes": size,
                          "destination": str(destination)}))
    finally:
        if partial.exists():
            partial.unlink()

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        print("NOX_R2_HOLD: " + str(exc), file=sys.stderr)
        sys.exit(2)
