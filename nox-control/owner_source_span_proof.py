#!/usr/bin/env python3
"""Pure, fail-closed byte-span provenance proof for NOX knowledge citations.

Use only with an independently owner-pinned manifest and exact full source bytes.
This proves identity and text inclusion, not truth or semantic entailment.
Never exports source text, secrets or conversational history to receipts.
No I/O, network, database, model, worker or state mutations.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import quote

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9_.-]{1,256}\Z")
_DRIVE_ID = re.compile(r"[A-Za-z0-9_-]{8,256}\Z")
_MAX_SOURCE_BYTES = 16 * 1024 * 1024
_PIN_KEYS = frozenset({"kind", "revision", "sha256", "size_bytes", "persona_ids"})


class SourceProofHold(RuntimeError):
    """Stable, non-sensitive failure code."""


@dataclass(frozen=True)
class VerifiedSpan:
    source_kind: str
    source_id: str
    source_revision: str
    source_sha256: str
    source_bytes: int
    persona_id: str
    start_byte: int
    end_byte: int
    excerpt_sha256: str
    citation_url: str | None
    proof_scope: str = "EXACT_BYTE_SPAN_ONLY_NOT_SEMANTIC_SUPPORT"


def verify_span(*, trusted_pins: Mapping, source_id: str, source_bytes: bytes,
                source_revision: str, persona_id: str, start_byte: int,
                end_byte: int, excerpt: str, query_evidence: bool,
                historical_unverified: bool) -> VerifiedSpan:
    """Verify exact cited UTF-8 span against owner-pinned full-source bytes.

    trusted_pins is supplied by an authorized manifest reader, not from
    retrieved web text, model output, or S03 history. HOLD on malformed data,
    excess size, digest/identity mismatch, or unsupported/revoked claims.
    """
    if not isinstance(trusted_pins, Mapping) or not isinstance(source_id, str) or not _ID.fullmatch(source_id):
        raise SourceProofHold("HOLD_SOURCE_PIN_REGISTRY")
    pin = trusted_pins.get(source_id)
    if not isinstance(pin, Mapping) or set(pin) != _PIN_KEYS:
        raise SourceProofHold("HOLD_SOURCE_PIN_MISSING_OR_SCHEMA")
    kind = pin.get("kind")
    if kind not in ("drive", "s03") or (kind == "drive" and not _DRIVE_ID.fullmatch(source_id)):
        raise SourceProofHold("HOLD_SOURCE_KIND_OR_ID")
    revision = pin.get("revision")
    expected_sha = pin.get("sha256")
    size = pin.get("size_bytes")
    personas = pin.get("persona_ids")
    if (not isinstance(revision, str) or not _ID.fullmatch(revision)
            or not isinstance(expected_sha, str) or not _SHA.fullmatch(expected_sha)
            or type(size) is not int or not 0 < size <= _MAX_SOURCE_BYTES
            or not isinstance(personas, (tuple, list)) or not personas
            or any(not isinstance(p, str) or not _ID.fullmatch(p) for p in personas)
            or len(set(personas)) != len(personas)):
        raise SourceProofHold("HOLD_SOURCE_PIN_INVALID")
    if source_revision != revision:
        raise SourceProofHold("HOLD_SOURCE_REVISION_CHANGED")
    if not isinstance(persona_id, str) or persona_id not in personas:
        raise SourceProofHold("DENY_SOURCE_PERSONA_SCOPE")
    if query_evidence is not True or historical_unverified is not False:
        raise SourceProofHold("HOLD_SOURCE_QUERY_EVIDENCE_UNVERIFIED")
    if not isinstance(source_bytes, bytes) or len(source_bytes) != size:
        raise SourceProofHold("HOLD_SOURCE_FULL_BYTES_MISSING")
    if hashlib.sha256(source_bytes).hexdigest() != expected_sha:
        raise SourceProofHold("HOLD_SOURCE_CONTENT_SHA_MISMATCH")
    if (type(start_byte) is not int or type(end_byte) is not int
            or not 0 <= start_byte < end_byte <= size or not isinstance(excerpt, str)
            or not excerpt or source_bytes[start_byte:end_byte] != excerpt.encode("utf-8")):
        raise SourceProofHold("HOLD_SOURCE_EXCERPT_NOT_EXACT")
    citation = ("https://drive.google.com/file/d/" + quote(source_id, safe="") + "/view"
                if kind == "drive" else None)
    return VerifiedSpan(kind, source_id, revision, expected_sha, size, persona_id,
                        start_byte, end_byte, hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                        citation)
