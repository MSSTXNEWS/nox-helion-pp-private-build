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
        self.assertEqual(self.owner.read_bytes(), self.reviewed.replace(b"\r\n", b"\n"))
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
