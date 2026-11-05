"""Source-level G2 regression for the original HKCU Run uninstall helper.
No Windows Registry is edited; physical NSIS/E07 acceptance remains separate.
"""
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "coordination/e06/NoXAutostart.cs"
BUILDER = ROOT / "coordination/e06/build_onehost_installer.ps1"

def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()

class NoXAutostartUninstallSource(unittest.TestCase):
    def test_deleted_executable_only_allowed_for_exact_uninstall_entry(self):
        code = SOURCE.read_text(encoding="utf-8")
        self.assertIn("bool allowDeletedOnUninstall = false", code)
        self.assertIn("(!allowDeletedOnUninstall && !File.Exists(path))", code)
        self.assertEqual(code.count("allowDeletedOnUninstall:true"), 1)
        self.assertIn("internal static void RemoveOnUninstall", code)
        self.assertIn("string.Equals(existing, expected, StringComparison.OrdinalIgnoreCase)", code)
        self.assertIn("Registry.CurrentUser.OpenSubKey(RunKey, writable:true)", code)
        self.assertIn("if (!nativeConsent) throw", code)

    def test_original_absolute_path_and_reparse_checks_stay_enabled(self):
        code = SOURCE.read_text(encoding="utf-8")
        self.assertIn("!Path.IsPathFullyQualified(executable)", code)
        self.assertIn("executable.Contains('\"')", code)
        self.assertIn('path.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)', code)
        self.assertIn("item.Exists && (item.Attributes & FileAttributes.ReparsePoint)", code)
        self.assertEqual(code.count("CheckedExecutable(executable));"), 1)

    def test_actual_staged_original_csharp_blob_is_re_pinned(self):
        code = SOURCE.read_bytes()
        builder = BUILDER.read_text(encoding="utf-8")
        declaration = "@{relative='coordination/e06/NoXAutostart.cs';dest='Integration/NoXAutostart.cs';blob='" + git_blob(code) + "'}"
        self.assertIn(declaration, builder)
        self.assertEqual(builder.count("relative='coordination/e06/NoXAutostart.cs'"), 1)


    def test_foreign_hkcu_run_value_types_are_no_loss_and_write_is_verified(self):
        code = SOURCE.read_text(encoding="utf-8")
        # REG_DWORD, REG_BINARY and even REG_NONE are owned by somebody else.
        # Mere "as string" cannot distinguish missing vs foreign Run values.
        self.assertIn("Array.Exists(key.GetValueNames()", code)
        self.assertIn("key.GetValueKind(Entry) != RegistryValueKind.String", code)
        self.assertIn("key.GetValue(Entry) is not string old", code)
        self.assertNotIn("var old = key.GetValue(Entry) as string;", code)
        self.assertIn('NOX_AUTOSTART_FOREIGN_ENTRY_HOLD', code)
        self.assertEqual(code.count("key.GetValueKind(Entry) == RegistryValueKind.String"), 1)
        self.assertIn("var persisted = ReadOwnedState(executable);", code)
        self.assertIn("if (persisted != enabled) throw new IOException", code)
        self.assertIn("NOX_AUTOSTART_PERSISTENCE_UNVERIFIED", code)
        self.assertIn("if (!nativeConsent) throw", code)
        self.assertIn("key.DeleteValue(Entry, throwOnMissingValue:false);", code)

    def test_disable_missing_entry_is_non_mutating_and_same_state_is_idempotent(self):
        code = SOURCE.read_text(encoding="utf-8")
        method = code[code.index("internal static bool SetEnabled"):code.index("internal static void RemoveOnUninstall")]
        self.assertLess(method.index("if (!nativeConsent)"), method.index("using var key = enabled"))
        self.assertIn("? Registry.CurrentUser.CreateSubKey(RunKey, writable:true)", method)
        self.assertIn(": Registry.CurrentUser.OpenSubKey(RunKey, writable:true)", method)
        self.assertIn("if (!enabled && !ReadOwnedState(executable)) return false;", method)
        self.assertLess(method.index("if (key is null)"), method.index("key.GetValueNames()"))
        self.assertLess(method.index("NOX_AUTOSTART_FOREIGN_ENTRY_HOLD"), method.index("if (hasEntry == enabled)"))
        self.assertLess(method.index("if (hasEntry == enabled)"), method.index("key.SetValue("))
        self.assertIn("var unchanged = ReadOwnedState(executable);", method)
        self.assertIn("NOX_AUTOSTART_PERSISTENCE_UNVERIFIED", method)


    def test_same_state_on_off_read_only_before_hkcu_write(self):
        code = SOURCE.read_text(encoding="utf-8")
        method = code[code.index("internal static bool SetEnabled"):code.index("internal static void RemoveOnUninstall")]
        consent = method.index("if (!nativeConsent)")
        no_op = method.index("if (ReadOwnedState(executable) == enabled) return enabled;")
        writable = method.index("using var key = enabled")
        self.assertLess(consent, no_op)
        self.assertLess(no_op, writable)
        self.assertLess(writable, method.index("NOX_AUTOSTART_FOREIGN_ENTRY_HOLD"))
        self.assertIn("var persisted = ReadOwnedState(executable);", method)

    def test_uninstall_foreign_entry_does_not_request_write_access(self):
        code = SOURCE.read_text(encoding="utf-8")
        method = code[code.index("internal static void RemoveOnUninstall"):]
        readonly = method.index("using var probe = Registry.CurrentUser.OpenSubKey(RunKey, writable:false)")
        guard = method.index("!string.Equals(candidate, expected, StringComparison.OrdinalIgnoreCase)")
        early_return = method.index("return;", guard)
        writable = method.index("using var key = Registry.CurrentUser.OpenSubKey(RunKey, writable:true)")
        second_match = method.index("string.Equals(existing, expected, StringComparison.OrdinalIgnoreCase)")
        delete = method.index("key.DeleteValue(Entry", second_match)
        self.assertTrue(readonly < guard < early_return < writable < second_match < delete)
        self.assertIn("probe.GetValueKind(Entry) != RegistryValueKind.String", method)
        self.assertIn("key.GetValueKind(Entry) == RegistryValueKind.String", method)

    def test_uninstall_owned_entry_must_disappear_or_hold(self):
        code = SOURCE.read_text(encoding="utf-8")
        method = code[code.index("internal static void RemoveOnUninstall"):]
        # Read-only owner probe first: no mutation of foreign values.
        self.assertLess(method.index("using var probe = "), method.index("using var key = "))
        self.assertLess(method.index("!string.Equals(candidate, expected"), method.index("using var key = "))
        # Owned entry + missing writable HKCU is a HOLD, not false success.
        self.assertIn('if (key is null)', method)
        self.assertIn("NOX_AUTOSTART_UNINSTALL_HKCU_WRITE_UNAVAILABLE", method)
        self.assertLess(method.index("if (key is null)"), method.index("key.DeleteValue("))
        # Original exact owner comparison must guard the only removal.
        self.assertLess(method.index("string.Equals(existing, expected"), method.index("key.DeleteValue("))
        # Real post-delete registry readback; don't remove a concurrent foreign value.
        self.assertLess(method.index("key.DeleteValue("), method.index("using var verify = "))
        self.assertIn("verify.GetValueKind(Entry) == RegistryValueKind.String", method)
        self.assertIn("string.Equals(remaining, expected, StringComparison.OrdinalIgnoreCase)", method)
        self.assertIn("NOX_AUTOSTART_UNINSTALL_PERSISTENCE_UNVERIFIED", method)
        self.assertEqual(method.count("key.DeleteValue("), 1)
        # Concurrent foreign Run replacements must be preserved AND fail closed.
        self.assertIn("NOX_AUTOSTART_UNINSTALL_OWNER_CHANGED_HOLD", method)
        self.assertIn("NOX_AUTOSTART_UNINSTALL_CONCURRENT_FOREIGN_ENTRY_HOLD", method)
        self.assertLess(method.index("string.Equals(existing, expected"), method.index("key.DeleteValue("))
        self.assertLess(method.index("key.DeleteValue("), method.index("NOX_AUTOSTART_UNINSTALL_CONCURRENT_FOREIGN_ENTRY_HOLD"))
        self.assertLess(method.index("key.DeleteValue("), method.index("NOX_AUTOSTART_UNINSTALL_OWNER_CHANGED_HOLD"))

    def test_legacy_status_foreign_entry_fails_closed(self):
        code = SOURCE.read_text(encoding="utf-8")
        method = code[code.index("internal static bool IsEnabled("):code.index("internal static bool ReadOwnedState(")]
        self.assertIn("return ReadOwnedState(executable);", method)
        self.assertNotIn("Registry.CurrentUser.OpenSubKey", method)
        reader = code[code.index("internal static bool ReadOwnedState("):code.index("internal static bool SetEnabled(")]
        self.assertIn("NOX_AUTOSTART_FOREIGN_ENTRY_HOLD", reader)
        self.assertIn("key.GetValueKind(Entry) != RegistryValueKind.String", reader)
        self.assertIn("!string.Equals(stored, command, StringComparison.OrdinalIgnoreCase)", reader)
        self.assertIn("if (!hasEntry) return false;", reader)

if __name__ == "__main__":
    unittest.main()
