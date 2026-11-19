#!/usr/bin/env python3
"""NOX cold model storage: rclone Drive -> verified staging -> optional RAM cache.
No credentials are logged or embedded. Eviction requires fresh owner evidence.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

BLOCKED_PARTS = {"s03", "checkpoint", "checkpoints", "optimizer", "training", "sqlite", "database", "db"}
ALLOWED_SUFFIX = {".safetensors", ".gguf", ".bin", ".pt", ".pth"}
GIB = 1024 ** 3

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def command(args):
    subprocess.run(args, check=True)

def assert_model(p):
    # resolve() before is_symlink() would silently allow linked targets.
    p = Path(os.path.abspath(p))
    if any(part.is_symlink() for part in (p, *p.parents)):
        raise ValueError("Symlinked model or parent rejected")
    if not p.is_file() or p.stat().st_nlink != 1 or p.suffix.lower() not in ALLOWED_SUFFIX:
        raise ValueError("Not an eligible unlinked regular model file")
    if any(part.lower() in BLOCKED_PARTS for part in p.parts):
        raise ValueError("Protected training, checkpoint or S03 path")
    return p

def verify_remote_stream(remote_file, expected_sha256, expected_size):
    """Read remote bytes back through rclone cat using O(8MiB) local memory."""
    h = hashlib.sha256()
    size = 0
    proc = subprocess.Popen(
        ["rclone", "cat", remote_file, "--retries", "3", "--low-level-retries", "3"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    try:
        while True:
            chunk = proc.stdout.read(8 * 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > expected_size:
                raise RuntimeError("Remote size exceeds local source; retained")
            h.update(chunk)
        if proc.wait() != 0 or size != expected_size or h.hexdigest() != expected_sha256:
            raise RuntimeError("Remote readback SHA256/size mismatch; original retained")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if proc.stdout:
            proc.stdout.close()


def assert_remote(remote):
    if ":" not in remote or remote.startswith(":") or ".." in remote.split(":")[-1].split("/"):
        raise ValueError("Provide explicit rclone remote:path (e.g. noxdrive:NOX_COLD)")
    return remote.rstrip("/")

def upload(a):
    src = assert_model(a.file)
    remote = assert_remote(a.remote)
    if a.active_manifest:
        active = set(json.loads(Path(a.active_manifest).read_text()).get("active_paths", []))
        if str(src) in {str(Path(x).resolve()) for x in active}:
            raise ValueError("Refusing to evict active model")
    dest = remote + "/" + src.name
    digest = sha256(src)
    size = src.stat().st_size
    command(["rclone", "copyto", "--retries", "3", "--checkers", "4", str(src), dest])
    # Stream remote readback without another model-sized SSD copy.
    verify_remote_stream(dest, digest, size)
    receipt = {"source": str(src), "destination": dest, "size": size,
               "sha256": digest, "readback_verified": True, "source_deleted": False}
    receipt_path = Path(a.receipt_dir).resolve() / (src.name + "." + digest[:16] + ".json")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    with open(receipt_path, "x") as out:
        json.dump(receipt, out, indent=2)
        out.flush()
        os.fsync(out.fileno())
    print(json.dumps({"receipt": str(receipt_path), **receipt}, ensure_ascii=False))
    if a.evict:
        # Require operator supplied manifest generated from live process inspection.
        if not a.active_manifest:
            raise RuntimeError("Verified upload complete; eviction requires --active-manifest")
        # Require current owner-produced active-file evidence for any eviction.
        manifest_path = Path(os.path.abspath(a.active_manifest))
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise RuntimeError("Eviction requires a regular owner active manifest")
        st = manifest_path.stat()
        if st.st_mode & 0o077 or st.st_uid != os.geteuid():
            raise RuntimeError("Eviction active manifest permissions/owner invalid")
        manifest = json.loads(manifest_path.read_text())
        when = manifest.get("checked_at_unix")
        if type(when) is not int or abs(time.time() - when) > 60:
            raise RuntimeError("Eviction requires a fresh owner process snapshot")
        if str(src) in {str(Path(os.path.abspath(x))) for x in manifest.get("active_paths", [])}:
            raise RuntimeError("Eviction refused: source became active")
        if src.stat().st_size != size or sha256(src) != digest:
            raise RuntimeError("Eviction refused: source changed after upload")
        src.unlink()
        receipt["source_deleted"] = True
        receipt_path.write_text(json.dumps(receipt, indent=2))
        print("EVICTED VERIFIED INACTIVE MODEL:", src)

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
    if size <= 0 or shutil.disk_usage(dest_dir).free < size + a.reserve_gib * GIB:
        raise RuntimeError("Insufficient tmpfs free space after RAM reserve")
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
    u.add_argument("--evict", action="store_true", help="Delete ONLY verified inactive source")
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
