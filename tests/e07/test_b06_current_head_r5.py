"""B06 R5: only current PR162 verifier can admit one immutable Setup SHA.

SOURCE_ONLY. No install, model download or physical E07 is performed.
"""
from pathlib import Path
import unittest

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/nox-express-independent-e07-current-d02.yml"


class B06VerifierHeadAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.admission = cls.source.split("      - name: B06 exclusive immutable SetupSHA and previous-run admission", 1)[1].split("      - name: Fast source regression gate", 1)[0]

    def test_explicit_setup_and_no_implicit_push(self):
        self.assertIn("workflow_dispatch:", self.source)
        self.assertNotIn("  push:", self.source)
        self.assertIn("E07_SETUP_SHA", self.admission)
        self.assertIn("E07_SAME_SETUP_PREVIOUS_RUN_HOLD", self.admission)

    def test_canonical_ref_and_live_verifier_sha(self):
        self.assertIn("refs/heads/", self.admission)
        self.assertIn("integration/nox-v16-unified-candidate-20261028-r01", self.admission)
        self.assertIn("$env:GITHUB_REF -cne", self.admission)
        self.assertIn("$env:GITHUB_SHA -cnotmatch '^[0-9a-f]{40}$'", self.admission)
        self.assertIn("$livePr.head.sha -cne $env:GITHUB_SHA", self.admission)
        self.assertIn("$livePr.head.repo.full_name -cne $env:GITHUB_REPOSITORY", self.admission)

    def test_fail_closed_before_expensive_downloads(self):
        self.assertIn("'/pulls/162'", self.admission)
        self.assertIn("'E07_VERIFIER_HEAD_LOOKUP_HOLD'", self.admission)
        self.assertIn("'E07_VERIFIER_WRONG_REF_HOLD'", self.admission)
        self.assertIn("'E07_VERIFIER_STALE_HEAD_HOLD'", self.admission)
        self.assertLess(self.admission.index("'E07_VERIFIER_STALE_HEAD_HOLD'"), self.admission.index("$complete=$false"))
        self.assertLess(self.source.index("E07_VERIFIER_STALE_HEAD_HOLD"), self.source.index("Download immutable candidate from DIFFERENT"))

    def test_same_sha_and_real_provider_still_required(self):
        self.assertIn("$history=Invoke-RestMethod", self.admission)
        self.assertIn("if (-not $complete)", self.admission)
        self.assertIn("steps.provider.outcome", self.source)
        self.assertIn("steps.test.outcome", self.source)
        self.assertIn("E07_INDEPENDENT_PHYSICAL_HOLD_NOT_RELEASE", self.source)


if __name__ == "__main__":
    unittest.main()
