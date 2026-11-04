"""NX03: stage the already reviewed C09 uninstall owner into disposable R11 only.

The immutable P01 C07 donor and C09 review source stay unchanged. This is a
strict source admission fix, not an E07 pass or permission for recursive delete.
"""
from __future__ import annotations
import hashlib
from pathlib import Path

_ARCHIVED_SHA256 = "6853f3d4a32eb5946c3c68d22b0d61e3a402b729ebda225cd3f6b8b154b1ec55"
_ARCHIVED_BYTES = 4013
_REVIEWED_BLOB = "fef0f6c5dd979cfa7c148169c18f278e7e72685d"
_REQUIRED = (
    "P01_UNINSTALL_WRONG_ROOT",
    "P01_UNINSTALL_BAD_MANIFEST",
    "P01_UNINSTALL_DUPLICATE_OR_INVALID_JSON_MANIFEST",
    "P01_UNINSTALL_FILE_CHANGED_DURING_COMMIT",
    "P01_UNINSTALL_DUPLICATE_PATH",
    "P01_UNINSTALL_PAYLOAD_PASS",
    "P01_UNINSTALL_MODIFIED_FILE",
    "PHASE 1", "PHASE 2", "PHASE 3",
)


class ReviewedRemoveHold(RuntimeError):
    pass


def _blob(data):
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def _plain(path):
    if not isinstance(path, Path) or not path.is_file():
        raise ReviewedRemoveHold("NX03_REVIEWED_REMOVE_FILE_REQUIRED")
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            raise ReviewedRemoveHold("NX03_REVIEWED_REMOVE_REPARSE_HOLD")


# The original NSIS /S and uninstaller use Windows PowerShell 5.1. Reuse
# exactly the verified .NET SHA-256 stream recipe from the original C09
# Verify-Payload.ps1 stage. No uninstall policy or ownership check changes.
_PS51_HASH_HELPER = """function Get-P01VerifiedSha256([string]$Path) {
  $inputStream=$null
  $digest=$null
  try {
    $inputStream=[IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    $digest=[Security.Cryptography.SHA256]::Create()
    return ([BitConverter]::ToString($digest.ComputeHash($inputStream))).Replace('-','').ToLowerInvariant()
  } finally {
    if ($null -ne $digest) { $digest.Dispose() }
    if ($null -ne $inputStream) { $inputStream.Dispose() }
  }
}
"""


def _ps51_uninstall_stage(canonical: bytes) -> bytes:
    """Exactly one reviewed hash substitution; deny any unexpected source."""
    try:
        text = canonical.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ReviewedRemoveHold("NX03_REVIEWED_REMOVE_UTF8_HOLD") from exc
    header = "$ErrorActionPreference = 'Stop'"
    old_hash = "  $actual = (Get-FileHash -LiteralPath $Entry.Full -Algorithm SHA256).Hash.ToLowerInvariant()"
    if (text.count(header) != 1 or text.count(old_hash) != 1 or
            text.count("Get-FileHash") != 1 or "Get-P01VerifiedSha256" in text or
            not all(marker in text for marker in _REQUIRED)):
        raise ReviewedRemoveHold("NX03_REVIEWED_REMOVE_POLICY_MISSING")
    eol = "\r\n" if "\r\n" in text else "\n"
    updated = text.replace(header, header + eol + _PS51_HASH_HELPER.replace("\n", eol) + eol)
    updated = updated.replace(old_hash, "  $actual = Get-P01VerifiedSha256 $Entry.Full")
    if (updated.count("Get-P01VerifiedSha256") != 2 or "Get-FileHash" in updated or
            not all(marker in updated for marker in _REQUIRED)):
        raise ReviewedRemoveHold("NX03_REVIEWED_REMOVE_PS51_TRANSFORM_HOLD")
    return updated.encode("utf-8")


def stage_reviewed_remove(owner: Path, reviewed: Path) -> dict:
    """Stage exact reviewed C09 with pinned PowerShell 5.1 SHA compatibility."""
    _plain(owner)
    _plain(reviewed)
    if (owner.name != "Remove-InstalledPayload.ps1" or
            owner.parent.name != "Installer" or
            owner.parent.parent.name != "R11" or
            reviewed.name != owner.name or
            reviewed.parent.name != "Installer" or
            reviewed.parent.parent.name != "C09"):
        raise ReviewedRemoveHold("NX03_REVIEWED_REMOVE_UNEXPECTED_OWNER_PATH")
    before = owner.read_bytes()
    canonical = reviewed.read_bytes().replace(b"\r\n", b"\n")
    if _blob(canonical) != _REVIEWED_BLOB:
        raise ReviewedRemoveHold("NX03_REVIEWED_REMOVE_UNAPPROVED_BLOB")
    staged = _ps51_uninstall_stage(canonical)
    if before == staged:
        return {"changed": False, "staged_sha256": hashlib.sha256(before).hexdigest(),
                "reviewed_git_blob": _REVIEWED_BLOB,
                "compatibility_scope": "POWERSHELL51_DOTNET_SHA256_ONLY",
                "release_accepted": False}
    if len(before) != _ARCHIVED_BYTES or hashlib.sha256(before).hexdigest() != _ARCHIVED_SHA256:
        raise ReviewedRemoveHold("NX03_REVIEWED_REMOVE_UNKNOWN_R11_PREIMAGE")
    owner.write_bytes(staged)
    if owner.read_bytes() != staged or reviewed.read_bytes().replace(b"\r\n", b"\n") != canonical:
        raise ReviewedRemoveHold("NX03_REVIEWED_REMOVE_READBACK_HOLD")
    return {
        "changed": True, "original_r11_sha256": _ARCHIVED_SHA256,
        "reviewed_git_blob": _REVIEWED_BLOB,
        "staged_sha256": hashlib.sha256(staged).hexdigest(),
        "staged_bytes": len(staged),
        "compatibility_scope": "POWERSHELL51_DOTNET_SHA256_ONLY",
        "policy": "TWO_PHASE_PREVERIFY_THEN_ONLY_MANIFEST_OWNED_REMOVE",
        "original_donor_changed": False, "reviewed_source_changed": False,
        "independent_e07": "NOT_RUN", "release_accepted": False,
    }
