#!/usr/bin/env python3
"""Owner-only read-only admission gate for the pinned Maya/DeepSeek deployment.

This action never removes STOP, creates a lease, writes model data, changes a
service, allocates CUDA memory, or starts/resumes a model. It reports READY
only after the exact owner lease, integrated source pins, Maya binary, complete
SHA-verified DeepSeek pack, and seekable storage reserve all match.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
import re
import stat
import sys
import time
from pathlib import Path

ROOT = Path("/root/nox")
INSTANCE = 60509551
OWNER = "MSSTXNEWS"
RESERVE_BYTES = 16 * 1024**3
MIN_PACK_BYTES = 248834257920
LEASE_PATH = ROOT / "state" / "dispatcher" / "model_deploy_lease.json"
MAYA_PATH = ROOT / "engine_builds" / "maya-c81fab6c9d63-cu124-sm70-v1" / "build" / "maya-ds4"
MAYA_SHA256 = "3783980bb65861de36fe4d93b8e6bbd6b6a631207677bcabf330bf7830c21b20"
PACK_FILES = {
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf": (5780704, "f356f198561f56df36f7ab92d7238a926646d76de992c34f15bcb939a5f529b9"),
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00002-of-00006.gguf": (39535781184, "25af3785ccf925f54137e1ead4c481a8952315dc0b1af6519a99407f67bce8f3"),
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00003-of-00006.gguf": (39736712000, "8168d0998fc494def2e1952d83c131425a108660aae9d29190f5a8670ab62b48"),
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00004-of-00006.gguf": (39036908384, "9eb9b4de1968f150dfc207eb31c27be9cd9b5666a9a6246bde8a22b184b4bee0"),
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00005-of-00006.gguf": (19923784832, "7e35f6b4e6fc46f6c4b152b593d84d683c5ece695ae6ad734f556198c041bec1"),
    "DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf": (110595290816, "3dac4c54893ad7aa89103c0028500eadc78e74112cef3a2930a97e67dc9fb4f3"),
}
STOP_PATHS = (
    ROOT / "STOP", ROOT / "STOP.flag", ROOT / "stop.flag", ROOT / ".stop",
    ROOT / "program" / "STOP", ROOT / "state" / "STOP",
    ROOT / "state" / "STOP.flag", ROOT / "state" / "OWNER_STOP",
    ROOT / "state" / "OWNER_MAINTENANCE.flag", ROOT / "state" / "OWNER_MAINTENANCE",
    ROOT / "state" / "TRAIN_HOLD", ROOT / "state" / "TRAIN_PAUSE",
    Path("/workspace/NOX_STOP"),
)
ALLOWED_STORAGE_ROOTS = (ROOT, Path("/workspace"), Path("/mnt/nox"))

class Hold(RuntimeError):
    pass

def same(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_nlink,
            st.st_size, st.st_mtime_ns, st.st_ctime_ns)

def lstat_path(path, kind=None):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise Hold("HOLD_PATH_NOT_CANONICAL")
    current = Path(path.anchor)
    parts = path.parts[1:]
    for index, part in enumerate(parts):
        current = current / part
        try:
            st = os.lstat(current)
        except FileNotFoundError as exc:
            raise Hold("HOLD_PATH_MISSING") from exc
        except OSError as exc:
            raise Hold("HOLD_PATH_UNREADABLE") from exc
        if stat.S_ISLNK(st.st_mode):
            raise Hold("HOLD_PATH_SYMLINK")
        leaf = index == len(parts) - 1
        if not leaf and not stat.S_ISDIR(st.st_mode):
            raise Hold("HOLD_PATH_PARENT_NOT_DIRECTORY")
        if leaf and kind == "dir" and not stat.S_ISDIR(st.st_mode):
            raise Hold("HOLD_PATH_NOT_DIRECTORY")
        if leaf and kind == "file":
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_nlink != 1:
                raise Hold("HOLD_PATH_NOT_PRIVATE_REGULAR_FILE")
    return st

def read_small_json(path, limit=8192):
    before = lstat_path(path, "file")
    if before.st_size > limit or before.st_mode & 0o077:
        raise Hold("HOLD_PRIVATE_JSON_METADATA")
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        opened = os.fstat(fd)
        if same(opened) != same(before):
            raise Hold("HOLD_JSON_FILE_CHANGED")
        raw = bytearray()
        while len(raw) <= limit:
            chunk = os.read(fd, min(4096, limit + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(fd)
        if same(after) != same(opened) or same(lstat_path(path, "file")) != same(opened):
            raise Hold("HOLD_JSON_FILE_CHANGED")
        if len(raw) != opened.st_size or len(raw) > limit:
            raise Hold("HOLD_PRIVATE_JSON_SIZE")
    except OSError as exc:
        raise Hold("HOLD_PRIVATE_JSON_UNREADABLE") from exc
    finally:
        if fd is not None:
            os.close(fd)
    def unique(pairs):
        doc = {}
        for key, value in pairs:
            if key in doc:
                raise Hold("HOLD_JSON_DUPLICATE_KEY")
            doc[key] = value
        return doc
    def no_constant(_):
        raise Hold("HOLD_JSON_NONFINITE")
    try:
        value = json.loads(bytes(raw), object_pairs_hook=unique, parse_constant=no_constant)
    except Hold:
        raise
    except (ValueError, UnicodeError, TypeError) as exc:
        raise Hold("HOLD_PRIVATE_JSON_INVALID") from exc
    if not isinstance(value, dict):
        raise Hold("HOLD_PRIVATE_JSON_SCHEMA")
    return value

def sha256_file(path, expected_bytes=None):
    before = lstat_path(path, "file")
    if expected_bytes is not None and before.st_size != expected_bytes:
        raise Hold("HOLD_MODEL_FILE_SIZE")
    if before.st_mode & 0o077:
        raise Hold("HOLD_MODEL_FILE_PERMISSIONS")
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        opened = os.fstat(fd)
        if same(opened) != same(before):
            raise Hold("HOLD_MODEL_FILE_CHANGED")
        if opened.st_size <= 0:
            raise Hold("HOLD_MODEL_FILE_EMPTY")
        # A genuine positional read proves that this backing path is seekable.
        if os.pread(fd, 1, 0) == b"" or os.pread(fd, 1, opened.st_size - 1) == b"":
            raise Hold("HOLD_MODEL_FILE_NOT_SEEKABLE")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(fd, 8 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(fd)
        if same(after) != same(opened) or same(lstat_path(path, "file")) != same(opened):
            raise Hold("HOLD_MODEL_FILE_CHANGED")
        return digest.hexdigest(), opened.st_size
    except OSError as exc:
        raise Hold("HOLD_MODEL_FILE_UNREADABLE") from exc
    finally:
        if fd is not None:
            os.close(fd)

def owner_stop():
    present = []
    unreadable = []
    for path in STOP_PATHS:
        try:
            os.lstat(path)
            present.append(str(path))
        except FileNotFoundError:
            continue
        except OSError:
            unreadable.append(str(path))
    if unreadable:
        raise Hold("HOLD_OWNER_STOP_UNREADABLE")
    if present:
        raise Hold("HOLD_OWNER_STOP")
    return "ABSENT"

def read_lease(source_sha):
    lease = read_small_json(LEASE_PATH)
    now = time.time()
    expiry = lease.get("expires_unix")
    if (lease.get("schema") != "NOX_ONEHOST_OWNER_LEASE_V1"
        or lease.get("instance_id") != INSTANCE
        or lease.get("owner") != OWNER
        or lease.get("resource") != "p0.model_deploy"
        or lease.get("source_sha") != source_sha
        or not isinstance(lease.get("request_id"), str)
        or not re.fullmatch(r"[0-9]{1,20}", lease["request_id"])
        or type(expiry) not in (int, float) or not math.isfinite(expiry)
        or not now < expiry <= now + 7200):
        raise Hold("HOLD_ORIGINAL_DEPLOY_LEASE")
    root = lease.get("model_pack_root")
    if not isinstance(root, str):
        raise Hold("HOLD_LEASE_STORAGE_ROOT")
    path = Path(root)
    if not path.is_absolute() or ".." in path.parts:
        raise Hold("HOLD_LEASE_STORAGE_ROOT")
    if not any(path == allowed or allowed in path.parents for allowed in ALLOWED_STORAGE_ROOTS):
        raise Hold("HOLD_STORAGE_ROOT_NOT_ALLOWED")
    return lease, path

def verify_receipt(path, name, size, digest):
    doc = read_small_json(path)
    at = doc.get("at_unix")
    if (doc.get("schema") != "NOX_DEEPSEEK_RANGE_RECEIPT_V10"
        or doc.get("file") != name or doc.get("bytes") != size
        or doc.get("sha256") != digest
        or not isinstance(doc.get("request"), str)
        or not re.fullmatch(r"[0-9]{1,20}", doc["request"])
        or type(doc.get("new_bytes")) is not int
        or not 0 <= doc["new_bytes"] <= size
        or type(at) not in (int, float) or not math.isfinite(at) or at <= 0):
        raise Hold("HOLD_MODEL_FILE_RECEIPT")
    return True

def inspect_pack(root):
    directory = lstat_path(root, "dir")
    vfs = os.statvfs(root)
    total = vfs.f_blocks * vfs.f_frsize
    free = vfs.f_bavail * vfs.f_frsize
    if total < MIN_PACK_BYTES + RESERVE_BYTES:
        raise Hold("HOLD_STORAGE_TOTAL_CAPACITY")
    if free < RESERVE_BYTES:
        raise Hold("HOLD_STORAGE_RESERVE")
    checked = 0
    observed = 0
    for name, (size, expected) in PACK_FILES.items():
        path = root / name
        actual, count = sha256_file(path, size)
        if actual != expected:
            raise Hold("HOLD_MODEL_FILE_SHA")
        verify_receipt(root / (name + ".verified.json"), name, size, expected)
        checked += 1
        observed += count
    if observed != MIN_PACK_BYTES:
        raise Hold("HOLD_MODEL_PACK_TOTAL")
    return {"state": "SHA_VERIFIED", "files": checked, "bytes": observed,
            "storage_total_bytes": total, "storage_free_bytes": free,
            "seekable": True}

def main():
    request = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    source_sha = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    if not re.fullmatch(r"[0-9]{1,20}", request):
        raise Hold("HOLD_OWNER_REQUEST_ID")
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise Hold("HOLD_SOURCE_PIN")
    result = {"schema": "NOX_DEPLOY_READY_GATE_V1", "request": request,
              "source_sha": source_sha, "action_taken": "NONE",
              "stop_flags_removed": 0, "service_control_actions": 0,
              "training_actions": 0, "files_written": 0, "start_attempted": False}
    blockers = []
    try:
        result["owner_stop"] = owner_stop()
    except Hold as exc:
        result["owner_stop"] = str(exc)
        blockers.append(str(exc))
    try:
        lease, root = read_lease(source_sha)
        result["lease"] = "VALID"
        result["storage_root"] = str(root)
        result["model_pack"] = inspect_pack(root)
    except Hold as exc:
        result["lease_or_pack"] = str(exc)
        blockers.append(str(exc))
    try:
        observed, _ = sha256_file(MAYA_PATH)
        if observed != MAYA_SHA256:
            raise Hold("HOLD_MAYA_BINARY_SHA")
        result["maya_binary"] = "SHA_PIN_MATCH"
    except Hold as exc:
        result["maya_binary"] = str(exc)
        blockers.append(str(exc))
    if blockers:
        result["state"] = "HOLD"
        result["blockers"] = sorted(set(blockers))
        print("NOX_MAINT_DEPLOY_READY_STATE=" + json.dumps(result, sort_keys=True), flush=True)
        raise SystemExit(2)
    result["state"] = "READY_NO_START"
    print("NOX_MAINT_DEPLOY_READY_STATE=" + json.dumps(result, sort_keys=True), flush=True)
    print("NOX_MAINT_DEPLOY_READY_COMPLETE=true", flush=True)

if __name__ == "__main__":
    try:
        main()
    except Hold as exc:
        print("NOX_MAINT_DEPLOY_READY_RESULT=" + str(exc), flush=True)
        raise SystemExit(2)
