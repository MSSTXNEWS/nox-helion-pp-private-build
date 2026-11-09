"""Original cross-VCS source-only regression; never an E07 release proof."""
import importlib.util
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "t06_build", ROOT / "coordination/e06/t06_compile_original_wpf_p02.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
GH, GL = "a" * 40, "b" * 40


class CrossVcs(unittest.TestCase):
    def probe(self, env):
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(
            m.subprocess, "run",
            return_value=SimpleNamespace(returncode=0, stdout=GH + "\n"),
        ):
            return m.verified_source_head()

    def good(self):
        return {
            "CI_COMMIT_SHA": GL,
            "CI_SERVER_HOST": "gitlab.com",
            "CI_PROJECT_PATH": "s-grouptwet/nox-helion-pp-private-build",
            "NOX_T06_AUTHENTICATED_GITHUB_FETCH": "PASS",
            "NOX_T06_GITHUB_FROZEN_SHA": GH,
            "NOX_T06_GITLAB_ORIGIN_SHA": GL,
            "NOX_T06_GITHUB_FROZEN_REF": "buildpin/nox-express-20261102-" + GH[:12],
        }

    def test_local_not_ci(self):
        self.assertEqual(self.probe({}), GH)

    def test_gitlab_equal_sha_without_auth_is_not_canonical(self):
        with self.assertRaisesRegex(RuntimeError, "T06_GITLAB_AUTHENTICATED_FROZEN_SOURCE_REQUIRED"):
            self.probe({"CI_COMMIT_SHA": GH, "CI_SERVER_HOST": "gitlab.com"})

    def test_old_gitlab_source_denied(self):
        with self.assertRaisesRegex(RuntimeError, "T06_GITLAB_AUTHENTICATED_FROZEN_SOURCE_REQUIRED"):
            self.probe({"CI_COMMIT_SHA": GL})

    def test_authenticated_exact_frozen(self):
        self.assertEqual(self.probe(self.good()), GH)

    def test_wrong_frozen_sha_denied(self):
        env = self.good()
        env["NOX_T06_GITHUB_FROZEN_SHA"] = "c" * 40
        with self.assertRaisesRegex(RuntimeError, "T06_GITLAB_AUTHENTICATED_FROZEN_SOURCE_REQUIRED"):
            self.probe(env)

    def test_wrong_frozen_ref_denied(self):
        env = self.good()
        env["NOX_T06_GITHUB_FROZEN_REF"] = "buildpin/nox-express-20261102-cccccccccccc"
        with self.assertRaisesRegex(RuntimeError, "T06_GITLAB_AUTHENTICATED_FROZEN_SOURCE_REQUIRED"):
            self.probe(env)

    def test_wrong_origin_denied(self):
        env = self.good()
        env["NOX_T06_GITLAB_ORIGIN_SHA"] = "c" * 40
        with self.assertRaisesRegex(RuntimeError, "T06_GITLAB_AUTHENTICATED_FROZEN_SOURCE_REQUIRED"):
            self.probe(env)

    def test_wrong_project_denied(self):
        env = self.good()
        env["CI_PROJECT_PATH"] = "other/fork"
        with self.assertRaisesRegex(RuntimeError, "T06_GITLAB_AUTHENTICATED_FROZEN_SOURCE_REQUIRED"):
            self.probe(env)

    def test_sha_regex_not_double_escaped(self):
        script = (ROOT / "coordination/e06/t06_fetch_canonical_github.ps1").read_text("utf-8")
        for field in ("$ExpectedSha", "$env:CI_COMMIT_SHA"):
            self.assertIn(field + " -cnotmatch '^[0-9a-f]{40}$'", script)
        self.assertNotIn(r"'\\A[0-9a-f]{40}\\z'", script)

    def test_frozen_ref_and_precheckout_no_loss(self):
        script = (ROOT / "coordination/e06/t06_fetch_canonical_github.ps1").read_text("utf-8")
        self.assertIn("T06_FROZEN_SOURCE_REF_INVALID", script)
        self.assertIn("$frozenRef='refs/heads/'+$env:NOX_T06_GITHUB_FROZEN_REF", script)
        self.assertIn("$ExpectedSha.Substring(0,12)", script)
        self.assertIn("'T06_GITHUB_PRECHECKOUT_DIRTY_TREE_NOLOSS_HOLD'", script)
        self.assertIn("status --porcelain --untracked-files=all", script)
        self.assertLess(script.index("T06_GITHUB_PRECHECKOUT_DIRTY_TREE_NOLOSS_HOLD"),
                        script.index("checkout --detach --force"))
        self.assertIn("$frozenRef\n", script)
        self.assertNotIn("'refs/heads/integration/nox-v16-unified-candidate-20261028-r01'", script)

    def test_unchanged_auth_and_runner_gates(self):
        script = (ROOT / "coordination/e06/t06_fetch_canonical_github.ps1").read_text("utf-8")
        for gate in ("T06_GITHUB_CI_SCOPE_HOLD", "T06_GITHUB_MASKED_READ_TOKEN_REQUIRED",
                     "T06_GITHUB_REF_MOVED_OR_FROZEN_SHA_HOLD",
                     "T06_GITHUB_EXACT_TREE_READBACK_HOLD", "GIT_CONFIG_VALUE_0"):
            self.assertIn(gate, script)
        ci = (ROOT / ".gitlab-ci.yml").read_text("utf-8")
        self.assertIn("t06_fetch_canonical_github.ps1", ci)


if __name__ == "__main__":
    unittest.main()
