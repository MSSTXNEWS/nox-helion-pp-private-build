"""R11 HOME source/payload SHA provenance; never a substitute for installed UIA."""
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location(
    "nox_t06_home_packaging", ROOT/"coordination/e06/t06_package_original_onehost.py")
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class TestR11HomeSourceAndPayload(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root=Path(directory.name)
        self.original=self.root/"index-original.html"
        self.published=self.root/"index-payload.html"
        self.original.write_bytes(b"home" * (94908//4))
        self.published.write_bytes(self.original.read_bytes())
        pin=hashlib.sha256(self.original.read_bytes()).hexdigest()
        anchor=patch.object(MOD,"HOME_R11_EXPECTED_SHA256",pin)
        anchor.start()
        self.addCleanup(anchor.stop)

    def test_pinned_original_staged_without_claiming_gui_pass(self):
        proof=MOD.attest_original_home_provenance(self.original,self.published)
        self.assertTrue(proof["published_equals_original"])
        self.assertEqual(proof["original_home_bytes"],94908)
        self.assertEqual(proof["five_primary_installed_uia"],"NOT_RUN")
        self.assertFalse(proof["release_accepted"])

    def test_changed_same_byte_length_original_fails_closed(self):
        self.original.write_bytes(b"x"*94908)
        with self.assertRaisesRegex(RuntimeError,"T06_ORIGINAL_HOME_PIN_HOLD"):
            MOD.attest_original_home_provenance(self.original,self.published)

    def test_truncated_original_fails_closed(self):
        self.original.write_bytes(b"short")
        with self.assertRaisesRegex(RuntimeError,"T06_ORIGINAL_HOME_BYTES_HOLD"):
            MOD.attest_original_home_provenance(self.original,self.published)

    def test_modified_published_home_gets_distinct_digest_not_fake_pass(self):
        self.published.write_bytes(b"approved stage not proved by this test")
        proof=MOD.attest_original_home_provenance(self.original,self.published)
        self.assertFalse(proof["published_equals_original"])
        self.assertNotEqual(proof["published_home_sha256"],proof["original_home_sha256"])
        self.assertFalse(proof["release_accepted"])

    def test_source_symlink_refused(self):
        self.original.unlink()
        self.original.symlink_to(self.published)
        with self.assertRaisesRegex(RuntimeError,"T06_ORIGINAL_HOME_REGULAR_FILE_HOLD"):
            MOD.attest_original_home_provenance(self.original,self.published)

    def test_published_symlink_refused(self):
        self.published.unlink()
        self.published.symlink_to(self.original)
        with self.assertRaisesRegex(RuntimeError,"T06_PUBLISHED_HOME_REGULAR_FILE_HOLD"):
            MOD.attest_original_home_provenance(self.original,self.published)


if __name__=="__main__":
    unittest.main()
