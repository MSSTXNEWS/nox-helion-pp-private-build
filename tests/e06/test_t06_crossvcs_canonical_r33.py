"""Cross-VCS exact-source contract; unit tests do NOT attest installed E07."""
import importlib.util,os,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("t06_build",ROOT/"coordination/e06/t06_compile_original_wpf_p02.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
GH="a"*40;GL="b"*40
class CrossVcs(unittest.TestCase):
    def probe(self,e):
        with mock.patch.dict(os.environ,e,clear=True),mock.patch.object(
            m.subprocess,"run",return_value=SimpleNamespace(returncode=0,stdout=GH+"\n")):
            return m.verified_source_head()
    def good(self):
        return dict(CI_COMMIT_SHA=GL,CI_SERVER_HOST="gitlab.com",
          CI_PROJECT_PATH="s-grouptwet/nox-helion-pp-private-build",
          NOX_T06_AUTHENTICATED_GITHUB_FETCH="PASS",
          NOX_T06_GITHUB_FROZEN_SHA=GH,NOX_T06_GITLAB_ORIGIN_SHA=GL)
    def test_local(self):self.assertEqual(self.probe({}),GH)
    def test_same_commit(self):self.assertEqual(self.probe({"CI_COMMIT_SHA":GH}),GH)
    def test_old_gitlab_denied(self):
        with self.assertRaisesRegex(RuntimeError,"T06_SOURCE_CI_SHA_MISMATCH"):self.probe({"CI_COMMIT_SHA":GL})
    def test_authenticated_frozen(self):self.assertEqual(self.probe(self.good()),GH)
    def test_wrong_frozen_denied(self):
        d=self.good();d["NOX_T06_GITHUB_FROZEN_SHA"]="c"*40
        with self.assertRaisesRegex(RuntimeError,"T06_SOURCE_CI_SHA_MISMATCH"):self.probe(d)
    def test_wrong_origin_denied(self):
        d=self.good();d["NOX_T06_GITLAB_ORIGIN_SHA"]="c"*40
        with self.assertRaisesRegex(RuntimeError,"T06_SOURCE_CI_SHA_MISMATCH"):self.probe(d)
    def test_wrong_project_denied(self):
        d=self.good();d["CI_PROJECT_PATH"]="other/fork"
        with self.assertRaisesRegex(RuntimeError,"T06_SOURCE_CI_SHA_MISMATCH"):self.probe(d)
    def test_sha_regex_is_single_anchored_not_escaped_twice(self):
        # PowerShell uses .NET regex in a *single-quoted* literal. Two
        # backslashes make the regex match literal backslash+A, rejecting
        # every otherwise valid Git commit SHA.
        script=(ROOT/"coordination/e06/t06_fetch_canonical_github.ps1").read_text("utf-8")
        for field in ("$ExpectedSha", "$env:CI_COMMIT_SHA"):
            self.assertIn(field+" -cnotmatch '^[0-9a-f]{40}
        script=(ROOT/"coordination/e06/t06_fetch_canonical_github.ps1").read_text("utf-8")
        ci=(ROOT/".gitlab-ci.yml").read_text("utf-8")
        self.assertIn("T06_GITHUB_REF_MOVED_OR_FROZEN_SHA_HOLD",script)
        self.assertIn("T06_GITHUB_EXACT_TREE_READBACK_HOLD",script)
        self.assertIn("GIT_CONFIG_VALUE_0",script)
        self.assertIn("t06_fetch_canonical_github.ps1",ci)
if __name__=="__main__":unittest.main()
",script)
        self.assertNotIn(r"'\\A[0-9a-f]{40}\\z'",script)

    def test_fetcher_contract(self):
        script=(ROOT/"coordination/e06/t06_fetch_canonical_github.ps1").read_text("utf-8")
        ci=(ROOT/".gitlab-ci.yml").read_text("utf-8")
        self.assertIn("T06_GITHUB_REF_MOVED_OR_FROZEN_SHA_HOLD",script)
        self.assertIn("T06_GITHUB_EXACT_TREE_READBACK_HOLD",script)
        self.assertIn("GIT_CONFIG_VALUE_0",script)
        self.assertIn("t06_fetch_canonical_github.ps1",ci)
if __name__=="__main__":unittest.main()
