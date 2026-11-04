"""Source-only checks for the opt-in, SHA-frozen GitLab OneHost Windows path.
Cannot substitute for a real Windows run, WPF GUI or independent E07.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".gitlab-ci.yml"


class GitlabT06OneHost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.yaml = CI.read_text(encoding="utf-8")
        cls.t06 = cls.yaml.split("nox_t06_original_onehost_candidate:", 1)[-1]

    def test_only_one_r78_candidate_and_original_two_jobs_preserved(self):
        self.assertEqual(self.yaml.count("nox_t06_original_onehost_candidate:"), 1)
        self.assertEqual(self.yaml.count("nox_v16_windows_source_qa:"), 1)
        self.assertEqual(self.yaml.count("nox_v16_windows_diagnostic:"), 1)
        self.assertIn("gitlab_windows_source_qa.ps1", self.yaml)
        self.assertIn("gitlab_windows_entrypoint.ps1", self.yaml)

    def test_three_modes_are_mutually_exclusive_and_opt_in(self):
        self.assertGreaterEqual(self.yaml.count('$NOX_APPROVE_T06_BRIDGE != "YES"'), 6)
        self.assertIn('$NOX_APPROVE_WINDOWS_QA != "YES"', self.t06)
        self.assertIn('$NOX_APPROVE_WINDOWS_BUILD != "YES"', self.t06)
        self.assertIn("CI_PIPELINE_SOURCE -notin @('web','api')", self.t06)
        self.assertNotIn("CI_PIPELINE_SOURCE == \"push\"", self.yaml)

    def test_exact_head_must_be_verified_before_running_compiler(self):
        for required in (
            "T06_GITLAB_OWNER_DISPOSABLE_EXACT_SOURCE_HOLD",
            "T06_GITLAB_CHECKOUT_HEAD_DRIFT",
            "CI_RUNNER_EXECUTABLE_ARCH",
            "CI_PROJECT_PATH",
            "CI_JOB_ID",
            "NOX_T06_FROZEN_REF",
            "NOX_T06_FROZEN_SHA",
            "git rev-parse HEAD",
        ):
            self.assertIn(required, self.t06)
        self.assertLess(self.t06.index("git rev-parse HEAD"),
                        self.t06.index("t06_local_onehost_bridge.py"))

    def test_original_signed_installer_and_receipts_reused(self):
        self.assertIn('NOX_M1_CI_INSTALL_WEBVIEW2: "YES"', self.t06)
        self.assertIn("t06_local_onehost_bridge.py", self.t06)
        self.assertIn("NOX-HELION-V16-ONEHOST-CANDIDATE-SETUP.exe", self.t06)
        self.assertIn("T06_GITLAB_SAME_VM_CANDIDATE_BUILD_HOLD", self.t06)
        self.assertIn("expire_in: 30 days", self.t06)


if __name__ == "__main__":
    unittest.main()
