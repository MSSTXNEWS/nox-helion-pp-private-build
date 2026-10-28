"""Independent source-only E07 guard: reject mutilated PowerShell handoff scripts.

E07 ownership: tests only, no runtime installation or release acceptance.
Run: python -m unittest discover -s qa/e07 -p 'test_handoff_immutable_source_contract.py' -v
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
HANDOFF = ROOT / "coordination/e06/Emit-E07ImmutableHandoff.ps1"
CANONICAL = ROOT / "coordination/source-lock/verify_original_archive.py"

SEAL = 'Write-Host "E07_BUILDID_SEALED'
PART_EQUALS_SHA = "([string]$matching[0].sha256).ToLowerInvariant() -cne ([string]$expected.sha256).ToLowerInvariant()"
PART_EQUALS_GIT = "([string]$matching[0].gitBlobSha1).ToLowerInvariant() -cne ([string]$expected.git_blob_sha1).ToLowerInvariant()"
EXPECTED_REGEX_SHA = "-cnotmatch '^[0-9a-f]{64}$'"
EXPECTED_REGEX_GIT = "-cnotmatch '^[0-9a-f]{40}$'"

def check_handoff(ps: str, source_py: str) -> None:
    if ps.count(SEAL) != 1:
        raise ValueError("E07_DUPLICATE_OR_MISSING_SEAL")
    for token in (
        "$identity=", "if ($onehost.schema", "foreach ($expected in @($source.parts))",
        "if ($matching.Count -ne 1 -or", "if ($Phase -ceq 'INSTALLED')",
        "E07_HANDOFF_READBACK_DRIFT",
    ):
        if ps.count(token) != 1:
            raise ValueError("E07_DUPLICATED_OR_MISSING_" + token)
    if ps.count(PART_EQUALS_SHA) != 1 or ps.count(PART_EQUALS_GIT) != 1:
        raise ValueError("E07_PART_SHA_OR_GIT_PARITY_MISSING")
    if ps.count(EXPECTED_REGEX_SHA) < 3 or ps.count(EXPECTED_REGEX_GIT) < 2:
        raise ValueError("E07_PART_DIGEST_FORMAT_GATE_MISSING")
    if ps.count("independent_e07_cases_accepted=0") != 1 or ps.count("release_accepted=$false") != 1:
        raise ValueError("E07_FALSE_RELEASE_PASS")
    if re.search(r"-cnotmatch '\^\[0-9a-f\]\{(?:40|64)\}(?!\$')", ps):
        raise ValueError("E07_TRUNCATED_DIGEST_REGEX")
    if "git_blob_sha1" not in source_py or '"sha256": part_sha256.hexdigest()' not in source_py:
        raise ValueError("E07_CANONICAL_SOURCE_RECEIPT_SCHEMA_MISMATCH")
    if ps.count("E07_BUILDID_SEALED") != 1:
        raise ValueError("E07_DUPLICATED_FINAL_TAIL")

class ImmutableHandoffSourceTests(unittest.TestCase):
    def setUp(self):
        self.source = (
            'part_receipts.append({"name": p.name, "bytes": sizes[index], '
            '"git_blob_sha1": actual_part_blob, '
            '"sha256": part_sha256.hexdigest()})'
        )
        self.good = "\n".join([
            'param([string]$Owner729Receipt)',
            "foreach ($expected in @($source.parts)) {",
            " if ($matching.Count -ne 1 -or",
            "  ([string]$matching[0].sha256) -cnotmatch '^[0-9a-f]{64}$' -or",
            "  ([string]$expected.sha256) -cnotmatch '^[0-9a-f]{64}$' -or",
            "  ([string]$matching[0].gitBlobSha1) -cnotmatch '^[0-9a-f]{40}$' -or",
            "  ([string]$expected.git_blob_sha1) -cnotmatch '^[0-9a-f]{40}$' -or",
            "  ([string]$matching[0].sha256) -cnotmatch '^[0-9a-f]{64}$' -or",
            "  ([string]$expected.sha256) -cnotmatch '^[0-9a-f]{64}$' -or",
            "  ([string]$matching[0].gitBlobSha1) -cnotmatch '^[0-9a-f]{40}$' -or",
            "  ([string]$expected.git_blob_sha1) -cnotmatch '^[0-9a-f]{40}$') {",
            " }",
            PART_EQUALS_SHA,
            PART_EQUALS_GIT,
            "$identity='source|commit|setup|exe'",
            "if ($onehost.schema) { }",
            "if ($Phase -ceq 'INSTALLED') { }",
            "E07_HANDOFF_READBACK_DRIFT",
            "independent_e07_cases_accepted=0",
            "release_accepted=$false",
            SEAL + ' $buildId"',
        ])

    def test_valid_fixture(self):
        check_handoff(self.good, self.source)

    def test_duplicate_tail_rejected(self):
        with self.assertRaises(ValueError):
            check_handoff(self.good + "\n" + SEAL + ' $buildId"', self.source)

    def test_missing_sha_equality_rejected(self):
        with self.assertRaises(ValueError):
            check_handoff(self.good.replace(PART_EQUALS_SHA, ""), self.source)

    def test_missing_git_equality_rejected(self):
        with self.assertRaises(ValueError):
            check_handoff(self.good.replace(PART_EQUALS_GIT, ""), self.source)

    def test_corrupted_regex_rejected(self):
        bad = self.good.replace("-cnotmatch '^[0-9a-f]{64}$'", "-cnotmatch '^[0-9a-f]{64}", 1)
        with self.assertRaises(ValueError):
            check_handoff(bad, self.source)

    def test_release_flag_tampering_rejected(self):
        with self.assertRaises(ValueError):
            check_handoff(self.good.replace("release_accepted=$false", "release_accepted=$true"), self.source)

    def test_missing_canonical_sha_field_rejected(self):
        with self.assertRaises(ValueError):
            check_handoff(self.good, self.source.replace('"sha256": part_sha256.hexdigest()', ""))

    def test_actual_checked_out_files(self):
        if not (HANDOFF.is_file() and CANONICAL.is_file()):
            self.skipTest("Git checkout absent; synthetic regressions still run")
        check_handoff(HANDOFF.read_text(encoding="utf-8"),
                      CANONICAL.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
