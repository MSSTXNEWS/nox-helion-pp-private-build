"""B06 SOURCE_ONLY: one fd and pathname identity for physical E06 receipts.

These tests use temporary files; they do not accept a Windows installer or E07.
"""
from pathlib import Path
import importlib.util
import os
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "b06_e07_receipt_reader_r5", ROOT / "coordination/e07/independent_setup_e07.py")
E07 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(E07)


class B06ReceiptDescriptor(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "E07_BUILT_HANDOFF.json"
        self.path.write_bytes(b'{"source_commit_sha1":"a","release_accepted":false}')

    def test_unchanged_regular_receipt(self):
        self.assertEqual(E07._read_locked_e06_json(self.path)["source_commit_sha1"], "a")

    def test_duplicate_field_still_refused(self):
        self.path.write_bytes(b'{"x":1,"x":2}')
        with self.assertRaisesRegex(E07.Hold, "DUPLICATE_FIELD"):
            E07._read_locked_e06_json(self.path)

    def test_nonfinite_number_still_refused(self):
        self.path.write_bytes(b'{"x":NaN}')
        with self.assertRaisesRegex(E07.Hold, "NONFINITE_NUMBER"):
            E07._read_locked_e06_json(self.path)

    def test_hardlink_refused_without_mutating_files(self):
        other = self.root / "foreign"
        try:
            os.link(self.path, other)
        except OSError:
            self.skipTest("Hardlinks unavailable on this host")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(E07.Hold, "NOT_REGULAR"):
            E07._read_locked_e06_json(self.path)
        self.assertEqual(other.read_bytes(), before)

    def test_identical_bytes_swap_before_open_refused(self):
        real_open = E07.os.open
        swaps = []
        def switched(path, flags, *args, **kwargs):
            if Path(path) == self.path and not swaps:
                other = self.root / "replacement"
                other.write_bytes(self.path.read_bytes())
                os.replace(other, self.path)
                swaps.append(1)
            return real_open(path, flags, *args, **kwargs)
        with patch.object(E07.os, "open", side_effect=switched):
            with self.assertRaisesRegex(E07.Hold, "OPEN_IDENTITY_HOLD"):
                E07._read_locked_e06_json(self.path)
        self.assertEqual(swaps, [1])

    def test_identical_bytes_swap_during_read_refused(self):
        real_read = E07.os.read
        swaps = []
        def switched(fd, size):
            if not swaps:
                other = self.root / "replacement"
                other.write_bytes(self.path.read_bytes())
                os.replace(other, self.path)
                swaps.append(1)
            return real_read(fd, size)
        with patch.object(E07.os, "read", side_effect=switched):
            with self.assertRaisesRegex(E07.Hold, "MUTATED_HOLD"):
                E07._read_locked_e06_json(self.path)
        self.assertEqual(swaps, [1])

    def test_oversized_receipt_refused(self):
        self.path.write_bytes(b'{' + b' ' * 1048577 + b'}')
        with self.assertRaisesRegex(E07.Hold, "NOT_REGULAR"):
            E07._read_locked_e06_json(self.path)


if __name__ == "__main__":
    unittest.main()
