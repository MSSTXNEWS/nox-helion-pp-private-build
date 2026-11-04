"""NX03 exact-source C07→reviewed C09 uninstall staging, NOT E07."""
from __future__ import annotations
import hashlib
import importlib.util
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT/"coordination/e06/nx03_reviewed_uninstall_stage.py"
spec = importlib.util.spec_from_file_location("nox_nx03_reviewed_remove", MODULE)
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)
DONOR = ROOT/"donors/P01_C07"
C09 = ROOT/"stage/proposals/P01/C09/Installer/Remove-InstalledPayload.ps1"


def frozen_c07_bytes():
    parts = [DONOR/f"P01_C07_{i:02d}.part" for i in range(28)]
    raw = b"".join(p.read_bytes() for p in parts)
    assert hashlib.sha256(raw).hexdigest() == (
        "90076eba83a213ba2b410632ced3288d41a6691ab63f81ad0520aa3cbbbfcb52")
    with ZipFile(BytesIO(raw)) as archive:
        return archive.read("R11/Installer/Remove-InstalledPayload.ps1")


class NX03ReviewedRemove(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = frozen_c07_bytes()
        cls.reviewed = C09.read_bytes()
    def setUp(self):
        t = tempfile.TemporaryDirectory(prefix="nox-nx03-nsis-")
        self.addCleanup(t.cleanup)
        self.temp = Path(t.name)
        self.owner = self.temp/"R11/Installer/Remove-InstalledPayload.ps1"
        self.copy = self.temp/"C09/Installer/Remove-InstalledPayload.ps1"
        self.owner.parent.mkdir(parents=True)
        self.copy.parent.mkdir(parents=True)
        self.owner.write_bytes(self.original)
        self.copy.write_bytes(self.reviewed)
    def test_exact_archive_and_reviewed_copy_staged_only(self):
        out = stage.stage_reviewed_remove(self.owner, self.copy)
        self.assertTrue(out["changed"])
        staged = self.owner.read_bytes()
        self.assertNotEqual(staged, self.reviewed.replace(b"\r\n", b"\n"))
        text = staged.decode("utf-8")
        self.assertEqual(text.count("Get-P01VerifiedSha256"), 2)
        self.assertNotIn("Get-FileHash", text)
        self.assertIn("[Security.Cryptography.SHA256]::Create()", text)
        self.assertIn("$actual = Get-P01VerifiedSha256 $Entry.Full", text)
        self.assertIn("PHASE 1", text)
        self.assertIn("PHASE 2", text)
        self.assertIn("PHASE 3", text)
        self.assertEqual(out["compatibility_scope"], "POWERSHELL51_DOTNET_SHA256_ONLY")
        self.assertEqual(out["staged_sha256"], hashlib.sha256(staged).hexdigest())
        self.assertEqual(self.copy.read_bytes(), self.reviewed)
        self.assertEqual(hashlib.sha256(self.original).hexdigest(), out["original_r11_sha256"])
        self.assertFalse(out["release_accepted"])
        self.assertEqual(out["independent_e07"], "NOT_RUN")
    def test_second_call_idempotent_no_rewrite(self):
        stage.stage_reviewed_remove(self.owner, self.copy)
        before = self.owner.read_bytes()
        result = stage.stage_reviewed_remove(self.owner, self.copy)
        self.assertFalse(result["changed"])
        self.assertEqual(self.owner.read_bytes(), before)
        self.assertEqual(result["compatibility_scope"], "POWERSHELL51_DOTNET_SHA256_ONLY")
    def test_partial_staged_script_not_accepted(self):
        staged = stage.stage_reviewed_remove(self.owner, self.copy)
        altered = self.owner.read_bytes().replace(
            b"Get-P01VerifiedSha256 $Entry.Full", b"Get-P01VerifiedSha256 $Entry.Bogus")
        self.assertNotEqual(self.owner.read_bytes(), altered)
        self.owner.write_bytes(altered)
        with self.assertRaisesRegex(stage.ReviewedRemoveHold, "UNKNOWN_R11_PREIMAGE"):
            stage.stage_reviewed_remove(self.owner, self.copy)
        self.assertEqual(self.owner.read_bytes(), altered)
        self.assertFalse(staged["release_accepted"])
    def test_reviewed_source_git_blob_intact_after_stage(self):
        original_reviewed = self.copy.read_bytes()
        stage.stage_reviewed_remove(self.owner, self.copy)
        self.assertEqual(self.copy.read_bytes(), original_reviewed)
        self.assertEqual(stage._blob(original_reviewed.replace(b"\r\n", b"\n")),
                         stage._REVIEWED_BLOB)
    def test_unknown_archived_owner_no_write(self):
        altered = (b"!" if self.original[:1] != b"!" else b"?") + self.original[1:]
        self.owner.write_bytes(altered)
        with self.assertRaisesRegex(stage.ReviewedRemoveHold,"UNKNOWN_R11_PREIMAGE"):
            stage.stage_reviewed_remove(self.owner,self.copy)
        self.assertEqual(self.owner.read_bytes(),altered)
    def test_modified_review_source_no_write(self):
        wrong = self.reviewed.replace(b"PHASE 2", b"PHASE X", 1)
        self.copy.write_bytes(wrong)
        with self.assertRaisesRegex(stage.ReviewedRemoveHold,"UNAPPROVED_BLOB"):
            stage.stage_reviewed_remove(self.owner,self.copy)
        self.assertEqual(self.owner.read_bytes(),self.original)
    def test_symlink_owner_fails_closed(self):
        outside = self.temp/"external.ps1"
        outside.write_bytes(self.original)
        self.owner.unlink()
        try:
            self.owner.symlink_to(outside)
        except (OSError,NotImplementedError):
            self.skipTest("No symlink permissions")
        with self.assertRaises(stage.ReviewedRemoveHold):
            stage.stage_reviewed_remove(self.owner,self.copy)
        self.assertEqual(outside.read_bytes(),self.original)


if __name__ == "__main__":
    unittest.main()
