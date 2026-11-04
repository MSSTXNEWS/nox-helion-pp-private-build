#!/usr/bin/env python3
"""C06 consolidated native Back: exact HOME and async retry source regression.
Run: python -m unittest tests/test_c06_unified_back_source.py -v
Source-contract tests only; native WebView2/.NET/Windows E07 remain NOT_RUN.
"""
from pathlib import Path
import unittest

SRC=(Path(__file__).resolve().parents[1] / "coordination/e06/OneHostP02WebView2Bridge.cs").read_text(encoding="utf-8")

class NativeBackSource(unittest.TestCase):
    def test_exact_home_is_only_pending_return(self):
        self.assertIn("private bool ExactShellReturn(string? raw)", SRC)
        self.assertIn("string.Equals(uri.AbsoluteUri, _virtualOrigin.AbsoluteUri, StringComparison.Ordinal)", SRC)
        self.assertIn("_nativeReturnPending && ExactShellReturn(url)", SRC)
        self.assertIn("_nativeReturnPending && ExactShellReturn(e.Uri)", SRC)
        self.assertIn("_nativeReturnPending && ExactShellReturn(_web.Source)", SRC)
        for arg in ("url", "e.Uri", "_web.Source"):
            self.assertNotIn("_nativeReturnPending && Trusted("+arg+")", SRC)

    def test_failed_or_redirected_return_clears_retry_only(self):
        start=SRC.index("private void OnNavigationCompleted(")
        end=SRC.index("private void OnNewWindowRequested(",start)
        handler=SRC[start:end]
        self.assertIn("!e.IsSuccess || !ExactShellReturn(_web.Source)",handler)
        self.assertIn("_nativeReturnPending = false;",handler)
        self.assertNotIn("_externalMode = false",handler)
        self.assertNotIn("IsWebMessageEnabled = true",handler)

    def test_event_lifecycle_symmetry(self):
        self.assertEqual(SRC.count("_web.NavigationCompleted += OnNavigationCompleted;"),1)
        self.assertEqual(SRC.count("_web.NavigationCompleted -= OnNavigationCompleted;"),1)

    def test_authority_and_single_browser_preserved(self):
        self.assertIn("_web.Navigate(_virtualOrigin.AbsoluteUri); return true;",SRC)
        self.assertIn("e.Handled = true;",SRC)
        self.assertIn("if (Volatile.Read(ref _disposed) != 0 || _externalMode ||",SRC)
        # Current bridge uses an explicit block so the rejected redirect returns
        # before document revocation. Preserve that stronger fail-closed shape.
        self.assertIn("if (!IsApprovedExternal(e.Uri))",SRC)
        self.assertIn("e.Cancel = true;",SRC)
        start=SRC.index("private void OnNavigationStarting(")
        end=SRC.index("private void OnNavigationCompleted(",start)
        handler=SRC[start:end]
        denied=handler.index("if (!IsApprovedExternal(e.Uri))")
        cancelled=handler.index("e.Cancel = true;",denied)
        returned=handler.index("return;",cancelled)
        revoked=handler.index("RevokeDocument();",returned)
        self.assertLess(denied,cancelled)
        self.assertLess(cancelled,returned)
        self.assertLess(returned,revoked)
        self.assertIn("private bool NativeSidMatches()", SRC)
        self.assertIn("_nativeAcl(_ownerWindowsSid, route)",SRC)
        self.assertIn("_document.Cancel();",SRC)
        self.assertIn("_web.Settings.IsWebMessageEnabled = false;",SRC)

if __name__ == "__main__":
    unittest.main()
