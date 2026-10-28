"""Targeted SOURCE-only ZIP namespace parity tests (no original ZIP, no EXE)."""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import unittest
import zipfile

SOURCE = Path(os.environ.get("NOX_CANONICAL_SOURCE_FILE", str(Path(__file__).resolve().parents[4] / "coordination/source-lock/verify_original_archive.py")))

def gate():
    spec = importlib.util.spec_from_file_location("source_gate_r20", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class SourceZipNamespaceR20(unittest.TestCase):
    def test_duplicate_directory_slashes_rejected(self):
        self.assertFalse(gate().safe_name("assets//"))

    def test_three_directory_slashes_rejected(self):
        self.assertFalse(gate().safe_name("assets///"))

    def test_malformed_directory_entry_rejected_before_hashing(self):
        with self.assertRaisesRegex(ValueError, "Unsafe path"):
            gate().validate_members([zipfile.ZipInfo("assets//")])

    def test_single_directory_slash_accepted(self):
        self.assertTrue(gate().safe_name("assets/"))
        gate().validate_members([zipfile.ZipInfo("assets/")])

    def test_regular_child_with_one_directory_separator_accepted(self):
        gate().validate_members([zipfile.ZipInfo("assets/"), zipfile.ZipInfo("assets/logo.png")])

    def test_internal_duplicate_separator_still_rejected(self):
        self.assertFalse(gate().safe_name("assets//logo.png"))

    def test_nfd_unicode_still_rejected(self):
        self.assertFalse(gate().safe_name("e\u0301.txt"))

    def test_overlong_zip_member_still_rejected(self):
        self.assertFalse(gate().safe_name("a" * 501))

    def test_file_parent_collisions_still_rejected(self):
        with self.assertRaises(ValueError):
            gate().validate_members([zipfile.ZipInfo("assets"), zipfile.ZipInfo("assets/logo.png")])

if __name__ == "__main__":
    unittest.main(verbosity=2)

