"""R83: original WPF native-owner routes and real MENU STOP; SOURCE contracts only.

Windows .NET compile, installed WebView2/IPC, and independent E07 are separate gates.
"""
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
E06 = ROOT / "coordination" / "e06"
OWNER = E06 / "MainWindow.NativeP02.cs"
BRIDGE = E06 / "OneHostP02WebView2Bridge.cs"
BUILDER = E06 / "build_onehost_installer.ps1"
COMPILER = E06 / "t06_compile_original_wpf_p02.py"


def git_blob(path):
    raw = path.read_bytes()
    if b"\r\n" in raw and b"\r" not in raw.replace(b"\r\n", b""):
        raw = raw.replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


class OriginalNativeOwnerMenuStopR83(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = OWNER.read_text(encoding="utf-8")
        cls.bridge = BRIDGE.read_text(encoding="utf-8")
        cls.builder = BUILDER.read_text(encoding="utf-8")
        cls.compiler = COMPILER.read_text(encoding="utf-8")

    def test_all_existing_wpf_only_routes_reach_original_owner(self):
        clause = self.bridge.split("if (_nativeOwnerAction is not null &&", 1)[1].split("var ownerResult", 1)[0]
        for route in ("browser.navidle", "menu.dispatch", "menu.binding",
                      "selfwrite.ack", "selflearn.ack"):
            with self.subTest(route=route):
                self.assertIn('route=="' + route + '"', clause)
        self.assertIn("_nativeOwnerAction(route, payload.Clone(), cancel)", self.bridge)

    def test_menu_stop_delegates_to_real_native_onehost(self):
        stop = self.owner.split('if (route == "menu.binding") {', 1)[1].split('if (route == "menu.dispatch") {', 1)[0]
        self.assertIn('await DispatchNativeOwnerAsync(', stop)
        self.assertIn('"chat.stop", JsonSerializer.SerializeToElement(new { }), cancel', stop)
        self.assertIn('NativeP02Acl(stopSid, "chat.stop")', stop)
        self.assertIn('if (!nativeStop.Accepted)', stop)
        self.assertIn('status = "MENU_STOP_REQUESTED"', stop)
        self.assertNotIn('status = "MENU_STOP_ACK"', stop)

    def test_stop_overtakes_modal_and_rejects_stale_completion(self):
        self.assertIn('!isMenuStop &&\n                !await _nativeConsent(', self.bridge)
        self.assertIn('route == "chat.stop" || isMenuStop)\n                Interlocked.Increment(ref _streamEpoch)', self.bridge)
        self.assertIn('route == "chat.stop" || isMenuStop)\n                    ownerState = ownerResult.Accepted ? "STOP_REQUESTED" : "HOLD";', self.bridge)
        self.assertIn('payload.EnumerateObject().Count() == 1', self.bridge)
        self.assertIn('MENU_STOP_PAYLOAD_HOLD', self.owner)

    def test_original_builder_and_compiler_pins_are_coherent(self):
        for filename, sha in ((OWNER, git_blob(OWNER)), (BRIDGE, git_blob(BRIDGE))):
            with self.subTest(path=filename.name):
                self.assertIn(("sha='" if filename == OWNER else "blob='") + sha + "'", self.builder)
                self.assertIn('"' + filename.name + '":"' + sha + '"',
                              self.compiler)
        self.assertIn('T06_CANONICAL_OWNER_STAGING_PINS_DIVERGED', self.compiler)


if __name__ == "__main__":
    unittest.main()
