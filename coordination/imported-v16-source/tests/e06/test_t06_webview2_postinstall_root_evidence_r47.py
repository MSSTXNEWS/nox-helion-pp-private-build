"""R47 original same-VM WebView2 install-failure evidence regression (source-only)."""
import json
import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"coordination/e06"))
from t06_local_onehost_bridge import webview2_root_evidence

class WebView2RootEvidenceR47(unittest.TestCase):
    def test_signed_bootstrapper_and_standalone_both_zero_do_not_grant_runtime(self):
        facts={
            "webview2_selected_verified_source":"evergreen-bootstrapper",
            "microsoft_webview2_provision_ci":{"exit_code":0,"kind":"evergreen-bootstrapper","signed_microsoft":True},
            "webview2_standalone_fallback":{"exit_code":0,"kind":"evergreen-standalone-x64","signed_microsoft":True},
            "webview2_initial_registration":{"HKLM_32_VIEW":{"present":False,"winerror":2}},
            "webview2_evergreen-standalone-x64_registration_diagnostic":{"HKLM_32_VIEW":{"present":False,"winerror":2}},
            "webview2_evergreen-standalone-x64_strict_preflight_poll":[{"strict_preflight_status":"RUNTIME_MISSING","exit_code":1,"delay_seconds":30}],
            "webview2_evergreen-standalone-x64_strict_preflight_verdict":"RUNTIME_MISSING",
            "webview2_final_postinstall_preflight":{"code":1}}
        evidence=webview2_root_evidence(facts)
        self.assertIs(evidence["release_accepted"],False)
        self.assertEqual(evidence["installer"]["standalone"]["exit_code"],0)
        self.assertEqual(evidence["final_preflight_exit"],1)
        self.assertEqual(evidence["registration"]["standalone"]["HKLM_32_VIEW"]["winerror"],2)

    def test_registry_view_disagreement_never_promotes_owner_preflight(self):
        evidence=webview2_root_evidence({
            "webview2_evergreen-bootstrapper_registration_diagnostic":{
                "HKLM_32_VIEW":{"present":True,"pv":"156.0.4314.58"}},
            "webview2_evergreen-bootstrapper_strict_preflight_verdict":
                "REGISTRY_PREFLIGHT_DIVERGENCE",
            "webview2_final_postinstall_preflight":{"code":1}})
        self.assertEqual(evidence["registration"]["bootstrapper"]["HKLM_32_VIEW"]["pv"],
                         "156.0.4314.58")
        self.assertEqual(evidence["verdict"]["bootstrapper"],"REGISTRY_PREFLIGHT_DIVERGENCE")
        self.assertIs(evidence["release_accepted"],False)

    def test_allowlist_never_emits_credentials_or_arbitrary_provider_errors(self):
        evidence=webview2_root_evidence({
            "NOX_T06_GITHUB_READ_TOKEN":"PRIVATE_TOKEN_SHOULD_NOT_APPEAR",
            "webview2_initial_registration":{"HKLM_64_VIEW":{
                "present":"true","pv":"PRIVATE_PATH","winerror":"PRIVATE_DETAIL"}},
            "webview2_selected_verified_source":"../../notapproved"})
        serialized=json.dumps(evidence,sort_keys=True)
        for forbidden in ("PRIVATE_TOKEN","PRIVATE_PATH","PRIVATE_DETAIL","notapproved"):
            self.assertNotIn(forbidden,serialized)
        self.assertLess(len(serialized),4800)

    def test_no_lifecycle_is_explicit_non_acceptance(self):
        self.assertEqual(webview2_root_evidence(None),
                         {"status":"LIFECYCLE_ABSENT_NOT_E07"})

    def test_original_driver_persists_and_emits_root_without_altering_gate(self):
        code=(ROOT/"coordination/e06/t06_local_onehost_bridge.py").read_text("utf-8")
        self.assertIn('data["webview2_root_evidence"]=runtime_evidence',code)
        self.assertIn("T06_WEBVIEW2_RUNTIME_ROOT_EVIDENCE",code)
        self.assertIn('raise RuntimeError("T06_M1_REAL_WINDOWS_GUI_IPC_LIFECYCLE_GATE_HOLD")',code)

if __name__=="__main__":
    unittest.main()
