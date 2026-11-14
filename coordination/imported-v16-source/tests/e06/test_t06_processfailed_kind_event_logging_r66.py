"""R66: the original WPF owner must log typed WebView2 process failures.

Source-contract regression only; Windows WebView2 behavior and E07 still require
an installed same-SHA Windows run.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "coordination/e06/OneHostP02WebView2Bridge.cs"
OWNER = ROOT / "coordination/e06/MainWindow.NativeP02.cs"
SMOKE = ROOT / "coordination/e06/t06_samevm_installed_smoke.py"


class TypedWebView2FailureLogging(unittest.TestCase):
    def test_original_bridge_emits_allowlisted_process_failure_kind(self):
        source = BRIDGE.read_text(encoding="utf-8")
        block = re.search(
            r"private void OnProcessFailed\(.*?\n    }",
            source, re.DOTALL
        )
        self.assertIsNotNone(block)
        body = block.group(0)
        self.assertIn(
            '_writeDiagnostic("WEBVIEW_PROCESS_FAILED " + e.ProcessFailedKind.ToString());',
            body
        )
        self.assertIn("catch (Exception)", body)

    def test_original_wpf_logger_is_wired_into_existing_bridge(self):
        bridge = BRIDGE.read_text(encoding="utf-8")
        owner = OWNER.read_text(encoding="utf-8")
        self.assertIn("private readonly Action<string> _writeDiagnostic;", bridge)
        self.assertIn("Action<string> writeDiagnostic,", bridge)
        self.assertIn("_writeDiagnostic = writeDiagnostic ??", bridge)
        self.assertIn(
            "NativeP02Acl,ConfirmP02NativeAsync,WriteLog,DispatchNativeOwnerAsync);",
            owner
        )

    def test_existing_smoke_parser_extracts_the_typed_marker(self):
        smoke = SMOKE.read_text(encoding="utf-8")
        self.assertIn("webview_process_failure_kind", smoke)
        self.assertIn("WEBVIEW_PROCESS_FAILED[ \\t]+([A-Za-z][A-Za-z0-9]{0,63})", smoke)


if __name__ == "__main__":
    unittest.main()
