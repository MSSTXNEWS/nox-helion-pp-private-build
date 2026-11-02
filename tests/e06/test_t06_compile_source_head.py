"""T06 source receipt must identify the *checked out* Git commit, never a historic SHA."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[2] / "coordination/e06/t06_compile_original_wpf_p02.py"
SPEC = importlib.util.spec_from_file_location("nox_t06_compile_source_identity", MODULE)
compile_owner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compile_owner)

class SourceHeadIdentity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "tracked.txt").write_text("original\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        self.git("-c", "user.name=NOX Test", "-c", "user.email=nox-test@example.invalid", "commit", "-qm", "first")
        root_patch = patch.object(compile_owner, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        env_patch = patch.dict(os.environ, {"CI_COMMIT_SHA": ""})
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], text=True).strip()

    def test_returns_real_checkout_head_not_stale_constant(self):
        self.assertEqual(compile_owner.verified_source_head(), self.git("rev-parse", "HEAD"))
        self.assertNotEqual(compile_owner.verified_source_head(), "74e03bc99d82467e8b9f48f367b8815fb13a0798")

    def test_ci_head_mismatch_fails_closed(self):
        with patch.dict(os.environ, {"CI_COMMIT_SHA": "f" * 40}):
            with self.assertRaisesRegex(RuntimeError, "T06_SOURCE_CI_SHA_MISMATCH"):
                compile_owner.verified_source_head()

    def test_matching_ci_head_accepted(self):
        with patch.dict(os.environ, {"CI_COMMIT_SHA": self.git("rev-parse", "HEAD")}):
            self.assertEqual(compile_owner.verified_source_head(), self.git("rev-parse", "HEAD"))

    def test_missing_git_checkout_fails_closed(self):
        with patch.object(compile_owner, "ROOT", self.root / "missing_checkout"):
            with self.assertRaisesRegex(RuntimeError, "T06_SOURCE_COMMIT_UNVERIFIED"):
                compile_owner.verified_source_head()

    def test_receipt_is_measured_at_start_and_before_persist(self):
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn("source_git_sha=verified_source_head()", source)
        self.assertIn("require(verified_source_head()==source_git_sha", source)
        self.assertIn('"source_git_sha":source_git_sha', source)
        self.assertNotIn('"source_git_sha":"74e03bc99d82467e8b9f48f367b8815fb13a0798"', source)

    def test_later_commit_is_detectably_different(self):
        first = compile_owner.verified_source_head()
        (self.root / "tracked.txt").write_text("changed\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        self.git("-c", "user.name=NOX Test", "-c", "user.email=nox-test@example.invalid", "commit", "-qm", "second")
        self.assertNotEqual(first, compile_owner.verified_source_head())

if __name__ == "__main__":
    unittest.main()
