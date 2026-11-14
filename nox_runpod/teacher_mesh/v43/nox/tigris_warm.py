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
    return any(Path(s).exists() for s in STOP_PATHS)


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
    args = ap.parse_args(argv)
    try:
        cli = s3_from_env()
        if args.command == "probe":
            result = probe(cli)
        elif args.command == "backup":
            result = backup(cli, args.model_root, args.file)
        elif args.command == "verify":
            result = verify_remote(cli, args.key)
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
