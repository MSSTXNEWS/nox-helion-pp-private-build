"""D06 original WPF SETTINGS cannot fall back to the Python worker.

Source-contract regression only. Windows HKCU/consent/UIA requires physical E07.
"""
from pathlib import Path
import hashlib
import unittest

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "coordination/e06/OneHostP02WebView2Bridge.cs"
BUILDER = ROOT / "coordination/e06/build_onehost_installer.ps1"
COMPILER = ROOT / "coordination/e06/t06_compile_original_wpf_p02.py"

class TestAutostartNativeOwnerGuard(unittest.TestCase):
    def test_missing_owner_fails_closed_before_consent_and_python(self):
        source = BRIDGE.read_text(encoding="utf-8")
        check = 'route == "system.autostart" && _nativeOwnerAction is null'
        hold = 'Reply(source, epoch, id, route, "HOLD", "NOX_AUTOSTART_NATIVE_OWNER_REQUIRED");'
        self.assertEqual(source.count(check), 1)
        self.assertEqual(source.count(hold), 1)
        start = source.index('private async void OnWebMessageReceived')
        i = source.index(check, start)
        self.assertLess(source.index('if (!NativeSidMatches() || !_nativeAcl', start), i)
        self.assertLess(i, source.index('!await _nativeConsent(route, payload.Clone(), cancel)', i))
        self.assertLess(i, source.index('_existingPipe.RequestAsync(', i))
        self.assertIn('return;', source[i:source.index('}', i)])
        self.assertIn('route=="system.autostart"', source[source.index('if (_nativeOwnerAction is not null'):])
    def test_exact_builder_and_compiler_git_pins(self):
        source = BRIDGE.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(source)).encode() + bytes([0]) + source).hexdigest()
        self.assertIn("blob='" + blob + "'", BUILDER.read_text(encoding="utf-8"))
        self.assertIn('"coordination/e06/OneHostP02WebView2Bridge.cs":"' + blob + '"',
                      COMPILER.read_text(encoding="utf-8"))

    def test_native_autostart_receipt_bound_to_request_and_hkcu_mode(self):
        source = BRIDGE.read_text(encoding="utf-8")
        self.assertIn("private static bool NativeAutostartReceiptMatches", source)
        method = source.split("private static bool NativeAutostartReceiptMatches", 1)[1].split(
            "private async void OnWebMessageReceived", 1)[0]
        self.assertIn("requested.Length > 1", method)
        self.assertIn('requested[0].Name != "enabled"', method)
        self.assertIn("fields.Length != 2", method)
        self.assertIn("Distinct(StringComparer.Ordinal).Count() != 2", method)
        self.assertIn('receipt.TryGetProperty("enabled", out var actual)', method)
        self.assertIn('receipt.TryGetProperty("readOnly", out var readOnly)', method)
        self.assertIn("if (requested.Length == 0) return readOnly.GetBoolean();", method)
        self.assertIn("!readOnly.GetBoolean()", method)
        self.assertIn("requested[0].Value.GetBoolean() == actual.GetBoolean()", method)
        guard = 'if (ownerAccepted && route == "system.autostart" &&'
        self.assertEqual(source.count(guard), 1)
        self.assertLess(source.index("NativeResultExplicitlyDenied(ownerResult.Result)"),
                        source.index(guard))
        self.assertLess(source.index(guard),
                        source.index('var ownerState = ownerAccepted ? "COMPLETED" : "HOLD";'))

if __name__ == "__main__":
    unittest.main()
