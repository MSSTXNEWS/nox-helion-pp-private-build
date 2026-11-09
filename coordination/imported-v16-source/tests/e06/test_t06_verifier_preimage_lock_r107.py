"""W01 R107: real unit checks for immutable archived R11 verifier admission.

Source-level only; never claims Windows installed smoke or E07.
"""
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "coordination/e06/t06_package_original_onehost.py"
APPROVED = ROOT / "stage/proposals/P01/C09/Installer/Verify-Payload.ps1"
ARCHIVE_SHA = "e741c131ddc1af45391ed64b4cdce686895aa78bd67e6bd4795fa97f548d455b"
APPROVED_BLOB = "2fe86cad7e96eaf1a67354dfce3cf3f96dd33dfa"


def read_module():
    spec = importlib.util.spec_from_file_location("nox_r107_stage_source", SOURCE)
    owner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owner)
    return owner


class ExactArchivedVerifierAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = read_module()
        cls.raw = APPROVED.read_bytes()
        canonical = cls.raw.replace(b"\r\n", b"\n")
        blob = hashlib.sha1(b"blob " + str(len(canonical)).encode() + b"\x00" + canonical).hexdigest()
        assert blob == APPROVED_BLOB, (blob, APPROVED_BLOB)
        cls.canonical = canonical

    def fixture(self, raw):
        scratch = tempfile.TemporaryDirectory()
        root = Path(scratch.name)
        archived = root/"R11/Installer/Verify-Payload.ps1"
        reviewed = root/"Approved/Installer/Verify-Payload.ps1"
        archived.parent.mkdir(parents=True)
        reviewed.parent.mkdir(parents=True)
        archived.write_bytes(raw)
        reviewed.write_bytes(self.raw)
        return scratch, archived, reviewed

    def test_pins_match_verified_physical_and_git_receipts(self):
        self.assertEqual(self.owner.P01_ARCHIVED_VERIFIER_SHA256, ARCHIVE_SHA)
        self.assertEqual(self.owner.P01_INSTALLED_VERIFIER_GIT_BLOB, APPROVED_BLOB)

    def test_untrusted_marker_compatible_original_refused_without_overwrite(self):
        marker = (b"# P01_PAYLOAD_VERIFY_FAILED payload.sha256.json SHA256\n" * 18)
        scratch, archived, reviewed = self.fixture(marker)
        with scratch:
            before = archived.read_bytes()
            with self.assertRaisesRegex(RuntimeError, "T06_P01_VERIFY_ARCHIVE_PREIMAGE_SHA_HOLD"):
                self.owner.stage_reviewed_installed_payload_verifier(archived, reviewed)
            self.assertEqual(archived.read_bytes(), before)

    def test_exact_mock_preimage_can_stage_and_read_back(self):
        marker = (b"# P01_PAYLOAD_VERIFY_FAILED payload.sha256.json SHA256\n" * 18)
        scratch, archived, reviewed = self.fixture(marker)
        with scratch:
            prior = self.owner.P01_ARCHIVED_VERIFIER_SHA256
            self.owner.P01_ARCHIVED_VERIFIER_SHA256 = hashlib.sha256(marker).hexdigest()
            try:
                receipt = self.owner.stage_reviewed_installed_payload_verifier(archived, reviewed)
                self.assertTrue(receipt["changed_disposable_R11"])
                self.assertFalse(receipt["release_accepted"])
                self.assertEqual(archived.read_bytes(), self.canonical)
            finally:
                self.owner.P01_ARCHIVED_VERIFIER_SHA256 = prior

    def test_marker_preserving_byte_change_is_fail_closed(self):
        marker = (b"# P01_PAYLOAD_VERIFY_FAILED payload.sha256.json SHA256\n" * 18)
        mutated = marker[:-1] + b"X"
        scratch, archived, reviewed = self.fixture(mutated)
        with scratch:
            prior = self.owner.P01_ARCHIVED_VERIFIER_SHA256
            self.owner.P01_ARCHIVED_VERIFIER_SHA256 = hashlib.sha256(marker).hexdigest()
            try:
                with self.assertRaisesRegex(RuntimeError, "T06_P01_VERIFY_ARCHIVE_PREIMAGE_SHA_HOLD"):
                    self.owner.stage_reviewed_installed_payload_verifier(archived, reviewed)
                self.assertEqual(archived.read_bytes(), mutated)
            finally:
                self.owner.P01_ARCHIVED_VERIFIER_SHA256 = prior

    def test_identical_approved_already_staged_is_idempotent(self):
        scratch, archived, reviewed = self.fixture(self.canonical)
        with scratch:
            before = archived.stat()
            receipt = self.owner.stage_reviewed_installed_payload_verifier(archived, reviewed)
            self.assertFalse(receipt["changed_disposable_R11"])
            self.assertEqual(archived.read_bytes(), self.canonical)
            self.assertEqual(archived.stat().st_mtime_ns, before.st_mtime_ns)


if __name__ == "__main__":
    unittest.main()
