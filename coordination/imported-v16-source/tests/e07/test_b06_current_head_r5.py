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

    def test_exact_producer_run_origin_before_same_setup_attempt(self):
        # These are strict fail-closed source contracts, never runtime E07.
        for value in (
            "E07_PRODUCER_RUN_LOOKUP_HOLD",
            "E07_PRODUCER_RUN_SOURCE_IDENTITY_HOLD",
            "/actions/runs/",
            "[string]$producer.id -cne $env:E07_PRODUCER_RUN_ID",
            "$producer.head_sha -cne $env:E07_SOURCE_SHA",
            "$producer.head_branch -cne $expectedBranch",
            "$producer.path -cne '.github/workflows/nox-v16-e06-d02-onehost.yml'",
            "$producer.repository.full_name -cne $env:GITHUB_REPOSITORY",
            "$producer.head_repository.full_name -cne $env:GITHUB_REPOSITORY",
            "$producer.status -cne 'completed'",
            "$producer.conclusion -notin @('success','failure')",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.admission)
        # An old, cancelled or unrelated run must fail before same-SHA
        # admission can consume the sole physical attempt.
        self.assertLess(
            self.admission.index("E07_PRODUCER_RUN_SOURCE_IDENTITY_HOLD"),
            self.admission.index("$complete=$false"))
        self.assertLess(
            self.source.index("E07_PRODUCER_RUN_SOURCE_IDENTITY_HOLD"),
            self.source.index("Download immutable candidate from DIFFERENT"))
        self.assertNotIn("continue-on-error: true", self.admission)

    def test_same_sha_and_real_provider_still_required(self):
        self.assertIn("$history=Invoke-RestMethod", self.admission)
        self.assertIn("if (-not $complete)", self.admission)
        self.assertIn("steps.provider.outcome", self.source)
        self.assertIn("steps.test.outcome", self.source)
        self.assertIn("E07_INDEPENDENT_PHYSICAL_HOLD_NOT_RELEASE", self.source)


if __name__ == "__main__":
    unittest.main()
