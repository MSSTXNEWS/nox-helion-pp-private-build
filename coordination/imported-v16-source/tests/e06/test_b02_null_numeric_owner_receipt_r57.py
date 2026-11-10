"""B02 SOURCE_ONLY regression for null/numeric owner proof in ORIGINAL WPF IPC.
Never treats a source check as Windows E06 or installed E07 acceptance.
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEGACY = ROOT / "coordination/e06/MainWindow.NativeP02.cs"
BRIDGE = ROOT / "coordination/e06/OneHostP02WebView2Bridge.cs"

class MissingNativeProofContract(unittest.TestCase):
    def test_legacy_rejects_null_undefined_numeric(self):
        source = LEGACY.read_text(encoding="utf-8")
        section = source.split("private static bool LegacyOwnerDenial(", 1)[1].split("private async Task DispatchLegacyNativeAsync", 1)[0]
        guard = "if (value.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined or JsonValueKind.Number) return true;"
        self.assertEqual(section.count(guard), 1)
        self.assertIn("LegacyOwnerDenial(p.Value,depth+1)", section)
        self.assertLess(section.index("if (depth>=4)"), section.index(guard))
        self.assertLess(section.index(guard), section.index("if (value.ValueKind!=JsonValueKind.Object) return false;"))

    def test_bridge_rejects_null_undefined_numeric(self):
        source = BRIDGE.read_text(encoding="utf-8")
        section = source.split("private static bool NativeResultExplicitlyDenied(", 1)[1].split("private static bool NativeAutostartReceiptMatches(", 1)[0]
        guard = "if (result.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined or JsonValueKind.Number) return true;"
        self.assertEqual(section.count(guard), 1)
        self.assertIn("NativeResultExplicitlyDenied(field.Value, depth + 1)", section)
        self.assertLess(section.index("if (depth >= 4)"), section.index(guard))
        self.assertLess(section.index(guard), section.index("if (result.ValueKind != JsonValueKind.Object) return false;"))

if __name__ == "__main__":
    unittest.main()
