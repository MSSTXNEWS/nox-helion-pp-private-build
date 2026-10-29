"""E06 immutable SourceLock gate for the ORIGINAL three-part NOX source ZIP.

Read-only input; never extracts files, overwrites owner source or opens a port.
A Git inventory is only a claim: this tool proves raw bytes + each safe ZIP member.
Windows build is forbidden until the resulting receipt is explicitly owner-reviewed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import importlib.util
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import unicodedata
import zipfile

PARTS = (
    ("source_00.part", 20971520, "e484e10d7b4ec9badeaae4c9d3a7e3aee5faa16b"),
    ("source_01.part", 20971520, "7853cb43ff4ba0ed3023e8d794d8222eedea56a6"),
    ("source_02.part", 18421306, "cbd9deb30860737f15e2adbaef2eaaf5d607a0de"),
)
ARCHIVE_SHA256 = "ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a"
HISTORICAL_BASE_COMMIT = "0b3a7d435be735148d64171deb9027093a89646e"
HISTORICAL_BASE_TREE = "f108d604c444f718b32aaecfd07b90b8f91b9a6f"
EXPECTED_FILES = 729
CHUNK = 1 << 20
MAX_FILES = 4096
MAX_UNCOMPRESSED = 4 * 1024**3
DEVICE = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$", re.I)


class SourceHold(RuntimeError):
    """An evidence failure: do not claim SourceLock, build or Windows acceptance."""

# Same immutable canonical ZIP namespace gate as the existing R11 owner stage.
# Do not introduce an independent validator or duplicate security logic.
CANONICAL_VALIDATOR = Path(__file__).resolve().parents[1] / "source-lock/verify_original_archive.py"

def canonical_archive_module():
    if not CANONICAL_VALIDATOR.is_file() or CANONICAL_VALIDATOR.is_symlink():
        raise SourceHold("CANONICAL_ZIP_VALIDATOR_UNAVAILABLE")
    spec = importlib.util.spec_from_file_location("nox_original_zip_namespace", CANONICAL_VALIDATOR)
    if spec is None or spec.loader is None:
        raise SourceHold("CANONICAL_ZIP_VALIDATOR_INVALID")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not callable(getattr(mod, "validate_members", None)):
        raise SourceHold("CANONICAL_ZIP_NAMESPACE_FUNCTION_MISSING")
    return mod


def verify_zip_namespace(infos) -> None:
    mod = canonical_archive_module()
    try:
        mod.validate_members(infos)
    except ValueError as exc:
        # Preserve earlier public error codes for existing E06 consumers while
        # rejecting new dangerous ancestor and nonregular UNIX ZIP members.
        reason = str(exc)
        if reason.startswith("Duplicate/case collision:"):
            raise SourceHold("ZIP_DUPLICATE_WINDOWS_NAME: " + reason) from exc
        if reason.startswith("Symlink/special file:"):
            raise SourceHold("ZIP_SYMLINK_NOT_ALLOWED_OR_SPECIAL_UNIX: " + reason) from exc
        raise SourceHold("ZIP_NAMESPACE_OR_SPECIAL_FILE_HOLD: " + reason) from exc


def safe_member(name: str, directory: bool) -> str:
    if not name or len(name) > 500 or "\\" in name or "\0" in name:
        raise SourceHold("ZIP_UNSAFE_MEMBER_NAME")
    if unicodedata.normalize("NFC", name) != name:
        raise SourceHold("ZIP_NONCANONICAL_UNICODE")
    path = name[:-1] if directory else name
    if not path or path.startswith("/") or path.startswith("//") or ":" in path:
        raise SourceHold("ZIP_ABSOLUTE_OR_ADS_PATH")
    segments = path.split("/")
    if any(s in ("", ".", "..") or s.endswith(" ") or s.endswith(".") or DEVICE.fullmatch(s)
           or any(ord(c) < 32 for c in s) for s in segments):
        raise SourceHold("ZIP_WINDOWS_PATH_COLLISION_OR_TRAVERSAL")
    if PurePosixPath(path).as_posix() != path:
        raise SourceHold("ZIP_NONCANONICAL_PATH")
    return path


def verify_original(parts_dir: Path, *, part_pins=PARTS,
                    archive_sha=ARCHIVE_SHA256, expected_files=EXPECTED_FILES,
                    run_id: str) -> dict:
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]{8,120}", run_id):
        raise SourceHold("INVALID_RUN_ID")
    if len(part_pins) != 3 or expected_files < 1 or expected_files > MAX_FILES:
        raise SourceHold("INVALID_ARCHIVE_PIN_CONTRACT")
    root = parts_dir.resolve(strict=True)
    if not root.is_dir() or parts_dir.is_symlink():
        raise SourceHold("UNSAFE_SOURCE_DIRECTORY")
    digest = hashlib.sha256()
    parts_receipts = []
    # TemporaryFile is disposed regardless of failure; do not leave reconstructed ZIPs.
    with tempfile.TemporaryFile(mode="w+b") as joined:
        for name, size, expected_blob in part_pins:
            if name not in (p[0] for p in PARTS):
                raise SourceHold("UNEXPECTED_SOURCE_PART_NAME")
            candidate = root / name
            if candidate.is_symlink() or not candidate.is_file():
                raise SourceHold("MISSING_OR_SYMLINK_SOURCE_PART:" + name)
            before = candidate.stat()
            if before.st_size != size:
                raise SourceHold("SOURCE_PART_SIZE_MISMATCH:" + name)
            git = hashlib.sha1(b"blob " + str(size).encode("ascii") + b"\0")
            own = hashlib.sha256()
            with candidate.open("rb") as stream:
                while block := stream.read(CHUNK):
                    joined.write(block)
                    digest.update(block)
                    own.update(block)
                    git.update(block)
                after = os.fstat(stream.fileno())
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
            ):
                raise SourceHold("SOURCE_PART_CHANGED_DURING_READ:" + name)
            if git.hexdigest() != expected_blob:
                raise SourceHold("SOURCE_PART_GIT_BLOB_SHA1_MISMATCH:" + name)
            parts_receipts.append({"path": name, "bytes": size, "sha256": own.hexdigest(),
                                   "gitBlobSha1": git.hexdigest()})
        observed = digest.hexdigest()
        if observed != archive_sha:
            raise SourceHold("RECONSTRUCTED_ZIP_SHA256_MISMATCH")
        joined.seek(0)
        try:
            archive = zipfile.ZipFile(joined, mode="r", allowZip64=True)
        except (zipfile.BadZipFile, OSError, ValueError) as exc:
            raise SourceHold("ORIGINAL_ZIP_STRUCTURE_INVALID") from exc
        files, seen, total = [], set(), 0
        with archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILES + 4096:
                raise SourceHold("ZIP_TOO_MANY_MEMBERS")
            # File-as-parent (either order), implicit Windows casefold collisions
            # and UNIX special nodes are denied before reading member bytes.
            # Keep original E06 unsafe-name error codes before the stricter
            # shared parent/type preflight, so existing consumers do not regress.
            for entry in infos:
                safe_member(entry.filename, entry.is_dir())
            verify_zip_namespace(infos)
            for entry in infos:
                directory = entry.is_dir()
                name = safe_member(entry.filename, directory)
                key = name.casefold()
                if key in seen:
                    raise SourceHold("ZIP_DUPLICATE_WINDOWS_NAME:" + name)
                seen.add(key)
                unix_mode = (entry.external_attr >> 16) & 0xFFFF
                if (unix_mode & 0o170000) == 0o120000:
                    raise SourceHold("ZIP_SYMLINK_NOT_ALLOWED:" + name)
                if entry.flag_bits & 0x1:
                    raise SourceHold("ZIP_ENCRYPTED_MEMBER_NOT_ALLOWED:" + name)
                if directory:
                    continue
                if len(files) >= MAX_FILES or total + entry.file_size > MAX_UNCOMPRESSED:
                    raise SourceHold("ZIP_UNCOMPRESSED_LIMIT")
                if entry.file_size > max(1, entry.compress_size) * 500:
                    raise SourceHold("ZIP_SUSPICIOUS_COMPRESSION_RATIO:" + name)
                actual = hashlib.sha256()
                count = 0
                try:
                    with archive.open(entry, "r") as stream:
                        while chunk := stream.read(CHUNK):
                            actual.update(chunk)
                            count += len(chunk)
                            if count > entry.file_size:
                                raise SourceHold("ZIP_MEMBER_SIZE_OVERFLOW:" + name)
                except (OSError, RuntimeError, zipfile.BadZipFile, EOFError) as exc:
                    raise SourceHold("ZIP_MEMBER_CRC_OR_STREAM_FAILURE:" + name) from exc
                if count != entry.file_size:
                    raise SourceHold("ZIP_MEMBER_SIZE_MISMATCH:" + name)
                total += count
                files.append({"path": name, "bytes": count, "sha256": actual.hexdigest(),
                              "crc32": format(entry.CRC, "08x")})
        if len(files) != expected_files:
            raise SourceHold(f"ZIP_FILE_COUNT_MISMATCH:{len(files)}!= {expected_files}")
    return {
        "schema": "NOX_V16_ORIGINAL_729_INNER_SHA256_SOURCELOCK_V1",
        "runId": run_id,
        "status": "ORIGINAL_ARCHIVE_BYTES_AND_INNER_FILES_VERIFIED_ONLY",
        "historicalGitBaseline": {"commit": HISTORICAL_BASE_COMMIT, "tree": HISTORICAL_BASE_TREE},
        "combinedZip": {"sha256": observed, "bytes": sum(s for _, s, _ in part_pins),
                        "sourceParts": parts_receipts},
        "fileCount": len(files), "uncompressedBytes": total,
        "files": sorted(files, key=lambda f: f["path"]),
        "ownerReceiptsVerified": False, "unifiedRuntimeIntegrated": False,
        "nativeWindowsAccepted": False, "releaseAccepted": False,
    }


def _trusted_output_parent(output: Path) -> None:
    """Reject redirected receipt ancestors before any write to owner output."""
    parent = output.absolute().parent
    for node in (parent, *parent.parents):
        try:
            attrs = node.lstat()
        except OSError as exc:
            raise SourceHold("OUTPUT_PARENT_UNAVAILABLE") from exc
        if (not stat.S_ISDIR(attrs.st_mode) or stat.S_ISLNK(attrs.st_mode)
                or (getattr(attrs, "st_file_attributes", 0) &
                    getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))):
            raise SourceHold("OUTPUT_PARENT_REPARSE_OR_UNSAFE")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed original source ZIP+729 SHA gate")
    parser.add_argument("--parts-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    try:
        if args.out.is_symlink() or args.out.exists() or not args.out.parent.is_dir():
            raise SourceHold("OUTPUT_ALREADY_EXISTS_OR_UNSAFE")
        _trusted_output_parent(args.out)
        receipt = verify_original(args.parts_dir, run_id=args.run_id)
        encoded = (json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        # Exclusive create: never overwrite an existing receipt or owner file.
        _trusted_output_parent(args.out)
        # Use the existing fsync-before-publication, no-clobber implementation.
        # A failed write must not leave a receipt that looks like complete evidence.
        publisher = canonical_archive_module()
        publisher.publish_manifest_exclusive(args.out, receipt)
        encoded = args.out.read_bytes()
        print("ORIGINAL_729_SOURCELOCK_INNER_SHA_PASS", hashlib.sha256(encoded).hexdigest())
        return 0
    except (SourceHold, OSError, ValueError) as exc:
        print("ORIGINAL_729_SOURCELOCK_HOLD", str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
