"""T06 real Windows CI fail-closed source regression; not installed acceptance."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
class T06ScopeFailClosed(unittest.TestCase):
    def test_scope_failure_reports_only_nonsecret_field_names(self):
        s=(ROOT/"coordination/e06/t06_fetch_canonical_github.ps1").read_text("utf-8")
        self.assertIn("T06_GITHUB_CI_SCOPE_FAILED_FIELDS=",s)
        for field in ("CI_SERVER_HOST","CI_PROJECT_PATH","CI_PIPELINE_SOURCE",
                      "CI_RUNNER_EXECUTABLE_ARCH","EXPLICIT_T06_APPROVAL",
                      "FROZEN_GITHUB_SHA","CI_COMMIT_SHA"):
            self.assertIn("$scopeFailed+= '"+field+"'",s)
        self.assertIn("throw 'T06_GITHUB_CI_SCOPE_HOLD'",s)
        diag=next(line for line in s.splitlines() if "Write-Host ('T06_GITHUB_CI_SCOPE_FAILED_FIELDS=" in line)
        self.assertNotIn("TOKEN",diag)
        self.assertNotIn("ExpectedSha",diag)
    def test_t06_ci_stops_after_failed_bootstrap(self):
        s=(ROOT/".gitlab-ci.yml").read_text("utf-8")
        job=s.split("nox_t06_original_onehost_candidate:",1)[1].split("  artifacts:",1)[0]
        self.assertIn("try {",job)
        self.assertIn(". ./coordination/e06/t06_fetch_canonical_github.ps1",job)
        self.assertIn("} catch {",job)
        self.assertIn("T06_CI_FAILCLOSED_HOLD=",job)
        self.assertIn("exit 1",job.split("} catch {",1)[1])
        self.assertLess(job.index("try {"),job.index("t06_fetch_canonical_github.ps1"))
        self.assertLess(job.index("t06_fetch_canonical_github.ps1"),job.index("} catch {"))
    def test_no_scope_gate_downgrade(self):
        s=(ROOT/"coordination/e06/t06_fetch_canonical_github.ps1").read_text("utf-8")
        self.assertIn("T06_GITHUB_REF_MOVED_OR_FROZEN_SHA_HOLD",s)
        self.assertIn("T06_GITHUB_EXACT_TREE_READBACK_HOLD",s)
        self.assertIn("T06_GITHUB_MASKED_READ_TOKEN_REQUIRED",s)
        self.assertIn("GIT_CONFIG_VALUE_0",s)
if __name__=="__main__":unittest.main()
