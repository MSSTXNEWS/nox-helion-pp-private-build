"""Source-level regression for exact original three-part receipt equality.

E06 checks two independent manifests before producing a BUILT E07 handoff.
This is a read-only source contract test, not original raw ZIP or Windows E2E.
Run: python -m unittest discover -s tests/e06 -p 'test_e07_source_part_identity_r14.py' -v
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
HANDOFF = ROOT / "coordination/e06/Emit-E07ImmutableHandoff.ps1"
AZURE = ROOT / "azure-pipelines-nox-v16.yml"


class E07OriginalPartIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = HANDOFF.read_text(encoding="utf-8")
        cls.azure = AZURE.read_text(encoding="utf-8")
        marker = "foreach ($expected in @($source.parts)) {"
        if cls.code.count(marker) != 1:
            raise AssertionError("E07_CANONICAL_PART_LOOP_MISSING_OR_DUPLICATED")
        cls.part_gate = cls.code.split(marker, 1)[1].split("\nif ($onehost.schema", 1)[0]

    def test_owner_receipt_is_an_independent_required_input(self):
        self.assertIn("[Parameter(Mandatory=$true)][string]$Owner729Receipt", self.code)
        self.assertIn("nox-original-729-owner-pinned.json", self.azure)

    def test_three_exact_part_names_and_sizes_already_compared(self):
        self.assertIn("$_.path -ceq $expected.name -and $_.bytes -eq $expected.bytes",
                      self.part_gate)
        self.assertIn("$matching.Count -ne 1", self.part_gate)

    def test_both_sha256_hex_formats_are_required(self):
        self.assertIn("([string]$matching[0].sha256) -cnotmatch '^[0-9a-f]{64}$'",
                      self.part_gate)
        self.assertIn("([string]$expected.sha256) -cnotmatch '^[0-9a-f]{64}$'",
                      self.part_gate)

    def test_real_sha256_value_must_match_not_only_format(self):
        self.assertIn(
            "([string]$matching[0].sha256).ToLowerInvariant() -cne "
            "([string]$expected.sha256).ToLowerInvariant()", self.part_gate)

    def test_both_git_blob_ids_and_values_must_match(self):
        self.assertIn("([string]$expected.git_blob_sha1) -cnotmatch '^[0-9a-f]{40}$'",
                      self.part_gate)
        self.assertIn(
            "([string]$matching[0].gitBlobSha1).ToLowerInvariant() -cne "
            "([string]$expected.git_blob_sha1).ToLowerInvariant()", self.part_gate)

    def test_729_member_file_parity_remains(self):
        self.assertIn("E07_OWNER_729_FILE_SHA_DIFFERS", self.code)
        self.assertIn("E07_OWNER_729_FILE_SET_INCOMPLETE", self.code)

    def test_forged_receipt_fails_closed_and_no_release_promotion(self):
        self.assertIn("E07_OWNER_SOURCE_PART_IDENTITY_MISMATCH", self.part_gate)
        self.assertIn("independent_e07_cases_accepted=0", self.code)
        self.assertIn("release_accepted=$false", self.code)
        self.assertIn("PENDING_E07_INDEPENDENT_SAME_SHA_QA", self.code)


if __name__ == "__main__":
    unittest.main()
