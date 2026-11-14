"""W10 R105: only review-gated C09 installed metadata mode enters disposable R11.
Source-only test; real PowerShell5.1 /S, update, rollback and E07 require Windows.
"""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "coordination/e06/build_onehost_installer.ps1"
C09 = ROOT / "stage/proposals/P01/C09/Installer/Verify-Payload.ps1"
BEGIN = "# W10 R105: original R11 SHA-locked verifier lacks installed-metadata mode."
END = "# W01 R102: only the disposable SHA-verified original R11 verifier is adapted."
C09_BLOB = "2fe86cad7e96eaf1a67354dfce3cf3f96dd33dfa"
OLD_SHA256 = "e741c131ddc1af45391ed64b4cdce686895aa78bd67e6bd4795fa97f548d455b"


class ReviewedInstalledVerifierStage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = BUILD.read_text(encoding="utf-8")
        cls.c09 = C09.read_text(encoding="utf-8")
        cls.block = cls.builder.split(BEGIN, 1)[1].split(END, 1)[0]

    def test_one_explicit_stage_before_existing_compat_and_nsis(self):
        self.assertEqual(self.builder.count(BEGIN), 1)
        self.assertEqual(self.builder.count(END), 1)
        self.assertLess(self.builder.index(BEGIN), self.builder.index(END))
        self.assertLess(self.builder.index(END), self.builder.index("& $makensisPath"))
        self.assertEqual(self.block.count("[IO.File]::Copy($reviewedVerifier,$originalStagedVerifier,$true)"), 1)

    def test_reviewed_source_git_blob_is_current(self):
        result = subprocess.run(["git", "-C", str(ROOT), "hash-object", "--", str(C09)],
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip().lower(), C09_BLOB)
        self.assertIn(C09_BLOB, self.block)

    def test_old_r11_preimage_must_match_physical_native_receipt(self):
        self.assertIn(OLD_SHA256, self.block)
        self.assertIn("P01_C09_ORIGINAL_R11_PREIMAGE_SHA_HOLD", self.block)
        self.assertIn("P01_C09_APPROVED_VERIFIER_BLOB_HOLD", self.block)
        self.assertIn("P01_C09_DISPOSABLE_VERIFIER_READBACK_HOLD", self.block)
        self.assertIn("Get-FileHash -LiteralPath $originalStagedVerifier", self.block)
        self.assertIn("Get-FileHash -LiteralPath $reviewedVerifier", self.block)

    def test_reused_c09_is_strict_original_not_a_new_verifier(self):
        for marker in ("[switch]$AllowInstalledMetadata", "Assert-P01UniqueManifestMembers",
                       "Assert-NoReparseAncestors", "invalid backup ownership marker",
                       "file count mismatch", "sha mismatch", "Uninstall.exe",
                       "duplicate JSON member"):
            self.assertIn(marker, self.c09)
            if marker != "duplicate JSON member":
                self.assertIn(marker, self.block)
        self.assertIn("P01_C09_APPROVED_VERIFIER_CONTRACT_HOLD", self.block)

    def test_no_weakening_or_mutation_of_original_archive(self):
        for forbidden in ("source_00.part", "source_01.part", "source_02.part",
                          "Set-ExecutionPolicy", "SetErrorLevel", "release_accepted=$true",
                          "Remove-Item", "IncludeMega814"):
            self.assertNotIn(forbidden, self.block)
        self.assertIn("Assert-E06PlainPathAncestors", self.block)
        self.assertIn("[IO.FileAttributes]::ReparsePoint", self.block)
        self.assertIn("ORIGINAL_SHA_CHECK_RETAINED", self.builder)

    def test_existing_r102_hash_transform_independent_and_unchanged(self):
        after = self.builder.split(END, 1)[1]
        self.assertIn("P01_PS51_DOTNET_SHA256_STAGED", after)
        self.assertIn("Get-P01VerifiedSha256 $full", after)
        self.assertNotIn("-AllowInstalledMetadata",
                         after.split("& powershell.exe -NoProfile -NonInteractive", 1)[0])
        self.assertIn("C11_NSIS_ROLLBACK_OLD_PAYLOAD_SHA_GATE_STAGED", after)


if __name__ == "__main__":
    unittest.main()
