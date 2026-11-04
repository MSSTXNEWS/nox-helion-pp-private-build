"""R93 cross-platform SourceLock path/fd differential; no archive or release PASS.

Uses the TWO original readers against real temporary files. Windows owner positive
case is an intentional regression gate: it must go green only when the owner
reader is safe on that platform; never skip the failure as a release receipt.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative: str):
    source = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, source)
    if spec is None or spec.loader is None:
        raise RuntimeError("SOURCELOCK_ORIGINAL_READER_UNAVAILABLE:" + relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CANONICAL = _load("r93_canonical", "coordination/source-lock/verify_original_archive.py")
OWNER = _load("r93_owner", "coordination/e06/verify_original_729_source.py")


def _meta(**changes):
    values = dict(st_dev=10, st_ino=20, st_size=9, st_mtime_ns=30,
                  st_ctime_ns=40, st_birthtime_ns=50)
    values.update(changes)
    return SimpleNamespace(**values)


class SourcePartIdentityDifferentialTests(unittest.TestCase):
    def _real_reader(self, reader):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "source_00.part"
            payload = b"NOX-R93-source-reader"
            target.write_bytes(payload)
            with reader(target) as stream:
                self.assertEqual(stream.read(), payload)
                self.assertTrue(stat.S_ISREG(os.fstat(stream.fileno()).st_mode))

    def test_canonical_real_descriptor_read(self):
        self._real_reader(CANONICAL._trusted_part_stream)

    def test_owner_real_descriptor_read_windows_regression_gate(self):
        # This intentionally FAILS on Windows if path/descriptor identity differs.
        # It is NOT a replacement for validating the original 729-file archive.
        self._real_reader(OWNER._trusted_part_reader)

    def test_both_reject_symlink_leaf(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            real = root / "real.part"
            real.write_bytes(b"immutable")
            alias = root / "source_00.part"
            try:
                alias.symlink_to(real)
            except (OSError, NotImplementedError) as exc:
                self.skipTest("symlink unavailable: " + str(exc))
            for reader in (CANONICAL._trusted_part_stream, OWNER._trusted_part_reader):
                with self.subTest(reader=reader.__name__):
                    with self.assertRaises((ValueError, OWNER.SourceHold)):
                        with reader(alias):
                            self.fail("symlink must not be opened")

    @unittest.skipIf(os.name == "nt", "Win32 denies replacing an open source file")
    def test_both_reject_filename_swap_mid_read(self):
        for reader in (CANONICAL._trusted_part_stream, OWNER._trusted_part_reader):
            with self.subTest(reader=reader.__name__), tempfile.TemporaryDirectory() as temp:
                original = Path(temp) / "source_00.part"
                switched = Path(temp) / "incoming.part"
                original.write_bytes(b"A" * 20)
                switched.write_bytes(b"B" * 20)
                with self.assertRaisesRegex((ValueError, OWNER.SourceHold),
                                            "SOURCE_PART_CHANGED_DURING_READ"):
                    with reader(original) as stream:
                        self.assertEqual(stream.read(1), b"A")
                        os.replace(switched, original)

    def test_canonical_win_birthtime_parity_preserves_file_identity(self):
        named = _meta(st_ctime_ns=100)
        opened = _meta(st_ctime_ns=999)
        with mock.patch.object(CANONICAL, "_WINDOWS_STAT", True):
            self.assertTrue(CANONICAL._same_named_descriptor(named, opened))
            for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_birthtime_ns"):
                with self.subTest(mutated=field):
                    values = vars(opened).copy()
                    values[field] += 1
                    self.assertFalse(CANONICAL._same_named_descriptor(
                        named, SimpleNamespace(**values)))
            absent = vars(opened).copy()
            absent.pop("st_birthtime_ns")
            self.assertFalse(CANONICAL._same_named_descriptor(
                named, SimpleNamespace(**absent)))

    def test_canonical_posix_identity_rejects_changed_ctime(self):
        with mock.patch.object(CANONICAL, "_WINDOWS_STAT", False):
            self.assertFalse(CANONICAL._same_named_descriptor(
                _meta(st_ctime_ns=100), _meta(st_ctime_ns=999)))

    def test_archive_and_tree_count_are_not_conflated(self):
        self.assertEqual(OWNER.EXPECTED_FILES, 729)
        self.assertEqual(len(OWNER.PARTS), 3)
        self.assertNotEqual(OWNER.EXPECTED_FILES, 1568)
        # The separate 1568-file source tree is not an inner-ZIP member inventory.


if __name__ == "__main__":
    unittest.main()
