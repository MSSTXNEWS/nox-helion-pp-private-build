"""R23: original ZIP SourceLock rejects noncanonical repeated directory slashes.

Canonical validator is shared by the original 729 archive and the E06 gate.
These are source-only tests, not Windows installation or E07 evidence.
"""
from pathlib import Path
import importlib.util
import unittest
import zipfile

SOURCE = Path(__file__).resolve().parents[2] / "coordination/source-lock/verify_original_archive.py"
SPEC = importlib.util.spec_from_file_location("nox_original_zip_tail_r23", SOURCE)
assert SPEC is not None and SPEC.loader is not None
original = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(original)


class CanonicalZipDirectorySuffixR23(unittest.TestCase):
    def test_repeated_directory_separators_are_rejected(self):
        for name in ("owner//", "owner///", "owner/child//"):
            with self.subTest(name=name):
                self.assertFalse(original.safe_name(name))
                with self.assertRaisesRegex(ValueError, "Unsafe path"):
                    original.validate_members([zipfile.ZipInfo(name)])

    def test_single_directory_separator_and_regular_path_survive(self):
        for name in ("owner/", "owner/child/", "owner/child.txt"):
            with self.subTest(name=name):
                self.assertTrue(original.safe_name(name))
                original.validate_members([zipfile.ZipInfo(name)])

    def test_internal_empty_segment_remains_rejected(self):
        self.assertFalse(original.safe_name("owner//child"))
        with self.assertRaisesRegex(ValueError, "Unsafe path"):
            original.validate_members([zipfile.ZipInfo("owner//child")])


if __name__ == "__main__":
    unittest.main()
