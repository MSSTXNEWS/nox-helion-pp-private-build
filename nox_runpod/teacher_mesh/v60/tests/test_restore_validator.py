"""Synthetic V60 archive validation. No key, age, SSH, OneHost or production DB."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import sqlite3
import tarfile
import unittest
import warnings
from pathlib import Path
import zipfile
from unittest.mock import patch

from nox_runpod.teacher_mesh.v60 import encrypted_backup
from nox_runpod.teacher_mesh.v60 import restore_validator as validator


def sqlite_image(corrupt: bool = False) -> bytes:
    if corrupt:
        return b"not-a-sqlite-database"
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE memory (id INTEGER PRIMARY KEY, text TEXT NOT NULL)")
        connection.execute("INSERT INTO memory(text) VALUES (?)", ("synthetic-only",))
        return connection.serialize()
    finally:
        connection.close()


def plaintext_tar(
    *,
    corrupt_db: bool = False,
    traversal_manifest: bool = False,
    duplicate_member: bool = False,
    omit_member: bool = False,
) -> bytes:
    rows = {}
    for name in validator.EXPECTED_FILES:
        rows[name] = sqlite_image(corrupt_db) if name.endswith(".sqlite3") else b"synthetic fixture bytes"
    records = [
        {"path": name, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in sorted(rows.items())
    ]
    if traversal_manifest:
        records[0] = {**records[0], "path": "S03/../escape.sqlite3"}
    manifest = {
        "schema": "NOX_V60_CRITICAL_BACKUP_MANIFEST_V1",
        "origin_instance_id": 60509551,
        "snapshot": "SQLITE_ONLINE_BACKUP",
        "s03_db_count": 3,
        "web_lock_count": 4,
        "source_contents_changed": False,
        "files": records,
    }
    result = io.BytesIO()
    missing_name = sorted(rows)[0]
    with tarfile.open(fileobj=result, mode="w:gz") as archive:
        for name, data in sorted(rows.items()):
            if omit_member and name == missing_name:
                continue
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(data))
        if duplicate_member:
            data = rows[missing_name]
            info = tarfile.TarInfo(missing_name)
            info.size = len(data)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(data))
        encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        info = tarfile.TarInfo(validator.MANIFEST_NAME)
        info.size = len(encoded)
        info.mtime = 0
        archive.addfile(info, io.BytesIO(encoded))
    return result.getvalue()


def gzip_bomb(expanded_bytes: int = 8192) -> bytes:
    result = io.BytesIO()
    with gzip.GzipFile(fileobj=result, mode="wb", mtime=0) as stream:
        stream.write(bytes(expanded_bytes))
    return result.getvalue()


def receipt_object(ciphertext: bytes, overrides: dict | None = None) -> dict:
    receipt = {
        "schema": "NOX_V60_OFFSITE_ENCRYPTED_BACKUP_RECEIPT_V1",
        "instance_id": 60509551,
        "ciphertext_file": validator.INNER_CIPHERTEXT_NAME,
        "ciphertext_bytes": len(ciphertext),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
        "existing_owner_ssh_recipient_sha256": "a" * 64,
        "restoration_with_temporary_test_identity": "PASS",
        "restored_file_sha256_count": 7,
        "plaintext_tar_sha256": "b" * 64,
        "web_frozen_source_count": 4,
        "consistent_sqlite_online_backups": 3,
        "raw_source_files_uploaded_to_github": False,
        "remote_source_files_deleted": False,
        "owner_ssh_private_key_decryption_tested": False,
        "native_queue_deployment": False,
    }
    receipt.update(overrides or {})
    return receipt


def outer_zip(
    ciphertext: bytes,
    name: str = validator.INNER_CIPHERTEXT_NAME,
    *,
    include_receipt: bool = True,
    receipt_overrides: dict | None = None,
    extra_member: tuple[str, bytes] | None = None,
    duplicate_ciphertext: bool = False,
) -> bytes:
    result = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(name, ciphertext)
            if duplicate_ciphertext:
                archive.writestr(name, ciphertext)
            if include_receipt:
                raw_receipt = json.dumps(
                    receipt_object(ciphertext, receipt_overrides),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                archive.writestr(validator.RECEIPT_NAME, raw_receipt)
            if extra_member is not None:
                archive.writestr(extra_member[0], extra_member[1])
    return result.getvalue()


class V60RestoreValidatorTests(unittest.TestCase):
    def verify_outer(self, raw: bytes, ciphertext: bytes):
        return validator.verify_outer_zip(
            raw,
            expected_outer_bytes=len(raw),
            expected_outer_sha256=hashlib.sha256(raw).hexdigest(),
            expected_ciphertext_sha256=hashlib.sha256(ciphertext).hexdigest(),
        )

    def test_outer_and_inner_hashes_are_independently_pinned(self):
        ciphertext = b"synthetic age ciphertext"
        raw = outer_zip(ciphertext)
        self.assertEqual(self.verify_outer(raw, ciphertext), ciphertext)
        with self.assertRaisesRegex(RuntimeError, "HOLD_OUTER_ZIP_SHA256"):
            validator.verify_outer_zip(
                raw, expected_outer_bytes=len(raw), expected_outer_sha256="0" * 64,
                expected_ciphertext_sha256=hashlib.sha256(ciphertext).hexdigest(),
            )
        with self.assertRaisesRegex(RuntimeError, "HOLD_INNER_CIPHERTEXT_SHA256"):
            validator.verify_outer_zip(
                raw, expected_outer_bytes=len(raw), expected_outer_sha256=hashlib.sha256(raw).hexdigest(),
                expected_ciphertext_sha256="0" * 64,
            )

    def test_outer_zip_path_traversal_fails_closed(self):
        ciphertext = b"synthetic age ciphertext"
        raw = outer_zip(ciphertext, "../escape.tar.age")
        with self.assertRaisesRegex(RuntimeError, "HOLD_OUTER_ZIP_MEMBERS"):
            validator.verify_outer_zip(
                raw, expected_outer_bytes=len(raw), expected_outer_sha256=hashlib.sha256(raw).hexdigest(),
                expected_ciphertext_sha256=hashlib.sha256(ciphertext).hexdigest(),
            )

    def test_outer_zip_exact_ciphertext_and_receipt_pair_passes(self):
        ciphertext = b"synthetic age ciphertext"
        raw = outer_zip(ciphertext)
        self.assertEqual(self.verify_outer(raw, ciphertext), ciphertext)

    def test_outer_zip_requires_receipt_member(self):
        ciphertext = b"synthetic age ciphertext"
        raw = outer_zip(ciphertext, include_receipt=False)
        with self.assertRaisesRegex(RuntimeError, "HOLD_OUTER_ZIP_MEMBERS"):
            self.verify_outer(raw, ciphertext)

    def test_outer_zip_rejects_extra_member(self):
        ciphertext = b"synthetic age ciphertext"
        raw = outer_zip(ciphertext, extra_member=("unexpected.txt", b"synthetic"))
        with self.assertRaisesRegex(RuntimeError, "HOLD_OUTER_ZIP_MEMBERS"):
            self.verify_outer(raw, ciphertext)

    def test_outer_zip_rejects_duplicate_member(self):
        ciphertext = b"synthetic age ciphertext"
        raw = outer_zip(ciphertext, duplicate_ciphertext=True)
        with self.assertRaisesRegex(RuntimeError, "HOLD_OUTER_ZIP_MEMBERS"):
            self.verify_outer(raw, ciphertext)

    def test_receipt_ciphertext_sha_mismatch_fails_closed(self):
        ciphertext = b"synthetic age ciphertext"
        raw = outer_zip(ciphertext, receipt_overrides={"ciphertext_sha256": "0" * 64})
        with self.assertRaisesRegex(RuntimeError, "HOLD_RECEIPT_CIPHERTEXT_BINDING"):
            self.verify_outer(raw, ciphertext)

    def test_receipt_ciphertext_size_mismatch_fails_closed(self):
        ciphertext = b"synthetic age ciphertext"
        raw = outer_zip(ciphertext, receipt_overrides={"ciphertext_bytes": len(ciphertext) + 1})
        with self.assertRaisesRegex(RuntimeError, "HOLD_RECEIPT_CIPHERTEXT_BINDING"):
            self.verify_outer(raw, ciphertext)

    def test_plaintext_hashes_and_sqlite_integrity_pass_on_synthetic_fixture(self):
        result = validator.verify_plaintext_tar(plaintext_tar())
        self.assertEqual(result["verified_files"], 7)
        self.assertEqual(result["sqlite_integrity_checked"], 3)
        self.assertEqual(result["production_writes"], 0)

    def test_manifest_path_traversal_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "HOLD_MANIFEST_UNSAFE_PATH"):
            validator.verify_plaintext_tar(plaintext_tar(traversal_manifest=True))

    def test_corrupt_sqlite_database_fails_integrity_check(self):
        with self.assertRaisesRegex(RuntimeError, "HOLD_SQLITE_INTEGRITY"):
            validator.verify_plaintext_tar(plaintext_tar(corrupt_db=True))

    def test_missing_owner_decryptor_fails_closed_after_outer_hash(self):
        ciphertext = b"synthetic age ciphertext"
        raw = outer_zip(ciphertext)
        with self.assertRaisesRegex(RuntimeError, "HOLD_OWNER_KEY_OR_DECRYPTOR_REQUIRED"):
            validator.verify_offsite_candidate(
                raw,
                expected_outer_bytes=len(raw),
                expected_outer_sha256=hashlib.sha256(raw).hexdigest(),
                expected_ciphertext_sha256=hashlib.sha256(ciphertext).hexdigest(),
            )

    def test_injected_fixture_decryptor_validates_without_production_writes(self):
        ciphertext = b"synthetic age ciphertext"
        raw = outer_zip(ciphertext)
        plain = plaintext_tar()
        original_connect = sqlite3.connect
        seen = []

        def memory_only_connect(database, *args, **kwargs):
            seen.append(database)
            return original_connect(database, *args, **kwargs)

        with patch.object(validator.sqlite3, "connect", side_effect=memory_only_connect):
            result = validator.verify_offsite_candidate(
                raw,
                decryptor=lambda value: plain if value == ciphertext else b"",
                expected_outer_bytes=len(raw),
                expected_outer_sha256=hashlib.sha256(raw).hexdigest(),
                expected_ciphertext_sha256=hashlib.sha256(ciphertext).hexdigest(),
            )
        self.assertEqual(result["state"], "SOURCE_BYTES_VALIDATED_ONLY")
        self.assertTrue(seen)
        self.assertEqual(set(seen), {":memory:"})
        self.assertEqual(result["production_writes"], 0)


    def test_tar_gzip_expansion_limit_stops_before_member_scan(self):
        bomb = gzip_bomb(8192)
        with patch.object(validator, "MAX_TAR_EXPANDED_BYTES", 4096):
            with patch.object(validator, "MAX_TAR_COMPRESSION_RATIO", 10**9):
                with self.assertRaisesRegex(RuntimeError, "HOLD_TAR_EXPANDED_SIZE"):
                    validator.verify_plaintext_tar(bomb)

    def test_tar_gzip_compression_ratio_limit_fails_closed(self):
        with patch.object(validator, "MAX_TAR_COMPRESSION_RATIO", 1):
            with patch.object(validator, "MAX_TAR_RATIO_FLOOR_BYTES", 0):
                with self.assertRaisesRegex(RuntimeError, "HOLD_TAR_EXPANSION_RATIO"):
                    validator.verify_plaintext_tar(plaintext_tar())

    def test_duplicate_tar_member_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "HOLD_TAR_MEMBER_COUNT_OR_DUPLICATE"):
            validator.verify_plaintext_tar(plaintext_tar(duplicate_member=True))

    def test_missing_tar_member_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "HOLD_TAR_MEMBER_COVERAGE"):
            validator.verify_plaintext_tar(plaintext_tar(omit_member=True))

    def test_inner_hash_mismatch_never_calls_decryptor(self):
        ciphertext = b"synthetic age ciphertext"
        raw = outer_zip(ciphertext)
        calls = []
        with self.assertRaisesRegex(RuntimeError, "HOLD_INNER_CIPHERTEXT_SHA256"):
            validator.verify_offsite_candidate(
                raw,
                decryptor=lambda value: calls.append(value) or b"",
                expected_outer_bytes=len(raw),
                expected_outer_sha256=hashlib.sha256(raw).hexdigest(),
                expected_ciphertext_sha256="0" * 64,
            )
        self.assertEqual(calls, [])

    def test_synthetic_decryptor_failure_fails_closed(self):
        ciphertext = b"synthetic age ciphertext"
        raw = outer_zip(ciphertext)
        calls = []

        def failing_decryptor(value):
            calls.append(value)
            raise ValueError("synthetic decrypt failure")

        with self.assertRaisesRegex(RuntimeError, "HOLD_OWNER_DECRYPTION_FAILED"):
            validator.verify_offsite_candidate(
                raw,
                decryptor=failing_decryptor,
                expected_outer_bytes=len(raw),
                expected_outer_sha256=hashlib.sha256(raw).hexdigest(),
                expected_ciphertext_sha256=hashlib.sha256(ciphertext).hexdigest(),
            )
        self.assertEqual(calls, [ciphertext])


    def test_restore_test_stops_before_age_on_inner_hash_mismatch(self):
        ciphertext = b"synthetic age ciphertext"
        raw = outer_zip(ciphertext)
        with patch.object(
            encrypted_backup.subprocess,
            "run",
            side_effect=AssertionError("age must not run before inner SHA passes"),
        ):
            with self.assertRaisesRegex(RuntimeError, "HOLD_INNER_CIPHERTEXT_SHA256"):
                encrypted_backup.restore_test(
                    raw,
                    Path("synthetic-identity"),
                    expected_outer_bytes=len(raw),
                    expected_outer_sha256=hashlib.sha256(raw).hexdigest(),
                    expected_ciphertext_sha256="0" * 64,
                )


if __name__ == "__main__":
    unittest.main()
