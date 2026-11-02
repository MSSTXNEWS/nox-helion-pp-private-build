"""Fail-closed provenance join for the *existing* T06 OneHost/NSIS candidate.

Source-only admission; never compiles, installs, downloads or certifies E07.
The original T06 producer, Windows WPF compiler and NSIS builder remain owners.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
import os
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


def _same_open_file(path: Path, opened) -> bool:
    """An already-open file must still be the original trusted path object."""
    try:
        current = path.lstat()
    except OSError:
        return False
    return (_trusted_regular_path(path) and
            stat.S_ISREG(opened.st_mode) and
            (current.st_dev, current.st_ino, current.st_size,
             current.st_mtime_ns, current.st_ctime_ns) ==
            (opened.st_dev, opened.st_ino, opened.st_size,
             opened.st_mtime_ns, opened.st_ctime_ns))


@contextmanager
def _trusted_binary_reader(path: Path):
    """Read from one verified descriptor, never re-open an unchecked pathname.

    O_NOFOLLOW closes the leaf swap on POSIX; on Windows the second path and
    fd identity verification also denies swapped reparse/junction targets.
    Stable inode/size/timestamps are checked again after the actual read.
    """
    if not _trusted_regular_path(path):
        raise OSError("untrusted path or reparse ancestor")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        stream = os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise
    with stream:
        before = os.fstat(stream.fileno())
        if not _same_open_file(path, before):
            raise OSError("trusted source was replaced before open")
        yield stream
        after = os.fstat(stream.fileno())
        if (after.st_dev, after.st_ino, after.st_size,
            after.st_mtime_ns, after.st_ctime_ns) != (
            before.st_dev, before.st_ino, before.st_size,
            before.st_mtime_ns, before.st_ctime_ns) or not _same_open_file(path, after):
            raise OSError("trusted source changed during read")


def _receipt(path: Path) -> dict:
    """Bounded exact bytes, no reparse ancestors or duplicate JSON properties."""
    def reject_duplicate(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("duplicate property: " + key)
            obj[key] = value
        return obj
    try:
        with _trusted_binary_reader(path) as stream:
            if not 0 < os.fstat(stream.fileno()).st_size <= 131072:
                raise OSError("receipt length invalid")
            raw = stream.read(131073)
        if not 0 < len(raw) <= 131072:
            raise OSError("receipt length changed")
    except OSError as exc:
        raise RuntimeError("T06_SOURCE_RECEIPT_MISSING_OR_UNTRUSTED") from exc
    def reject_nonfinite(token):
        raise ValueError("non-JSON constant: " + token)
    def parse_finite_float(token):
        value = float(token)
        if not math.isfinite(value):
            raise ValueError("nonfinite JSON number")
        return value
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicate,
                            parse_float=parse_finite_float,
                            parse_constant=reject_nonfinite)
    except (ValueError, UnicodeError, OverflowError) as exc:
        raise RuntimeError("T06_SOURCE_RECEIPT_INVALID_JSON") from exc
    if type(result) is not dict:
        raise RuntimeError("T06_SOURCE_RECEIPT_INVALID_OBJECT")
    return result



def _looks_like_windows_pe(stream, length: int) -> bool:
    """Reject tiny saved-copy placeholders and non-PE bytes before a Setup receipt.

    This is a structural Windows binary gate, NOT Authenticode verification,
    native Windows execution, or independently installed E07 acceptance.
    The existing NSIS bootstrap can be PE32 (x86) for a Windows x64 payload.
    """
    if length < 65536:
        return False
    stream.seek(0)
    if stream.read(2) != b"MZ":
        return False
    stream.seek(0x3c)
    pe_offset = int.from_bytes(stream.read(4), "little")
    if pe_offset < 0x40 or pe_offset > min(1048576, length - 64):
        return False
    stream.seek(pe_offset)
    if stream.read(4) != b"PE\x00\x00":
        return False
    machine = int.from_bytes(stream.read(2), "little")
    sections = int.from_bytes(stream.read(2), "little")
    if machine not in (0x14c, 0x8664) or not (1 <= sections <= 96):
        return False
    stream.seek(pe_offset + 20)
    optional_size = int.from_bytes(stream.read(2), "little")
    if (optional_size < 96 or optional_size > 1024 or
            pe_offset + 24 + optional_size + 40 * sections > length):
        return False
    stream.seek(pe_offset + 24)
    magic = int.from_bytes(stream.read(2), "little")
    if magic != (0x10b if machine == 0x14c else 0x20b):
        return False
    stream.seek(0)
    return True

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
            candidate.get("source_git_sha") != source_head or
            candidate.get("source_zip_sha256") != expected_r11_zip_sha256 or
            candidate.get("release_accepted") is not False or
            candidate.get("e07") != "NOT_ACCEPTED" or
            candidate.get("wpf_source_compilation") != "PASS" or
            candidate.get("backend_native_stdio_windows_exe_smoke") != "PASS"):
        raise RuntimeError("T06_SOURCE_CANDIDATE_SCHEMA_OR_R11_HOLD")
    sha = candidate.get("setup_sha256")
    size = candidate.get("setup_bytes")
    if (type(sha) is not str or not _SHA256.fullmatch(sha) or
            type(size) is not int or size <= 0):
        raise RuntimeError("T06_SOURCE_SETUP_IDENTITY_HOLD")
    digest = hashlib.sha256()
    try:
        with _trusted_binary_reader(setup) as stream:
            if (os.fstat(stream.fileno()).st_size != size or
                    not _looks_like_windows_pe(stream, size)):
                raise OSError("setup length or Windows PE structure invalid")
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise RuntimeError("T06_SOURCE_SETUP_IDENTITY_HOLD") from exc
    if digest.hexdigest() != sha:
        raise RuntimeError("T06_SOURCE_SETUP_BYTES_SHA_HOLD")
    return sha
