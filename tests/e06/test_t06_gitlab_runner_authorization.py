"""Real T06 GitLab runner admission regression. No installer or network is run."""
from pathlib import Path
import importlib.util
import os
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "t06_disposable_gitlab_smoke", ROOT / "coordination/e06/t06_samevm_installed_smoke.py")
SMOKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SMOKE)

GOOD = {
    "GITLAB_CI": "true",
    "CI_SERVER_HOST": "gitlab.com",
    "CI_PROJECT_PATH": "s-grouptwet/nox-helion-pp-private-build",
    "CI_RUNNER_EXECUTABLE_ARCH": "windows/amd64",
    "CI_JOB_ID": "17614283824",
    "NOX_T06_LOCAL_BRIDGE": "YES",
}


class DisposableRunnerGate(unittest.TestCase):
    def check_preinstall(self, env, *, local_bridge=True):
        """Mock the receipt reader to stop BEFORE any native install step."""
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            with (patch.dict(os.environ, env, clear=True),
                  patch.object(SMOKE.sys, "platform", "win32"),
                  patch.multiple(SMOKE, ON_LOCAL_BRIDGE=local_bridge, ON_GITHUB=False,
                                 OUTPUT=out, NSIS_PROOF=out / "T06_INSTALLED_SMOKE.json"),
                  patch.object(SMOKE, "candidate_gate",
                               side_effect=RuntimeError("TEST_STOP_BEFORE_INSTALL")) as gate):
                self.assertEqual(SMOKE.main(), 1)
                return gate.called

    def test_exact_existing_gitlab_windows_project_runs_candidate_check(self):
        self.assertTrue(self.check_preinstall(GOOD))

    def test_wrong_project_refused_before_candidate(self):
        self.assertFalse(self.check_preinstall({**GOOD, "CI_PROJECT_PATH": "other/project"}))

    def test_wrong_host_refused(self):
        self.assertFalse(self.check_preinstall({**GOOD, "CI_SERVER_HOST": "gitlab.example"}))

    def test_linux_and_invalid_job_id_refused(self):
        self.assertFalse(self.check_preinstall({**GOOD, "CI_RUNNER_EXECUTABLE_ARCH": "linux/amd64"}))
        self.assertFalse(self.check_preinstall({**GOOD, "CI_JOB_ID": "../1"}))

    def test_local_bridge_cannot_borrow_github_disposable_flag(self):
        forged = {**GOOD, "GITLAB_CI": "false", "GITHUB_ACTIONS": "true",
                  "RUNNER_OS": "Windows", "GITHUB_RUN_ID": "1234",
                  "NOX_E07_CI_WINDOWS_DISPOSABLE": "YES"}
        self.assertFalse(self.check_preinstall(forged))


if __name__ == "__main__":
    unittest.main()
