"""B03: diagnostic Setup candidate and published artifact must be byte-identical.

This is a SOURCE_ONLY test; it does not replace physical Windows E06/E07.
"""
from pathlib import Path
import unittest

BUILDER = Path(__file__).resolve().parents[2] / "coordination/e06/build_onehost_installer.ps1"

class CandidateIdentityTest(unittest.TestCase):
    def test_sha_bound_before_and_after_atomic_publish(self):
        s = BUILDER.read_text(encoding="utf-8-sig")
        candidate = "$candidateSha=(Get-FileHash -LiteralPath $setupCandidate -Algorithm SHA256).Hash.ToLowerInvariant()"
        move = "try { [IO.File]::Move($setupCandidate,$setup) }"
        published = "$sha=(Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()"
        comparison = "if ($sha -cne $candidateSha) { throw 'E06_SETUP_PUBLISHED_DIGEST_MISMATCH_HOLD' }"
        receipt = "installer_sha256=$sha;installer_bytes="
        for line in (candidate, move, published, comparison, receipt):
            self.assertEqual(s.count(line), 1, line)
        self.assertLess(s.index(candidate), s.index(move))
        self.assertLess(s.index(move), s.index(published))
        self.assertLess(s.index(published), s.index(comparison))
        self.assertLess(s.index(comparison), s.index(receipt))
        self.assertIn("E06_SETUP_CANDIDATE_SHA_HOLD", s)
        self.assertIn("E06_SETUP_ATOMIC_NO_OVERWRITE_HOLD", s)

if __name__ == "__main__":
    unittest.main()
