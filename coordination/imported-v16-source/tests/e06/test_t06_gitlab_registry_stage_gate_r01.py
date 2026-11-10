"""Guard the original GitLab T06 Windows gate, not installed E07 evidence."""
from pathlib import Path
import unittest

CI = Path(__file__).resolve().parents[2] / ".gitlab-ci.yml"


class SameVmGitLabStagePolicy(unittest.TestCase):
    def setUp(self):
        text = CI.read_text(encoding="utf-8")
        self.assertEqual(text.count("nox_t06_original_onehost_candidate:"), 1)
        self.job = text.split("nox_t06_original_onehost_candidate:", 1)[1]
        self.job = self.job.split("\n  artifacts:", 1)[0] + "\n  artifacts:" + self.job.split("\n  artifacts:", 1)[1]

    def test_exact_python_and_reviewed_registry_staging_before_build(self):
        job = self.job
        self.assertIn("T06_WINDOWS_PYTHON_31210_REQUIRED", job)
        self.assertIn("-cne '3.12.10'", job)
        self.assertIn("test_t06_samevm_webview2_preflight_stage.py", job)
        self.assertIn("T06_WEBVIEW2_REGISTRY_STAGE_REGRESSION_HOLD", job)
        self.assertLess(job.index("test_t06_samevm_webview2_preflight_stage.py"),
                        job.index("coordination/e06/t06_local_onehost_bridge.py"))
        self.assertIn("T06_GITLAB_OWNER_DISPOSABLE_EXACT_SOURCE_HOLD", job)

    def test_nonexpiring_setup_wpf_backend_and_manifest_are_candidate_only(self):
        job = self.job
        self.assertIn("expire_in: never", job)
        for item in ("NOX-HELION-V16-ONEHOST-CANDIDATE-SETUP.exe",
                     "payload/NOX.P01.Shell.exe",
                     "payload/Backend/NOX_HELION_PRIVATE_CANDIDATE.exe",
                     "payload/payload.sha256.json",
                     "python-exe-candidate/NOX_HELION_PRIVATE_CANDIDATE.exe",
                     "work/t06-local-bridge/"):
            with self.subTest(item=item):
                self.assertIn(item, job)
        self.assertIn("This is not E07", job)
        self.assertIn("T06_GITLAB_SAME_VM_CANDIDATE_BUILD_HOLD", job)


if __name__ == "__main__":
    unittest.main()
