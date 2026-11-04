"""Real filesystem preflight regression for frozen independent E07 installer.

This never launches NSIS and cannot report install/GUI/E07 PASS.
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "nox_e07_u09", ROOT / "coordination/e07/independent_setup_e07.py")
e07 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e07)


class FreshInstallPreflightU09(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.local = Path(self.tmp.name) / "LocalAppData"
        self.local.mkdir()
        self.base = self.local / "Programs"
        self.slots = tuple(self.base / name for name in (
            "NOX HELION", "NOX HELION.__p01_stage",
            "NOX HELION.__p01_previous", "NOX HELION.__p01_rollback_saved"))

    def verify(self):
        return e07.verify_fresh_install_targets(self.local, *self.slots)

    def mklink(self, link, target):
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("Filesystem forbids symlink creation: " + type(exc).__name__)

    def test_absent_base_allows_fresh_installer(self):
        self.assertIsNone(self.verify())

    def test_real_clean_base_allows_fresh_installer(self):
        self.base.mkdir()
        self.assertIsNone(self.verify())

    def test_file_instead_of_programs_directory_holds(self):
        self.base.write_text("untrusted")
        with self.assertRaisesRegex(e07.Hold, "E07_INSTALL_BASE_REPARSE_HOLD"):
            self.verify()

    def test_existing_programs_symlink_holds(self):
        other = Path(self.tmp.name) / "external"
        other.mkdir()
        self.mklink(self.base, other)
        with self.assertRaisesRegex(e07.Hold, "E07_INSTALL_BASE_REPARSE_HOLD"):
            self.verify()

    def test_dangling_programs_symlink_holds(self):
        self.mklink(self.base, Path(self.tmp.name) / "missing")
        with self.assertRaisesRegex(e07.Hold, "E07_INSTALL_BASE_REPARSE_HOLD"):
            self.verify()

    def test_existing_recovery_slot_holds(self):
        self.base.mkdir()
        self.slots[1].mkdir()
        with self.assertRaisesRegex(e07.Hold, "E07_VM_NOT_FRESH_SKIP"):
            self.verify()

    def test_dangling_rollback_symlink_holds(self):
        self.base.mkdir()
        self.mklink(self.slots[3], self.base / "missing")
        with self.assertRaisesRegex(e07.Hold, "E07_VM_NOT_FRESH_SKIP"):
            self.verify()

    def test_wrong_parent_is_never_admitted(self):
        self.base.mkdir()
        with self.assertRaisesRegex(e07.Hold, "E07_VM_NOT_FRESH_SKIP"):
            e07.verify_fresh_install_targets(
                self.local, self.local / "wrong", *self.slots[1:])

    def test_windows_junction_programs_even_when_exists_false_holds(self):
        with patch.object(Path, "is_junction", autospec=True,
                          side_effect=lambda obj: obj == self.base):
            with self.assertRaisesRegex(e07.Hold, "E07_INSTALL_BASE_REPARSE_HOLD"):
                self.verify()

    def test_windows_dangling_junction_slot_holds(self):
        with patch.object(Path, "is_junction", autospec=True,
                          side_effect=lambda obj: obj == self.slots[2]):
            with self.assertRaisesRegex(e07.Hold, "E07_VM_NOT_FRESH_SKIP"):
                self.verify()


if __name__ == "__main__":
    unittest.main()
