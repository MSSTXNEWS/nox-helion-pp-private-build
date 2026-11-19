"""NOX Tigris warm model vault for the EXISTING OneHost (no second backend).

Explicit, one-shot commands only. Source objects are content addressed; no
model, S03, trainer, or GPU process is stopped, modified, or deleted.
S3 credentials come ONLY from runtime env; never stored in source or receipts.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

BUCKET = "nox"
ENDPOINT = "https://t3.storage.dev"
REGION = "auto"
CHUNK = 8 * 1024 * 1024
RESERVE = 10 * 1024**3
RAM_RESERVE = 12 * 1024**3
RAM_MAX_OBJECT = 96 * 1024**3
RAM_ROOT = "/dev/shm/nox_model_warm"
SHA = re.compile(r"^[a-f0-9]{64}$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,200}$")
KEY = re.compile(r"^models/sha256/([a-f0-9]{64})/([A-Za-z0-9][A-Za-z0-9._-]{0,200})$")
WEIGHT_EXT = {".gguf", ".safetensors", ".pt", ".pth", ".ckpt", ".bin"}
STOP_PATHS = (
    "/root/nox/STOP", "/root/nox/STOP.flag", "/root/nox/stop.flag",
    "/root/nox/.stop", "/workspace/NOX_STOP", "/root/nox/program/STOP",
)


class Hold(RuntimeError):
    """A safe, non-destructive refusal. Its message is a fixed status code."""


def stopped():
    try:
        return any(Path(s).exists() for s in STOP_PATHS)
    except OSError:
        # Never ignore an unreadable STOP state on a real host.
        raise Hold("HOLD_STOP_STATE_UNREADABLE") from None


def require_run_allowed():
    if stopped():
        raise Hold("HOLD_NOX_STOP_ACTIVE")


def sha256_file(f):
    h = hashlib.sha256()
    for b in iter(lambda: f.read(CHUNK), b""):
        require_run_allowed()
        h.update(b)
    return h.hexdigest()


def guarded_source(root, src):
    """Read only model binaries beneath an explicit root; no symlink escapes."""
    root = Path(root).absolute()
    src = Path(src).absolute()
    if root.is_symlink() or src.is_symlink():
        raise Hold("HOLD_SYMLINK")
    try:
        parts = src.relative_to(root).parts
    except ValueError:
        raise Hold("HOLD_SOURCE_OUTSIDE_MODEL_ROOT") from None
    if not parts or any(p in ("..", ".") for p in parts):
        raise Hold("HOLD_SOURCE_PATH")
    node = root
    for part in parts:
        node = node / part
        if node.is_symlink():
            raise Hold("HOLD_SYMLINK")
    if not src.is_file() or not NAME.fullmatch(src.name) or src.suffix.lower() not in WEIGHT_EXT:
        raise Hold("HOLD_NON_MODEL_BINARY")
    if root.resolve() not in src.resolve().parents:
        raise Hold("HOLD_SOURCE_ESCAPE")
    return src


def s3_from_env():
    if not os.environ.get("AWS_ACCESS_KEY_ID") or not os.environ.get("AWS_SECRET_ACCESS_KEY"):
        raise Hold("HOLD_TIGRIS_CREDENTIALS_NOT_PROVISIONED")
    try:
        import boto3
    except ImportError:
        raise Hold("HOLD_INSTALL_BOTO3_IN_EXISTING_ENV") from None
    return boto3.client("s3", endpoint_url=ENDPOINT, region_name=REGION,
                        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
                        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"])


def _head(s3, key):
    try:
        return s3.head_object(Bucket=BUCKET, Key=key)
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        if str(code) in ("404", "NoSuchKey", "NotFound"):
            return None
        raise Hold("HOLD_REMOTE_HEAD_FAILED") from None


def probe(s3):
    require_run_allowed()
    try:
        s3.list_objects_v2(Bucket=BUCKET, MaxKeys=1)
    except Exception:
        raise Hold("HOLD_TIGRIS_READ_ACCESS") from None
    return {"state": "READ_ACCESS_OK", "bucket": BUCKET, "endpoint": ENDPOINT,
            "instance_modified": False, "write_test_performed": False}


def backup(s3, root, src):
    """Upload one explicitly requested model file; do NOT delete local source."""
    require_run_allowed()
    path = guarded_source(root, src)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as file:
        before = os.fstat(file.fileno())
        if before.st_size <= 0:
            raise Hold("HOLD_EMPTY_MODEL")
        digest = sha256_file(file)
        key = f"models/sha256/{digest}/{path.name}"
        existing = _head(s3, key)
        if existing is not None:
            if (existing.get("ContentLength") != before.st_size or
                existing.get("Metadata", {}).get("sha256") != digest):
                raise Hold("HOLD_REMOTE_CONTENT_ADDRESS_CONFLICT")
            return {"state": "EXISTS_REMOTE_HEAD_MATCH_ONLY", "key": key,
                    "sha256": digest, "bytes": before.st_size, "local_preserved": True}
        require_run_allowed()
        file.seek(0)
        try:
            from boto3.s3.transfer import TransferConfig
            transfer = TransferConfig(multipart_threshold=64 * 1024**2,
                                      multipart_chunksize=32 * 1024**2,
                                      max_concurrency=3)
            s3.upload_fileobj(file, BUCKET, key,
                ExtraArgs={"Metadata": {"sha256": digest}}, Config=transfer)
        except Exception:
            raise Hold("HOLD_REMOTE_UPLOAD_FAILED") from None
        after = os.fstat(file.fileno())
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_ino, after.st_size, after.st_mtime_ns):
            raise Hold("HOLD_SOURCE_CHANGED_DURING_UPLOAD")
    remote = _head(s3, key)
    if remote is None or remote.get("ContentLength") != before.st_size or \
            remote.get("Metadata", {}).get("sha256") != digest:
        raise Hold("HOLD_REMOTE_HEAD_MISMATCH")
    return {"state": "OFFSITE_HEAD_CONFIRMED_RESTORE_NOT_YET_TESTED",
            "key": key, "sha256": digest, "bytes": before.st_size,
            "local_preserved": True, "model_unloaded": False}


def verify_remote(s3, key):
    """Full streamed remote readback (expensive for multi-GB models)."""
    matched = KEY.fullmatch(key)
    if not matched:
        raise Hold("HOLD_INVALID_CONTENT_ADDRESS")
    expected = matched.group(1)
    head = _head(s3, key)
    if head is None or head.get("Metadata", {}).get("sha256") != expected:
        raise Hold("HOLD_REMOTE_METADATA_MISMATCH")
    require_run_allowed()
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=key)
        body = obj["Body"]
        h, count = hashlib.sha256(), 0
        try:
            for chunk in body.iter_chunks(chunk_size=CHUNK):
                require_run_allowed()
                count += len(chunk)
                h.update(chunk)
        finally:
            body.close()
    except Hold:
        raise
    except Exception:
        raise Hold("HOLD_REMOTE_READBACK_FAILED") from None
    if count != head.get("ContentLength") or h.hexdigest() != expected:
        raise Hold("HOLD_REMOTE_BYTES_SHA_MISMATCH")
    return {"state": "REMOTE_SHA256_READBACK_PASS", "key": key,
            "sha256": expected, "bytes": count}


def _disk_free_for(path):
    p = Path(path).absolute()
    while not p.exists():
        if p == p.parent:
            raise Hold("HOLD_CACHE_PARENT_MISSING")
        p = p.parent
    if p.is_symlink():
        raise Hold("HOLD_CACHE_SYMLINK")
    return shutil.disk_usage(p).free


def restore(s3, key, cache_root, reserve_bytes=RESERVE):
    """Disk-admitted SHA-verified read-through restore, never overwrite files."""
    matched = KEY.fullmatch(key)
    if not matched:
        raise Hold("HOLD_INVALID_CONTENT_ADDRESS")
    expected, name = matched.groups()
    require_run_allowed()
    head = _head(s3, key)
    if head is None or head.get("Metadata", {}).get("sha256") != expected:
        raise Hold("HOLD_REMOTE_METADATA_MISMATCH")
    size = head.get("ContentLength")
    if not isinstance(size, int) or size <= 0:
        raise Hold("HOLD_REMOTE_SIZE_UNKNOWN")
    root = Path(cache_root).absolute()
    if root.is_symlink() or not root.name:
        raise Hold("HOLD_CACHE_ROOT")
    if root.exists() and not root.is_dir():
        raise Hold("HOLD_CACHE_NOT_DIRECTORY")
    dest = root / f"{expected}-{name}"
    if dest.is_symlink():
        raise Hold("HOLD_EXISTING_SYMLINK")
    if dest.exists():
        if not dest.is_file() or dest.stat().st_size != size:
            raise Hold("HOLD_EXISTING_CACHE_COLLISION")
        with dest.open("rb") as f:
            if sha256_file(f) != expected:
                raise Hold("HOLD_EXISTING_CACHE_SHA_MISMATCH")
        return {"state": "LOCAL_SHA256_VERIFIED", "local": str(dest),
                "bytes": size, "sha256": expected}
    free = _disk_free_for(root)
    if free < size + reserve_bytes:
        return {"state": "HOLD_DISK_RESERVE", "required_bytes": size + reserve_bytes,
                "available_bytes": free, "no_files_modified": True}
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise Hold("HOLD_CACHE_SYMLINK")
    fd, tmp = tempfile.mkstemp(prefix=".nox-tigris-incomplete-", dir=root)
    try:
        with os.fdopen(fd, "wb") as out:
            try:
                body = s3.get_object(Bucket=BUCKET, Key=key)["Body"]
                digest, count = hashlib.sha256(), 0
                try:
                    for chunk in body.iter_chunks(chunk_size=CHUNK):
                        require_run_allowed()
                        count += len(chunk)
                        if count > size or _disk_free_for(root) < reserve_bytes:
                            raise Hold("HOLD_DISK_LIMIT_DURING_RESTORE")
                        out.write(chunk)
                        digest.update(chunk)
                finally:
                    body.close()
            except Hold:
                raise
            except Exception:
                raise Hold("HOLD_REMOTE_STREAM_FAILED") from None
            out.flush()
            os.fsync(out.fileno())
        if count != size or digest.hexdigest() != expected:
            raise Hold("HOLD_RESTORED_SHA256_MISMATCH")
        require_run_allowed()
        # Atomic create-if-absent, not replace: concurrent NOX jobs are protected.
        try:
            os.link(tmp, dest)
        except FileExistsError:
            raise Hold("HOLD_CONCURRENT_CACHE_WRITER") from None
        return {"state": "RESTORED_LOCAL_SHA256_VERIFIED", "local": str(dest),
                "bytes": count, "sha256": expected, "gpu_unchanged": True}
    finally:
        Path(tmp).unlink(missing_ok=True)



def _ram_root_guard(ram_root):
    """Only accept a dedicated tmpfs subdirectory, never a regular SSD path."""
    root = Path(ram_root).absolute()
    base = Path(RAM_ROOT)
    if root != base and base not in root.parents:
        raise Hold("HOLD_RAM_ROOT_NOT_DEDICATED_TMPFS")
    if Path("/dev/shm").is_symlink():
        raise Hold("HOLD_RAM_TMPFS_SYMLINK")
    try:
        mountinfo = Path("/proc/self/mountinfo").read_text()
        if not any(
            entry.split(" - ", 1)[0].split()[4] == "/dev/shm"
            and entry.split(" - ", 1)[1].split()[0] == "tmpfs"
            for entry in mountinfo.splitlines() if " - " in entry
        ):
            raise Hold("HOLD_RAM_TMPFS_NOT_MOUNTED")
    except OSError:
        raise Hold("HOLD_RAM_TMPFS_UNVERIFIED") from None
    node = Path("/dev/shm")
    for part in root.relative_to(node).parts:
        node = node / part
        if node.is_symlink():
            raise Hold("HOLD_RAM_PATH_SYMLINK")
    if root.exists() and not root.is_dir():
        raise Hold("HOLD_RAM_NOT_DIRECTORY")
    return root


def _ram_available_bytes():
    """Minimum of tmpfs room, host MemAvailable and container cgroup headroom."""
    try:
        stat = os.statvfs("/dev/shm")
        tmpfs_free = stat.f_bavail * stat.f_frsize
        lines = Path("/proc/meminfo").read_text().splitlines()
        mem = {line.split(":", 1)[0]: int(line.split(":", 1)[1].split()[0]) * 1024
               for line in lines if ":" in line}
        host_free = mem.get("MemAvailable")
        if host_free is None:
            raise Hold("HOLD_HOST_MEMORY_UNKNOWN")
        maxpath = Path("/sys/fs/cgroup/memory.max")
        curpath = Path("/sys/fs/cgroup/memory.current")
        if maxpath.is_file() and curpath.is_file():
            limit = maxpath.read_text().strip()
            current = int(curpath.read_text().strip())
            cgroup_free = max(0, int(limit) - current) if limit.isdigit() else host_free
            swap = Path("/sys/fs/cgroup/memory.swap.current")
            if swap.is_file() and int(swap.read_text().strip()) > 0:
                raise Hold("HOLD_SWAP_IN_USE")
        else:
            maxpath = Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")
            curpath = Path("/sys/fs/cgroup/memory/memory.usage_in_bytes")
            if not maxpath.is_file() or not curpath.is_file():
                raise Hold("HOLD_CGROUP_MEMORY_UNKNOWN")
            raw_limit = int(maxpath.read_text().strip())
            current = int(curpath.read_text().strip())
            cgroup_free = max(0, raw_limit - current) if raw_limit < (1 << 60) else host_free
        return min(tmpfs_free, host_free, cgroup_free)
    except Hold:
        raise
    except (OSError, ValueError, IndexError):
        raise Hold("HOLD_RAM_CAPACITY_UNVERIFIED") from None


def warm_ram(s3, key, ram_root=RAM_ROOT, reserve_bytes=RAM_RESERVE):
    """Fetch one complete, verified model weight into dedicated tmpfs, not SSD.

    Does not load into GPU or switch models. The existing OneHost must still
    check its CHAT/STOP/resource leases before launching the teacher. Do not
    warm full multi-shard models without verifying *all* required shards.
    """
    matched = KEY.fullmatch(key)
    if not matched:
        raise Hold("HOLD_INVALID_CONTENT_ADDRESS")
    if not 0 <= reserve_bytes <= 256 * 1024**3:
        raise Hold("HOLD_RAM_RESERVE_BOUNDS")
    require_run_allowed()
    root = _ram_root_guard(ram_root)
    expected, name = matched.groups()
    head = _head(s3, key)
    if head is None or head.get("Metadata", {}).get("sha256") != expected:
        raise Hold("HOLD_REMOTE_METADATA_MISMATCH")
    size = head.get("ContentLength")
    if not isinstance(size, int) or size <= 0 or size > RAM_MAX_OBJECT:
        raise Hold("HOLD_RAM_OBJECT_SIZE")
    dest = root / f"{expected}-{name}"
    if dest.is_symlink():
        raise Hold("HOLD_RAM_SYMLINK")
    if dest.exists():
        if not dest.is_file() or dest.stat().st_size != size:
            raise Hold("HOLD_RAM_COLLISION")
        with dest.open("rb") as f:
            if sha256_file(f) != expected:
                raise Hold("HOLD_RAM_SHA_MISMATCH")
        return {"state": "ALREADY_IN_RAM_SHA_VERIFIED", "local": str(dest),
                "bytes": size, "sha256": expected, "gpu_unchanged": True}
    free = _ram_available_bytes()
    if free < size + reserve_bytes:
        return {"state": "HOLD_RAM_RESERVE", "needed_bytes": size + reserve_bytes,
                "free_bytes": free, "no_files_modified": True}
    # No automatic delete/eviction: only the native OneHost owns lifecycle.
    root.mkdir(parents=True, exist_ok=True)
    root = _ram_root_guard(root)
    fd, tmp = tempfile.mkstemp(prefix=".nox-ram-incomplete-", dir=root)
    try:
        with os.fdopen(fd, "wb") as out:
            try:
                body = s3.get_object(Bucket=BUCKET, Key=key)["Body"]
                count, digest = 0, hashlib.sha256()
                try:
                    for chunk in body.iter_chunks(chunk_size=CHUNK):
                        require_run_allowed()
                        if not chunk:
                            continue
                        count += len(chunk)
                        if count > size:
                            raise Hold("HOLD_RAM_REMOTE_OVERRUN")
                        # Additional bytes already allocated are reflected in
                        # cgroup usage; preserve reserve as streaming proceeds.
                        if _ram_available_bytes() < reserve_bytes + len(chunk):
                            raise Hold("HOLD_RAM_PRESSURE_DURING_STREAM")
                        out.write(chunk)
                        digest.update(chunk)
                finally:
                    body.close()
            except Hold:
                raise
            except Exception:
                raise Hold("HOLD_RAM_STREAM_FAILED") from None
            out.flush()
            os.fsync(out.fileno())
        if count != size or digest.hexdigest() != expected:
            raise Hold("HOLD_RAM_STREAM_SHA_MISMATCH")
        require_run_allowed()
        if _ram_available_bytes() < reserve_bytes:
            raise Hold("HOLD_RAM_PRESSURE_AFTER_STREAM")
        try:
            os.link(tmp, dest)
        except FileExistsError:
            raise Hold("HOLD_RAM_CONCURRENT_WRITER") from None
        return {"state": "WARM_RAM_SHA_VERIFIED", "local": str(dest),
                "bytes": count, "sha256": expected, "gpu_unchanged": True,
                "disk_downloaded": False, "student_evicted": False}
    finally:
        Path(tmp).unlink(missing_ok=True)



class RAMWeightHandle:
    """Memfd is valid only while owning OneHost process retains this handle.

    The path /proc/self/fd/<fd> is usable only within the same process.
    For a separate native loader, use the owner's /proc/<pid>/fd/<fd> under
    an explicitly permissioned local process; this does not spawn one.
    """
    def __init__(self, fd, digest, size):
        self.fd, self.sha256, self.bytes = fd, digest, size
        self.closed = False
    @property
    def local(self):
        if self.closed:
            raise Hold("HOLD_MEMFD_CLOSED")
        return f"/proc/self/fd/{self.fd}"
    def close(self):
        if not self.closed:
            os.close(self.fd)
            self.closed = True
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, traceback):
        self.close()


def _memfd_available_bytes():
    """Conservative headroom excluding /dev/shm size; no swap fallback."""
    try:
        lines = Path("/proc/meminfo").read_text().splitlines()
        available = [int(row.split()[1]) * 1024 for row in lines
                     if row.startswith("MemAvailable:")]
        if len(available) != 1:
            raise Hold("HOLD_HOST_RAM_UNVERIFIED")
        host_free = available[0]
        cmax = Path("/sys/fs/cgroup/memory.max")
        ccur = Path("/sys/fs/cgroup/memory.current")
        if cmax.is_file() and ccur.is_file():
            limit = cmax.read_text().strip()
            current = int(ccur.read_text().strip())
            cgroup_free = (max(0, int(limit)-current)
                           if limit.isdigit() else host_free)
            swap = Path("/sys/fs/cgroup/memory.swap.current")
            if swap.is_file() and int(swap.read_text().strip()) > 0:
                raise Hold("HOLD_SWAP_IN_USE")
        else:
            limit_path = Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")
            current_path = Path("/sys/fs/cgroup/memory/memory.usage_in_bytes")
            if not limit_path.is_file() or not current_path.is_file():
                raise Hold("HOLD_CGROUP_RAM_UNVERIFIED")
            limit, current = int(limit_path.read_text()), int(current_path.read_text())
            cgroup_free = max(0, limit-current) if limit < (1 << 60) else host_free
        return min(host_free, cgroup_free)
    except Hold:
        raise
    except (OSError, ValueError, IndexError):
        raise Hold("HOLD_MEMFD_MEMORY_UNVERIFIED") from None


def warm_memfd(s3, key, *, reserve_bytes=RAM_RESERVE):
    """Native OneHost-only API: verified S3 model weight directly into RAM.

    Not a CLI command: returning only a path would close the fd on process
    exit. Owner must keep handle alive until the native teacher unloads.
    No model is loaded, no VRAM is changed, no separate service is created.
    """
    if not 0 <= reserve_bytes <= 256 * 1024**3:
        raise Hold("HOLD_RAM_RESERVE_BOUNDS")
    if not hasattr(os, "memfd_create") or not hasattr(os, "MFD_ALLOW_SEALING"):
        raise Hold("HOLD_MEMFD_UNSUPPORTED")
    try:
        import fcntl
    except ImportError:
        raise Hold("HOLD_MEMFD_SEALS_UNSUPPORTED") from None
    matched = KEY.fullmatch(key)
    if not matched:
        raise Hold("HOLD_INVALID_CONTENT_ADDRESS")
    require_run_allowed()
    expected, _ = matched.groups()
    head = _head(s3, key)
    if head is None or head.get("Metadata", {}).get("sha256") != expected:
        raise Hold("HOLD_REMOTE_METADATA_MISMATCH")
    size = head.get("ContentLength")
    if not isinstance(size, int) or size <= 0 or size > RAM_MAX_OBJECT:
        raise Hold("HOLD_RAM_OBJECT_SIZE")
    available = _memfd_available_bytes()
    if available < size + reserve_bytes:
        return {"state": "HOLD_RAM_RESERVE", "needed_bytes": size + reserve_bytes,
                "free_bytes": available, "no_files_modified": True}
    fd = os.memfd_create("nox-onehost-weight-" + expected[:12],
                         os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    handle = RAMWeightHandle(fd, expected, size)
    try:
        try:
            body = s3.get_object(Bucket=BUCKET, Key=key)["Body"]
            count, digest = 0, hashlib.sha256()
            try:
                for chunk in body.iter_chunks(chunk_size=CHUNK):
                    require_run_allowed()
                    if not chunk:
                        continue
                    count += len(chunk)
                    if count > size:
                        raise Hold("HOLD_MEMFD_REMOTE_OVERRUN")
                    if _memfd_available_bytes() < reserve_bytes + len(chunk):
                        raise Hold("HOLD_MEMFD_RAM_PRESSURE")
                    off = 0
                    while off < len(chunk):
                        off += os.write(fd, chunk[off:])
                    digest.update(chunk)
            finally:
                body.close()
        except Hold:
            raise
        except Exception:
            raise Hold("HOLD_MEMFD_REMOTE_STREAM") from None
        if count != size or digest.hexdigest() != expected:
            raise Hold("HOLD_MEMFD_SHA_MISMATCH")
        require_run_allowed()
        if _memfd_available_bytes() < reserve_bytes:
            raise Hold("HOLD_MEMFD_RAM_AFTER_STREAM")
        os.lseek(fd, 0, os.SEEK_SET)
        seals = (fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW |
                 fcntl.F_SEAL_SEAL)
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals)
        return handle
    except Exception:
        handle.close()
        raise


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("probe")
    back = sub.add_parser("backup")
    back.add_argument("--model-root", required=True)
    back.add_argument("--file", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--key", required=True)
    rest = sub.add_parser("restore")
    rest.add_argument("--key", required=True)
    rest.add_argument("--cache-root", required=True)
    rest.add_argument("--reserve-gib", type=int, default=10)
    ram = sub.add_parser("warm-ram")
    ram.add_argument("--key", required=True)
    ram.add_argument("--ram-root", default=RAM_ROOT)
    ram.add_argument("--reserve-gib", type=int, default=12)
    args = ap.parse_args(argv)
    try:
        cli = s3_from_env()
        if args.command == "probe":
            result = probe(cli)
        elif args.command == "backup":
            result = backup(cli, args.model_root, args.file)
        elif args.command == "verify":
            result = verify_remote(cli, args.key)
        elif args.command == "warm-ram":
            if not 0 <= args.reserve_gib <= 256:
                raise Hold("HOLD_RAM_RESERVE_BOUNDS")
            result = warm_ram(cli, args.key, args.ram_root,
                              args.reserve_gib * 1024**3)
        else:
            if not 1 <= args.reserve_gib <= 1024:
                raise Hold("HOLD_RESERVE_BOUNDS")
            result = restore(cli, args.key, args.cache_root,
                             args.reserve_gib * 1024**3)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2 if result["state"].startswith("HOLD_") else 0
    except Hold as exc:
        print(json.dumps({"state": str(exc)}, sort_keys=True))
        return 2
    except Exception:
        # Do not leak exception repr (some SDK exceptions contain credentials).
        print('{"state":"HOLD_UNCLASSIFIED_STORAGE_ERROR"}')
        return 2


if __name__ == "__main__":
    sys.exit(main())
