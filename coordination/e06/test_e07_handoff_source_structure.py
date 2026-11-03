"""Source-only guard for the immutable E06->E07 release handoff script.

This protects against duplicate/truncated PowerShell blocks during edits.
It does not replace Windows runtime, E07 acceptance or archive rehashing.
"""
from pathlib import Path
import unittest

SCRIPT = (Path(__file__).resolve().parent / "Emit-E07ImmutableHandoff.ps1")


class HandoffSourceStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_single_immutable_handoff(self):
        for token in (
            "[CmdletBinding()]",
            "function FileSha(",
            "$identity=",
            "$receipt=[ordered]@{",
            "Write-Host \"E07_BUILDID_SEALED",
        ):
            with self.subTest(token=token):
                self.assertEqual(self.source.count(token), 1)

    def test_all_three_parts_are_checked_by_value(self):
        self.assertIn("foreach ($expected in @($source.parts))", self.source)
        self.assertIn("if ($matching.Count -ne 1 -or", self.source)
        self.assertIn(
            "([string]$matching[0].sha256).ToLowerInvariant() -cne ([string]$expected.sha256).ToLowerInvariant()",
            self.source,
        )
        self.assertIn(
            "([string]$matching[0].gitBlobSha1).ToLowerInvariant() -cne ([string]$expected.git_blob_sha1).ToLowerInvariant()",
            self.source,
        )

    def test_no_truncated_regex_or_duplicated_trailing_blocks(self):
        self.assertNotIn("'^[0-9a-f]{64}\n}", self.source)
        self.assertNotIn("'^[0-9a-f]{40}\n}", self.source)
        self.assertEqual(self.source.count("E07_BUILD_INPUT_MUTATED_DURING_HANDOFF"), 1)
        self.assertEqual(self.source.count("E07_HANDOFF_READBACK_DRIFT"), 1)

    def test_release_acceptance_is_not_faked(self):
        self.assertIn("independent_e07_cases_accepted=0", self.source)
        self.assertIn("release_accepted=$false", self.source)
        self.assertIn("source_receipts_729_parity_verified=$true", self.source)


if __name__ == "__main__":
    unittest.main()
