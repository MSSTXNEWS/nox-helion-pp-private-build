"""Focused fake-provider tests for the additive read-only Drive boundary."""
from __future__ import annotations

import hashlib
import unittest

from nox_drive_readonly import DriveReadHold, ReadOnlyDriveSidecar


OWNER = "persona-owner-nox"
READER = "persona-nox-memory"
FILE_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz"
FOLDER_ID = "1FolderAbCdEfGhIjKlMnOpQrStUvW"
REVISION_ID = "rev-17"
PAYLOAD = b"Complete fixture payload; never truncated."


def allowlist(**file_overrides):
    file_spec = {
        "file_id": FILE_ID,
        "parent_folder_id": FOLDER_ID,
        "revision_id": REVISION_ID,
        "mime_type": "text/plain",
        "size_bytes": len(PAYLOAD),
        "max_size_bytes": len(PAYLOAD),
        "sha256": hashlib.sha256(PAYLOAD).hexdigest(),
        "persona_ids": [READER],
    }
    file_spec.update(file_overrides)
    return {
        "schema_version": 1,
        "owner_persona_id": OWNER,
        "folders": [{"folder_id": FOLDER_ID}],
        "files": [file_spec],
    }


def metadata(**overrides):
    value = {
        "file_id": FILE_ID,
        "parent_folder_id": FOLDER_ID,
        "revision_id": REVISION_ID,
        "mime_type": "text/plain",
        "size_bytes": len(PAYLOAD),
    }
    value.update(overrides)
    return value


class FakeProvider:
    def __init__(self, metadata_value=None, content=PAYLOAD, error=None):
        self.metadata_value = metadata_value if metadata_value is not None else metadata()
        self.content = content
        self.error = error
        self.calls = []

    def read_revision(self, *, file_id, revision_id, max_bytes):
        self.calls.append((file_id, revision_id, max_bytes))
        if self.error:
            raise RuntimeError("Bearer secret-fixture-that-must-not-leak")
        return self.metadata_value, self.content


