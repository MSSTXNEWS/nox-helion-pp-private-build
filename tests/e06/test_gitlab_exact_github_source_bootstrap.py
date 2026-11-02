"""Source-only regression for existing GitLab Windows T06 pinned GitHub PR162 checkout."""
import pathlib
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
class ExactSourceBootstrapContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text=(ROOT/"coordination/e06/Run-GitLabExactGithubSource.ps1").read_text("utf-8")
    def test_owner_and_masked_token(self):
        for s in ("CI_PROJECT_PATH","CI_RUNNER_EXECUTABLE_ARCH",
                  "NOX_T06_LOCAL_BRIDGE","NOX_PR162_EXACT_SHA","NOX_GITHUB_READ_TOKEN"):
            self.assertIn(s,self.text)
    def test_only_official_exact_source(self):
        for s in ("https://github.com/MSSTXNEWS/nox-helion-pp-private-build.git",
                  "refs/pull/162/head","http.followRedirects=false",
                  "T06_GITHUB_PR162_HEAD_CHANGED_HOLD","HEAD^{tree}"):
            self.assertIn(s,self.text)
    def test_original_builder_and_safe_prerequisites(self):
        for s in ("3.12.10","test_t06_samevm_webview2_preflight_stage.py",
                  "t06_local_onehost_bridge.py","GIT_LFS_SKIP_SMUDGE"):
            self.assertIn(s,self.text)
    def test_physical_candidate_is_not_release(self):
        for s in ("Get-FileHash","T06_EXACT_SOURCE_SETUP_COPY_SHA_HOLD",
                  "NOX-HELION-V16-ONEHOST-CANDIDATE-SETUP.exe",
                  "installed_independent_e07='NOT_RUN'","release_accepted=$false"):
            self.assertIn(s,self.text)
        self.assertNotIn("GIT_SSL_NO_VERIFY",self.text)
        self.assertNotIn("https://x-access-token:",self.text)
if __name__=="__main__":
    unittest.main()
