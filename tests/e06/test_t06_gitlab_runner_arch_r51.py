"""R51 source-scope GitLab Windows runner gate; native install/E07 not simulated."""
import ast
from pathlib import Path
import unittest

SOURCE=Path(__file__).resolve().parents[2]/"coordination/e06/t06_samevm_installed_smoke.py"

def candidate_from_original():
    original=ast.parse(SOURCE.read_text("utf-8"), filename=str(SOURCE))
    nodes=[node for node in original.body if isinstance(node,ast.FunctionDef) and node.name=="gitlab_native_windows_amd64"]
    if len(nodes)!=1:
        raise AssertionError("ONE_ORIGINAL_WINDOWS_RUNNER_HELPER_REQUIRED")
    local={}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE),"exec"),local)
    return local["gitlab_native_windows_amd64"]

class GitLabNativeWindowsRunnerR51(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.gate=staticmethod(candidate_from_original())
    def test_reported_blank_real_windows_amd64_64bit(self):
        self.assertTrue(self.gate("", "win32", "AMD64",64))
    def test_explicit_matching_arch(self):
        self.assertTrue(self.gate("windows/amd64", "win32", "x86_64",64))
    def test_mismatched_explicit_export_denied(self):
        self.assertFalse(self.gate("linux/amd64", "win32", "AMD64",64))
    def test_nonwindows_denied(self):
        self.assertFalse(self.gate("", "linux", "AMD64",64))
    def test_32bit_denied(self):
        self.assertFalse(self.gate("", "win32", "AMD64",32))
    def test_arm64_denied(self):
        self.assertFalse(self.gate("", "win32", "ARM64",64))
    def test_invalid_types_denied(self):
        self.assertFalse(self.gate(None,"win32","AMD64",64))
        self.assertFalse(self.gate("","win32","AMD64",True))
    def test_original_gate_is_wired_and_ci_approvals_retained(self):
        text=SOURCE.read_text("utf-8")
        for item in ("gitlab_native_windows_amd64(", "CI_PROJECT_PATH",
                     "CI_JOB_ID", "GITLAB_CI", "CI_SERVER_HOST",
                     "T06_INSTALL_SMOKE_REQUIRES_AUTHORIZED_DISPOSABLE_WINDOWS"):
            self.assertIn(item,text)

if __name__=="__main__": unittest.main()
