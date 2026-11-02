"""Fail-closed provenance join for the *existing* T06 OneHost/NSIS candidate.

Source-only admission; never compiles, installs, downloads or certifies E07.
The original T06 producer, Windows WPF compiler and NSIS builder remain owners.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import stat

_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _trusted_regular_path(path: Path) -> bool:
    """Deny Windows junctions/reparse parents, not only a symlinked leaf.

    An authenticated candidate must never resolve a receipt or Setup outside
    the native owner's intended path through a reparse ancestor. The caller
    still pins bytes and source HEAD; this is not an installed-EXE proof.
    """
    try:
        nodes = [path.lstat(), *(parent.lstat() for parent in path.parents)]
    except OSError:
        return False
    return (stat.S_ISREG(nodes[0].st_mode) and
            all(not stat.S_ISLNK(node.st_mode) and not
                (getattr(node, "st_file_attributes", 0) &
                 getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
                for node in nodes))


def _receipt(path: Path) -> dict:
    """Bounded exact bytes, no reparse ancestors or duplicate JSON properties."""
    if not _trusted_regular_path(path) or not 0 < path.stat().st_size <= 131072:
        raise RuntimeError("T06_SOURCE_RECEIPT_MISSING_OR_UNTRUSTED")
    def reject_duplicate(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("duplicate property: " + key)
            obj[key] = value
        return obj
    try:
        result = json.loads(path.read_bytes().decode("utf-8"), object_pairs_hook=reject_duplicate)
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError("T06_SOURCE_RECEIPT_INVALID_JSON") from exc
    if type(result) is not dict:
        raise RuntimeError("T06_SOURCE_RECEIPT_INVALID_OBJECT")
    return result


def attest_candidate(source_head: str, compile_receipt: Path, candidate_receipt: Path,
                     setup: Path, expected_r11_zip_sha256: str) -> str:
    """Tie actual T06 compile evidence and NSIS candidate to source + setup bytes.

    This is a source provenance fence, not an installed/native Windows E07 test.
    The caller must resolve current git HEAD *before and after* the native run.
    """
    if (type(source_head) is not str or not _SHA1.fullmatch(source_head) or
            type(expected_r11_zip_sha256) is not str or
            not _SHA256.fullmatch(expected_r11_zip_sha256)):
        raise RuntimeError("T06_SOURCE_SHA_INPUT_INVALID")
    compile_data = _receipt(compile_receipt)
    candidate = _receipt(candidate_receipt)
    if (compile_data.get("source_git_sha") != source_head or
            compile_data.get("original_zip_sha256") != expected_r11_zip_sha256 or
            type(compile_data.get("original_files_staged")) is not int or
            compile_data["original_files_staged"] != 729 or
            type(compile_data.get("dotnet_build_exit")) is not int or
            compile_data["dotnet_build_exit"] != 0):
        raise RuntimeError("T06_SOURCE_COMPILE_EXACT_HEAD_OR_729_HOLD")
    if (candidate.get("schema") != "NOX-E06-ONEHOST-CANDIDATE-v1" or
            candidate.get("source_zip_sha256") != expected_r11_zip_sha256 or
            candidate.get("release_accepted") is not False or
            candidate.get("e07") != "NOT_ACCEPTED" or
            candidate.get("wpf_source_compilation") != "PASS" or
            candidate.get("backend_native_stdio_windows_exe_smoke") != "PASS"):
        raise RuntimeError("T06_SOURCE_CANDIDATE_SCHEMA_OR_R11_HOLD")
    sha = candidate.get("setup_sha256")
    size = candidate.get("setup_bytes")
    if (type(sha) is not str or not _SHA256.fullmatch(sha) or
            type(size) is not int or size <= 0 or
            not _trusted_regular_path(setup) or setup.stat().st_size != size):
        raise RuntimeError("T06_SOURCE_SETUP_IDENTITY_HOLD")
    digest = hashlib.sha256()
    with setup.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != sha or setup.stat().st_size != size:
        raise RuntimeError("T06_SOURCE_SETUP_BYTES_SHA_HOLD")
    return sha
