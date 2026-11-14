"""Original T06 EdgeUpdate unknown Win32 registry faults: strict HOLD, no reinstall."""
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
    "nox_t06_samevm_webview2_r63", OWNER / "t06_samevm_installed_smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class RegistryProbeErrorR63(unittest.TestCase):
    def preflight(self, code=1):
        return {"code": code, "stdout_tail": "P01_WEBVIEW2_RUNTIME_MISSING", "stderr_tail": ""}

    def poll(self, registration, code=1):
        return smoke.poll_webview2_postinstall(
            lambda: self.preflight(code), lambda: registration,
            lambda _delay: self.fail("Unexpected retry after unknown registry error"),
            delays=(0, 1))

    @staticmethod
    def fake_winreg(exception):
        fake = types.ModuleType("winreg")
        fake.HKEY_LOCAL_MACHINE = 1
        fake.HKEY_CURRENT_USER = 2
        fake.KEY_READ = 0x20019
        fake.KEY_WOW64_32KEY = 0x200
        fake.KEY_WOW64_64KEY = 0x100
        fake.REG_SZ = 1
        fake.OpenKey = lambda *_args: (_ for _ in ()).throw(exception)
        fake.QueryValueEx = lambda *_args: ("123.0.0.0", fake.REG_SZ)
        return fake

    def test_unexpected_winerror_is_not_runtime_missing(self):
        exc = OSError("ERROR_INVALID_PARAMETER")
        exc.winerror = 87
        with mock.patch.dict(sys.modules, {"winreg": self.fake_winreg(exc)}):
            rows = smoke.webview2_registration_diagnostic()
        self.assertTrue(rows["HKLM_64_VIEW"]["probe_error"])
        self.assertTrue(smoke.webview2_registry_probe_failed(rows))
        self.assertEqual(self.poll(rows)[3], "REGISTRY_PROBE_FAILED")

    def test_unknown_error_without_winerror_is_fail_closed(self):
        with mock.patch.dict(sys.modules, {"winreg": self.fake_winreg(OSError("I/O error"))}):
            rows = smoke.webview2_registration_diagnostic()
        self.assertTrue(smoke.webview2_registry_probe_failed(rows))
        self.assertEqual(self.poll(rows)[3], "REGISTRY_PROBE_FAILED")

    def test_missing_key_is_not_probe_failure(self):
        with mock.patch.dict(sys.modules, {"winreg": self.fake_winreg(FileNotFoundError(2, "Missing"))}):
            rows = smoke.webview2_registration_diagnostic()
        self.assertFalse(smoke.webview2_registry_probe_failed(rows))
        self.assertFalse(smoke.webview2_registry_access_denied(rows))
        outcome = smoke.poll_webview2_postinstall(lambda: self.preflight(), lambda: rows,
                                                   lambda _delay: None, delays=(0,))
        self.assertEqual(outcome[3], "RUNTIME_MISSING")

    def test_access_denied_retains_separate_hold(self):
        with mock.patch.dict(sys.modules, {"winreg": self.fake_winreg(PermissionError(13, "Denied"))}):
            rows = smoke.webview2_registration_diagnostic()
        self.assertTrue(smoke.webview2_registry_access_denied(rows))
        self.assertFalse(smoke.webview2_registry_probe_failed(rows))
        self.assertEqual(self.poll(rows)[3], "REGISTRY_ACCESS_DENIED")

    def test_original_preflight_success_remains_sole_success(self):
        rows = {"HKLM_32_VIEW": {"present": False, "probe_error": True, "winerror": 87}}
        self.assertEqual(self.poll(rows, code=0)[3], "PASS_BY_ORIGINAL_PREFLIGHT")

    def test_unexpected_untyped_registry_evidence_fails_closed(self):
        self.assertTrue(smoke.webview2_registry_probe_failed(["bad-evidence"]))
        self.assertEqual(self.poll(["bad-evidence"])[3], "REGISTRY_PROBE_FAILED")


if __name__ == "__main__":
    unittest.main()
