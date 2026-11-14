"""B02 source-only regression: scalar/false native owner receipts cannot become a positive ACK.
Windows C# execution and the installed E06/E07 remain independent physical gates.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "coordination/e06/OneHostP02WebView2Bridge.cs"
LEGACY = ROOT / "coordination/e06/MainWindow.NativeP02.cs"


class ScalarOwnerAckFence(unittest.TestCase):
    def test_webview2_rejects_scalar_denial_before_object_parsing(self):
        text = BRIDGE.read_text(encoding="utf-8")
        start = text.index("private static bool NativeResultExplicitlyDenied(")
        end = text.index("private async void OnWebMessageReceived(", start)
        method = text[start:end]
        self.assertLess(method.index("NativeOwnerStatusDenied(result.GetString())"),
                        method.index("if (result.ValueKind != JsonValueKind.Object) return false;"))
        self.assertIn("if (result.ValueKind == JsonValueKind.False) return true;", method)
        self.assertIn("NativeResultExplicitlyDenied(child, depth + 1)", method)
        self.assertIn("NativeResultExplicitlyDenied(field.Value, depth + 1)", method)
        self.assertIn("if (ownerAccepted && NativeResultExplicitlyDenied(ownerResult.Result))", text)
        self.assertIn("if (accepted && NativeResultExplicitlyDenied(result.Result))", text)

    def test_legacy_home_rejects_scalar_denial_before_object_parsing(self):
        text = LEGACY.read_text(encoding="utf-8")
        start = text.index("private static bool LegacyOwnerDenial(")
        end = text.index("private async Task DispatchLegacyNativeAsync(", start)
        method = text[start:end]
        self.assertLess(method.index("LegacyOwnerStatusDenied(value.GetString())"),
                        method.index("if (value.ValueKind!=JsonValueKind.Object) return false;"))
        self.assertIn("if (value.ValueKind==JsonValueKind.False) return true;", method)
        self.assertIn("LegacyOwnerDenial(child,depth+1)", method)
        self.assertIn("LegacyOwnerDenial(p.Value,depth+1)", method)
        self.assertIn("LegacyOwnerDenial(result.Result)", text)

if __name__ == "__main__":
    unittest.main()
