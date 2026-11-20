#!/usr/bin/env python3
"""Metadata-only FORGE manifest validator for original TaskID 4B01.

This source component describes candidate examples from caller-reported
verified knowledge, successful actions, or permitted teachers. It validates
provenance, license and permission references, content hashes, and per-source
example-count share. A typed Drive file ID can produce a canonical locator only;
there are no requests, OAuth, signed-query retention, or access claims. It never
downloads or reads example bytes, fetches URLs, writes S03, starts collection,
or authorizes training. Output remains structural/reference-only until an
independent owner workflow verifies it.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, ROUND_HALF_UP
import datetime as dt
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlsplit, urlunsplit

INPUT_SCHEMA = "nox.forge.input.v1"
OUTPUT_SCHEMA = "nox.forge.manifest.v1"
TASK_ID = "4B01"
TASK_SPEC_SHA256 = "983347cc1a070f6cbe51e067df0de30cc5854593615f80183cf6aaa59705ff8f"
SOURCE_REGISTRY_BLOB_SHA = "f5c45dc8919b1b800e89a421676a3627e75fb3bb"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}\Z")
LICENSE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:+-]{0,119}\Z")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SENSITIVE_QUERY_KEY = re.compile(
    r"(?i)^(?:access[_-]?token|authorization|auth|api[_-]?key|apikey|key|client[_-]?secret|secret|password|passwd|"
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
OPAQUE_PATH_TOKEN = re.compile(r"[A-Za-z0-9_-]{24,}\Z")
DRIVE_FILE_ID = re.compile(r"[A-Za-z0-9_-]{10,128}\Z")
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_SOURCES = 256
MAX_EXAMPLES = 10000
ORIGIN_KINDS = {"VERIFIED_KNOWLEDGE", "SUCCESSFUL_ACTION", "ALLOWED_TEACHER"}


class ForgeError(ValueError):
    """Invalid, unbounded, or unpinned FORGE metadata."""


def _keys(value: Any, required: set[str], optional: Any = ()) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ForgeError("section must be an object")
    keys = set(value)
    if not required <= keys or keys - required - set(optional):
        raise ForgeError("section has missing or unsupported fields")
    return value


def _text(value: Any, field: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ForgeError(f"{field} must be text")
    result = " ".join(value.split())
    if not 1 <= len(result) <= limit or CONTROL.search(result):
        raise ForgeError(f"{field} must contain 1-{limit} safe characters")
    return result


def _timestamp(value: Any, field: str) -> str:
    raw = _text(value, field, 40)
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ForgeError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ForgeError(f"{field} must include a timezone")
    return parsed.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ForgeError(f"{field} must be a lowercase SHA-256")
    return value


def _reference(value: Any, field: str) -> str:
    raw = _text(value, field, 2048)
    # urlsplit(), hostname and port can all raise ValueError for an invalid
    # IPv6 authority or malformed port. Convert them to a typed HOLD error
    # rather than letting untrusted provenance crash the CLI.
    try:
        parts = urlsplit(raw)
        hostname = parts.hostname
        username = parts.username
        password = parts.password
        port = parts.port
    except ValueError as exc:
        raise ForgeError(f"{field} has an invalid URL authority") from exc
    if parts.scheme.lower() != "https" or not hostname or username is not None or password is not None:
        raise ForgeError(f"{field} must be HTTPS without credentials")
    if port not in (None, 443):
        raise ForgeError(f"{field} may not use a non-default HTTPS port")
    host = hostname.lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ForgeError(f"{field} may not point to a local host")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ForgeError(f"{field} may not point to a non-public IP")
    for key, _ in parse_qsl(parts.query, keep_blank_values=True):
        decoded = key
        for _ in range(8):
            next_value = unquote(decoded)
            if next_value == decoded:
                break
            decoded = next_value
        else:
            if re.search(r"%[0-9a-fA-F]{2}", decoded):
                raise ForgeError(f"{field} has excessively nested query encoding")
        normalized = decoded.strip().casefold()
        while normalized.endswith("[]"):
            normalized = normalized[:-2]
        if SENSITIVE_QUERY_KEY.fullmatch(normalized):
            raise ForgeError(f"{field} may not contain sensitive query keys")
    path = parts.path
    prior = None
    for _ in range(8):
        if path == prior:
            break
        prior = path
        path = unquote(path)
    else:
        raise ForgeError(f"{field} has excessively nested path encoding")
    if re.search(r"%[0-9a-fA-F]{2}", path):
        raise ForgeError(f"{field} has excessively nested path encoding")
    segments = [segment for segment in path.split("/") if segment]
    for index, segment in enumerate(segments):
        if segment.casefold() in SENSITIVE_PATH_MARKERS and index + 1 < len(segments) and len(segments[index + 1]) >= 12:
            raise ForgeError(f"{field} may not contain secret-like path tokens")
        if PREFIXED_PATH_SECRET.search(segment):
            raise ForgeError(f"{field} may not contain secret-like path tokens")
        if OPAQUE_PATH_TOKEN.fullmatch(segment):
            public_git_revision = (
                host in {"github.com", "www.github.com"}
                and len(segment) in {40, 64}
                and re.fullmatch(r"[0-9a-fA-F]+", segment)
                and index > 0
                and segments[index - 1].casefold() in {"blob", "tree", "commit", "commits"}
            )
            if not public_git_revision:
                raise ForgeError(f"{field} may not contain secret-like path tokens")
    normalized_path = quote(path or "/", safe="/:@-._~!$&'()*+,;=")
    return urlunsplit(("https", host, normalized_path, "", ""))


def _evidence(value: Any, field: str) -> dict[str, str]:
    row = _keys(value, {"url", "sha256", "observed_at"})
    return {
        "reference": _reference(row["url"], field + ".url"),
        "claimed_sha256": _sha(row["sha256"], field + ".sha256"),
        "observed_at": _timestamp(row["observed_at"], field + ".observed_at"),
    }


def _drive_source_reference(file_id: Any, source_url: Any = None) -> tuple[str, str]:
    """Return a stable Drive file locator; never preserve a URL query or fetch it."""
    drive_id = _text(file_id, "source.drive_file_id", 128)
    if not DRIVE_FILE_ID.fullmatch(drive_id) or PREFIXED_PATH_SECRET.search(drive_id):
        raise ForgeError("source.drive_file_id must be a safe Google Drive file ID")
    path = f"/file/d/{drive_id}/view"
    canonical = "https://drive.google.com" + path
    if source_url is not None:
        raw = _text(source_url, "source.source_url", 2048)
        # Exact equality is a closed URL allowlist: no redirects, query strings,
        # fragments, alternate hosts, or embedded credentials survive.
        if raw != canonical:
            raise ForgeError("source.source_url must be the canonical Drive file URL without query or fragment")
    return canonical, drive_id


def _source(value: Any) -> dict[str, Any]:
    row = _keys(
        value,
        {"source_id", "origin_kind", "source_sha256", "license_id", "license_url",
         "license_sha256", "permission_status", "permission_receipt"},
        {"source_url", "drive_file_id"},
    )
    source_id = _text(row["source_id"], "source.source_id", 120)
    if not IDENTIFIER.fullmatch(source_id):
        raise ForgeError("source_id must be a safe stable identifier")
    if not isinstance(row["origin_kind"], str) or row["origin_kind"] not in ORIGIN_KINDS:
        raise ForgeError("source.origin_kind is unsupported")
    if row["permission_status"] != "ALLOWED":
        raise ForgeError("source permission must be explicitly caller-reported ALLOWED")
    license_id = _text(row["license_id"], "source.license_id", 120)
    if not LICENSE_ID.fullmatch(license_id):
        raise ForgeError("license_id must be a stable license identifier")

    drive_file_id = None
    if "drive_file_id" in row:
        source_reference, drive_file_id = _drive_source_reference(
            row["drive_file_id"], row.get("source_url"))
    else:
        if "source_url" not in row:
            raise ForgeError("source requires source_url or typed drive_file_id")
        source_reference = _reference(row["source_url"], "source.source_url")

    result = {
        "source_id": source_id,
        "origin_kind": row["origin_kind"],
        "source_reference": source_reference,
        "claimed_source_sha256": _sha(row["source_sha256"], "source.source_sha256"),
        "license_id": license_id,
        "license_reference": _reference(row["license_url"], "source.license_url"),
        "claimed_license_sha256": _sha(row["license_sha256"], "source.license_sha256"),
        "permission_status_reported": "ALLOWED",
        "permission_receipt": _evidence(row["permission_receipt"], "source.permission_receipt"),
    }
    if drive_file_id is not None:
        result["drive_file_id"] = drive_file_id
    return result


def _example(value: Any, source_ids: set[str]) -> dict[str, str]:
    row = _keys(value, {"example_id", "source_id", "source_record_id", "content_sha256", "captured_at"})
    example_id = _text(row["example_id"], "example.example_id", 120)
    source_id = _text(row["source_id"], "example.source_id", 120)
    source_record_id = _text(row["source_record_id"], "example.source_record_id", 160)
    if not IDENTIFIER.fullmatch(example_id) or not IDENTIFIER.fullmatch(source_record_id):
        raise ForgeError("example and source record IDs must be safe stable identifiers")
    if source_id not in source_ids:
        raise ForgeError("example refers to a source absent from the pinned source catalog")
    return {
        "example_id": example_id,
        "source_id": source_id,
        "source_record_id": source_record_id,
        "claimed_content_sha256": _sha(row["content_sha256"], "example.content_sha256"),
        "captured_at": _timestamp(row["captured_at"], "example.captured_at"),
    }


def build_manifest(data: Any) -> dict[str, Any]:
    """Validate source metadata and report count-based shares; never reads payloads."""
    top = _keys(data, {"schema", "manifest_id", "created_at", "task", "sources", "examples"})
    if top["schema"] != INPUT_SCHEMA:
        raise ForgeError("unsupported FORGE input schema")
    manifest_id = _text(top["manifest_id"], "manifest_id", 120)
    if not IDENTIFIER.fullmatch(manifest_id):
        raise ForgeError("manifest_id must be a safe identifier")
    task = _keys(top["task"], {"id", "spec_sha256", "registry_blob_sha"})
    if task["id"] != TASK_ID or task["spec_sha256"] != TASK_SPEC_SHA256:
        raise ForgeError("task reference does not match the pinned original 4B01 spec")
    if task["registry_blob_sha"] != SOURCE_REGISTRY_BLOB_SHA:
        raise ForgeError("task reference does not match the pinned all295 registry blob")

    sources_raw = top["sources"]
    examples_raw = top["examples"]
    if not isinstance(sources_raw, list) or not 1 <= len(sources_raw) <= MAX_SOURCES:
        raise ForgeError(f"sources must contain 1-{MAX_SOURCES} rows")
    if not isinstance(examples_raw, list) or len(examples_raw) > MAX_EXAMPLES:
        raise ForgeError(f"examples must contain 0-{MAX_EXAMPLES} rows")
    sources = [_source(value) for value in sources_raw]
    source_ids = [source["source_id"] for source in sources]
    if len(set(source_ids)) != len(source_ids):
        raise ForgeError("source_id values must be unique")
    source_id_set = set(source_ids)
    examples = [_example(value, source_id_set) for value in examples_raw]
    if len({item["example_id"] for item in examples}) != len(examples):
        raise ForgeError("example_id values must be unique")
    if len({(item["source_id"], item["source_record_id"]) for item in examples}) != len(examples):
        raise ForgeError("source_record_id values must be unique within each source")

    total = len(examples)
    counts = {source_id: 0 for source_id in source_id_set}
    for item in examples:
        counts[item["source_id"]] += 1
    source_shares = []
    for source_id in sorted(source_id_set):
        count = counts[source_id]
        percent = (Decimal(count) * Decimal(100) / Decimal(total)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP) if total else Decimal(0)
        source_shares.append({
            "source_id": source_id,
            "example_count": count,
            "share_numerator": count,
            "share_denominator": total,
            "share_percent": str(percent),
        })

    result = {
        "schema": OUTPUT_SCHEMA,
        "manifest_id": manifest_id,
        "created_at": _timestamp(top["created_at"], "created_at"),
        "task": {"id": TASK_ID, "spec_sha256": TASK_SPEC_SHA256, "registry_blob_sha": SOURCE_REGISTRY_BLOB_SHA},
        "sources": sorted(sources, key=lambda item: item["source_id"]),
        "candidate_examples": sorted(examples, key=lambda item: item["example_id"]),
        "source_shares": source_shares,
        "integrity_scope": {
            "source_and_license_hashes_verified": False,
            "content_bytes_read": False,
            "content_hashes_verified": False,
            "permission_receipts_verified": False,
            "drive_file_access_verified": False,
            "drive_reference_is_locator_only": True,
            "source_counts_are_manifest_rows": True,
            "duplicates_removed": False,
            "training_authorized": False,
            "native_task_accepted": False,
        },
    }
    canonical = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    result["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate one metadata-only FORGE 4B01 manifest.")
    parser.add_argument("--input", required=True, help="JSON input using nox.forge.input.v1")
    args = parser.parse_args(argv)
    try:
        path = Path(args.input)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
            raise ForgeError("input must be a non-symlink regular file no larger than 8 MiB")
        raw = path.read_bytes()
        if len(raw) > MAX_INPUT_BYTES:
            raise ForgeError("input must be a non-symlink regular file no larger than 8 MiB")
        result = build_manifest(json.loads(raw.decode("utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ForgeError) as exc:
        print(json.dumps({"status": "HOLD", "error": f"{type(exc).__name__}: {str(exc)[:300]}"}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

