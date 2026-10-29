"""Exact metadata adapter for original ModelArtifactReviewRegistry exports.

E06 must inject the authenticated native export reader, never page JSON/flags.
This adapter does not approve a model, grant admission, enqueue or download.
The existing 25-tag admission allowlist remains unchanged. Reviewer receipt IDs
are references, not receipt content hashes; E06 still verifies their content,
rights, SourceLock and current user scope before calling the existing gate.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from types import MappingProxyType
from typing import Callable, Mapping, Any

from p03_modelcenter_gate import _https_url, _immutable_revision, _positive, _sha

_SCHEMA = "NOX_P03_NATIVE_REVIEWED_ARTIFACT_V1"
_FIELDS = frozenset(("schema", "familyId", "exactTag", "version", "licenseId",
    "licenseEvidenceUrl", "artifactBytes", "requiredDiskBytes", "recommendedRamBytes",
    "requiredVramBytes", "artifactSha256", "manifestSha256", "immutableRevision",
    "compatibilityEvidenceUrl", "reviewerReceiptId"))
_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*:[A-Za-z0-9][A-Za-z0-9._-]*")


class ReviewedArtifactHold(RuntimeError):
    """Native reviewed metadata unavailable or not an exact safe snapshot."""


@dataclass(frozen=True)
class ReviewedArtifactSnapshot:
    fields: Mapping[str, Any]
    export_sha256: str  # exact export bytes only; NOT an authenticity proof

    def matches_artifact_identity(self, evidence: Mapping[str, Any]) -> bool:
        """Compare identity only; no permission/rights or installed-state claim."""
        if not isinstance(evidence, Mapping) or evidence.get("kind") != "ollama":
            return False
        pairs = (("modelTag", "exactTag"), ("licenseId", "licenseId"),
                 ("licenseEvidenceUrl", "licenseEvidenceUrl"),
                 ("artifactBytes", "artifactBytes"), ("requiredDiskBytes", "requiredDiskBytes"),
                 ("artifactSha256", "artifactSha256"), ("manifestSha256", "manifestSha256"),
                 ("immutableRevision", "immutableRevision"))
        if any(type(evidence.get(a)) is not type(self.fields[b]) or evidence.get(a) != self.fields[b]
               for a, b in pairs):
            return False
        gpu = _positive(self.fields["requiredVramBytes"])
        return evidence.get("requiresGPU") is gpu and (not gpu or
            type(evidence.get("requiredVramBytes")) is int and
            evidence.get("requiredVramBytes") == self.fields["requiredVramBytes"])


def read_native_reviewed_artifact(model_tag: str,
        trusted_registry_export: Callable[[str], str | bytes] | None) -> ReviewedArtifactSnapshot:
    """Read one original owner export through trusted native composition only.

    No fallback to caller evidence. Exact requested tag must equal the returned
    native record. Missing/ambiguous/malformed results HOLD. The returned frozen
    snapshot is not accepted by admit_for_existing_downloader as authorization.
    """
    if (type(model_tag) is not str or len(model_tag) > 160 or not _TAG.fullmatch(model_tag)
            or ".." in model_tag or model_tag.lower().endswith(":latest")):
        raise ReviewedArtifactHold("Exact non-latest model tag required")
    if not callable(trusted_registry_export):
        raise ReviewedArtifactHold("Trusted native registry export provider missing")
    try:
        raw = trusted_registry_export(model_tag)
        if type(raw) not in (str, bytes) or len(raw) > 16384:
            raise ValueError("bounded native JSON export required")
        encoded = raw.encode("utf-8") if type(raw) is str else raw
        if len(encoded) > 16384:
            raise ValueError("export byte cap")
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate export field")
                result[key] = value
            return result
        def reject_constant(value):
            raise ValueError("non-finite export number")
        doc = json.loads(encoded.decode("utf-8"), object_pairs_hook=unique, parse_constant=reject_constant)
        if type(doc) is not dict or frozenset(doc) != _FIELDS or doc["schema"] != _SCHEMA:
            raise ValueError("export schema mismatch")
        if doc["exactTag"] != model_tag or doc["familyId"] != model_tag.split(":", 1)[0]:
            raise ValueError("native artifact identity mismatch")
        for key in ("version", "licenseId", "reviewerReceiptId"):
            value = doc[key]
            if (type(value) is not str or not 0 < len(value) <= 160 or value != value.strip()
                    or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
                raise ValueError("unbounded native review field")
        if not _https_url(doc["licenseEvidenceUrl"]) or not _https_url(doc["compatibilityEvidenceUrl"]):
            raise ValueError("native evidence URI invalid")
        if (not _positive(doc["artifactBytes"]) or not _positive(doc["requiredDiskBytes"])
                or doc["requiredDiskBytes"] < doc["artifactBytes"]):
            raise ValueError("native artifact byte requirements invalid")
        for key in ("recommendedRamBytes", "requiredVramBytes"):
            if doc[key] is not None and not _positive(doc[key]):
                raise ValueError("native memory requirement invalid")
        if not (_positive(doc["recommendedRamBytes"]) or _positive(doc["requiredVramBytes"])):
            raise ValueError("native memory requirements absent")
        if not _sha(doc["artifactSha256"]) or not _sha(doc["manifestSha256"]):
            raise ValueError("native artifact digest invalid")
        if not _immutable_revision(doc["immutableRevision"], "ollama"):
            raise ValueError("native revision invalid")
        return ReviewedArtifactSnapshot(MappingProxyType(doc), hashlib.sha256(encoded).hexdigest())
    except Exception as exc:
        raise ReviewedArtifactHold("Native reviewed artifact export unavailable or invalid") from None
