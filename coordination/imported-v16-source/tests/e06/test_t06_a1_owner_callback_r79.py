"""R79: exact original WPF -> OneHost A1 owner callback regression (source-level only).

Requires the real Windows WPF/WebView2 integration for runtime acceptance.
"""
import hashlib
from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parents[2]
E06 = REPO / "coordination" / "e06"
BRIDGE = E06 / "OneHostP02WebView2Bridge.cs"
OWNER = E06 / "MainWindow.NativeP02.cs"
BUILDER = E06 / "build_onehost_installer.ps1"
COMPILER = E06 / "t06_compile_original_wpf_p02.py"

def git_blob(path):
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

class A1OwnerCallbackR79(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge = BRIDGE.read_text(encoding="utf-8")
        cls.owner = OWNER.read_text(encoding="utf-8")
        cls.builder = BUILDER.read_text(encoding="utf-8")
        cls.compiler = COMPILER.read_text(encoding="utf-8")

    def test_a1_and_training_import_dispatch_through_same_native_owner(self):
        clause = self.bridge.split("if (_nativeOwnerAction is not null &&", 1)[1].split("var ownerResult", 1)[0]
        for exact in ('route=="chat.commands"', 'ownerCommand=="training.import"',
                      'ownerCommand=="selfbuilder.a1.boot"', 'ownerCommand=="selfbuilder.a1.tick"'):
            self.assertIn(exact, clause)
        self.assertIn("_nativeOwnerAction(route, payload.Clone(), cancel)", self.bridge)
        self.assertIn("var result = await _existingPipe.RequestAsync(", self.bridge)

    def test_private_hmac_ticket_is_consumed_by_real_mainwindow(self):
        for witness in ("CreateA1PrivateConsentReceipt(a1Name)",
                        "RequestWpfApprovedA1Async(a1Name,ticket,cancel)",
                        "_a1OwnerApprovedAction=a1Command",
                        "_a1OwnerApprovedAction=null; // WPF approval is consumed once.",
                        "HMACSHA256.HashData(secret,Encoding.ASCII.GetBytes(transcript))"):
            self.assertIn(witness, self.owner)

    def test_original_sid_acl_consent_and_document_fences_retained(self):
        for witness in ("AuthorityFields.Contains(p.Name)",
                        "!await _nativeConsent(route, payload.Clone(), cancel)",
                        "!IsCurrent(source, epoch) || !NativeSidMatches()",
                        "_nativeAcl(_ownerWindowsSid, route)"):
            self.assertIn(witness, self.bridge)
        self.assertIn("!NativeP02Acl(sid,route)", self.owner)

    def test_original_builder_and_compiler_pin_this_exact_bridge_blob(self):
        digest = git_blob(BRIDGE)
        self.assertIn("blob='" + digest + "'", self.builder)
        self.assertIn('"coordination/e06/OneHostP02WebView2Bridge.cs":"' + digest + '"', self.compiler)

if __name__ == "__main__":
    unittest.main()
