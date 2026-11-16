"""Fail-closed Maya E2E and active training-lease gate for V135.

This module only verifies owner-issued receipts. It never creates or edits one.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from pathlib import Path

INSTANCE = 60509551
ROOT = Path("/root/nox")
READINESS = ROOT / "state/maya_ds4_owner_deploy/readiness.json"
READINESS_DIR = ROOT / "state/maya_ds4_owner_deploy"
DISPATCHER_DIR = ROOT / "state/dispatcher"
MODEL_ID = "deepseek-v4.1-flash"
SOURCE_REVISION = "65d53bc8be65123e255ff02f3ded958b6dbf54fd"
MAYA_COMMIT = "c81fab6c9d63cf69b928f92460e0a662b28aa9ec"
MAYA_BINARY_SHA256 = "3783980bb65861de36fe4d93b8e6bbd6b6a631207677bcabf330bf7830c21b20"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_REQUEST = re.compile(r"^[A-Za-z0-9._:-]{1,160}$")


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("HOLD_DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def _secure_json(path: Path, base: Path, max_bytes: int) -> tuple[dict, str]:
    path = Path(path)
    base = Path(base)
    if (not path.is_absolute() or ".." in path.parts
            or path.parts[:len(base.parts)] != base.parts
            or len(path.parts) <= len(base.parts)):
        raise RuntimeError("HOLD_MAYA_EVIDENCE_PATH")
    try:
        before = os.lstat(path)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                or before.st_nlink != 1 or before.st_mode & 0o077
                or before.st_size <= 0 or before.st_size > max_bytes):
            raise RuntimeError("HOLD_MAYA_EVIDENCE_PERMISSIONS")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        try:
            opened = os.fstat(fd)
            ident = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mode, s.st_uid,
                               s.st_nlink, s.st_mtime_ns, s.st_ctime_ns)
            if not stat.S_ISREG(opened.st_mode) or ident(opened) != ident(before):
                raise RuntimeError("HOLD_MAYA_EVIDENCE_CHANGED")
            raw = bytearray()
            while len(raw) <= max_bytes:
                chunk = os.read(fd, min(65536, max_bytes + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
            after = os.fstat(fd)
            if len(raw) != opened.st_size or ident(after) != ident(opened):
                raise RuntimeError("HOLD_MAYA_EVIDENCE_CHANGED")
            path_after = os.lstat(path)
            if ident(path_after) != ident(opened):
                raise RuntimeError("HOLD_MAYA_EVIDENCE_CHANGED")
        finally:
            os.close(fd)
    except OSError as exc:
        raise RuntimeError("HOLD_MAYA_EVIDENCE_UNREADABLE") from exc
    try:
        value = json.loads(bytes(raw).decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               ValueError("HOLD_NONFINITE_JSON")))
    except (ValueError, UnicodeError, TypeError) as exc:
        raise RuntimeError("HOLD_MAYA_EVIDENCE_JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("HOLD_MAYA_EVIDENCE_SCHEMA")
    return value, hashlib.sha256(raw).hexdigest()


def verify_maya_admission(native: dict, *, now: int | None = None) -> dict:
    """Bind signed training admission to accepted Maya E2E receipt and p0.training lease."""
    if not isinstance(native, dict):
        raise RuntimeError("HOLD_MAYA_NATIVE_ADMISSION")
    ts = int(time.time()) if now is None else now

    if native.get("maya_readiness_path") != str(READINESS):
        raise RuntimeError("HOLD_MAYA_READINESS_PATH")
    receipt, receipt_sha = _secure_json(READINESS, READINESS_DIR, 32768)
    if not _SHA.fullmatch(str(native.get("maya_readiness_receipt_sha256"))) or (
            receipt_sha != native.get("maya_readiness_receipt_sha256")):
        raise RuntimeError("HOLD_MAYA_READINESS_SHA")
    expected = {
        "schema": "NOX_MAYA_CHAT_ACCEPTANCE_V1",
        "model_id": MODEL_ID,
        "source_revision": SOURCE_REVISION,
        "maya_commit": MAYA_COMMIT,
        "maya_binary_sha256": MAYA_BINARY_SHA256,
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise RuntimeError("HOLD_MAYA_MODEL_IDENTITY")
    for key in ("model_manifest_sha256", "model_pack_receipt_sha256",
                "chat_receipt_sha256", "cancel_receipt_sha256",
                "s03_receipt_sha256", "lease_sha256"):
        if not _SHA.fullmatch(str(receipt.get(key))):
            raise RuntimeError("HOLD_MAYA_RECEIPT_FIELD")
    owner_request = receipt.get("owner_request_id")
    lease_request = receipt.get("lease_request_id")
    if (not isinstance(owner_request, str) or not _REQUEST.fullmatch(owner_request)
            or not isinstance(lease_request, str) or not _REQUEST.fullmatch(lease_request)
            or not isinstance(receipt.get("lease_path"), str)):
        raise RuntimeError("HOLD_MAYA_OWNER_LEASE_BINDING")
    if (native.get("maya_owner_request_id") != owner_request
            or native.get("maya_model_manifest_sha256") != receipt["model_manifest_sha256"]
            or native.get("maya_model_pack_receipt_sha256") != receipt["model_pack_receipt_sha256"]):
        raise RuntimeError("HOLD_MAYA_SIGNED_NATIVE_BINDING")
    accepted, expires = receipt.get("accepted_at_unix"), receipt.get("expires_unix")
    if (type(accepted) is not int or type(expires) is not int or accepted <= 0
            or accepted > ts or expires <= ts or expires - accepted > 7200):
        raise RuntimeError("HOLD_MAYA_READINESS_EXPIRED")

    lease_path = native.get("training_lease_path")
    lease_request_id = native.get("training_lease_request_id")
    if (not isinstance(lease_path, str)
            or not isinstance(lease_request_id, str)
            or not _REQUEST.fullmatch(lease_request_id)):
        raise RuntimeError("HOLD_TRAINING_LEASE_REQUIRED")
    lease, lease_sha = _secure_json(Path(lease_path), DISPATCHER_DIR, 8192)
    if (not _SHA.fullmatch(str(native.get("training_lease_sha256")))
            or lease_sha != native.get("training_lease_sha256")):
        raise RuntimeError("HOLD_TRAINING_LEASE_SHA")
    if (lease.get("schema") != "NOX_ONEHOST_OWNER_LEASE_V1"
            or lease.get("instance_id") != INSTANCE
            or lease.get("owner") != "MSSTXNEWS"
            or lease.get("resource") != "p0.training"
            or lease.get("request_id") != lease_request_id
            or type(lease.get("expires_unix")) not in (int, float)
            or not ts < lease["expires_unix"] <= ts + 7200):
        raise RuntimeError("HOLD_TRAINING_OWNER_LEASE")
    pid, ticks = native.get("training_lease_pid"), native.get("training_lease_start_ticks")
    if (type(pid) is not int or pid <= 0 or type(ticks) is not int or ticks <= 0
            or lease.get("pid") != pid or lease.get("start_ticks") != ticks):
        raise RuntimeError("HOLD_TRAINING_LEASE_PROCESS_IDENTITY")
    return {
        "maya_readiness_receipt_sha256": receipt_sha,
        "maya_model_id": MODEL_ID,
        "maya_source_revision": SOURCE_REVISION,
        "maya_model_manifest_sha256": receipt["model_manifest_sha256"],
        "maya_model_pack_receipt_sha256": receipt["model_pack_receipt_sha256"],
        "maya_binary_sha256": MAYA_BINARY_SHA256,
        "maya_chat_receipt_sha256": receipt["chat_receipt_sha256"],
        "maya_cancel_receipt_sha256": receipt["cancel_receipt_sha256"],
        "maya_s03_receipt_sha256": receipt["s03_receipt_sha256"],
        "maya_owner_request_id": owner_request,
        "training_lease_sha256": lease_sha,
        "training_lease_pid": pid,
        "training_lease_start_ticks": ticks,
    }
