"""B02 SOURCE_ONLY guard: malformed WebView2 provider must fail closed.

This test inspects ORIGINAL WPF sources; it does not claim Windows execution.
Actual .NET JsonElement.GetString raises on Number/True/False/Object/Array.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "coordination/e06/MainWindow.NativeP02.cs"
STAGE = ROOT / "coordination/e06/stage_native_p02.py"
COMPILER = ROOT / "coordination/e06/t06_compile_original_wpf_p02.py"
BUILDER = ROOT / "coordination/e06/build_onehost_installer.ps1"


class LegacyProviderTypeGuard(unittest.TestCase):
    def test_malformed_provider_is_consumed_before_getstring(self):
        source = SOURCE.read_text(encoding="utf-8")
        start = source.index('if (name == "chatStart" && root.TryGetProperty("provider", out var provider))')
        end = source.index('if (name is not ("chatModels" or "chatStart" or "chatStop" or "openModelCenter"))', start)
        admission = source[start:end]
        guard = "if (provider.ValueKind != JsonValueKind.String) return true;"
        passthrough = 'string.Equals(provider.GetString(), "OPENAI", StringComparison.OrdinalIgnoreCase)) return false;'
        self.assertEqual(admission.count(guard), 1)
        self.assertEqual(admission.count("provider.GetString()"), 1)
        self.assertLess(admission.index(guard), admission.index(passthrough))
        self.assertEqual(source.count("provider.GetString()"), 1)

    def test_existing_native_stop_and_owner_consent_unchanged(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('if (name == "chatStop") StopChat(GetString(root, "chatId"));', source)
        self.assertIn('!await ConfirmP02NativeAsync(route,payload,CancellationToken.None)', source)
        self.assertIn('NativeP02Acl(sid, route)', source)

    def test_dependent_pin_dag_maintains_fail_closed(self):
        import hashlib
        def blob(raw):
            return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        wp=blob(SOURCE.read_bytes())
        st=blob(STAGE.read_bytes())
        self.assertIn('ADDON_SHA="' + wp + '"', STAGE.read_text(encoding="utf-8"))
        self.assertIn('"coordination/e06/MainWindow.NativeP02.cs":"' + wp + '"', COMPILER.read_text(encoding="utf-8"))
        self.assertIn('"coordination/e06/stage_native_p02.py":"' + st + '"', COMPILER.read_text(encoding="utf-8"))
        build=BUILDER.read_text(encoding="utf-8")
        self.assertIn("sha='" + wp + "'", build)
        self.assertIn("sha='" + st + "'", build)


if __name__ == "__main__":
    unittest.main()
