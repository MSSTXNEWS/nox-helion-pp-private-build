#!/usr/bin/env python3
"""Evidence-bound, read-only self-model snapshot builder for original TaskID 3A04.

The input contract covers allowed capabilities, active TaskIDs, weight revision,
external-service availability, Genesis revision, and recent error codes. This
module only validates and normalizes caller-supplied records; it does not probe
services, read server state, access Genesis/S03, or infer missing facts. Every
non-UNKNOWN claim requires a dated SHA-bound source reference. The output
explicitly says that references were not independently fetched and that no
native acceptance is asserted.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit

INPUT_SCHEMA = "nox.self_model.input.v1"
OUTPUT_SCHEMA = "nox.self_model.snapshot.v1"
TASK_ID = "3A04"
TASK_SPEC_SHA256 = "a315692ac5162d6b9a1883cd12b2ce013ce26876dbfd03be08d45c7b1e0e377a"
SOURCE_REGISTRY_BLOB_SHA = "f5c45dc8919b1b800e89a421676a3627e75fb3bb"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
TASK_ID_PATTERN = re.compile(r"(?:[0-9]+[A-Z][0-9]{2}(?:-[0-9]{2})?|I-[0-9]+)\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z")
ERROR_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SENSITIVE_QUERY_KEY = re.compile(
    r"(?i)^(?:access[_-]?token|authorization|auth|api[_-]?key|apikey|client[_-]?secret|secret|password|passwd|"
    r"credential|session(?:id)?|sid|signature|sig|token|jwt|refresh[_-]?token|id[_-]?token|private[_-]?key|"
    r"code|state|x-amz-(?:credential|signature|security-token)|x-goog-(?:credential|signature))$"
)
SENSITIVE_PATH_MARKERS = {
    "access_token", "access-token", "api_key", "api-key", "apikey", "auth", "authorization",
    "client_secret", "client-secret", "credential", "jwt", "password", "secret", "session",
    "signature", "sig", "token",
}
PREFIXED_PATH_SECRET = re.compile(
    r"(?i)(?:\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b|"
    r"\bsk-[A-Za-z0-9_-]{16,}\b|\bAKIA[0-9A-Z]{16}\b|\bAIza[A-Za-z0-9_-]{30,}\b|"
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b)"
)
LONG_PATH_TOKEN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_-]{32,}(?![A-Za-z0-9])")
MAX_INPUT_BYTES = 262144
MAX_CAPABILITIES = 100
MAX_ACTIVE_TASKS = 295
MAX_SERVICES = 100
MAX_RECENT_ERRORS = 50


class SelfModelError(ValueError):
    """Malformed, unbound, or unsafe self-model input."""


def _keys(value: Any, required: set[str], optional: Any = ()) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SelfModelError("section must be an object")
    keys = set(value)
    if not required <= keys or keys - required - set(optional):
        raise SelfModelError("section has missing or unsupported fields")
    return value


def _text(value: Any, field: str, limit: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise SelfModelError(f"{field} must be text")
    result = " ".join(value.split())
    minimum = 0 if allow_empty else 1
    if not minimum <= len(result) <= limit or CONTROL.search(result):
        raise SelfModelError(f"{field} must contain at most {limit} safe characters")
    return result


def _timestamp(value: Any, field: str) -> str:
    raw = _text(value, field, 40)
    try:
        stamp = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SelfModelError(f"{field} must be ISO-8601") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise SelfModelError(f"{field} must include a timezone")
    return stamp.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _reference_url(value: Any, field: str) -> str:
    raw = _text(value, field, 2048)
    parts = urlsplit(raw)
    if parts.scheme.lower() != "https" or not parts.hostname or parts.username or parts.password:
        raise SelfModelError(f"{field} must be an HTTPS reference without credentials")
    try:
        port = parts.port
    except ValueError as exc:
        raise SelfModelError(f"{field} has an invalid port") from exc
    if port not in (None, 443):
        raise SelfModelError(f"{field} may not use a non-default HTTPS port")
    host = parts.hostname.lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise SelfModelError(f"{field} may not point to a local host")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise SelfModelError(f"{field} may not point to a non-public IP")
    for key, _ in parse_qsl(parts.query, keep_blank_values=True):
        if SENSITIVE_QUERY_KEY.fullmatch(unquote(key).strip()):
            raise SelfModelError(f"{field} may not contain sensitive query keys")
    decoded_path = unquote(parts.path)
    segments = [segment for segment in decoded_path.split("/") if segment]
    for index, segment in enumerate(segments[:-1]):
        if segment.casefold() in SENSITIVE_PATH_MARKERS and len(segments[index + 1]) >= 12:
            raise SelfModelError(f"{field} may not contain secret-like path tokens")
    if PREFIXED_PATH_SECRET.search(decoded_path):
        raise SelfModelError(f"{field} may not contain secret-like path tokens")
    for match in LONG_PATH_TOKEN.finditer(decoded_path):
        token = match.group()
        if re.fullmatch(r"(?i)(?:[0-9a-f]{40}|[0-9a-f]{64})", token):
            continue
        if any(char.isalpha() for char in token) and any(char.isdigit() for char in token):
            raise SelfModelError(f"{field} may not contain secret-like path tokens")
    # References are metadata only; strip safe query values and all fragments
    # so a caller cannot accidentally persist signed or session-bearing URLs.
    return urlunsplit(("https", host, parts.path or "/", "", ""))


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise SelfModelError(f"{field} must be a lowercase SHA-256")
    return value


def _evidence(value: Any, field: str, *, required: bool = True) -> dict[str, str] | None:
    if value is None and not required:
        return None
    raw = _keys(value, {"url", "sha256", "observed_at"})
    return {
        "url": _reference_url(raw["url"], field + ".url"),
        "sha256": _sha(raw["sha256"], field + ".sha256"),
        "observed_at": _timestamp(raw["observed_at"], field + ".observed_at"),
    }


def _enum(value: Any, allowed: set[str], field: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise SelfModelError(f"{field} has an unsupported value")
    return value


def _capabilities(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list) or len(values) > MAX_CAPABILITIES:
        raise SelfModelError("capabilities must be a bounded array")
    result = []
    seen = set()
    for item in values:
        row = _keys(item, {"name", "state", "evidence"})
        name = _text(row["name"], "capability.name", 80)
        if not IDENTIFIER.fullmatch(name) or name in seen:
            raise SelfModelError("capability names must be unique safe identifiers")
        seen.add(name)
        state = _enum(row["state"], {"ALLOWED", "DENIED", "UNKNOWN"}, "capability.state")
        evidence = _evidence(row["evidence"], "capability.evidence", required=state != "UNKNOWN")
        result.append({"name": name, "state": state, "evidence": evidence})
    return result


def _active_tasks(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list) or len(values) > MAX_ACTIVE_TASKS:
        raise SelfModelError("active_tasks must be a bounded array")
    result = []
    seen = set()
    for item in values:
        row = _keys(item, {"task_id", "state", "evidence"})
        task_id = _text(row["task_id"], "active_task.task_id", 16)
        if not TASK_ID_PATTERN.fullmatch(task_id) or task_id in seen:
            raise SelfModelError("active task IDs must be unique original TaskIDs")
        seen.add(task_id)
        state = _enum(row["state"], {"QUEUED", "RUNNING", "BLOCKED", "COMPLETED", "UNKNOWN"}, "active_task.state")
        evidence = _evidence(row["evidence"], "active_task.evidence", required=state != "UNKNOWN")
        result.append({"task_id": task_id, "state": state, "evidence": evidence})
    return result


def _weights(value: Any) -> dict[str, Any]:
    row = _keys(value, {"state", "version", "sha256", "evidence"})
    state = _enum(row["state"], {"LOADED", "AVAILABLE", "UNAVAILABLE", "UNKNOWN"}, "weights.state")
    version = None if row["version"] is None else _text(row["version"], "weights.version", 120)
    digest = None if row["sha256"] is None else _sha(row["sha256"], "weights.sha256")
    evidence = _evidence(row["evidence"], "weights.evidence", required=state != "UNKNOWN")
    if state in {"LOADED", "AVAILABLE"} and (not version or not digest):
        raise SelfModelError("loaded/available weights require both version and SHA-256")
    if state in {"UNAVAILABLE", "UNKNOWN"} and (version is not None or digest is not None):
        raise SelfModelError("unavailable/unknown weights may not claim a version or SHA")
    return {"state": state, "version": version, "sha256": digest, "evidence": evidence}


def _services(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list) or len(values) > MAX_SERVICES:
        raise SelfModelError("external_services must be a bounded array")
    result = []
    seen = set()
    for item in values:
        row = _keys(item, {"name", "state", "evidence"})
        name = _text(row["name"], "external_service.name", 80)
        if not IDENTIFIER.fullmatch(name) or name in seen:
            raise SelfModelError("external service names must be unique safe identifiers")
        seen.add(name)
        state = _enum(row["state"], {"AVAILABLE", "UNAVAILABLE", "UNKNOWN"}, "external_service.state")
        evidence = _evidence(row["evidence"], "external_service.evidence", required=state != "UNKNOWN")
        result.append({"name": name, "state": state, "evidence": evidence})
    return result


def _genesis(value: Any) -> dict[str, Any]:
    row = _keys(value, {"state", "revision", "evidence"})
    state = _enum(row["state"], {"AVAILABLE", "UNAVAILABLE", "UNKNOWN"}, "genesis.state")
    revision = None if row["revision"] is None else _text(row["revision"], "genesis.revision", 120)
    evidence = _evidence(row["evidence"], "genesis.evidence", required=state != "UNKNOWN")
    if state != "AVAILABLE" and revision is not None:
        raise SelfModelError("only available Genesis data may name a revision")
    if state == "AVAILABLE" and revision is None:
        raise SelfModelError("available Genesis data requires a revision")
    return {"state": state, "revision": revision, "evidence": evidence}


def _errors(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list) or len(values) > MAX_RECENT_ERRORS:
        raise SelfModelError("recent_errors must be a bounded array")
    result = []
    seen = set()
    for item in values:
        row = _keys(item, {"code", "severity", "occurred_at", "evidence"})
        code = _text(row["code"], "recent_error.code", 64)
        if not ERROR_CODE.fullmatch(code):
            raise SelfModelError("recent error code must be a safe uppercase identifier")
        occurred = _timestamp(row["occurred_at"], "recent_error.occurred_at")
        key = (code, occurred)
        if key in seen:
            raise SelfModelError("recent errors must be unique by code and timestamp")
        seen.add(key)
        severity = _enum(row["severity"], {"INFO", "WARNING", "ERROR", "CRITICAL"}, "recent_error.severity")
        result.append({
            "code": code,
            "severity": severity,
            "occurred_at": occurred,
            "evidence": _evidence(row["evidence"], "recent_error.evidence"),
        })
    result.sort(key=lambda item: item["occurred_at"], reverse=True)
    return result


def build_snapshot(data: Any) -> dict[str, Any]:
    """Normalize one pinned 3A04 snapshot without asserting evidence authenticity."""
    top = _keys(
        data,
        {"schema", "snapshot_id", "observed_at", "task", "collection_evidence",
         "capabilities", "active_tasks", "weights", "external_services", "genesis", "recent_errors"},
    )
    if top["schema"] != INPUT_SCHEMA:
        raise SelfModelError("unsupported self-model input schema")
    snapshot_id = _text(top["snapshot_id"], "snapshot_id", 80)
    if not IDENTIFIER.fullmatch(snapshot_id):
        raise SelfModelError("snapshot_id must be a safe identifier")
    task = _keys(top["task"], {"id", "spec_sha256", "registry_blob_sha"})
    if task["id"] != TASK_ID or task["spec_sha256"] != TASK_SPEC_SHA256:
        raise SelfModelError("task reference does not match the pinned original 3A04 spec")
    if task["registry_blob_sha"] != SOURCE_REGISTRY_BLOB_SHA:
        raise SelfModelError("task reference does not match the pinned all295 registry blob")
    result = {
        "schema": OUTPUT_SCHEMA,
        "snapshot_id": snapshot_id,
        "observed_at": _timestamp(top["observed_at"], "observed_at"),
        "task": {"id": TASK_ID, "spec_sha256": TASK_SPEC_SHA256, "registry_blob_sha": SOURCE_REGISTRY_BLOB_SHA},
        "collection_evidence": _evidence(top["collection_evidence"], "collection_evidence"),
        "allowed_capabilities": _capabilities(top["capabilities"]),
        "active_tasks": _active_tasks(top["active_tasks"]),
        "weights": _weights(top["weights"]),
        "external_services": _services(top["external_services"]),
        "genesis": _genesis(top["genesis"]),
        "recent_errors": _errors(top["recent_errors"]),
        "evidence_scope": {
            "state": "REFERENCE_ONLY",
            "evidence_bytes_fetched": False,
            "owner_authentication_verified": False,
            "native_task_accepted": False,
        },
    }
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    result["snapshot_sha256"] = hashlib.sha256(encoded).hexdigest()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate one evidence-bound 3A04 self-model snapshot.")
    parser.add_argument("--input", required=True, help="JSON document using nox.self_model.input.v1")
    args = parser.parse_args(argv)
    try:
        path = Path(args.input)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
            raise SelfModelError("input must be a non-symlink regular JSON file no larger than 256 KiB")
        raw = path.read_bytes()
        if len(raw) > MAX_INPUT_BYTES:
            raise SelfModelError("input must be a non-symlink regular JSON file no larger than 256 KiB")
        snapshot = build_snapshot(json.loads(raw.decode("utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, SelfModelError) as exc:
        print(json.dumps({"status": "HOLD", "error": f"{type(exc).__name__}: {str(exc)[:300]}"}), file=sys.stderr)
        return 2
    print(json.dumps(snapshot, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

