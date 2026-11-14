"""Source-only PowerShell 5.1 BuildID regression for original E07 handoff.
This does NOT run Windows, the original installer, or independent installed E07.
"""
from pathlib import Path
import hashlib
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "coordination/e06/Emit-E07ImmutableHandoff.ps1"

def ps51_compatible(text):
    required = (
        "$e07Hasher=[Security.Cryptography.SHA256]::Create()",
        "$hash=$e07Hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($identity))",
        "$e07Hasher.Dispose()",
        "[BitConverter]::ToString($hash).Replace('-','').ToLowerInvariant().Substring(0,24)",
    )
    return (all(text.count(part) == 1 for part in required)
            and "::HashData(" not in text and "::ToHexString(" not in text
            and text.index("$e07Hasher=[Security.Cryptography.SHA256]::Create()")
               < text.index("$hash=$e07Hasher.ComputeHash(")
               < text.index("$e07Hasher.Dispose()")
               < text.index("$buildId='NOX-V16-'"))

class WindowsPowerShell51BuildID(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")

    def test_legacy_net_framework_hash_api(self):
        self.assertTrue(ps51_compatible(self.source))

    def test_mutant_net5_api_rejected(self):
        mutant = self.source.replace(
            "$hash=$e07Hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($identity))",
            "$hash=[Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($identity))",
            1)
        self.assertFalse(ps51_compatible(mutant))

    def test_mutant_hex_conversion_rejected(self):
        mutant = self.source.replace("[BitConverter]::ToString($hash)",
                                     "[Convert]::ToHexString($hash)", 1)
        self.assertFalse(ps51_compatible(mutant))

    def test_immutable_identity_and_acceptance_kept(self):
        for marker in (
            '$identity="$($source.zip_sha256)|$commit|$setupSha|$exeSha"',
            "E07_BUILD_INPUT_MUTATED_DURING_HANDOFF",
            "E07_OWNER_SOURCE_PART_IDENTITY_MISMATCH",
            "E07_CHECKOUT_SHA_DRIFT_BEFORE_SEAL",
            "independent_e07_cases_accepted=0",
            "release_accepted=$false",
        ):
            self.assertIn(marker, self.source)

    def test_same_sha256_build_id_as_prior_algorithm(self):
        zip_sha = "ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a"
        head = "7b97487ecfb0a797ea12ab5a0c19fa9786eeb959"
        identity = "|".join((zip_sha, head, "a" * 64, "b" * 64))
        self.assertEqual("NOX-V16-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
                         "NOX-V16-fe537bb7c08ab79587d752df")

if __name__ == "__main__":
    unittest.main()