class ReadOnlyDriveSidecarTests(unittest.TestCase):
    def test_exact_revision_returns_full_content_and_persona_provenance(self):
        provider = FakeProvider()
        result = ReadOnlyDriveSidecar(
            provider=provider, allowlist=allowlist()
        ).read(file_id=FILE_ID, persona_id=READER)

        self.assertEqual(result.content, PAYLOAD)
        self.assertEqual(
            provider.calls,
            [(FILE_ID, REVISION_ID, len(PAYLOAD))],
        )
        self.assertEqual(result.owner_persona_id, OWNER)
        self.assertEqual(result.persona_ids, (READER,))
        self.assertEqual(result.file_id, FILE_ID)
        self.assertEqual(result.parent_folder_id, FOLDER_ID)
        self.assertEqual(result.revision_id, REVISION_ID)
        self.assertEqual(result.mime_type, "text/plain")
        self.assertEqual(result.size_bytes, len(PAYLOAD))
        self.assertEqual(result.sha256, hashlib.sha256(PAYLOAD).hexdigest())
        self.assertEqual(
            result.citation_url,
            f"https://drive.google.com/file/d/{FILE_ID}/view",
        )

    def test_absent_provider_or_allowlist_holds_without_provider_io(self):
        fake = FakeProvider()
        with self.assertRaisesRegex(DriveReadHold, "HOLD_DRIVE_PROVIDER_MISSING"):
            ReadOnlyDriveSidecar(provider=None, allowlist=allowlist()).read(
                file_id=FILE_ID, persona_id=READER
            )
        with self.assertRaisesRegex(DriveReadHold, "HOLD_DRIVE_ALLOWLIST_MISSING"):
            ReadOnlyDriveSidecar(provider=fake, allowlist=None).read(
                file_id=FILE_ID, persona_id=READER
            )
        self.assertEqual(fake.calls, [])

    def test_unknown_file_id_and_arbitrary_remote_are_denied_before_provider(self):
        provider = FakeProvider()
        sidecar = ReadOnlyDriveSidecar(provider=provider, allowlist=allowlist())
        for value, code in (
            ("1NotAllowlistedFileId123456", "DENY_DRIVE_FILE_NOT_ALLOWLISTED"),
            ("noxdrive:folder/model.gguf", "HOLD_DRIVE_FILE_ID_INVALID"),
            ("https://drive.google.com/file/d/" + FILE_ID, "HOLD_DRIVE_FILE_ID_INVALID"),
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(DriveReadHold, code):
                    sidecar.read(file_id=value, persona_id=READER)
        self.assertEqual(provider.calls, [])

    def test_persona_not_in_exact_persona_allowlist_is_denied(self):
        provider = FakeProvider()
        with self.assertRaisesRegex(DriveReadHold, "DENY_DRIVE_PERSONA_NOT_ALLOWLISTED"):
            ReadOnlyDriveSidecar(provider=provider, allowlist=allowlist()).read(
                file_id=FILE_ID, persona_id="persona-other-reader"
            )
        self.assertEqual(provider.calls, [])

    def test_parent_revision_or_mime_mismatch_holds(self):
        cases = (
            (metadata(parent_folder_id="1OtherFolderAbCdEfGhIjKlMnOpQ"), "HOLD_DRIVE_PARENT_FOLDER_MISMATCH"),
            (metadata(revision_id="rev-18"), "HOLD_DRIVE_REVISION_MISMATCH"),
            (metadata(mime_type="application/pdf"), "HOLD_DRIVE_MIME_TYPE_MISMATCH"),
        )
        for bad_metadata, code in cases:
            with self.subTest(code=code):
                provider = FakeProvider(metadata_value=bad_metadata)
                with self.assertRaisesRegex(DriveReadHold, code):
                    ReadOnlyDriveSidecar(provider=provider, allowlist=allowlist()).read(
                        file_id=FILE_ID, persona_id=READER
                    )

    def test_byte_size_and_digest_mismatches_hold_without_truncation(self):
        cases = (
            (metadata(size_bytes=len(PAYLOAD) - 1), PAYLOAD, "HOLD_DRIVE_SIZE_MISMATCH"),
            (metadata(), PAYLOAD[:-1], "HOLD_DRIVE_SIZE_MISMATCH"),
            (metadata(), PAYLOAD + b"x", "HOLD_DRIVE_PROVIDER_SIZE_EXCEEDED"),
            (metadata(), b"x" * len(PAYLOAD), "HOLD_DRIVE_SHA256_MISMATCH"),
        )
        for bad_metadata, bad_content, code in cases:
            with self.subTest(code=code):
                provider = FakeProvider(metadata_value=bad_metadata, content=bad_content)
                with self.assertRaisesRegex(DriveReadHold, code):
                    ReadOnlyDriveSidecar(provider=provider, allowlist=allowlist()).read(
                        file_id=FILE_ID, persona_id=READER
                    )

    def test_provider_exception_text_is_not_exposed(self):
        provider = FakeProvider(error=True)
        with self.assertRaisesRegex(DriveReadHold, "HOLD_DRIVE_PROVIDER_READ_FAILED") as caught:
            ReadOnlyDriveSidecar(provider=provider, allowlist=allowlist()).read(
                file_id=FILE_ID, persona_id=READER
            )
        self.assertNotIn("secret-fixture", str(caught.exception))

    def test_allowlist_requires_exact_parent_and_rejects_extra_fields(self):
        with self.assertRaisesRegex(DriveReadHold, "HOLD_DRIVE_PARENT_FOLDER_NOT_ALLOWLISTED"):
            ReadOnlyDriveSidecar(
                provider=FakeProvider(),
                allowlist=allowlist(parent_folder_id="1OtherFolderAbCdEfGhIjKlMnOpQ"),
            ).read(file_id=FILE_ID, persona_id=READER)
        with self.assertRaisesRegex(DriveReadHold, "HOLD_DRIVE_FILE_SCHEMA"):
            ReadOnlyDriveSidecar(
                provider=FakeProvider(),
                allowlist=allowlist(remote="arbitrary:path"),
            ).read(file_id=FILE_ID, persona_id=READER)


if __name__ == "__main__":
    unittest.main()
