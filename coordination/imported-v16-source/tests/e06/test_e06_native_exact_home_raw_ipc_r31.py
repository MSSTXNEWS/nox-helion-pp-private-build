"""Source-level fail-closed exact-HOME boundary for original E06 OneHost WebView2.

Not a Windows compiler, signed consent, native IPC or installed E07 acceptance.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "coordination/e06/OneHostP02WebView2Bridge.cs"
BUILDER = ROOT / "coordination/e06/build_onehost_installer.ps1"
REVIEWED_STAGE = ROOT / "coordination/e06/t06_compile_original_wpf_p02.py"
BRIDGE_BLOB = "dee767ec4cb4a8210b6a6feb28f13730760521a7"
REGISTRY_BLOCK_SHA256 = "e9d91ac3ed0bf5437ff38f07d2179a9e7a130835c4d0d1be49fa2c563f0e8bd1"

def section(text, start, end):
    if text.count(start) != 1 or text.count(end) != 1:
        raise AssertionError("E06_WEBVIEW2_BRIDGE_SOURCE_ANCHOR_DRIFT")
    return text.split(start, 1)[1].split(end, 1)[0]

class OriginalOneHostExactHomeSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = BRIDGE.read_text(encoding="utf-8")
        cls.builder = BUILDER.read_text(encoding="utf-8")
        cls.stage = REVIEWED_STAGE.read_text(encoding="utf-8")

    def test_exact_home_predicate_not_only_same_origin(self):
        body = section(self.source, "private bool ExactShellReturn(string? raw)", "private void RevokeDocument()")
        self.assertIn("Trusted(raw)", body)
        self.assertIn("string.Equals(uri.AbsoluteUri, _virtualOrigin.AbsoluteUri, StringComparison.Ordinal)", body)

    def test_untrusted_same_origin_path_cannot_open_native_external(self):
        body = section(self.source, "internal bool TryOpenReviewedExternal(", "internal bool ReturnToReviewedShell()")
        self.assertIn("!ExactShellReturn(_web.Source) || !NativeSidMatches()", body)
        self.assertNotIn("!Trusted(_web.Source) || !NativeSidMatches()", body)
        self.assertIn("nativeGestureVerified", body)

    def test_raw_ipc_rejects_non_home_sender_or_active_document(self):
        body = section(self.source, "private async void OnWebMessageReceived(", "public void Dispose()")
        self.assertIn("!ExactShellReturn(e.Source) || !ExactShellReturn(_web.Source)", body)
        self.assertNotIn("!Trusted(e.Source) || !Trusted(_web.Source)", body)
        self.assertIn('kinds[0].Value.GetString()', body)
        self.assertIn("p02.native", body)

    def test_late_ack_and_stream_recheck_exact_home(self):
        body = section(self.source, "private bool IsCurrent(string source, long epoch)", "private void Reply(")
        self.assertIn("ExactShellReturn(source) && ExactShellReturn(_web.Source)", body)
        self.assertIn("Interlocked.Read(ref _epoch) == epoch", body)
        self.assertIn("string.Equals(source, _web.Source, StringComparison.Ordinal)", body)

    def test_original_builder_bridge_pin_and_webview2_registry_are_preserved(self):
        self.assertEqual(self.builder.count("blob='" + BRIDGE_BLOB + "'"), 1)
        self.assertNotIn("blob='56475efc920f935677e6bab258aa211b1ae7f344'", self.builder)
        self.assertIn(REGISTRY_BLOCK_SHA256, self.stage)

    def test_owner_sid_acl_consent_and_stop_remain_required(self):
        for guard in ("NativeSidMatches()", "_nativeAcl(", "_nativeConsent(", "chat.stop", "RevokeDocument()", "OnNavigationCompleted", "OnProcessFailed"):
            self.assertIn(guard, self.source)
        self.assertIn("_externalMode && _nativeReturnPending", self.source)

if __name__ == "__main__":
    unittest.main()
