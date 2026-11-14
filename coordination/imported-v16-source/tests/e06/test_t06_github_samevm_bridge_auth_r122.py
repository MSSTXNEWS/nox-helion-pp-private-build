"""Exact GitHub-hosted Windows same-VM admission; never E07 PASS."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location(
    "nox_r122_samevm",ROOT/"coordination/e06/t06_samevm_installed_smoke.py")
owner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)

VALID={
    "GITHUB_RUN_ID":"41751106869",
    "GITHUB_ACTIONS":"true",
    "GITHUB_REPOSITORY":"MSSTXNEWS/nox-helion-pp-private-build",
    "GITHUB_REF":"refs/heads/integration/nox-v16-unified-candidate-20261028-r01",
    "GITHUB_WORKFLOW":"NOX EXPRESS single-SHA Windows Setup and source",
    "GITHUB_EVENT_NAME":"push",
    "RUNNER_OS":"Windows",
    "RUNNER_ARCH":"X64",
    "RUNNER_ENVIRONMENT":"github-hosted",
    "NOX_T06_LOCAL_BRIDGE":"YES",
    "NOX_E07_CI_WINDOWS_DISPOSABLE":"YES",
}
class HostedBridgeR122(unittest.TestCase):
    def call(self,env=VALID,platform="win32",arch="AMD64",bits=64):
        return owner.github_disposable_bridge_authorized(env,platform,arch,bits)
    def test_exact_hosted_branch_and_execution_required(self):
        self.assertTrue(self.call())
        self.assertTrue(self.call({**VALID,"GITHUB_EVENT_NAME":"workflow_dispatch"}))
        for name,value in (
            ("GITHUB_RUN_ID","abc"),("GITHUB_ACTIONS","false"),
            ("GITHUB_REPOSITORY","other/repo"),
            ("GITHUB_REF","refs/heads/main"),
            ("GITHUB_WORKFLOW","other build"),
            ("GITHUB_EVENT_NAME","pull_request"),
            ("RUNNER_OS","Linux"),("RUNNER_ARCH","ARM64"),
            ("RUNNER_ENVIRONMENT","self-hosted"),
            ("NOX_T06_LOCAL_BRIDGE","NO"),
            ("NOX_E07_CI_WINDOWS_DISPOSABLE","NO"),
        ):
            with self.subTest(name=name):
                self.assertFalse(self.call({**VALID,name:value}))
        for missing in VALID:
            with self.subTest(missing=missing):
                self.assertFalse(self.call({k:v for k,v in VALID.items() if k!=missing}))
    def test_not_local_or_unapproved_architecture(self):
        self.assertFalse(self.call(platform="linux"))
        self.assertFalse(self.call(arch="ARM64"))
        self.assertFalse(self.call(bits=32))
    def test_stage_does_not_grant_e07_release(self):
        raw=(ROOT/"coordination/e06/t06_samevm_installed_smoke.py").read_text("utf-8")
        self.assertIn('"e07_independent_acceptance":"NOT_RUN"',raw)
        self.assertIn('"release_accepted":False',raw)

if __name__=="__main__":unittest.main()
