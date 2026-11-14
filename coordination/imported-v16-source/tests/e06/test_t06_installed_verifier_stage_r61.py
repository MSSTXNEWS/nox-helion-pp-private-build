"""Original OneHost C09 installed verifier staging regression; NOT Windows E07."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"coordination/e06/t06_package_original_onehost.py"
APPROVED=ROOT/"stage/proposals/P01/C09/Installer/Verify-Payload.ps1"
spec=importlib.util.spec_from_file_location("t06_onehost_installed_verifier_r61",SOURCE)
owner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)


class OriginalInstalledVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        installer=Path(self.temp.name)/"Installer"
        installer.mkdir()
        self.staged=installer/"Verify-Payload.ps1"
        self.legacy=(b"# original P01 owner: P01_PAYLOAD_VERIFY_FAILED\n"
                     b"payload.sha256.json\nSHA256\n"+b"# old verifier\n"*50)
        self.staged.write_bytes(self.legacy)

    def tearDown(self):
        self.temp.cleanup()

    def test_c09_reviewed_bytes_staged_and_idempotent(self):
        first=owner.stage_reviewed_installed_payload_verifier(self.staged,APPROVED)
        raw=APPROVED.read_bytes().replace(b"\r\n",b"\n")
        self.assertEqual(owner._git_blob(raw),owner.P01_INSTALLED_VERIFIER_GIT_BLOB)
        self.assertEqual(self.staged.read_bytes(),raw)
        self.assertTrue(first["changed_disposable_R11"])
        self.assertTrue(first["installed_metadata_switch_pinned"])
        self.assertFalse(first["release_accepted"])
        self.assertFalse(owner.stage_reviewed_installed_payload_verifier(
            self.staged,APPROVED)["changed_disposable_R11"])

    def test_tampered_reviewed_file_rejected_without_overwriting_original(self):
        reviewed=Path(self.temp.name)/"tampered.ps1"
        reviewed.write_bytes(APPROVED.read_bytes()+b"\n# unreviewed change\n")
        with self.assertRaisesRegex(RuntimeError,"APPROVED_GIT_BLOB_HOLD"):
            owner.stage_reviewed_installed_payload_verifier(self.staged,reviewed)
        self.assertEqual(self.staged.read_bytes(),self.legacy)

    def test_unrecognized_original_rejected_without_overwrite(self):
        untrusted=b"# anonymous script\n"*90
        self.staged.write_bytes(untrusted)
        with self.assertRaisesRegex(RuntimeError,"ARCHIVED_SOURCE_UNRECOGNIZED_HOLD"):
            owner.stage_reviewed_installed_payload_verifier(self.staged,APPROVED)
        self.assertEqual(self.staged.read_bytes(),untrusted)

    def test_symlinked_stage_target_rejected(self):
        link=self.staged.parent/"redirect.ps1"
        try:
            link.symlink_to(self.staged)
        except (OSError,NotImplementedError):
            self.skipTest("symlinks unavailable; Windows reparse check remains runtime HOLD")
        with self.assertRaisesRegex(RuntimeError,"PATH_REPARSE_HOLD"):
            owner.stage_reviewed_installed_payload_verifier(link,APPROVED)

    def test_existing_nsis_packager_calls_verifier_before_build(self):
        source=SOURCE.read_text("utf-8")
        a=source.index("verifier_proof=stage_reviewed_installed_payload_verifier(")
        b=source.index('proof=subprocess.run(["powershell.exe"',a)
        c=source.index('args=[nsis,',b)
        self.assertLess(a,b)
        self.assertLess(b,c)
        self.assertIn('"installed_owner_verifier":verifier_proof',source)


if __name__=="__main__":
    unittest.main()
