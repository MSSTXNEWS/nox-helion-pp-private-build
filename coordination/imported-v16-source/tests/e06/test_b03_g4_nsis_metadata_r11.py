"""B03 G4 R11: no foreign metadata under exact installed NSIS backup (SOURCE_ONLY)."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "coordination" / "e06"))
from t06_user_probe_slot import verify_locked_nsis_metadata


class G4LockedNsisMetadata(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.marker = self.root / "nox-p01-owned.txt"
        self.marker.write_bytes(b"NOXHELION.P01 V16\r\n")
        self.uninstaller = self.root / "Uninstall.exe"
        self.uninstaller.write_bytes(b"MZ" + b"X" * 2046)
        # The original CI verifier supplies a stricter no-reparse-ancestor safe().
        self.safe = lambda p: p.parent == self.root and p.is_file() and not p.is_symlink()

    def test_real_owned_marker_and_uninstaller(self):
        self.assertTrue(verify_locked_nsis_metadata(self.marker, self.safe, marker=True))
        self.assertTrue(verify_locked_nsis_metadata(self.uninstaller, self.safe, marker=False))

    def test_foreign_hardlink_cannot_be_admitted(self):
        os.link(self.marker, self.root / "foreign.dat")
        self.assertFalse(verify_locked_nsis_metadata(self.marker, self.safe, marker=True))

    def test_reparse_symlink_cannot_be_admitted(self):
        self.marker.rename(self.root / "real.dat")
        try:
            self.marker.symlink_to(self.root / "real.dat")
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable")
        self.assertFalse(verify_locked_nsis_metadata(self.marker, self.safe, marker=True))

    def test_identical_byte_path_swap_changes_file_identity(self):
        real_open = Path.open
        swapped = [False]
        def replacement_open(path, *args, **kwargs):
            if path == self.marker and not swapped[0]:
                swapped[0] = True
                path.rename(self.root / "old.dat")
                path.write_bytes(b"NOXHELION.P01 V16\r\n")
            return real_open(path, *args, **kwargs)
        with patch.object(Path, "open", replacement_open):
            self.assertFalse(verify_locked_nsis_metadata(self.marker, self.safe, marker=True))

    def test_same_inode_mutation_after_read_denied(self):
        real_fstat = os.fstat
        calls = [0]
        def mutated_fstat(fd):
            calls[0] += 1
            if calls[0] == 2:
                self.marker.write_bytes(b"NOXHELION.P01 V17\r\n")
            return real_fstat(fd)
        with patch("t06_user_probe_slot.os.fstat", side_effect=mutated_fstat):
            self.assertFalse(verify_locked_nsis_metadata(self.marker, self.safe, marker=True))


if __name__ == "__main__":
    unittest.main()
