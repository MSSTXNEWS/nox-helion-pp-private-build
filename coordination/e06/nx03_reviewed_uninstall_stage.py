"""NX03: stage the already reviewed C09 uninstall owner into disposable R11 only.

The immutable P01 C07 donor and C09 review source stay unchanged. This is a
strict source admission fix, not an E07 pass or permission for recursive delete.
"""
from __future__ import annotations
import hashlib
import os
import stat
import tempfile
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
    if not isinstance(path, Path):
        raise ReviewedRemoveHold("NX03_REVIEWED_REMOVE_FILE_REQUIRED")
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except OSError as exc:
            raise ReviewedRemoveHold("NX03_REVIEWED_REMOVE_FILE_REQUIRED") from exc
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ReviewedRemoveHold("NX03_REVIEWED_REMOVE_REPARSE_HOLD")
        if getattr(part, "is_junction", lambda: False)():
            raise ReviewedRemoveHold("NX03_REVIEWED_REMOVE_REPARSE_HOLD")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        # Never truncate a hard-linked foreign file or write to special paths.
        raise ReviewedRemoveHold("NX03_REVIEWED_REMOVE_NONEXCLUSIVE_FILE_HOLD")


def _atomic_stage_owned(owner: Path, before: bytes, staged: bytes) -> None:
    """Write disposable R11 via unique exclusive temp, never truncate preimage.

    Exact-path ownership is still required across cooperating build workers;
    a filesystem rename is not a global compare-and-swap with rogue writers.
    """
    _plain(owner)
    original = owner.lstat()
    temp = None
    temp_identity = None
    try:
        fd, name = tempfile.mkstemp(prefix=".nox-nx03-", suffix=".pending",
                                    dir=str(owner.parent))
        temp = Path(name)
        try:
            temp_identity = (os.fstat(fd).st_dev, os.fstat(fd).st_ino)
            with os.fdopen(fd, "wb") as stream:
                stream.write(staged)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            # fdopen owns fd only after successful construction.
            try:
                os.close(fd)
            except OSError:
                pass
            raise
        os.chmod(temp, stat.S_IMODE(original.st_mode))
        if temp.read_bytes() != staged:
            raise ReviewedRemoveHold("NX03_ATOMIC_PENDING_READBACK_HOLD")
        _plain(owner)
        current = owner.lstat()
        if ((current.st_dev, current.st_ino, current.st_mtime_ns,
             current.st_size, current.st_nlink) !=
            (original.st_dev, original.st_ino, original.st_mtime_ns,
             original.st_size, original.st_nlink) or
                owner.read_bytes() != before):
            raise ReviewedRemoveHold("NX03_FOREIGN_OWNER_CHANGED_HOLD")
        # A concurrent writer can swap the pending name even with IDENTICAL
        # bytes. Verify its original inode/one-link ownership immediately
        # before publish; never trust content hashing alone for a staging path.
        _plain(temp)
        pending = temp.lstat()
        if ((pending.st_dev, pending.st_ino) != temp_identity or
                pending.st_nlink != 1 or temp.read_bytes() != staged):
            raise ReviewedRemoveHold("NX03_FOREIGN_PENDING_CHANGED_HOLD")
        # Only an owner-verified, unique pending file may replace disposable R11.
        os.replace(temp, owner)
        temp = None
    except OSError as exc:
        raise ReviewedRemoveHold("NX03_ATOMIC_STAGE_IO_HOLD") from exc
    finally:
        if temp is not None and temp_identity is not None:
            try:
                info = temp.lstat()
                # A foreign writer may have changed the original inode's
                # contents. Never delete that now-foreign pending evidence.
                if (stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                        (info.st_dev, info.st_ino) == temp_identity and
                        temp.read_bytes() == staged):
                    temp.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass  # A failed cleanup is not permission to touch foreign files.


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
    _atomic_stage_owned(owner, before, staged)
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
