"""D06 R5 native HKCU idempotent owner-readback guard. SOURCE_ONLY.
Windows physical SID/ACL, HKCU, consent, restart and UIA remain mandatory.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "coordination/e06/NoXAutostart.cs"
BUILDER = ROOT / "coordination/e06/build_onehost_installer.ps1"

class TestD06NativeNoopReadback(unittest.TestCase):
    def test_native_noop_requires_second_owned_hkcu_read(self):
        source = SOURCE.read_text(encoding="utf-8")
        method = source.split("internal static bool SetEnabled(", 1)[1].split(
            "internal static void RemoveOnUninstall(", 1)[0]
        self.assertNotIn("if (ReadOwnedState(executable) == enabled) return enabled;", method)
        self.assertIn("var observed = ReadOwnedState(executable);", method)
        self.assertIn("if (observed == enabled)", method)
        self.assertIn("if (ReadOwnedState(executable) != enabled)", method)
        self.assertIn('throw new IOException("NOX_AUTOSTART_NOOP_READBACK_CHANGED_HOLD");', method)
        self.assertLess(method.index("if (ReadOwnedState(executable) != enabled)"),
                        method.index("return enabled;"))
        self.assertLess(method.index("return enabled;"),
                        method.index("Registry.CurrentUser.CreateSubKey("))
        # Strict owner reader still rejects all foreign same-name registry values.
        self.assertIn("NOX_AUTOSTART_FOREIGN_ENTRY_HOLD", source)
        self.assertIn("NOX_AUTOSTART_OWNER_CONSENT_REQUIRED", source)

    def test_builder_pin_matches_original_source(self):
        import hashlib
        data = SOURCE.read_bytes()
        blob = hashlib.sha1(
            b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        ).hexdigest()
        self.assertIn("relative='coordination/e06/NoXAutostart.cs'", BUILDER.read_text(encoding="utf-8"))
        self.assertIn("blob='" + blob + "'", BUILDER.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
