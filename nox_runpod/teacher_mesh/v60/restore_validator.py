"""Fail-closed, no-extraction validator for the V60 encrypted S03 backup.

This module only validates bytes supplied by a caller. It never reads keys,
starts age/SSH, extracts files, or writes production data. A decryptor must be
explicitly supplied; the owner-key path remains a separate, unverified gate.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import sqlite3
import zlib
import stat
import tarfile
import zipfile
from collections.abc import Callable

OUTER_ZIP_BYTES = 8_109_924
OUTER_ZIP_SHA256 = "367ce4efbad525f998f282efd63b257413235f5f3f0378ccb707932e1d5f62dc"
INNER_CIPHERTEXT_SHA256 = "083aeb52aff15da3598bffb5161a7489e965de72ae51bdc68e69b0da0ad187f6"
INNER_CIPHERTEXT_NAME = "NOX_V60_S03_GENESIS_WEB_20261114.tar.age"

MAX_OUTER_BYTES = 64 * 1024 * 1024
MAX_CIPHERTEXT_BYTES = 64 * 1024 * 1024
MAX_PLAINTEXT_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_TAR_EXPANDED_BYTES = MAX_TOTAL_BYTES + 16 * 1024
MAX_TAR_COMPRESSION_RATIO = 2048
MAX_TAR_RATIO_FLOOR_BYTES = 1024 * 1024
MANIFEST_NAME = "RESTORE_MANIFEST.json"
RECEIPT_NAME = "NOX_V60_ENCRYPTED_BACKUP_RECEIPT.json"
MAX_RECEIPT_BYTES = 64 * 1024

EXPECTED_FILES = frozenset({
    "S03/s03_seed_primary.sqlite3",
    "S03/infinite_synaptic_memory.sqlite3",
    "S03/s03_seed_second_copy.sqlite3",
    "WEB_V29_3/site/chat.html",
    "WEB_V29_3/site/pc/resonance.html",
    "WEB_V29_3/site/nox-chat.js",
    "WEB_V29_3/site/pc/nox-chat.js",
})
EXPECTED_TAR_MEMBERS = EXPECTED_FILES | {MANIFEST_NAME}
EXPECTED_ZIP_MEMBERS = frozenset({INNER_CIPHERTEXT_NAME, RECEIPT_NAME})
EXPECTED_RECEIPT_KEYS = frozenset({
    "schema", "instance_id", "ciphertext_file", "ciphertext_bytes",
    "ciphertext_sha256", "existing_owner_ssh_recipient_sha256",
    "restoration_with_temporary_test_identity", "restored_file_sha256_count",
    "plaintext_tar_sha256", "web_frozen_source_count",
    "consistent_sqlite_online_backups", "raw_source_files_uploaded_to_github",
    "remote_source_files_deleted", "owner_ssh_private_key_decryption_tested",
    "native_queue_deployment",
})


def _safe_relative_name(name: object) -> bool:
    if not isinstance(name, str) or not name or len(name) > 4096:
        return False
    if name.startswith(("/", "\\")) or "\\" in name or "\x00" in name or ":" in name:
        return False
    parts = name.split("/")
    return all(part not in ("", ".", "..") for part in parts)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("HOLD_JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _reject_json_constant(_value):
    raise ValueError("HOLD_JSON_NONFINITE")


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _validate_receipt(raw_receipt: bytes, ciphertext: bytes, inner_name: str) -> dict:
    """Validate the sibling receipt and bind its payload claims to the age bytes."""
    try:
        receipt = json.loads(
            raw_receipt.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, ValueError, RecursionError):
        raise RuntimeError("HOLD_OUTER_ZIP_RECEIPT_JSON") from None
    if not isinstance(receipt, dict) or set(receipt) != EXPECTED_RECEIPT_KEYS:
        raise RuntimeError("HOLD_OUTER_ZIP_RECEIPT_SCHEMA")

    ciphertext_sha256 = hashlib.sha256(ciphertext).hexdigest()
    if (receipt.get("ciphertext_file") != inner_name
            or type(receipt.get("ciphertext_bytes")) is not int
            or receipt.get("ciphertext_bytes") != len(ciphertext)
            or receipt.get("ciphertext_sha256") != ciphertext_sha256):
        raise RuntimeError("HOLD_RECEIPT_CIPHERTEXT_BINDING")

    if (receipt.get("schema") != "NOX_V60_OFFSITE_ENCRYPTED_BACKUP_RECEIPT_V1"
            or type(receipt.get("instance_id")) is not int
            or receipt.get("instance_id") != 60509551
            or not _is_sha256(receipt.get("existing_owner_ssh_recipient_sha256"))
            or receipt.get("restoration_with_temporary_test_identity") != "PASS"
            or type(receipt.get("restored_file_sha256_count")) is not int
            or receipt.get("restored_file_sha256_count") != 7
            or not _is_sha256(receipt.get("plaintext_tar_sha256"))
            or type(receipt.get("web_frozen_source_count")) is not int
            or receipt.get("web_frozen_source_count") != 4
            or type(receipt.get("consistent_sqlite_online_backups")) is not int
            or receipt.get("consistent_sqlite_online_backups") != 3
            or receipt.get("raw_source_files_uploaded_to_github") is not False
            or receipt.get("remote_source_files_deleted") is not False
            or receipt.get("owner_ssh_private_key_decryption_tested") is not False
            or receipt.get("native_queue_deployment") is not False):
        raise RuntimeError("HOLD_OUTER_ZIP_RECEIPT_SCHEMA")
    return receipt


def _verify_outer_zip_pair(
    outer_bytes: bytes,
    *,
    expected_outer_bytes: int = OUTER_ZIP_BYTES,
    expected_outer_sha256: str = OUTER_ZIP_SHA256,
    expected_ciphertext_sha256: str = INNER_CIPHERTEXT_SHA256,
    inner_name: str = INNER_CIPHERTEXT_NAME,
) -> tuple[bytes, dict]:
    """Verify exact ZIP pair, hashes, and receipt before any decryptor is called."""
    if not isinstance(outer_bytes, bytes) or not 0 < len(outer_bytes) <= MAX_OUTER_BYTES:
        raise RuntimeError("HOLD_OUTER_ZIP_SIZE")
    if type(expected_outer_bytes) is not int or expected_outer_bytes <= 0:
        raise RuntimeError("HOLD_OUTER_EXPECTED_SIZE")
    if len(outer_bytes) != expected_outer_bytes:
        raise RuntimeError("HOLD_OUTER_ZIP_SIZE")
    if not _is_sha256(expected_outer_sha256):
        raise RuntimeError("HOLD_OUTER_EXPECTED_SHA")
    if hashlib.sha256(outer_bytes).hexdigest() != expected_outer_sha256:
        raise RuntimeError("HOLD_OUTER_ZIP_SHA256")
    if not _is_sha256(expected_ciphertext_sha256) or not _safe_relative_name(inner_name):
        raise RuntimeError("HOLD_INNER_EXPECTATION")

    try:
        with zipfile.ZipFile(io.BytesIO(outer_bytes), "r") as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if (len(infos) != 2 or len(set(names)) != 2
                    or set(names) != {inner_name, RECEIPT_NAME}):
                raise RuntimeError("HOLD_OUTER_ZIP_MEMBERS")

            by_name = {item.filename: item for item in infos}
            for info in infos:
                mode = info.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if (not _safe_relative_name(info.filename) or info.is_dir()
                        or info.flag_bits & 0x1
                        or kind not in (0, stat.S_IFREG)):
                    raise RuntimeError("HOLD_OUTER_ZIP_UNSAFE_MEMBER")

            ciphertext_info = by_name[inner_name]
            receipt_info = by_name[RECEIPT_NAME]
            if not 0 < ciphertext_info.file_size <= MAX_CIPHERTEXT_BYTES:
                raise RuntimeError("HOLD_CIPHERTEXT_SIZE")
            if not 0 < receipt_info.file_size <= MAX_RECEIPT_BYTES:
                raise RuntimeError("HOLD_RECEIPT_SIZE")
            with archive.open(ciphertext_info, "r") as stream:
                ciphertext = stream.read(MAX_CIPHERTEXT_BYTES + 1)
            with archive.open(receipt_info, "r") as stream:
                raw_receipt = stream.read(MAX_RECEIPT_BYTES + 1)
            if (len(ciphertext) != ciphertext_info.file_size
                    or len(ciphertext) > MAX_CIPHERTEXT_BYTES):
                raise RuntimeError("HOLD_CIPHERTEXT_SIZE")
            if (len(raw_receipt) != receipt_info.file_size
                    or len(raw_receipt) > MAX_RECEIPT_BYTES):
                raise RuntimeError("HOLD_RECEIPT_SIZE")
    except RuntimeError:
        raise
    except (OSError, EOFError, KeyError, NotImplementedError,
            zipfile.BadZipFile, zipfile.LargeZipFile):
        raise RuntimeError("HOLD_OUTER_ZIP_INVALID") from None

    receipt = _validate_receipt(raw_receipt, ciphertext, inner_name)
    if hashlib.sha256(ciphertext).hexdigest() != expected_ciphertext_sha256:
        raise RuntimeError("HOLD_INNER_CIPHERTEXT_SHA256")
    return ciphertext, receipt


def verify_outer_zip(
    outer_bytes: bytes,
    *,
    expected_outer_bytes: int = OUTER_ZIP_BYTES,
    expected_outer_sha256: str = OUTER_ZIP_SHA256,
    expected_ciphertext_sha256: str = INNER_CIPHERTEXT_SHA256,
    inner_name: str = INNER_CIPHERTEXT_NAME,
) -> bytes:
    """Verify the pinned two-member ZIP and return its age ciphertext."""
    ciphertext, _ = _verify_outer_zip_pair(
        outer_bytes,
        expected_outer_bytes=expected_outer_bytes,
        expected_outer_sha256=expected_outer_sha256,
        expected_ciphertext_sha256=expected_ciphertext_sha256,
        inner_name=inner_name,
    )
    return ciphertext


def _sqlite_integrity_check(database_bytes: bytes) -> None:
    """Run SQLite integrity_check on an in-memory deserialization only."""
    connection = None
    try:
        connection = sqlite3.connect(":memory:")
        if not hasattr(connection, "deserialize"):
            raise RuntimeError("HOLD_SQLITE_DESERIALIZE_UNAVAILABLE")
        connection.deserialize(database_bytes)
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute("PRAGMA integrity_check").fetchall()
        if rows != [("ok",)]:
            raise RuntimeError("HOLD_SQLITE_INTEGRITY")
    except RuntimeError:
        raise
    except sqlite3.DatabaseError:
        raise RuntimeError("HOLD_SQLITE_INTEGRITY") from None
    finally:
        if connection is not None:
            connection.close()


class _BoundedGzipReader:
    """Forward-only gzip reader with byte and expansion-ratio quotas."""

    def __init__(self, compressed: bytes):
        self._source_bytes = len(compressed)
        self._gzip = gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb")
        self._expanded = 0
        self._max_expanded = MAX_TAR_EXPANDED_BYTES
        self._max_ratio_bytes = max(
            MAX_TAR_RATIO_FLOOR_BYTES,
            self._source_bytes * MAX_TAR_COMPRESSION_RATIO,
        )

    def read(self, size: int = -1) -> bytes:
        if size == 0:
            return b""
        remaining = self._max_expanded - self._expanded
        request = remaining + 1 if size is None or size < 0 else min(size, 64 * 1024, remaining + 1)
        try:
            chunk = self._gzip.read(request)
        except (OSError, EOFError, zlib.error):
            raise RuntimeError("HOLD_TAR_INVALID") from None
        self._expanded += len(chunk)
        if self._expanded > self._max_expanded:
            raise RuntimeError("HOLD_TAR_EXPANDED_SIZE")
        if self._expanded > self._max_ratio_bytes:
            raise RuntimeError("HOLD_TAR_EXPANSION_RATIO")
        return chunk

    def readable(self) -> bool:
        return True

    def close(self) -> None:
        self._gzip.close()


def verify_plaintext_tar(plaintext: bytes) -> dict:
    """Validate exact V60 manifest/file coverage, hashes, paths and SQLite DBs.

    The gzip layer is read through a forward-only quota wrapper before TAR
    parsing. TAR members are consumed in order, so expansion/member limits apply
    before the parser can walk an unbounded decompressed stream. SQLite bytes
    are deserialized only into :memory: with query_only enabled.
    """
    if not isinstance(plaintext, bytes) or not 0 < len(plaintext) <= MAX_PLAINTEXT_BYTES:
        raise RuntimeError("HOLD_PLAINTEXT_SIZE")

    reader = _BoundedGzipReader(plaintext)
    members = {}
    contents = {}
    total = 0
    try:
        with tarfile.open(fileobj=reader, mode="r|") as archive:
            for member in archive:
                if len(members) >= len(EXPECTED_TAR_MEMBERS):
                    raise RuntimeError("HOLD_TAR_MEMBER_COUNT_OR_DUPLICATE")
                if member.name in members:
                    raise RuntimeError("HOLD_TAR_MEMBER_COUNT_OR_DUPLICATE")
                if (not _safe_relative_name(member.name)
                        or member.name not in EXPECTED_TAR_MEMBERS
                        or not member.isfile()):
                    raise RuntimeError("HOLD_TAR_UNSAFE_MEMBER")
                if member.size < 0 or member.size > MAX_MEMBER_BYTES:
                    raise RuntimeError("HOLD_TAR_MEMBER_SIZE")
                if member.name == MANIFEST_NAME and not 0 < member.size <= MAX_MANIFEST_BYTES:
                    raise RuntimeError("HOLD_MANIFEST_SIZE")
                total += member.size
                if total > MAX_TOTAL_BYTES:
                    raise RuntimeError("HOLD_TAR_TOTAL_SIZE")

                stream = archive.extractfile(member)
                if stream is None:
                    raise RuntimeError("HOLD_RESTORED_MEMBER_MISSING")
                data = bytearray()
                count = 0
                while count < member.size:
                    chunk = stream.read(min(1024 * 1024, member.size - count))
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > member.size or count > MAX_MEMBER_BYTES:
                        raise RuntimeError("HOLD_RESTORED_SIZE")
                    data.extend(chunk)
                if count != member.size:
                    raise RuntimeError("HOLD_RESTORED_SIZE")
                members[member.name] = member
                contents[member.name] = bytes(data)

        if len(members) != len(EXPECTED_TAR_MEMBERS) or set(members) != EXPECTED_TAR_MEMBERS:
            raise RuntimeError("HOLD_TAR_MEMBER_COVERAGE")

        raw_manifest = contents[MANIFEST_NAME]
        try:
            manifest = json.loads(
                raw_manifest.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_json_constant,
            )
        except (UnicodeError, ValueError, RecursionError):
            raise RuntimeError("HOLD_MANIFEST_JSON") from None
        expected_manifest_keys = {
            "schema", "origin_instance_id", "snapshot", "s03_db_count",
            "web_lock_count", "source_contents_changed", "files",
        }
        if (not isinstance(manifest, dict)
                or set(manifest) != expected_manifest_keys
                or manifest.get("schema") != "NOX_V60_CRITICAL_BACKUP_MANIFEST_V1"
                or type(manifest.get("origin_instance_id")) is not int
                or manifest.get("origin_instance_id") != 60509551
                or manifest.get("snapshot") != "SQLITE_ONLINE_BACKUP"
                or type(manifest.get("s03_db_count")) is not int
                or manifest.get("s03_db_count") != 3
                or type(manifest.get("web_lock_count")) is not int
                or manifest.get("web_lock_count") != 4
                or manifest.get("source_contents_changed") is not False):
            raise RuntimeError("HOLD_MANIFEST_SCHEMA")
        records = manifest.get("files")
        if not isinstance(records, list) or len(records) != 7:
            raise RuntimeError("HOLD_MANIFEST_FILE_COUNT")

        seen = set()
        total_manifest = 0
        sqlite_count = 0
        for record in records:
            if not isinstance(record, dict) or set(record) != {"path", "size_bytes", "sha256"}:
                raise RuntimeError("HOLD_MANIFEST_RECORD")
            name = record["path"]
            size = record["size_bytes"]
            digest = record["sha256"]
            if not _safe_relative_name(name) or name not in EXPECTED_FILES:
                raise RuntimeError("HOLD_MANIFEST_UNSAFE_PATH")
            if name in seen:
                raise RuntimeError("HOLD_MANIFEST_DUPLICATE_PATH")
            if (type(size) is not int or size < 0 or size > MAX_MEMBER_BYTES
                    or not _is_sha256(digest)):
                raise RuntimeError("HOLD_MANIFEST_RECORD")
            seen.add(name)
            total_manifest += size
            if total_manifest > MAX_TOTAL_BYTES:
                raise RuntimeError("HOLD_TAR_TOTAL_SIZE")
            member = members[name]
            data = contents[name]
            if not member.isfile() or member.size != size or len(data) != size:
                raise RuntimeError("HOLD_RESTORED_SIZE")
            if hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError("HOLD_RESTORED_SHA256")
            if name.startswith("S03/"):
                _sqlite_integrity_check(data)
                sqlite_count += 1

        if seen != EXPECTED_FILES or sqlite_count != 3:
            raise RuntimeError("HOLD_MANIFEST_FILE_COVERAGE")
        return {
            "state": "SOURCE_BYTES_VALIDATED_ONLY",
            "verified_files": len(seen),
            "sqlite_integrity_checked": sqlite_count,
            "verified_bytes": total_manifest,
            "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
            "production_writes": 0,
        }
    except RuntimeError:
        raise
    except (OSError, EOFError, KeyError, tarfile.TarError, zlib.error):
        raise RuntimeError("HOLD_TAR_INVALID") from None
    finally:
        reader.close()


def verify_offsite_candidate(
    outer_bytes: bytes,
    decryptor: Callable[[bytes], bytes] | None = None,
    *,
    expected_outer_bytes: int = OUTER_ZIP_BYTES,
    expected_outer_sha256: str = OUTER_ZIP_SHA256,
    expected_ciphertext_sha256: str = INNER_CIPHERTEXT_SHA256,
    inner_name: str = INNER_CIPHERTEXT_NAME,
) -> dict:
    """Validate an encrypted Drive candidate only with an explicit owner decryptor."""
    ciphertext, receipt = _verify_outer_zip_pair(
        outer_bytes,
        expected_outer_bytes=expected_outer_bytes,
        expected_outer_sha256=expected_outer_sha256,
        expected_ciphertext_sha256=expected_ciphertext_sha256,
        inner_name=inner_name,
    )
    if not callable(decryptor):
        raise RuntimeError("HOLD_OWNER_KEY_OR_DECRYPTOR_REQUIRED")
    try:
        plaintext = decryptor(ciphertext)
    except Exception:
        raise RuntimeError("HOLD_OWNER_DECRYPTION_FAILED") from None
    result = verify_plaintext_tar(plaintext)
    return {
        **result,
        "outer_zip_sha256": hashlib.sha256(outer_bytes).hexdigest(),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
        "owner_key_available": False,
        "receipt_verified": True,
    }
