"""GitLab Free NOX V16 source-only regression.
These checks do NOT grant Windows install/E07 acceptance.
Run: python -m unittest discover -s tests/e06 -p test_gitlab_free_source_gate.py -v
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "coordination/e06/gitlab_windows_entrypoint.ps1"
HANDOFF = ROOT / "coordination/e06/Emit-E07ImmutableHandoff.ps1"
PIPELINE = ROOT / ".gitlab-ci.yml"


class GitLabFreeSourceGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = ADAPTER.read_text(encoding="utf-8")
        cls.handoff = HANDOFF.read_text(encoding="utf-8")
        cls.pipeline = PIPELINE.read_text(encoding="utf-8")

    def test_explicit_manual_consent_only(self):
        self.assertIn('CI_PIPELINE_SOURCE == "web"', self.pipeline)
        self.assertIn('CI_PIPELINE_SOURCE == "api"', self.pipeline)
        self.assertIn("CI_PIPELINE_SOURCE -notin @('web','api')", self.adapter)
        self.assertNotIn('CI_PIPELINE_SOURCE == "push"', self.pipeline)
        self.assertNotIn('CI_PIPELINE_SOURCE == "schedule"', self.pipeline)
        self.assertIn('NOX_APPROVE_WINDOWS_BUILD == "YES"', self.pipeline)
        self.assertIn("when: never", self.pipeline)
        self.assertIn('retry: 0', self.pipeline)

    def test_original_four_stages_and_single_builder_preserved(self):
        self.assertIn("GITLAB_EXPECTED_FOUR_CANONICAL_STAGES", self.adapter)
        self.assertIn("build_onehost_installer.ps1", self.adapter)
        self.assertIn("PUBLISHED_PRIVATE_PAYLOAD_SHA256.json", self.adapter)
        self.assertIn("azure-pipelines-nox-v16.yml", self.adapter)

    def test_windows_adapter_powershell_variable_escape(self):
        self.assertIn('GITLAB_EXEC_FAILED:${name}:$LASTEXITCODE', self.adapter)
        self.assertNotIn('GITLAB_EXEC_FAILED:$name:$LASTEXITCODE', self.adapter)

    def test_e07_single_immutable_seal(self):
        self.assertEqual(self.handoff.count('Write-Host "E07_BUILDID_SEALED'), 1)
        self.assertEqual(
            self.handoff.count("foreach ($expected in @($source.parts))"), 1
        )
        self.assertEqual(self.handoff.count("E07_HANDOFF_READBACK_DRIFT"), 1)
        self.assertNotIn("'^[0-9a-f]{64}\n}", self.handoff)

    def test_part_digest_parity_values_not_only_format(self):
        self.assertIn(
            "([string]$matching[0].sha256).ToLowerInvariant() -cne "
            "([string]$expected.sha256).ToLowerInvariant()",
            self.handoff,
        )
        self.assertIn(
            "([string]$matching[0].gitBlobSha1).ToLowerInvariant() -cne "
            "([string]$expected.git_blob_sha1).ToLowerInvariant()",
            self.handoff,
        )

    def test_preflight_before_network_prerequisites(self):
        self.assertIn("GITLAB_E07_HANDOFF_POWERSHELL_SYNTAX_HOLD", self.adapter)
        self.assertIn("GITLAB_E07_SINGLE_SEAL_PART_PARITY_HOLD", self.adapter)
        self.assertLess(
            self.adapter.index("GITLAB_E07_SINGLE_SEAL_PART_PARITY_HOLD"),
            self.adapter.index("Find-Python31210\n"),
        )

    def test_release_not_auto_accepted(self):
        self.assertIn("release_accepted=$false", self.handoff)
        self.assertIn("independent_e07_installed_cases=0", self.adapter)
        self.assertIn("release_accepted=$false", self.adapter)


if __name__ == "__main__":
    unittest.main()
