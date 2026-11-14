"""R24: Windows SourceLock rejects ISO-8859-1 superscript COM/LPT aliases.

Microsoft Win32 reserved device names include COM¹/²/³ and LPT¹/²/³,
including those with extensions and in nested directories. Source-only test;
not Windows native A1, installer, model-license or independent E07 evidence.
"""
from pathlib import Path
import importlib.util
import unittest
import zipfile

SOURCE = Path(__file__).resolve().parents[2] / "coordination/source-lock/verify_original_archive.py"
SPEC = importlib.util.spec_from_file_location("nox_win32_device_alias_r24", SOURCE)
assert SPEC is not None and SPEC.loader is not None
original = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(original)


class WindowsDeviceAliasesR24(unittest.TestCase):
    def test_superscript_device_aliases_fail_closed(self):
        for prefix in ("COM", "LPT"):
            for digit in ("¹", "²", "³"):
                for name in (prefix + digit, prefix + digit + ".txt",
                             "assets/" + prefix + digit + "/body.bin",
                             (prefix + digit).lower() + "/"):
                    with self.subTest(name=name):
                        self.assertFalse(original.safe_name(name))
                        with self.assertRaisesRegex(ValueError, "Unsafe path"):
                            original.validate_members([zipfile.ZipInfo(name)])

    def test_safe_nondevice_names_remain_accepted(self):
        for name in ("MODEL¹.bin", "COM10.bin", "LPT⁴.bin",
                     "assets/hello.txt", "COM¹-model.bin", "COMX.bin"):
            with self.subTest(name=name):
                self.assertTrue(original.safe_name(name))
                original.validate_members([zipfile.ZipInfo(name)])

    def test_existing_invalid_namespace_rejections_remain(self):
        for name in ("COM1", "LPT9.txt", "NUL.log", "CON", "owner//", "../p"):
            with self.subTest(name=name):
                self.assertFalse(original.safe_name(name))
                with self.assertRaisesRegex(ValueError, "Unsafe path"):
                    original.validate_members([zipfile.ZipInfo(name)])


if __name__ == "__main__":
    unittest.main()
