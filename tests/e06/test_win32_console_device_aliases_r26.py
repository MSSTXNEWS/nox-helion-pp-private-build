"""R26: Windows console I/O device aliases cannot be ZIP SourceLock members.

These names refer to real Win32 console handles (CONIN$/CONOUT$), not normal
archive files.  This source-level check is not evidence of Windows E07.
"""
import importlib.util
from pathlib import Path
import unittest
import zipfile

SOURCE = Path(__file__).resolve().parents[2] / "coordination/source-lock/verify_original_archive.py"
SPEC = importlib.util.spec_from_file_location("nox_win32_console_devices_r26", SOURCE)
assert SPEC is not None and SPEC.loader is not None
original = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(original)


class WindowsConsoleDeviceAliasesR26(unittest.TestCase):
    def test_console_input_output_names_fail_closed_in_zip(self):
        for base in ("CONIN$", "CONOUT$"):
            for name in (base, base.lower() + ".txt", "assets/" + base + "/asset.bin",
                         "assets/" + base.title() + ".bin", base + "/"):
                with self.subTest(name=name):
                    self.assertFalse(original.safe_name(name))
                    with self.assertRaisesRegex(ValueError, "Unsafe path"):
                        original.validate_members([zipfile.ZipInfo(name)])

    def test_valid_dollar_names_and_existing_alias_gates_still_work(self):
        for name in ("assets/CONIN$-notes.txt", "CONOUT$-safe.bin", "CONIN-model.bin",
                     "assets/hello.txt", "COM10.bin", "LPT⁴.bin"):
            with self.subTest(name=name):
                self.assertTrue(original.safe_name(name))
                original.validate_members([zipfile.ZipInfo(name)])
        for name in ("CON", "NUL.log", "COM¹.dat", "LPT9.txt", "../escape", "owner//"):
            with self.subTest(name=name):
                self.assertFalse(original.safe_name(name))
                with self.assertRaisesRegex(ValueError, "Unsafe path"):
                    original.validate_members([zipfile.ZipInfo(name)])


if __name__ == "__main__":
    unittest.main()
