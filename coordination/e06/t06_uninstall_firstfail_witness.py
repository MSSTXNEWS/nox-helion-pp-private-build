"""Read-only physical first-failure witness for ORIGINAL T06 NSIS uninstall.

This is not a removal routine, an alternate verifier or an E07 acceptance gate.
Its only purpose is to distinguish a never-started/aborted uninstaller from
partial removal after an already-failed original fail-closed verifier.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import stat

_R11_REMOVER_SHA256 = "6853f3d4a32eb5946c3c68d22b0d61e3a402b729ebda225cd3f6b8b154b1ec55"
_R11_REMOVER_BYTES = 4013
_METADATA = ("payload.sha256.json", "nox-p01-owned.txt", "Uninstall.exe")


def _state(path: Path) -> str:
    """lstat only: never open/follow a symlink or Windows reparse point."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return "ABSENT"
    except OSError:
        return "UNREADABLE"
    if (stat.S_ISLNK(info.st_mode) or
            getattr(info, "st_file_attributes", 0) &
            getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        return "REPARSE_HOLD"
    if not stat.S_ISREG(info.st_mode):
        return "NOT_REGULAR_HOLD"
    return "PRESENT"


def read_only_uninstall_failure_snapshot(
        install: Path, owned: tuple[Path, ...], remover: Path | None = None) -> dict:
    """Bounded structural evidence ONLY after the original uninstall has failed.

    Names come solely from the already-validated original manifest. Never inspect
    unrelated user files, remove program files, run NSIS/PowerShell or return
    absolute paths. The caller MUST re-raise the original failure unchanged.
    """
    if (not isinstance(install, Path) or type(owned) is not tuple or
            not 1 <= len(owned) <= 50000):
        raise ValueError("T06_WITNESS_INVALID_ORIGINAL_INVENTORY")
    states = {k: 0 for k in ("ABSENT", "PRESENT", "UNREADABLE", "REPARSE_HOLD", "NOT_REGULAR_HOLD")}
    residues: list[dict] = []
    for path in owned:
        if not isinstance(path, Path):
            raise ValueError("T06_WITNESS_INVALID_ORIGINAL_INVENTORY")
        try:
            relative = path.relative_to(install).as_posix()
        except ValueError as exc:
            raise ValueError("T06_WITNESS_PATH_OUTSIDE_ORIGINAL_INSTALL") from exc
        if (not relative or len(relative) > 1024 or
                any(piece in ("", ".", "..") for piece in relative.split("/")) or
                "\\" in relative or ":" in relative):
            raise ValueError("T06_WITNESS_UNSAFE_MANIFEST_RELATIVE")
        state = _state(path)
        states[state] += 1
        if state != "ABSENT" and len(residues) < 5:
            residues.append({"manifest_relative": relative[:160], "state": state})
    metadata = {label: _state(install / label) for label in _METADATA}
    remover_receipt = {"expected_sha256": _R11_REMOVER_SHA256,
                       "expected_bytes": _R11_REMOVER_BYTES,
                       "observed_sha256": None,
                       "observed_bytes": None,
                       "immutable_r11_pin_match": False}
    if (remover is not None and isinstance(remover, Path) and
            all(_state(part) == "PRESENT" if part == remover else
                not (part.is_symlink() or getattr(part, "is_junction", lambda: False)())
                for part in (remover, *remover.parents)) and
            _state(remover) == "PRESENT"):
        # SHA only bounded local ORIGINAL disposable NSIS script; no execution.
        try:
            size = remover.stat().st_size
            remover_receipt["observed_bytes"] = size
            if 1 <= size <= 65536:
                data = remover.read_bytes()
                if len(data) == size:
                    remover_receipt["observed_sha256"] = hashlib.sha256(data).hexdigest()
                    remover_receipt["immutable_r11_pin_match"] = (
                        size == _R11_REMOVER_BYTES and
                        remover_receipt["observed_sha256"] == _R11_REMOVER_SHA256)
        except OSError:
            pass
    return {"schema": "NOX-T06-UNINSTALL-READONLY-FAILURE-WITNESS-v1",
            "disposition": "DIAGNOSTIC_ONLY_RELEASE_HOLD",
            "manifest_owned_total": len(owned),
            "manifest_owned_states": states,
            "first_owned_residues": residues,
            "original_nsis_metadata_states": metadata,
            "original_r11_remove_script": remover_receipt,
            "witness_executed_uninstaller": False,
            "witness_deleted_files": False,
            "independent_e07": "NOT_RUN"}
