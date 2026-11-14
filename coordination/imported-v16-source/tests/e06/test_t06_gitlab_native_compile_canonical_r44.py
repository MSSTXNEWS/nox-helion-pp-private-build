"""G3/G4: GitLab Windows T06 compilation must start at authenticated GitHub snapshot.

Execute the exact original verified_source_head() AST, with only git/environment
witnesses simulated. These tests do not claim native Windows or E07 acceptance.
"""
from __future__ import annotations
import ast
import os
import re
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "coordination/e06/t06_compile_original_wpf_p02.py"
CANON_HEAD = "0418fab5bdb18ebb75df74d2b619e8ea75ede0b6"
BOOTSTRAP_HEAD = "0178ebcabc7760eaed5cdd5194cdf8d010453123"
PROJECT = "s-grouptwet/nox-helion-pp-private-build"


def source_head_with_native_witnesses(env: dict[str, str]):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), str(SOURCE))
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef)
               and node.name == "verified_source_head"]
    if len(matches) != 1:
        raise AssertionError("Original T06 source guard missing/duplicated")
    expr = ast.Module(body=matches, type_ignores=[])
    namespace = {
        "ROOT": ROOT, "os": os, "re": re, "subprocess": subprocess,
        "require": lambda ok, why: None if ok else (_ for _ in ()).throw(RuntimeError(why))
    }
    git = subprocess.CompletedProcess(args=["git"], returncode=0,
                                  stdout=CANON_HEAD + "\n", stderr="")
    with patch.dict(os.environ, env, clear=True), \
         patch.object(subprocess, "run", return_value=git) as invoked:
        exec(compile(expr, str(SOURCE), "exec"), namespace)
        actual = namespace["verified_source_head"]()
        invoked.assert_called_once()
        return actual


class CanonicalSourceAdmission(unittest.TestCase):
    def gitlab(self):
        return {"CI_SERVER_HOST": "gitlab.com", "CI_PROJECT_PATH": PROJECT,
                "CI_COMMIT_SHA": BOOTSTRAP_HEAD,
                "NOX_T06_GITHUB_FROZEN_SHA": CANON_HEAD,
                "NOX_T06_GITHUB_FROZEN_REF":
                    "buildpin/nox-express-20261102-" + CANON_HEAD[:12],
                "NOX_T06_GITLAB_ORIGIN_SHA": BOOTSTRAP_HEAD,
                "NOX_T06_AUTHENTICATED_GITHUB_FETCH": "PASS"}

    def test_authenticated_exact_frozen_github_source(self):
        self.assertEqual(source_head_with_native_witnesses(self.gitlab()), CANON_HEAD)

    def test_unfetched_gitlab_checkout_equal_ci_head_denied(self):
        # A GitLab branch's own successful SHA check is not GitHub provenance.
        old = self.gitlab()
        old["CI_COMMIT_SHA"] = CANON_HEAD
        for key in ("NOX_T06_AUTHENTICATED_GITHUB_FETCH",
                    "NOX_T06_GITHUB_FROZEN_SHA", "NOX_T06_GITLAB_ORIGIN_SHA"):
            old.pop(key, None)
        with self.assertRaisesRegex(RuntimeError,
                                    "T06_GITLAB_AUTHENTICATED_FROZEN_SOURCE_REQUIRED"):
            source_head_with_native_witnesses(old)

    def test_missing_or_spoofed_evidence_denied(self):
        for key in ("NOX_T06_AUTHENTICATED_GITHUB_FETCH",
                    "NOX_T06_GITHUB_FROZEN_REF", "NOX_T06_GITHUB_FROZEN_SHA",
                    "NOX_T06_GITLAB_ORIGIN_SHA", "CI_COMMIT_SHA", "CI_PROJECT_PATH"):
            with self.subTest(key=key):
                env = self.gitlab()
                env.pop(key)
                with self.assertRaisesRegex(RuntimeError,
                                            "T06_GITLAB_AUTHENTICATED_FROZEN_SOURCE_REQUIRED"):
                    source_head_with_native_witnesses(env)

    def test_moving_source_ref_is_denied(self):
        env = self.gitlab()
        env["NOX_T06_GITHUB_FROZEN_REF"] = "integration/nox-v16-unified-candidate-20261028-r01"
        with self.assertRaisesRegex(RuntimeError,
                                    "T06_GITLAB_AUTHENTICATED_FROZEN_SOURCE_REQUIRED"):
            source_head_with_native_witnesses(env)

    def test_local_original_compile_preserved(self):
        self.assertEqual(source_head_with_native_witnesses({}), CANON_HEAD)

    def test_other_ci_runner_not_trusted(self):
        env = self.gitlab()
        env["CI_SERVER_HOST"] = "evil-ci.example"
        with self.assertRaisesRegex(RuntimeError,
                                    "T06_GITLAB_AUTHENTICATED_FROZEN_SOURCE_REQUIRED"):
            source_head_with_native_witnesses(env)


if __name__ == "__main__":
    unittest.main()
