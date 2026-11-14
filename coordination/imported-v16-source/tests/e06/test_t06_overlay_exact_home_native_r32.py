"""Original T06 same-VM WebView2 overlay: native messages require exact HOME.

Source-level regression on the real original checkout, NOT a Windows runtime or E07
acceptance. The separate canonical E06 bridge already checks exact mapped HOME;
the original GitLab T06 compiler stages this narrower legacy overlay instead.
"""
import hashlib
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "coordination/e06/t06_windows_overlay/OneHostP02WebView2Bridge.cs"
COMPILER = ROOT / "coordination/e06/t06_compile_original_wpf_p02.py"
MAINWINDOW = ROOT / "coordination/e06/t06_windows_overlay/MainWindow.NativeP02.cs"


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class OriginalOverlayExactHomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = OVERLAY.read_bytes()
        cls.bridge = cls.raw.decode("utf-8-sig")
        cls.compiler = COMPILER.read_text("utf-8")
        cls.mainwindow = MAINWINDOW.read_text("utf-8-sig")

    def test_original_windows_staging_pins_actual_overlay(self):
        match = re.search(r'"OneHostP02WebView2Bridge.cs":"([0-9a-f]{40})"', self.compiler)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), git_blob(self.raw))
        self.assertIn('(SRC/"OneHostP02WebView2Bridge.cs").read_bytes()', self.compiler)

    def test_only_exact_original_mapped_home_is_authorized(self):
        self.assertEqual(self.bridge.count("private bool ExactShellHome("), 1)
        self.assertIn("Trusted(raw) && Uri.TryCreate(raw, UriKind.Absolute, out var uri) &&", self.bridge)
        self.assertIn("string.Equals(uri.AbsoluteUri, _virtualOrigin.AbsoluteUri, StringComparison.Ordinal)", self.bridge)
        self.assertIn('if (!Trusted(e.Uri)) e.Cancel = true;', self.bridge)
        # Same-origin non-HOME pages may navigate; they cannot obtain native authority.

    def test_raw_message_and_late_ack_both_require_exact_home(self):
        self.assertIn("!ExactShellHome(e.Source) || !ExactShellHome(_web.Source)", self.bridge)
        self.assertIn("ExactShellHome(source) && ExactShellHome(_web.Source)", self.bridge)
        self.assertIn("Interlocked.Read(ref _epoch) == epoch", self.bridge)
        self.assertIn('string.Equals(source, _web.Source, StringComparison.Ordinal)', self.bridge)

    def test_original_consent_sid_acl_stop_and_host_contract_survive(self):
        for snippet in [
            'NativeSidMatches()', '_nativeAcl(_ownerWindowsSid, route)',
            '_nativeConsent(route, _lifetime.Token)',
            'RequestAsync("chat.stop"', 'StopRevokedChatAsync()',
            'route == "chat.stop" ? "STOP_REQUESTED" : "COMPLETED"',
            'internal sealed class OneHostP02WebView2Bridge : IDisposable',
        ]:
            self.assertIn(snippet, self.bridge)
        self.assertIn("ConfirmP02NativeAsync(string route, CancellationToken cancel)", self.mainwindow)
        self.assertIn("new OneHostP02WebView2Bridge(core,", self.mainwindow)


if __name__ == "__main__":
    unittest.main()
