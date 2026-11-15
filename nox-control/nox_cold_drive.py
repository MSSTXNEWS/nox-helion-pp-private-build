#!/usr/bin/env python3
"""NOX cold model storage: rclone Drive -> verified staging -> optional RAM cache.
No credentials are logged or embedded. No automatic deletion or training launch.
"""
import argparse
import fcntl
import stat
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BLOCKED_PARTS = {"s03", "checkpoint", "checkpoints", "optimizer", "training", "sqlite", "database", "db", "trainer", "optim"}
ALLOWED_SUFFIX = {".safetensors", ".gguf", ".bin", ".pt", ".pth"}
GIB = 1024 ** 3

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def command(args):
    # Never include provider stderr or credentials in public workflow logs.
    try:
        proc = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              check=False, timeout=14400)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("HOLD_REMOTE_TRANSFER_UNAVAILABLE") from None
    if proc.returncode:
        raise RuntimeError("HOLD_REMOTE_TRANSFER_FAILED")


def remote_sha256(remote):
    """Stream R2/Drive readback to SHA256 without a second large disk file."""
    try:
        p = subprocess.Popen(["rclone", "--timeout", "120s", "--contimeout", "30s", "cat", remote],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError:
        raise RuntimeError("HOLD_REMOTE_READBACK_UNAVAILABLE") from None
    h = hashlib.sha256()
    size = 0
    try:
        for block in iter(lambda: p.stdout.read(8 * 1024 * 1024), b""):
            h.update(block)
            size += len(block)
        if p.wait(timeout=120) != 0:
            raise RuntimeError("HOLD_REMOTE_READBACK_FAILED")
        return h.hexdigest(), size
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
        if p.stdout:
            p.stdout.close()


def ensure_linux_tmpfs(dest):
    """Never accidentally fill SSD under a mistyped /dev/shm path."""
    if os.name != "posix":
        raise RuntimeError("HOLD_LINUX_TMPFS_ONLY")
    candidates = []
    with open("/proc/self/mountinfo", encoding="utf-8") as f:
        for line in f:
            left, _, right = line.partition(" - ")
            parts = left.split()
            after = right.split()
            if len(parts) > 4 and after:
                mp = parts[4].replace("\\\\040", " ")
                if str(dest) == mp or str(dest).startswith(mp.rstrip("/") + "/"):
                    candidates.append((len(mp), after[0]))
    if not candidates or max(candidates)[1] != "tmpfs":
        raise RuntimeError("HOLD_DEST_NOT_TMPFS")
    try:
        data = open("/proc/meminfo", encoding="utf-8").read()
        return int(next(x for x in data.splitlines() if x.startswith("MemAvailable:")).split()[1]) * 1024
    except (OSError, ValueError, StopIteration):
        raise RuntimeError("HOLD_RAM_AVAILABLE_UNKNOWN") from None

def assert_model(p):
    p = Path(p).resolve(strict=True)
    if not p.is_file() or p.is_symlink() or p.suffix.lower() not in ALLOWED_SUFFIX:
        raise ValueError("Not an eligible regular model file")
    if any(part.lower() in BLOCKED_PARTS for part in p.parts) or any(x in p.name.lower() for x in ("checkpoint", "optimizer", "s03", "trainer")):
        raise ValueError("Protected training, checkpoint or S03 path")
    return p

def assert_remote(remote):
    if not remote.startswith(("noxdrive:", "noxr2:")) or ".." in remote.split(":")[-1].split("/") or "\\\\" in remote:
        raise ValueError("Provide explicit rclone remote:path (e.g. noxdrive:NOX_COLD)")
    return remote.rstrip("/")

def upload(a):
    # The old --evict path could unlink weights using a user-written "active"
    # manifest, without a native OneHost lease or restore acceptance.
    if a.evict:
        raise RuntimeError("HOLD_EVICTION_DISABLED_UNTIL_NATIVE_OWNER_LEASE")
    src = assert_model(a.file)
    remote = assert_remote(a.remote)
    if a.active_manifest:
        active = set(json.loads(Path(a.active_manifest).read_text()).get("active_paths", []))
        if str(src) in {str(Path(x).resolve()) for x in active}:
            raise ValueError("Refusing to evict active model")
    dest = remote + "/" + src.name
    before = src.stat()
    digest = sha256(src)
    size = src.stat().st_size
    if before.st_mtime_ns != src.stat().st_mtime_ns or before.st_size != size:
        raise RuntimeError("HOLD_SOURCE_CHANGED_DURING_HASH")
    command(["rclone", "copyto", "--immutable", "--retries", "3", "--checkers", "4", str(src), dest])
    # Independent readback: streamed bytes, not S3 ETag and no local SSD duplicate.
    remote_hash, remote_size = remote_sha256(dest)
    if (remote_size, remote_hash) != (size, digest):
        raise RuntimeError("HOLD_REMOTE_SHA256_MISMATCH")
    after = src.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise RuntimeError("HOLD_SOURCE_CHANGED_DURING_UPLOAD")
    receipt = {"source": str(src), "destination": dest, "size": size,
               "sha256": digest, "readback_verified": True, "source_deleted": False}
    receipt_path = Path(a.receipt_dir).resolve() / (src.name + "." + digest[:16] + ".json")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    with open(receipt_path, "x") as out:
        json.dump(receipt, out, indent=2)
        out.flush()
        os.fsync(out.fileno())
    print(json.dumps({"receipt": str(receipt_path), **receipt}, ensure_ascii=False))

def load(a):
    remote = assert_remote(a.remote)
    if "/" not in remote.split(":", 1)[1]:
        raise ValueError("Specify the complete remote file path")
    dest_dir = Path(a.ram_dir).resolve()
    if not dest_dir.is_dir() or not dest_dir.resolve().is_relative_to(Path("/dev/shm")):
        raise ValueError("RAM destination must be an existing directory under /dev/shm (tmpfs)")
    name = remote.rsplit("/", 1)[-1]
    if Path(name).suffix.lower() not in ALLOWED_SUFFIX:
        raise ValueError("Not a model file")
    size_text = subprocess.check_output(["rclone", "size", "--json", remote], text=True)
    size = int(json.loads(size_text)["bytes"])
    available = ensure_linux_tmpfs(dest_dir)
    if size <= 0 or shutil.disk_usage(dest_dir).free < size + min(a.reserve_gib, 4) * GIB or available < size + a.reserve_gib * GIB:
        raise RuntimeError("HOLD_INSUFFICIENT_RAM_RESERVE")
    dest = dest_dir / name
    if dest.exists():
        raise FileExistsError(dest)
    tmp = dest_dir / (name + ".partial")
    if tmp.exists():
        raise FileExistsError(tmp)
    try:
        command(["rclone", "copyto", remote, str(tmp)])
        if tmp.stat().st_size != size:
            raise RuntimeError("Incomplete RAM download")
        if a.sha256 and sha256(tmp).lower() != a.sha256.lower():
            raise RuntimeError("RAM download SHA256 mismatch")
        if not a.sha256:
            raise ValueError("Expected SHA256 from verified receipt required")
        tmp.rename(dest)
        print(json.dumps({"ram_model": str(dest), "bytes": size, "sha256": a.sha256}))
    finally:
        tmp.unlink(missing_ok=True)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sp = p.add_subparsers(dest="action", required=True)
    u = sp.add_parser("upload")
    u.add_argument("--file", required=True)
    u.add_argument("--remote", required=True)
    u.add_argument("--receipt-dir", default="./cold_receipts")
    u.add_argument("--active-manifest", help="JSON with active_paths populated from current process inspection")
    u.add_argument("--evict", action="store_true", help="DISABLED until OneHost owner-lease/restore acceptance")
    l = sp.add_parser("load")
    l.add_argument("--remote", required=True)
    l.add_argument("--ram-dir", default="/dev/shm/nox_models")
    l.add_argument("--sha256", required=True)
    l.add_argument("--reserve-gib", type=int, default=12)
    args = p.parse_args()
    if getattr(args, "reserve_gib", 0) < 1:
        p.error("RAM reserve must be positive")
    try:
        (upload if args.action == "upload" else load)(args)
    except Exception as e:
        print(f"NOX COLD: FAIL CLOSED: {type(e).__name__}: {e}", file=sys.stderr)
        raise SystemExit(1)
if __name__ == "__main__":
    main()
