#!/usr/bin/env python3
"""Owner-allowlisted, read-only Drive object boundary for NOX.

This module deliberately contains no OAuth client, network transport, remote
path handling, cache, persistence, upload, delete, or eviction operation. A
future adapter must be explicitly injected and must implement only the
``read_revision`` protocol below. Content is returned in full or held; it is
never silently truncated.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote

MAX_OBJECT_SIZE_BYTES = 16 * 1024 * 1024
_DRIVE_ID_RE = re.compile(r"[A-Za-z0-9_-]{8,256}\Z")
_OPAQUE_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,256}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_MIME_TYPE_RE = re.compile(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+\Z")


class DriveReadHold(RuntimeError):
    """Fail-closed reason code with no provider error or credential details."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ReadOnlyDriveProvider(Protocol):
    """Injected boundary for an exact immutable revision read.

    Implementations must not follow caller-supplied remotes or IDs: the caller
    passes an already allowlisted file ID and revision. They must enforce
    ``max_bytes`` while retrieving and return only the normalized metadata
    fields listed in ``_PROVIDER_FIELDS`` plus the full bytes.
    """

    def read_revision(
        self, *, file_id: str, revision_id: str, max_bytes: int
    ) -> tuple[Mapping[str, Any], bytes]:
        """Read one exact revision without writes and enforce the byte ceiling."""
        ...


@dataclass(frozen=True)
class _AllowlistedFile:
    file_id: str
    parent_folder_id: str
    revision_id: str
    mime_type: str
    size_bytes: int
    max_size_bytes: int
    sha256: str
    persona_ids: tuple[str, ...]


@dataclass(frozen=True)
class _Allowlist:
    owner_persona_id: str
    folder_ids: frozenset[str]
    files: Mapping[str, _AllowlistedFile]


@dataclass(frozen=True)
class VerifiedDriveObject:
    """Full verified bytes plus immutable identity and source provenance."""

    content: bytes
    owner_persona_id: str
    persona_ids: tuple[str, ...]
    file_id: str
    parent_folder_id: str
    revision_id: str
    mime_type: str
    size_bytes: int
    sha256: str
    citation_url: str


_ALLOWLIST_KEYS = {"schema_version", "owner_persona_id", "folders", "files"}
_FOLDER_KEYS = {"folder_id"}
_FILE_KEYS = {
    "file_id",
    "parent_folder_id",
    "revision_id",
    "mime_type",
    "size_bytes",
    "max_size_bytes",
    "sha256",
    "persona_ids",
}
_PROVIDER_FIELDS = {
    "file_id",
    "parent_folder_id",
    "revision_id",
    "mime_type",
    "size_bytes",
}


def _valid_label(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value) <= 160
        and all(ord(char) >= 32 and ord(char) != 127 for char in value)
    )


