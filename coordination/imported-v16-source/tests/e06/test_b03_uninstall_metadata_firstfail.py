"""B03 G4: real fail-closed metadata residue emits bounded read-only evidence.

Offline filesystem source test; never a physical Windows G4 or E07 PASS.
"""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "coordination" / "e06"))
from t06_uninstall_admission import verify_original_uninstall


class EmptyWindowsRegistry:
    HKEY_CURRENT_USER = object()
    KEY_WOW64_32KEY = 0x200
    KEY_WOW64_64KEY = 0x100
    KEY_READ = 0x20019

    def OpenKey(self, *_args):
        raise FileNotFoundError("absent")


class MetadataFirstFailure(unittest.TestCase):
    def test_marker_residue_is_diagnosed_without_delete_or_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "NOX HELION"
            install.mkdir()
            marker = install / "nox-p01-owned.txt"
            marker.write_bytes(b"NOXHELION.P01 V16\r\n")
            user_data = install / "personal-data-untracked.bin"
            user_data.write_bytes(b"retain me")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaisesRegex(
                    RuntimeError, "^T06_CONSERVATIVE_UNINSTALL_METADATA_REMAINS$"
                ):
                    verify_original_uninstall(
                        install, (install / "already-removed.exe",), EmptyWindowsRegistry()
                    )
            output = stderr.getvalue()
            self.assertIn('T06_UNINSTALL_FIRST_METADATA_RESIDUE "nox-p01-owned.txt"', output)
            prefix = "T06_UNINSTALL_METADATA_READONLY_WITNESS "
            self.assertIn(prefix, output)
            receipt = json.loads(output.split(prefix, 1)[1].splitlines()[0])
            self.assertEqual(
                receipt["original_nsis_metadata_states"]["nox-p01-owned.txt"], "PRESENT"
            )
            self.assertFalse(receipt["witness_deleted_files"])
            self.assertFalse(receipt["witness_executed_uninstaller"])
            self.assertNotIn(str(install), output)
            self.assertEqual(marker.read_bytes(), b"NOXHELION.P01 V16\r\n")
            self.assertEqual(user_data.read_bytes(), b"retain me")

    def test_fully_removed_metadata_remains_accepted_by_existing_registry_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "NOX HELION"
            install.mkdir()
            verify_original_uninstall(
                install, (install / "already-removed.exe",), EmptyWindowsRegistry()
            )


if __name__ == "__main__":
    unittest.main()
