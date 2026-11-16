"""Fail-closed, no-extraction validator for the V60 encrypted S03 backup.

This module only validates bytes supplied by a caller. It never reads keys,
starts age/SSH, extracts files, or writes production data. A decryptor must be
explicitly supplied; the owner-key path remains a separate, unverified gate.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sqlite3
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
MANIFEST_NAME = "RESTORE_MANIFEST.json"

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


def verify_outer_zip(
    outer_bytes: bytes,
    *,
    expected_outer_bytes: int = OUTER_ZIP_BYTES,
    expected_outer_sha256: str = OUTER_ZIP_SHA256,
    expected_ciphertext_sha256: str = INNER_CIPHERTEXT_SHA256,
    inner_name: str = INNER_CIPHERTEXT_NAME,
) -> bytes:
    """Verify outer ZIP and return one pinned age ciphertext, without extraction."""
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
            if len(infos) != 1 or names != [inner_name]:
                raise RuntimeError("HOLD_OUTER_ZIP_MEMBERS")
            info = infos[0]
            mode = info.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if (not _safe_relative_name(info.filename) or info.is_dir()
                    or info.flag_bits & 0x1
                    or kind not in (0, stat.S_IFREG)):
                raise RuntimeError("HOLD_OUTER_ZIP_UNSAFE_MEMBER")
            if not 0 < info.file_size <= MAX_CIPHERTEXT_BYTES:
                raise RuntimeError("HOLD_CIPHERTEXT_SIZE")
            with archive.open(info, "r") as stream:
                ciphertext = stream.read(MAX_CIPHERTEXT_BYTES + 1)
            if len(ciphertext) != info.file_size or len(ciphertext) > MAX_CIPHERTEXT_BYTES:
                raise RuntimeError("HOLD_CIPHERTEXT_SIZE")
    except RuntimeError:
        raise
    except (OSError, EOFError, KeyError, zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError):
        raise RuntimeError("HOLD_OUTER_ZIP_INVALID") from None

    if hashlib.sha256(ciphertext).hexdigest() != expected_ciphertext_sha256:
        raise RuntimeError("HOLD_INNER_CIPHERTEXT_SHA256")
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


def verify_plaintext_tar(plaintext: bytes) -> dict:
    """Validate exact V60 manifest/file coverage, hashes, paths and SQLite DBs.

    Data stays in memory. SQLite is deserialized into :memory: with query_only
    enabled. No filesystem extraction or production destination exists here.
    """
    if not isinstance(plaintext, bytes) or not 0 < len(plaintext) <= MAX_PLAINTEXT_BYTES:
        raise RuntimeError("HOLD_PLAINTEXT_SIZE")
    try:
        archive = tarfile.open(fileobj=io.BytesIO(plaintext), mode="r:gz")
    except (OSError, EOFError, tarfile.TarError):
        raise RuntimeError("HOLD_TAR_INVALID") from None

    with archive:
        try:
            members = archive.getmembers()
            names = [member.name for member in members]
            if len(members) != 8 or len(names) != len(set(names)):
                raise RuntimeError("HOLD_TAR_MEMBER_COUNT_OR_DUPLICATE")
            if set(names) != EXPECTED_TAR_MEMBERS:
                raise RuntimeError("HOLD_TAR_MEMBER_COVERAGE")
            if any(not _safe_relative_name(member.name) or not member.isfile()
                   for member in members):
                raise RuntimeError("HOLD_TAR_UNSAFE_MEMBER")
            if any(member.size < 0 or member.size > MAX_MEMBER_BYTES for member in members):
                raise RuntimeError("HOLD_TAR_MEMBER_SIZE")
            if sum(member.size for member in members) > MAX_TOTAL_BYTES:
                raise RuntimeError("HOLD_TAR_TOTAL_SIZE")
            by_name = {member.name: member for member in members}
            manifest_member = by_name[MANIFEST_NAME]
            if not 0 < manifest_member.size <= MAX_MANIFEST_BYTES:
                raise RuntimeError("HOLD_MANIFEST_SIZE")
            manifest_stream = archive.extractfile(manifest_member)
            if manifest_stream is None:
                raise RuntimeError("HOLD_MANIFEST_MISSING")
            raw_manifest = manifest_stream.read(MAX_MANIFEST_BYTES + 1)
            if len(raw_manifest) != manifest_member.size or len(raw_manifest) > MAX_MANIFEST_BYTES:
                raise RuntimeError("HOLD_MANIFEST_SIZE")
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
            total = 0
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
                total += size
                if total > MAX_TOTAL_BYTES:
                    raise RuntimeError("HOLD_TAR_TOTAL_SIZE")
                member = by_name[name]
                if not member.isfile() or member.size != size:
                    raise RuntimeError("HOLD_RESTORED_SIZE")
                stream = archive.extractfile(member)
                if stream is None:
                    raise RuntimeError("HOLD_RESTORED_MEMBER_MISSING")
                h = hashlib.sha256()
                content = bytearray() if name.startswith("S03/") else None
                count = 0
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > size or count > MAX_MEMBER_BYTES:
                        raise RuntimeError("HOLD_RESTORED_SIZE")
                    h.update(chunk)
                    if content is not None:
                        content.extend(chunk)
                if count != size or h.hexdigest() != digest:
                    raise RuntimeError("HOLD_RESTORED_SHA256")
                if content is not None:
                    _sqlite_integrity_check(bytes(content))
                    sqlite_count += 1
            if seen != EXPECTED_FILES or sqlite_count != 3:
                raise RuntimeError("HOLD_MANIFEST_FILE_COVERAGE")
            return {
                "state": "SOURCE_BYTES_VALIDATED_ONLY",
                "verified_files": len(seen),
                "sqlite_integrity_checked": sqlite_count,
                "verified_bytes": total,
                "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
                "production_writes": 0,
            }
        except RuntimeError:
            raise
        except (OSError, EOFError, KeyError, tarfile.TarError):
            raise RuntimeError("HOLD_TAR_INVALID") from None


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
    ciphertext = verify_outer_zip(
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
    }