def _valid_size(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _parse_allowlist(raw: object) -> _Allowlist:
    if raw is None:
        raise DriveReadHold("HOLD_DRIVE_ALLOWLIST_MISSING")
    if not isinstance(raw, Mapping) or set(raw) != _ALLOWLIST_KEYS:
        raise DriveReadHold("HOLD_DRIVE_ALLOWLIST_SCHEMA")
    if raw.get("schema_version") != 1 or isinstance(raw.get("schema_version"), bool):
        raise DriveReadHold("HOLD_DRIVE_ALLOWLIST_VERSION")

    owner = raw.get("owner_persona_id")
    if not _valid_label(owner):
        raise DriveReadHold("HOLD_DRIVE_OWNER_PERSONA_INVALID")

    folders_raw = raw.get("folders")
    if not isinstance(folders_raw, list) or not folders_raw:
        raise DriveReadHold("HOLD_DRIVE_FOLDER_ALLOWLIST_EMPTY")
    folder_ids: set[str] = set()
    for folder in folders_raw:
        if not isinstance(folder, Mapping) or set(folder) != _FOLDER_KEYS:
            raise DriveReadHold("HOLD_DRIVE_FOLDER_SCHEMA")
        folder_id = folder.get("folder_id")
        if not isinstance(folder_id, str) or not _DRIVE_ID_RE.fullmatch(folder_id):
            raise DriveReadHold("HOLD_DRIVE_FOLDER_ID_INVALID")
        if folder_id in folder_ids:
            raise DriveReadHold("HOLD_DRIVE_FOLDER_DUPLICATE")
        folder_ids.add(folder_id)

    files_raw = raw.get("files")
    if not isinstance(files_raw, list) or not files_raw:
        raise DriveReadHold("HOLD_DRIVE_FILE_ALLOWLIST_EMPTY")
    files: dict[str, _AllowlistedFile] = {}
    for file_spec in files_raw:
        if not isinstance(file_spec, Mapping) or set(file_spec) != _FILE_KEYS:
            raise DriveReadHold("HOLD_DRIVE_FILE_SCHEMA")
        file_id = file_spec.get("file_id")
        parent_id = file_spec.get("parent_folder_id")
        revision_id = file_spec.get("revision_id")
        mime_type = file_spec.get("mime_type")
        if not isinstance(file_id, str) or not _DRIVE_ID_RE.fullmatch(file_id):
            raise DriveReadHold("HOLD_DRIVE_FILE_ID_INVALID")
        if file_id in files:
            raise DriveReadHold("HOLD_DRIVE_FILE_DUPLICATE")
        if not isinstance(parent_id, str) or parent_id not in folder_ids:
            raise DriveReadHold("HOLD_DRIVE_PARENT_FOLDER_NOT_ALLOWLISTED")
        if not isinstance(revision_id, str) or not _OPAQUE_ID_RE.fullmatch(revision_id):
            raise DriveReadHold("HOLD_DRIVE_REVISION_ID_INVALID")
        if not isinstance(mime_type, str) or not _MIME_TYPE_RE.fullmatch(mime_type):
            raise DriveReadHold("HOLD_DRIVE_MIME_TYPE_INVALID")

        size = file_spec.get("size_bytes")
        maximum = file_spec.get("max_size_bytes")
        if not _valid_size(size) or not _valid_size(maximum):
            raise DriveReadHold("HOLD_DRIVE_SIZE_INVALID")
        if size > maximum or maximum > MAX_OBJECT_SIZE_BYTES:
            raise DriveReadHold("HOLD_DRIVE_SIZE_OUT_OF_BOUNDS")
        expected_sha = file_spec.get("sha256")
        if not isinstance(expected_sha, str) or not _SHA256_RE.fullmatch(expected_sha):
            raise DriveReadHold("HOLD_DRIVE_SHA256_INVALID")

        persona_ids_raw = file_spec.get("persona_ids")
        if not isinstance(persona_ids_raw, list) or not persona_ids_raw:
            raise DriveReadHold("HOLD_DRIVE_PERSONA_IDS_EMPTY")
        if any(not _valid_label(value) for value in persona_ids_raw):
            raise DriveReadHold("HOLD_DRIVE_PERSONA_ID_INVALID")
        if len(set(persona_ids_raw)) != len(persona_ids_raw):
            raise DriveReadHold("HOLD_DRIVE_PERSONA_ID_DUPLICATE")

        files[file_id] = _AllowlistedFile(
            file_id=file_id,
            parent_folder_id=parent_id,
            revision_id=revision_id,
            mime_type=mime_type,
            size_bytes=size,
            max_size_bytes=maximum,
            sha256=expected_sha,
            persona_ids=tuple(persona_ids_raw),
        )

    return _Allowlist(owner, frozenset(folder_ids), files)


class ReadOnlyDriveSidecar:
    """Read one exact owner-allowlisted revision through an injected provider."""

    def __init__(self, *, provider: ReadOnlyDriveProvider | None, allowlist: object):
        self._provider = provider
        self._raw_allowlist = allowlist

    def read(self, *, file_id: str, persona_id: str) -> VerifiedDriveObject:
        policy = _parse_allowlist(self._raw_allowlist)
        if self._provider is None:
            raise DriveReadHold("HOLD_DRIVE_PROVIDER_MISSING")
        if not isinstance(file_id, str) or not _DRIVE_ID_RE.fullmatch(file_id):
            raise DriveReadHold("HOLD_DRIVE_FILE_ID_INVALID")
        file_spec = policy.files.get(file_id)
        if file_spec is None:
            raise DriveReadHold("DENY_DRIVE_FILE_NOT_ALLOWLISTED")
        if not _valid_label(persona_id):
            raise DriveReadHold("HOLD_DRIVE_PERSONA_ID_INVALID")
        if persona_id not in file_spec.persona_ids:
            raise DriveReadHold("DENY_DRIVE_PERSONA_NOT_ALLOWLISTED")

        try:
            metadata, content = self._provider.read_revision(
                file_id=file_spec.file_id,
                revision_id=file_spec.revision_id,
                max_bytes=file_spec.max_size_bytes,
            )
        except Exception:
            # Never echo provider exception text; it may contain credentials.
            raise DriveReadHold("HOLD_DRIVE_PROVIDER_READ_FAILED") from None

        if not isinstance(metadata, Mapping) or set(metadata) != _PROVIDER_FIELDS:
            raise DriveReadHold("HOLD_DRIVE_PROVIDER_METADATA_SCHEMA")
        if metadata.get("file_id") != file_spec.file_id:
            raise DriveReadHold("HOLD_DRIVE_FILE_ID_MISMATCH")
        if metadata.get("parent_folder_id") != file_spec.parent_folder_id:
            raise DriveReadHold("HOLD_DRIVE_PARENT_FOLDER_MISMATCH")
        if metadata.get("revision_id") != file_spec.revision_id:
            raise DriveReadHold("HOLD_DRIVE_REVISION_MISMATCH")
        if metadata.get("mime_type") != file_spec.mime_type:
            raise DriveReadHold("HOLD_DRIVE_MIME_TYPE_MISMATCH")
        remote_size = metadata.get("size_bytes")
        if not _valid_size(remote_size) or remote_size > file_spec.max_size_bytes:
            raise DriveReadHold("HOLD_DRIVE_PROVIDER_SIZE_INVALID")
        if not isinstance(content, bytes):
            raise DriveReadHold("HOLD_DRIVE_PROVIDER_CONTENT_INVALID")
        if len(content) > file_spec.max_size_bytes:
            raise DriveReadHold("HOLD_DRIVE_PROVIDER_SIZE_EXCEEDED")
        if remote_size != file_spec.size_bytes or len(content) != file_spec.size_bytes:
            raise DriveReadHold("HOLD_DRIVE_SIZE_MISMATCH")
        actual_sha = hashlib.sha256(content).hexdigest()
        if actual_sha != file_spec.sha256:
            raise DriveReadHold("HOLD_DRIVE_SHA256_MISMATCH")

        return VerifiedDriveObject(
            content=content,
            owner_persona_id=policy.owner_persona_id,
            persona_ids=file_spec.persona_ids,
            file_id=file_spec.file_id,
            parent_folder_id=file_spec.parent_folder_id,
            revision_id=file_spec.revision_id,
            mime_type=file_spec.mime_type,
            size_bytes=file_spec.size_bytes,
            sha256=actual_sha,
            citation_url=(
                "https://drive.google.com/file/d/"
                + quote(file_spec.file_id, safe="")
                + "/view"
            ),
        )
