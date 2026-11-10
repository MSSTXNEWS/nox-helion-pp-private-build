"""Strict source/fixture contract for the existing original NSIS verifier compatibility stage.
Source-only on Linux; actual PowerShell 5.1 hash/NSIS install must run on Windows E06.
"""
import re
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BUILD=ROOT/'coordination/e06/build_onehost_installer.ps1'
BEGIN='# W01 R102: only the disposable SHA-verified original R11 verifier is adapted.'
END="& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $installer 'Verify-Payload.ps1') -Root $payload -Manifest $manifestPath"
class StrictOriginalHashCompat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=BUILD.read_text(encoding='utf-8')
        cls.block=cls.source.split(BEGIN,1)[1].split(END,1)[0]
    def test_original_pipeline_wires_single_bounded_stage(self):
        self.assertEqual(self.source.count(BEGIN),1)
        self.assertEqual(self.source.count(END),1)
        self.assertLess(self.source.index(BEGIN),self.source.index(END))
        self.assertIn("Join-Path $installer 'Verify-Payload.ps1'",self.block)
        self.assertIn("Assert-E06PlainPathAncestors -Candidate $verifierPath",self.block)
        self.assertIn("P01_VERIFIER_COMPAT_ORIGINAL_PREIMAGE_HOLD",self.block)
    def test_exact_single_source_call_never_bypasses_sha_or_reparse(self):
        for marker in ("$oldHash='  $actual = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()'",
                       "Get-P01VerifiedSha256 $full","P01_PAYLOAD_VERIFY_FAILED",
                       "Assert-NoReparseAncestors","sha mismatch", "SOURCE_SHA_CHECK_RETAINED"):
            if marker == "SOURCE_SHA_CHECK_RETAINED": marker="ORIGINAL_SHA_CHECK_RETAINED"
            self.assertIn(marker,self.block)
        self.assertIn('Count -ne 1',self.block)
        self.assertNotIn('Set-ExecutionPolicy',self.block)
    def test_real_streaming_dotnet_sha256_disposal_and_readback(self):
        for marker in ("[IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)",
                       "[Security.Cryptography.SHA256]::Create()",
                       "$digest.ComputeHash($inputStream)",
                       "$digest.Dispose()","$inputStream.Dispose()",
                       "P01_VERIFIER_COMPAT_WRITE_READBACK_HOLD"):
            self.assertIn(marker,self.block)
        self.assertNotIn('ReadAllBytes($Path)',self.block)
    def test_no_full_source_archive_mutation_or_security_bypass(self):
        for forbidden in ('source_00.part','source_01.part','source_02.part',
                          'SetErrorLevel 0','-AllowInstalledMetadata','release_accepted=$true',
                          'ContinueOnError','Remove-Item -Recurse'):
            self.assertNotIn(forbidden,self.block)
        self.assertIn("$verifierBefore.Contains('Get-P01VerifiedSha256')",self.block)
        self.assertIn("$verifierAfter.Contains($oldHash)",self.block)
        self.assertIn("$verifierAfter,'Get-P01VerifiedSha256')).Count -ne 2",self.block)
    def test_stage_keeps_existing_windows_hash_before_and_after(self):
        self.assertEqual(self.block.count('Get-FileHash -LiteralPath $verifierPath -Algorithm SHA256'),2)
        self.assertIn("P01_PS51_DOTNET_SHA256_STAGED",self.block)
        self.assertEqual(self.block.count("Get-P01VerifiedSha256([string]$Path)"),1)
if __name__=='__main__': unittest.main()
