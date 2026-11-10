"""R38: signed WebView2 async postinstall lifecycle contract; NOT real E07."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "coordination/e06/t06_samevm_installed_smoke.py"
spec = importlib.util.spec_from_file_location("t06_samevm_installed_smoke_r38", SOURCE)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)
poll_webview2_postinstall = smoke.poll_webview2_postinstall
valid_webview2_registration = smoke.valid_webview2_registration

MISS = {"code": 7, "stdout_tail": "P01_WEBVIEW2_RUNTIME_MISSING", "stderr_tail": ""}
PASS = {"code": 0, "stdout_tail": "P01_PREFLIGHT_OK", "stderr_tail": ""}
OTHER = {"code": 9, "stdout_tail": "OWNERSHIP_HOLD", "stderr_tail": ""}
NO = {"HKLM_32_VIEW": {"present": False}}
YES = {"HKLM_32_VIEW": {"present": True, "pv": "156.0.4314.58"}}


class Webview2PostinstallPollR38(unittest.TestCase):
    def run_poll(self, replies, registrations, delays=(0, 1, 2, 3)):
        queue = iter(replies)
        regs = iter(registrations)
        slept = []
        result = poll_webview2_postinstall(lambda: next(queue),
                  lambda: next(regs), slept.append, delays)
        return result, slept

    def test_original_smoke_wires_both_windows_views_and_no_pass_bypass(self):
        code = SOURCE.read_text("utf-8")
        for required in ("webview2_initial_registration", "HKCU_32_VIEW", "HKCU_64_VIEW",
                         "poll_webview2_postinstall(", "T06_WEBVIEW2_STAGED_PREFLIGHT_REGISTRY_DIVERGENCE",
                         "T06_WEBVIEW2_RUNTIME_STILL_MISSING_AFTER_INSTALL"):
            with self.subTest(required=required):
                self.assertIn(required, code)

    def test_asynchronous_registration_retries_until_original_preflight_passes(self):
        (result, attempts, _, verdict), slept = self.run_poll(
            [MISS, MISS, PASS], [NO, NO, YES])
        self.assertEqual(result["code"], 0)
        self.assertEqual(verdict, "PASS_BY_ORIGINAL_PREFLIGHT")
        self.assertEqual(slept, [1, 2])
        self.assertEqual(len(attempts), 3)

    def test_explicit_32_view_runtime_cannot_bypass_original_preflight(self):
        (result, attempts, _, verdict), slept = self.run_poll([MISS], [YES])
        self.assertEqual(verdict, "REGISTRY_PREFLIGHT_DIVERGENCE")
        self.assertNotEqual(result["code"], 0)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(slept, [])

    def test_unrelated_original_preflight_hold_stops_without_reinstall(self):
        (result, attempts, _, verdict), _ = self.run_poll([OTHER], [NO])
        self.assertEqual(verdict, "UNRELATED_HOLD")
        self.assertEqual(len(attempts), 1)
        self.assertEqual(result, OTHER)

    def test_no_registry_never_passes_and_poll_is_bounded(self):
        (result, attempts, _, verdict), slept = self.run_poll(
            [MISS, MISS, MISS, MISS], [NO] * 4)
        self.assertEqual(verdict, "RUNTIME_MISSING")
        self.assertNotEqual(result["code"], 0)
        self.assertEqual(len(attempts), 4)
        self.assertEqual(slept, [1, 2, 3])

    def test_invalid_registry_pv_and_wrong_type_rejected(self):
        for pv in ("0.0.0.0", "156", "156.0.4314.58x", "1.2.3.4.5", 123, None):
            with self.subTest(pv=pv):
                self.assertFalse(valid_webview2_registration({
                    "HKLM_32_VIEW": {"present": True, "pv": pv}}))
        self.assertTrue(valid_webview2_registration({
            "HKCU_64_VIEW": {"present": True, "pv": "156.0.4314.58"}}))


if __name__ == "__main__":
    unittest.main()
