"""Source-contract regression for R74: original ONE WPF bridge, no mocked E07."""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "coordination/e06/OneHostP02WebView2Bridge.cs"
COMPILER = ROOT / "coordination/e06/t06_compile_original_wpf_p02.py"
BUILDER = ROOT / "coordination/e06/build_onehost_installer.ps1"
EXPECTED_BLOB = "d99bd2f7bc69c3ab917954d28e91cd6edf328a2b"

class ProcessFailedOwnerTelemetry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = BRIDGE.read_text(encoding="utf-8")
        cls.compiler = COMPILER.read_text(encoding="utf-8")
        cls.builder = BUILDER.read_text(encoding="utf-8")

    def test_failure_event_is_revoked_before_diagnostic(self):
        self.assertRegex(self.source, r"(?s)private void OnProcessFailed.*?RevokeDocument\(\);.*?_writeDiagnostic\(FormatWebViewProcessFailure\(e\)\)")
        self.assertIn("_browserProcessLost = true;", self.source)
        self.assertIn("_onBrowserProcessExited?.Invoke(_web)", self.source)
        self.assertIn("if (e.ProcessFailedKind != CoreWebView2ProcessFailedKind.RenderProcessExited)", self.source)

    def test_live_webview_reason_exit_and_unsigned_hex(self):
        self.assertIn("e.Reason.ToString()", self.source)
        self.assertIn("e.ExitCode", self.source)
        self.assertIn('unchecked((uint)code).ToString("X8"', self.source)
        self.assertIn('"WEBVIEW_PROCESS_FAILED " + e.ProcessFailedKind.ToString()', self.source)

    def test_module_is_basename_only_not_full_private_path(self):
        self.assertIn("System.IO.Path.GetFileName(fullPath.Replace", self.source)
        self.assertIn('Regex.IsMatch(leaf, @"\\A[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\\z"', self.source)
        self.assertIn('return "none";', self.source)
        self.assertNotIn('module=" + modulePath', self.source)
        self.assertNotIn('module=" + e.FailureSourceModulePath', self.source)

    def test_optional_metadata_cannot_skip_original_owner_fence(self):
        self.assertIn('GetProperty("FailureSourceModulePath")?', self.source)
        self.assertIn("catch (Exception) { /* Optional metadata is not an admission gate. */ }", self.source)
        self.assertIn("OnNativeP02BrowserProcessExited", (ROOT / "coordination/e06/MainWindow.NativeP02.cs").read_text(encoding="utf-8"))

    def test_all_existing_builder_consumers_pin_exact_new_bridge_blob(self):
        self.assertIn(EXPECTED_BLOB, self.compiler)
        self.assertIn(EXPECTED_BLOB, self.builder)
        self.assertNotIn("749d87eac737b0162e9c3e5c101fe38866732d59", self.compiler)
        self.assertNotIn("749d87eac737b0162e9c3e5c101fe38866732d59", self.builder)

if __name__ == "__main__":
    unittest.main()
