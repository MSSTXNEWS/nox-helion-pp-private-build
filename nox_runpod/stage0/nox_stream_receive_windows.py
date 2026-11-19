#!/usr/bin/env python3
"""NOX Windows recovery: stream from A5000/A40, SHA-verify, atomic promote.

Use one long-lived SSH stream per volume, not SCP for every file. No remote
deletion, restart, GPU computation, model fabrication or false PASS.
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import shlex
import subprocess
import sys
import tarfile
import tempfile

STREAM_COMMIT = "b263f10d35031c16d0f25c828b3cd82bb781f0a0"
STREAM_URL = (
    "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/"
    + STREAM_COMMIT + "/nox_runpod/stage0/nox_snapshot_stream.py"
)
NODES = {
    "A5000": [
        ("erkgy956g04n6c-6441288b@ssh.runpod.io", 22),
        ("root@69.30.85.188", 22199),
    ],
    "A40": [
        ("ypfijzzibqvrl7-6441289b@ssh.runpod.io", 22),
        ("root@69.30.85.193", 22088),
    ],
}
TASKS = [
    ("A5000", "shared", "SHARED_NOX"),
    ("A5000", "container", "A5000_CONTAINER"),
    ("A40", "container", "A40_CONTAINER"),
]
RESERVE_BYTES = 4 * 1024**3

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def safe_relative(name):
    if not isinstance(name, str) or len(name) > 750 or "\\" in name or ":" in name:
        return None
    p = PurePosixPath(name)
    if p.is_absolute() or not p.parts or any(t in ("", ".", "..") for t in p.parts):
        return None
    if any("\x00" in t for t in p.parts):
        return None
    return p

def save_receipt(path, receipt):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".new")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def ssh_args(key, target, port, scope):
    remote = (
        "set -e; "
        "p=/tmp/nox_snapshot_stream_b263f10d.py; "
        "curl -fsSL --connect-timeout 20 " + shlex.quote(STREAM_URL)
        + " -o \"$p\"; "
        "python3 -m py_compile \"$p\"; "
        "python3 -u \"$p\" --scope " + shlex.quote(scope)
    )
    return [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=18",
        "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3",
        "-o", "StrictHostKeyChecking=accept-new",
        "-i", str(key), "-p", str(port), target, remote,
    ]

def attempt(key, target, port, scope, destination, log_dir):
    destination.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / ("ssh_" + scope + "_" + str(port) + ".log")
    pending = {}
    seen = {}
    rejected = []
    remote_manifest = None
    proc = None
    with log_path.open("wb") as stderr_log:
        proc = subprocess.Popen(
            ssh_args(key, target, port, scope),
            stdout=subprocess.PIPE,
            stderr=stderr_log,
        )
        try:
            with tarfile.open(fileobj=proc.stdout, mode="r|") as archive:
                for member in archive:
                    rel = safe_relative(member.name)
                    if rel is None or not member.isfile():
                        rejected.append(str(member.name)[:120])
                        continue
                    entry = archive.extractfile(member)
                    if entry is None:
                        rejected.append(member.name[:120])
                        continue
                    if member.name == "NOX_TRANSFER_MANIFEST.json":
                        if member.size > 20 * 1024**2:
                            raise RuntimeError("REMOTE_MANIFEST_TOO_LARGE")
                        remote_manifest = json.loads(entry.read().decode("utf-8"))
                        continue
                    # Each filename is confined to destination; no symlinks/extractall.
                    dest = destination.joinpath(*rel.parts)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    partial = dest.with_name(dest.name + ".noxstream-" + str(os.getpid()))
                    sha = hashlib.sha256()
                    read = 0
                    enough_space = shutil.disk_usage(destination).free >= member.size + RESERVE_BYTES
                    f = partial.open("wb") if enough_space else None
                    try:
                        while True:
                            block = entry.read(4 * 1024**2)
                            if not block:
                                break
                            sha.update(block)
                            read += len(block)
                            if f:
                                f.write(block)
                        if f:
                            f.flush()
                            os.fsync(f.fileno())
                    finally:
                        if f:
                            f.close()
                    if not enough_space:
                        rejected.append("DISK_RESERVE:" + member.name[:100])
                        continue
                    if read != member.size:
                        rejected.append("SIZE_MISMATCH:" + member.name[:100])
                        continue
                    pending[member.name] = (partial, dest)
                    seen[member.name] = {"bytes": read, "sha256": sha.hexdigest()}
        finally:
            if proc.stdout:
                proc.stdout.close()
            exitcode = proc.wait(timeout=120)
    if exitcode != 0:
        raise RuntimeError("SSH_EXIT=" + str(exitcode) + " (inspect " + str(log_path) + ")")
    if not isinstance(remote_manifest, dict):
        raise RuntimeError("NO_COMPLETE_TRANSFER_MANIFEST")
    if remote_manifest.get("scope") != scope or not isinstance(remote_manifest.get("files"), list):
        raise RuntimeError("INVALID_REMOTE_TRANSFER_MANIFEST")
    expected = {x.get("path"): x for x in remote_manifest["files"]
                if isinstance(x, dict) and isinstance(x.get("path"), str)}
    confirmed = 0
    bytes_ok = 0
    for rel, (partial, dest) in pending.items():
        entry = expected.get(rel)
        got = seen[rel]
        if (entry is None or entry.get("sha256") != got["sha256"]
                or entry.get("bytes") != got["bytes"]):
            rejected.append("SHA_OR_MANIFEST_MISMATCH:" + rel[:100])
            continue
        try:
            os.replace(partial, dest)
            confirmed += 1
            bytes_ok += got["bytes"]
        except OSError as exc:
            rejected.append("WINDOWS_PROMOTE:" + rel[:80] + ":" + type(exc).__name__)
    for rel in expected:
        if rel not in seen:
            rejected.append("MISSING_LOCAL:" + rel[:100])
    failures = remote_manifest.get("failures", [])
    if not isinstance(failures, list):
        failures = [{"error": "INVALID_FAILURES_FIELD"}]
    return {
        "status": "VERIFIED" if not rejected and not failures and confirmed == len(expected) else "PARTIAL",
        "source": target, "source_scope": scope,
        "verified_files": confirmed, "verified_bytes": bytes_ok,
        "expected_files": len(expected), "remote_failures": failures[:100],
        "local_failures": rejected[:100], "log": str(log_path), "utc": utc(),
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--key", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    key = Path(args.key)
    out = Path(args.output)
    if not key.is_file():
        raise SystemExit("HOLD_SSH_KEY_MISSING:" + str(key))
    out.mkdir(parents=True, exist_ok=True)
    result = {}
    for node, scope, folder in TASKS:
        print("NOX_TRANSFER", node, scope, "START", flush=True)
        last_error = None
        for target, port in NODES[node]:
            try:
                receipt = attempt(key, target, port, scope, out / folder, out / "LOGS")
                result[folder] = receipt
                save_receipt(out / ("NOX_" + folder + "_RECEIPT.json"), receipt)
                print("NOX_TRANSFER", folder, receipt["status"],
                      "files", receipt["verified_files"], "bytes", receipt["verified_bytes"], flush=True)
                break
            except (OSError, RuntimeError, ValueError, tarfile.TarError, subprocess.TimeoutExpired) as exc:
                last_error = type(exc).__name__ + ":" + str(exc)[:300]
                print("NOX_ROUTE_RETRY", node, scope, last_error, flush=True)
        else:
            result[folder] = {"status": "HOLD", "reason": last_error, "utc": utc()}
    overall = "VERIFIED" if all(x.get("status") == "VERIFIED" for x in result.values()) else "PARTIAL"
    save_receipt(out / "NOX_STREAM_SUMMARY.json", {"status": overall, "scopes": result, "utc": utc()})
    print("NOX_WINDOWS_OFFLOAD", overall, flush=True)
    if overall != "VERIFIED":
        print("NO_REMOTE_DELETION: unresolved file or transport errors remain", flush=True)
        return 2
    print("NOX_FULL_BACKUP_VERIFIED: sources unchanged; NO remote deletion", flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
