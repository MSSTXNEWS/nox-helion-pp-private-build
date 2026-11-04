"""Exact C09 original NSIS PowerShell 5.1 compatibility; not Windows E07."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[2]
SOURCE=REPO/"coordination/e06/t06_package_original_onehost.py"
C09=REPO/"stage/proposals/P01/C09/Installer/Verify-Payload.ps1"
spec=importlib.util.spec_from_file_location("t06_r129_source",SOURCE)
owner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)

class StagedPS51(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir=Path(self.temp.name)/"R11"/"Installer"
        self.dir.mkdir(parents=True)
        self.path=self.dir/"Verify-Payload.ps1"
        self.approved=C09.read_bytes()
        self.assertEqual(owner._git_blob(self.approved),owner.P01_INSTALLED_VERIFIER_GIT_BLOB)
        self.path.write_bytes(self.approved)

    def test_real_c09_transform_preserves_policy(self):
        receipt=owner.stage_reviewed_ps51_sha_compat(self.path)
        raw=self.path.read_bytes()
        self.assertEqual(receipt["staged_sha256"],hashlib.sha256(raw).hexdigest())
        self.assertFalse(receipt["release_accepted"])
        self.assertIn(b"[Security.Cryptography.SHA256]::Create()",raw)
        self.assertIn(b"Get-P01VerifiedSha256 $full",raw)
        self.assertNotIn(b"Get-FileHash",raw)
        for item in (b"Assert-NoReparseAncestors",b"Assert-P01UniqueManifestMembers",
                     b"P01_PAYLOAD_VERIFY_FAILED",b"sha mismatch",b"[switch]$AllowInstalledMetadata"):
            self.assertIn(item,raw)
        self.assertEqual(C09.read_bytes(),self.approved)

    def test_policy_drift_fails_without_write(self):
        altered=self.approved.replace(b"Assert-NoReparseAncestors",b"NoAncestorSecurity",1)
        self.path.write_bytes(altered)
        with self.assertRaisesRegex(RuntimeError,"UNAPPROVED_PREIMAGE"):
            owner.stage_reviewed_ps51_sha_compat(self.path)
        self.assertEqual(self.path.read_bytes(),altered)

    def test_second_transform_refused_without_write(self):
        owner.stage_reviewed_ps51_sha_compat(self.path)
        snapshot=self.path.read_bytes()
        with self.assertRaisesRegex(RuntimeError,"UNAPPROVED_PREIMAGE"):
            owner.stage_reviewed_ps51_sha_compat(self.path)
        self.assertEqual(snapshot,self.path.read_bytes())

    def test_reparse_leaf_refused(self):
        outside=Path(self.temp.name)/"outside.ps1"
        outside.write_bytes(self.approved)
        self.path.unlink()
        self.path.symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError,"UNSAFE_PATH"):
            owner.stage_reviewed_ps51_sha_compat(self.path)
        self.assertEqual(outside.read_bytes(),self.approved)

    def test_reparse_ancestor_refused(self):
        other=Path(self.temp.name)/"outside"/"Installer"
        other.mkdir(parents=True)
        target=other/"Verify-Payload.ps1"
        target.write_bytes(self.approved)
        alias=Path(self.temp.name)/"alias"
        alias.symlink_to(other,target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError,"UNSAFE_PATH"):
            owner.stage_reviewed_ps51_sha_compat(alias/"Verify-Payload.ps1")
        self.assertEqual(target.read_bytes(),self.approved)

if __name__=="__main__":
    unittest.main()
