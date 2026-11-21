#!/usr/bin/env python3
"""Bounded, auditable source-cycle records for original NOX TaskID 4B04.

This module validates explicit evidence supplied by a caller; it does not
generate hypotheses, execute commands, inspect a worktree, run checks, publish
to S03, or claim task acceptance. It stores only short public summaries and
sanitized references. The schema rejects extra fields, including private
reasoning/scratchpad fields. Caller-reported checks can produce only a proposed
fact/skill outcome; their receipt bytes and authenticity are never verified.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any
from urllib.parse import urlsplit, urlunsplit

INPUT_SCHEMA = "nox.reflection.input.v1"
RECEIPT_SCHEMA = "nox.reflection.receipt.v1"
TASK_ID = "4B04"
TASK_SPEC_SHA256 = "26f86c4f7fed48288b3e7c807eabea1c89de21e65fc44704a00d1823a90a1617"
SOURCE_REGISTRY_BLOB_SHA = "f5c45dc8919b1b800e89a421676a3627e75fb3bb"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
RECORD_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
BRANCH = re.compile(r"(?:codex|work|repair|feature|task)/[A-Za-z0-9][A-Za-z0-9._/-]{0,119}\Z")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SECRET_PATTERN = re.compile(
    r"(?i)(?:\bbearer\s+\S{8,}|\b(?:token|access[_-]?token|api[_-]?key|client[_-]?secret|secret|password|authorization)\s*[:=]\s*\S+|"
    r"[?&](?:token|access[_-]?token|api[_-]?key|client[_-]?secret|signature)=\S+|"
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|AIza[A-Za-z0-9_-]{30,})\b)"
)
MAX_INPUT_BYTES = 65536
MAX_RECEIPT_FILE_BYTES = 8 * 1024 * 1024
MAX_SOURCE_FILES = 40


class ReflectionError(ValueError):
    """Input is incomplete, unsafe, or not bound to the original 4B04 spec."""


def _exact_keys(value: Any, required: set[str], optional: Any = ()) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReflectionError("each record section must be an object")
    keys = set(value)
    if not required <= keys or keys - required - set(optional):
        raise ReflectionError("record section has missing or unsupported fields")
    return value


def _text(value: Any, field: str, max_length: int, *, min_length: int = 1) -> str:
    if not isinstance(value, str):
        raise ReflectionError(f"{field} must be text")
    clean = " ".join(value.split())
    if not min_length <= len(clean) <= max_length or CONTROL.search(clean):
        raise ReflectionError(f"{field} must contain {min_length}-{max_length} safe characters")
    return clean


def _summary(value: Any, field: str, max_length: int) -> str:
    clean = _text(value, field, max_length)
    if SECRET_PATTERN.search(clean):
        raise ReflectionError(f"{field} resembles a credential or token")
    return clean


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ReflectionError(f"{field} must be a lowercase SHA-256")
    return value


def _git_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not GIT_SHA.fullmatch(value):
        raise ReflectionError(f"{field} must be a lowercase Git object SHA")
    return value


def _timestamp(value: Any, field: str) -> str:
    stamp = _text(value, field, 40)
    try:
        parsed = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReflectionError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReflectionError(f"{field} must include a timezone")
    return parsed.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _date(value: Any, field: str) -> str:
    date_text = _text(value, field, 10)
    try:
        parsed = dt.date.fromisoformat(date_text)
    except ValueError as exc:
        raise ReflectionError(f"{field} must be YYYY-MM-DD") from exc
    return parsed.isoformat()


def _https_reference(value: Any, field: str) -> str:
    raw = _text(value, field, 2048)
    parts = urlsplit(raw)
    if parts.scheme.lower() != "https" or not parts.hostname or parts.username or parts.password:
        raise ReflectionError(f"{field} must be an HTTPS reference without credentials")
    try:
        port = parts.port
    except ValueError as exc:
        raise ReflectionError(f"{field} has an invalid port") from exc
    if port not in (None, 443):
        raise ReflectionError(f"{field} may not use a non-default HTTPS port")
    host = parts.hostname.lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ReflectionError(f"{field} may not point to a local host")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and not ip.is_global:
        raise ReflectionError(f"{field} may not point to a non-public IP")
    return urlunsplit(("https", host, parts.path or "/", "", ""))


def _source_path(value: Any) -> str:
    path = _text(value, "change.files[]", 256)
    if path.startswith(("/", "\\")) or "\\" in path or any(part in {"", ".", ".."} for part in path.split("/")):
        raise ReflectionError("change.files[] must be a normalized repository-relative path")
    return path


def validate_record(data: Any) -> dict[str, Any]:
    """Return a normalized source-cycle receipt; no mutation or acceptance."""
    top = _exact_keys(
        data,
        {"schema", "record_id", "task", "failure", "hypothesis", "change", "verification"},
        {"outcome"},
    )
    if top["schema"] != INPUT_SCHEMA:
        raise ReflectionError("unsupported input schema")
    record_id = top["record_id"]
    if not isinstance(record_id, str) or not RECORD_ID.fullmatch(record_id):
        raise ReflectionError("record_id must use 1-80 safe characters")

    task = _exact_keys(top["task"], {"id", "spec_sha256", "registry_blob_sha"})
    if task["id"] != TASK_ID or task["spec_sha256"] != TASK_SPEC_SHA256:
        raise ReflectionError("task must match the pinned original 4B04 specification")
    if task["registry_blob_sha"] != SOURCE_REGISTRY_BLOB_SHA:
        raise ReflectionError("task must bind the pinned original 295 registry blob")
    task_receipt = {
        "id": TASK_ID,
        "spec_sha256": TASK_SPEC_SHA256,
        "registry_blob_sha": SOURCE_REGISTRY_BLOB_SHA,
    }

    failure = _exact_keys(top["failure"], {"observed_at", "summary", "evidence_url", "evidence_sha256"})
    failure_receipt = {
        "observed_at": _timestamp(failure["observed_at"], "failure.observed_at"),
        "summary": _summary(failure["summary"], "failure.summary", 280),
        "evidence_url": _https_reference(failure["evidence_url"], "failure.evidence_url"),
        "evidence_sha256": _digest(failure["evidence_sha256"], "failure.evidence_sha256"),
    }

    hypothesis = _exact_keys(top["hypothesis"], {"statement", "observable"})
    hypothesis_receipt = {
        "statement": _summary(hypothesis["statement"], "hypothesis.statement", 280),
        "observable": _summary(hypothesis["observable"], "hypothesis.observable", 280),
    }

    change = _exact_keys(
        top["change"],
        {"branch", "commit_sha", "diff_sha256", "files", "permission_receipt_url", "permission_receipt_sha256"},
    )
    if not isinstance(change["branch"], str) or not BRANCH.fullmatch(change["branch"]):
        raise ReflectionError("change.branch must name an allowed work/repair feature branch")
    files = change["files"]
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_SOURCE_FILES:
        raise ReflectionError(f"change.files must contain 1-{MAX_SOURCE_FILES} paths")
    safe_files = [_source_path(path) for path in files]
    if len(set(safe_files)) != len(safe_files):
        raise ReflectionError("change.files contains duplicates")
    change_receipt = {
        "branch": change["branch"],
        "commit_sha": _git_sha(change["commit_sha"], "change.commit_sha"),
        "diff_sha256": _digest(change["diff_sha256"], "change.diff_sha256"),
        "files": safe_files,
        "permission_receipt_url": _https_reference(change["permission_receipt_url"], "change.permission_receipt_url"),
        "permission_receipt_sha256": _digest(change["permission_receipt_sha256"], "change.permission_receipt_sha256"),
    }

    verification = _exact_keys(
        top["verification"],
        {"status", "verified_at", "target_commit_sha", "receipt_url", "artifact_sha256"},
    )
    status = verification["status"]
    if not isinstance(status, str) or status not in {"PASS", "FAIL"}:
        raise ReflectionError("verification.status must be PASS or FAIL")
    verification_receipt = {
        "reported_status": status,
        "reported_at": _timestamp(verification["verified_at"], "verification.verified_at"),
        "target_commit_sha": _git_sha(verification["target_commit_sha"], "verification.target_commit_sha"),
        "receipt_reference": _https_reference(verification["receipt_url"], "verification.receipt_url"),
        "claimed_artifact_sha256": _digest(verification["artifact_sha256"], "verification.artifact_sha256"),
    }
    if verification_receipt["target_commit_sha"] != change_receipt["commit_sha"]:
        raise ReflectionError("verification must target the exact source-change commit")

    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "record_id": record_id,
        "task": task_receipt,
        "failure": failure_receipt,
        "hypothesis": hypothesis_receipt,
        "change": change_receipt,
        "verification": verification_receipt,
        "evidence_scope": {
            "input_structure_validated": True,
            "external_receipt_bytes_verified": False,
            "claim_authenticity_verified": False,
            "owner_permission_verified": False,
            "outcome_published": False,
        },
        "original_task_accepted": False,
    }
    if status == "PASS":
        if "outcome" not in top:
            raise ReflectionError("a PASS requires a cited fact or skill outcome")
        outcome = _exact_keys(
            top["outcome"],
            {"kind", "summary", "basis_url", "basis_date", "basis_sha256"},
        )
        if not isinstance(outcome["kind"], str) or outcome["kind"] not in {"fact", "skill"}:
            raise ReflectionError("outcome.kind must be fact or skill")
        basis_sha = _digest(outcome["basis_sha256"], "outcome.basis_sha256")
        if basis_sha != verification_receipt["claimed_artifact_sha256"]:
            raise ReflectionError("proposed outcome SHA must match the caller-reported artifact SHA")
        receipt["proposed_outcome"] = {
            "kind": outcome["kind"],
            "summary": _summary(outcome["summary"], "outcome.summary", 500),
            "basis_reference": _https_reference(outcome["basis_url"], "outcome.basis_url"),
            "basis_date": _date(outcome["basis_date"], "outcome.basis_date"),
            "claimed_basis_sha256": basis_sha,
        }
        receipt["status"] = "SOURCE_CYCLE_INPUT_VALIDATED_WITH_PROPOSED_OUTCOME"
    else:
        if "outcome" in top:
            raise ReflectionError("a failed check cannot publish a fact or skill")
        receipt["status"] = "SOURCE_CYCLE_INPUT_VALIDATED_WITH_REPORTED_FAIL"

    unsigned = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    receipt["receipt_sha256"] = hashlib.sha256(unsigned).hexdigest()
    return receipt


def append_receipt(path: str | os.PathLike[str], receipt: dict[str, Any]) -> None:
    """Append one schema-validated receipt to a private local JSONL ledger."""
    target = Path(path)
    parent = target.parent.absolute()
    cursor = parent
    while cursor != cursor.parent:
        if cursor.is_symlink():
            raise ReflectionError("receipt ledger parent path may not contain symlinks")
        cursor = cursor.parent
    try:
        parent_info = parent.stat(follow_symlinks=False)
    except OSError as exc:
        raise ReflectionError("receipt ledger parent must already exist") from exc
    if not stat.S_ISDIR(parent_info.st_mode) or parent_info.st_uid != os.geteuid() or parent_info.st_mode & 0o077:
        raise ReflectionError("receipt ledger parent must be owner-owned and private (no group/world access)")
    flags = os.O_RDWR | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_nlink != 1):
            raise ReflectionError("receipt ledger must be owner-owned, private, single-link regular file")
        if info.st_size > MAX_RECEIPT_FILE_BYTES:
            raise ReflectionError("receipt ledger exceeds the 8 MiB bound")
        os.lseek(fd, 0, os.SEEK_SET)
        previous = os.read(fd, MAX_RECEIPT_FILE_BYTES + 1)
        if len(previous) > MAX_RECEIPT_FILE_BYTES:
            raise ReflectionError("receipt ledger exceeds the 8 MiB bound")
        if previous and not previous.endswith(b"\n"):
            raise ReflectionError("receipt ledger must end on a complete record boundary")
        for line in previous.splitlines():
            try:
                existing = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ReflectionError("receipt ledger contains a malformed line") from exc
            if isinstance(existing, dict) and existing.get("record_id") == receipt["record_id"]:
                raise ReflectionError("record_id already exists in the append-only ledger")
        encoded = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(previous) + len(encoded) > MAX_RECEIPT_FILE_BYTES:
            raise ReflectionError("append would exceed the 8 MiB ledger bound")
        offset = 0
        while offset < len(encoded):
            offset += os.write(fd, encoded[offset:])
        os.fsync(fd)
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _load_input(path: str) -> Any:
    """Read one bounded regular-file snapshot from a single NOFOLLOW descriptor.

    A pathname may be swapped between an is_file/is_symlink preflight and
    read_bytes(). Descriptor-first checks prevent a raced symlink/FIFO/device
    from replacing the approved input, and bound growth after fstat().
    """
    if not hasattr(os, "O_NOFOLLOW"):
        raise ReflectionError("safe non-symlink input opening is unavailable")
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ReflectionError("input must be an accessible non-symlink file") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_INPUT_BYTES:
            raise ReflectionError("input must be a regular file no larger than 64 KiB")
        data = bytearray()
        while len(data) <= MAX_INPUT_BYTES:
            part = os.read(fd, min(8192, MAX_INPUT_BYTES + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        if len(data) > MAX_INPUT_BYTES:
            raise ReflectionError("input grew beyond the 64 KiB limit")
    finally:
        os.close(fd)
    try:
        return json.loads(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ReflectionError("input must be UTF-8 JSON") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate one bounded 4B04 source reflection record.")
    parser.add_argument("--input", required=True, help="JSON record following nox.reflection.input.v1")
    parser.add_argument("--append", help="optional owner-private local JSONL receipt ledger")
    args = parser.parse_args(argv)
    try:
        receipt = validate_record(_load_input(args.input))
        if args.append:
            append_receipt(args.append, receipt)
    except (OSError, json.JSONDecodeError, ReflectionError) as exc:
        print(json.dumps({"status": "HOLD", "error": f"{type(exc).__name__}: {str(exc)[:300]}"}), file=sys.stderr)
        return 2
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

