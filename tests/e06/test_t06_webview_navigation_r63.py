"""R63: diagnostics from fresh WPF log bytes; no release/GUI gate bypass."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
E06 = ROOT / "coordination" / "e06"
sys.path.insert(0, str(E06))
spec = importlib.util.spec_from_file_location(
    "nox_r63_installed_smoke", E06 / "t06_samevm_installed_smoke.py")
nox = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nox)

class WebViewNavigationEvidenceTests(unittest.TestCase):
    def test_real_nav_fail_is_classified_but_not_accepted(self):
        v = nox.summarize_fresh_webview_navigation(
            "[t] INIT_BEGIN\n[t] NAV_START\n[t] NAV_FAIL ConnectionAborted\n")
        self.assertEqual(v["nav_failure_status"], "ConnectionAborted")
        self.assertTrue(v["nav_failed"])
        self.assertTrue(v["nav_started"])
    def test_process_failure_status_uses_exact_bounded_token(self):
        v = nox.summarize_fresh_webview_navigation(
            "[t] WEBVIEW_PROCESS_FAILED RenderProcessExited\n")
        self.assertTrue(v["webview_process_failed"])
        self.assertEqual(v["webview_process_failure_kind"], "RenderProcessExited")
    def test_no_raw_untrusted_navigation_url_or_local_path_leaks(self):
        raw = ("[t] BLOCK_NAV https://evil.example/secret?token=private\n"
               "[t] NAV_FAIL ConnectionTimeout C:\\Users\\private\\token.txt\n")
        v = nox.summarize_fresh_webview_navigation(raw)
        self.assertTrue(v["navigation_blocked"])
        self.assertEqual(v["nav_failure_status"], "ConnectionTimeout")
        self.assertNotIn("evil.example",str(v))
        self.assertNotIn("private",str(v))
    def test_missing_event_prefix_cannot_fake_status(self):
        v = nox.summarize_fresh_webview_navigation(
            "NAV_FAIL ConnectionTimeout\\nWEBVIEW_PROCESS_FAILED RenderProcessExited\\n")
        self.assertIsNone(v["nav_failure_status"])
        self.assertIsNone(v["webview_process_failure_kind"])
        self.assertFalse(v["nav_failed"])
    def test_empty_and_malformed_cannot_supply_failure_status(self):
        for text in ("", "FAKE_NAV_FAIL BAD", "NAV_FAIL ../../secret",
                     "NAV_FAIL " + "X" * 100):
            self.assertIsNone(
                nox.summarize_fresh_webview_navigation(text)["nav_failure_status"])
    def test_original_gui_and_ipc_gates_remain_unmodified(self):
        source = (E06 / "t06_samevm_installed_smoke.py").read_text("utf8")
        self.assertIn('accepted and seen["NAV_OK"]', source)
        self.assertIn('find_visible_wpf_hwnd(process.pid)', source)
        self.assertIn('"independent_visual_e07":"NOT_RUN"', source)

if __name__=="__main__":
    unittest.main()
