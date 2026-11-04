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
        self.assertEqual(code.count("CheckedExecutable(executable));"), 2)

    def test_actual_staged_original_csharp_blob_is_re_pinned(self):
        code = SOURCE.read_bytes()
        builder = BUILDER.read_text(encoding="utf-8")
        declaration = "@{relative='coordination/e06/NoXAutostart.cs';dest='Integration/NoXAutostart.cs';blob='" + git_blob(code) + "'}"
        self.assertIn(declaration, builder)
        self.assertEqual(builder.count("relative='coordination/e06/NoXAutostart.cs'"), 1)

if __name__ == "__main__":
    unittest.main()
