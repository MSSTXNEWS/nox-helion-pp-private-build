"""Original T06 WebView2 32/64-bit registry access-denied admission regression."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
OWNER = ROOT / "coordination" / "e06"
sys.path.insert(0, str(OWNER))
spec = importlib.util.spec_from_file_location(
    "nox_t06_samevm_webview2_r56", OWNER / "t06_samevm_installed_smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class WebView2RegistryDeniedR56(unittest.TestCase):
    def preflight(self, code=1):
        return {"code": code,
                "stdout_tail": "P01_WEBVIEW2_RUNTIME_MISSING",
                "stderr_tail": ""}

    def poll(self, rows, code=1):
        return smoke.poll_webview2_postinstall(
            lambda: self.preflight(code), lambda: rows, lambda _: None,
            delays=(0,))

    def test_permission_denied_never_becomes_missing_runtime(self):
        rows = {"HKLM_64_VIEW": {"present": False, "winerror": 5,
                                 "access_denied": True}}
        self.assertTrue(smoke.webview2_registry_access_denied(rows))
        self.assertEqual(self.poll(rows)[3], "REGISTRY_ACCESS_DENIED")

    def test_missing_registry_key_remains_missing(self):
        rows = {"HKLM_64_VIEW": {"present": False, "winerror": 2,
                                 "access_denied": False}}
        self.assertFalse(smoke.webview2_registry_access_denied(rows))
        self.assertEqual(self.poll(rows)[3], "RUNTIME_MISSING")

    def test_positive_pv_is_not_authoritative_preflight(self):
        rows = {"HKCU_32_VIEW": {"present": True, "pv": "123.0.0.0"}}
        self.assertEqual(self.poll(rows)[3], "REGISTRY_PREFLIGHT_DIVERGENCE")

    def test_original_signed_preflight_is_sole_success(self):
        rows = {"HKLM_32_VIEW": {"present": False, "access_denied": True}}
        self.assertEqual(self.poll(rows, 0)[3], "PASS_BY_ORIGINAL_PREFLIGHT")

    def test_winreg_access_denied_distinguished_from_missing(self):
        fake = types.ModuleType("winreg")
        fake.HKEY_LOCAL_MACHINE = 1
        fake.HKEY_CURRENT_USER = 2
        fake.KEY_READ = 0x20019
        fake.KEY_WOW64_32KEY = 0x200
        fake.KEY_WOW64_64KEY = 0x100
        fake.REG_SZ = 1

        def open_key(root, _path, _reserved, flags):
            if root == fake.HKEY_LOCAL_MACHINE and flags & fake.KEY_WOW64_64KEY:
                exc = PermissionError(13, "registry view access denied")
                exc.winerror = 5
                raise exc
            raise FileNotFoundError(2, "EdgeUpdate key missing")
        fake.OpenKey = open_key
        fake.QueryValueEx = lambda _handle, _key: ("1.0.0.0", fake.REG_SZ)
        with mock.patch.dict(sys.modules, {"winreg": fake}):
            evidence = smoke.webview2_registration_diagnostic()
        self.assertTrue(evidence["HKLM_64_VIEW"]["access_denied"])
        self.assertFalse(evidence["HKLM_32_VIEW"]["access_denied"])
        self.assertFalse(evidence["HKCU_64_VIEW"]["access_denied"])
        self.assertTrue(smoke.webview2_registry_access_denied(evidence))

    def test_malformed_evidence_cannot_grant_success(self):
        self.assertFalse(smoke.webview2_registry_access_denied(["DENIED"]))
        self.assertFalse(smoke.valid_webview2_registration(
            {"HKLM_32_VIEW": {"present": True, "pv": "0.0.0.0"}}))


if __name__ == "__main__":
    unittest.main()
