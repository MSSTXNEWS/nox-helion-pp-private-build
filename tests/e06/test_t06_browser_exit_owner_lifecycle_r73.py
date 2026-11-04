"""R73: original WPF owner must revoke dead browser's native IPC before any rebind.

Source-level checks only. A Windows WebView2 installed test and E07 remain mandatory.
"""
from pathlib import Path
import hashlib
import unittest

ROOT = Path(__file__).resolve().parents[2] / "coordination" / "e06"
OWNER = ROOT / "MainWindow.NativeP02.cs"
BRIDGE = ROOT / "OneHostP02WebView2Bridge.cs"
STAGER = ROOT / "stage_native_p02.py"
BUILDER = ROOT / "build_onehost_installer.ps1"
COMPILER = ROOT / "t06_compile_original_wpf_p02.py"

class BrowserExitOwnerLifecycleR73(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = OWNER.read_text(encoding="utf-8")
        cls.bridge = BRIDGE.read_text(encoding="utf-8")
        cls.stage = STAGER.read_text(encoding="utf-8")
        cls.builder = BUILDER.read_text(encoding="utf-8")
        cls.compiler = COMPILER.read_text(encoding="utf-8")

    def test_browser_failure_fences_before_owner_callback(self):
        src = self.bridge.split("private void OnProcessFailed(", 1)[1]
        self.assertLess(src.index("_browserProcessLost = true;"),
                        src.index("_onBrowserProcessExited?.Invoke(_web);"))
        self.assertIn("CoreWebView2ProcessFailedKind.BrowserProcessExited", src)

    def test_owner_shuts_down_only_exact_dead_core(self):
        block = self.owner.split("private void OnNativeP02BrowserProcessExited(", 1)[1]
        block = block.split("private void OnNativeP02NavigationStarting(", 1)[0]
        self.assertIn("Dispatcher.CheckAccess()", block)
        self.assertIn("ReferenceEquals(_nativeP02Core, failedCore)", block)
        self.assertLess(block.index("_failedNativeP02Core = failedCore;"),
                        block.index("ShutdownNativeP02();"))

    def test_only_fresh_original_core_can_rebind(self):
        init = self.owner.split("private async Task InitializeNativeP02Async(", 1)[1]
        self.assertIn("ReferenceEquals(_failedNativeP02Core, core)", init)
        self.assertIn("P02_BROWSER_CLOSED_CORE_RECREATE_REQUIRED", init)
        self.assertIn("_nativeModelsStop = new CancellationTokenSource();", init)
        self.assertIn("OnNativeP02BrowserProcessExited);", init)
        self.assertLess(init.index("if(!handshake.Accepted)"),
                        init.index("_nativeP02Core=core;"))

    def test_subscription_lifecycle_detaches_real_handlers(self):
        for event in ("NavigationStarting", "SourceChanged", "ContentLoading"):
            name = "OnNativeP02" + event
            with self.subTest(event=event):
                self.assertIn("core." + event + " += " + name + ";", self.owner)
                self.assertIn("web." + event + " -= " + name + ";", self.owner)
        self.assertNotIn("core.NavigationStarting += (_,_) =>", self.owner)

    def test_original_security_and_stop_still_present(self):
        for marker in ("NativeSidMatches()", "StopRevokedChatAsync()",
                       "_browserProcessLost", "RevokeDocument()"):
            self.assertIn(marker, self.bridge)
        for marker in ("CreateA1PrivateConsentReceipt", "NativeP02Acl(",
                       "ShutdownNativeP02()", "NativePythonSha"):
            self.assertIn(marker, self.owner)
        self.assertNotIn("new WebView2(", self.owner)

    def test_all_original_owner_pins_reconciled(self):
        # Derive the exact original Git blob identity; static test pins go stale after merges.
        def git_blob(path):
            data = path.read_bytes()
            return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data).hexdigest()
        owner_blob = git_blob(OWNER)
        bridge_blob = git_blob(BRIDGE)
        stager_blob = git_blob(STAGER)
        self.assertIn(owner_blob, self.stage)
        for token in (owner_blob, bridge_blob, stager_blob):
            self.assertIn(token, self.builder)
            self.assertIn(token, self.compiler)

if __name__ == "__main__":
    unittest.main()
