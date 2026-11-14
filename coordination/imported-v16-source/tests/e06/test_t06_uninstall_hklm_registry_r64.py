"""R64: original NSIS uninstall admission must reject leftover HKLM entries.

Source-only registry mock; NOT a physical Windows install nor E07 receipt.
"""
from __future__ import annotations
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "coordination" / "e06"))
from t06_uninstall_admission import original_nsis_uninstall_registration_absent


class Registry:
    KEY_WOW64_32KEY, KEY_WOW64_64KEY, KEY_READ = 0x200, 0x100, 0x20019
    HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE = "HKCU", "HKLM"

    def __init__(self, present=(), denied=()):
        self.present, self.denied, self.seen = set(present), set(denied), []

    def OpenKey(self, hive, name, unused, flags):
        assert name.endswith(r"Uninstall\NOXHELION.P01")
        view = flags & 0x300
        self.seen.append((hive, view))
        if (hive, view) in self.denied:
            raise PermissionError("read denied")
        if (hive, view) in self.present:
            return object()
        raise FileNotFoundError(name)

    def CloseKey(self, handle):
        pass


class UninstallHklmR64(unittest.TestCase):
    def test_all_four_views_missing(self):
        registry = Registry()
        self.assertTrue(original_nsis_uninstall_registration_absent(registry))
        self.assertEqual(registry.seen, [
            ("HKCU", 0x200), ("HKCU", 0x100),
            ("HKLM", 0x200), ("HKLM", 0x100)])

    def test_hklm32_leftover_blocks(self):
        self.assertFalse(original_nsis_uninstall_registration_absent(
            Registry({("HKLM", 0x200)})))

    def test_hklm64_leftover_blocks(self):
        self.assertFalse(original_nsis_uninstall_registration_absent(
            Registry({("HKLM", 0x100)})))

    def test_hklm_read_denied_holds(self):
        with self.assertRaises(PermissionError):
            original_nsis_uninstall_registration_absent(
                Registry(denied={("HKLM", 0x100)}))

    def test_hkcu_existing_behavior_preserved(self):
        self.assertFalse(original_nsis_uninstall_registration_absent(
            Registry({("HKCU", 0x200)})))


if __name__ == "__main__":
    unittest.main()
