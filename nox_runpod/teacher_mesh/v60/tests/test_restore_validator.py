"""Synthetic V60 archive validation. No key, age, SSH, OneHost or production DB."""
from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import tarfile
import unittest
import zipfile
from unittest.mock import patch

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


def plaintext_tar(*, corrupt_db: bool = False, traversal_manifest: bool = False) -> bytes:
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
    with tarfile.open(fileobj=result, mode="w:gz") as archive:
        for name, data in sorted(rows.items()):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(data))
        encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        info = tarfile.TarInfo(validator.MANIFEST_NAME)
        info.size = len(encoded)
        info.mtime = 0
        archive.addfile(info, io.BytesIO(encoded))
    return result.getvalue()


def outer_zip(ciphertext: bytes, name: str = validator.INNER_CIPHERTEXT_NAME) -> bytes:
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(name, ciphertext)
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


if __name__ == "__main__":
    unittest.main()
