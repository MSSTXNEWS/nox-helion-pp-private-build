"""SourceLock descriptor/path race regressions, not native Windows E07."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[2] / "coordination/e06/verify_original_729_source.py"
spec = importlib.util.spec_from_file_location("nox_729_part_fd_guard", SOURCE)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OriginalSourcePartFDTests(unittest.TestCase):
    def test_regular_descriptor_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "source_00.part"
            part.write_bytes(b"original")
            with module._trusted_part_reader(part) as reader:
                self.assertEqual(reader.read(), b"original")

    def test_symlink_swap_during_open_denied(self):
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "source_00.part"
            other = Path(td) / "other"
            part.write_bytes(b"original")
            other.write_bytes(b"original")
            open_original = os.open

            def swap(path, flags):
                if Path(path) == part:
                    part.unlink()
                    try:
                        part.symlink_to(other)
                    except (OSError, NotImplementedError) as exc:
                        self.skipTest(str(exc))
                return open_original(path, flags)

            with mock.patch.object(module.os, "open", side_effect=swap):
                with self.assertRaises(module.SourceHold):
                    with module._trusted_part_reader(part) as reader:
                        reader.read()

    def test_leaf_redirect_after_read_denied(self):
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "source_00.part"
            backup = Path(td) / "backup"
            part.write_bytes(b"original")
            with self.assertRaisesRegex(module.SourceHold, "SOURCE_PART_CHANGED_DURING_READ"):
                with module._trusted_part_reader(part) as reader:
                    self.assertEqual(reader.read(), b"original")
                    try:
                        part.rename(backup)
                    except PermissionError as exc:
                        if os.name != "nt":
                            raise
                        # Windows prevents renaming a live descriptor; the race
                        # could not be induced. No fake source-level swap PASS.
                        self.assertTrue(part.is_file())
                        self.skipTest("Windows denied the open-file rename: " + str(exc))
                    try:
                        part.symlink_to(backup)
                    except (OSError, NotImplementedError) as exc:
                        self.skipTest(str(exc))

    def test_inplace_mutation_during_read_denied(self):
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "source_00.part"
            part.write_bytes(b"original")
            with self.assertRaisesRegex(module.SourceHold, "SOURCE_PART_CHANGED_DURING_READ"):
                with module._trusted_part_reader(part) as reader:
                    reader.read()
                    before = part.stat()
                    part.write_bytes(b"tampered")
                    # Windows timestamp granularity may hide an immediate
                    # same-size write; force a real, detectable mtime change.
                    os.utime(part, ns=(before.st_atime_ns,
                                       before.st_mtime_ns + 10_000_000_000))

    def test_nonregular_part_denied(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(module.SourceHold, "SOURCE_PART_UNTRUSTED_PATH"):
                with module._trusted_part_reader(Path(td)) as reader:
                    reader.read()

    def test_windows_path_stat_uses_birthtime_without_ignoring_identity(self):
        path = SimpleNamespace(st_dev=4, st_ino=21, st_size=100,
                               st_mtime_ns=800, st_ctime_ns=1200,
                               st_birthtime_ns=3333)
        fd = SimpleNamespace(st_dev=4, st_ino=21, st_size=100,
                             st_mtime_ns=800, st_ctime_ns=1999,
                             st_birthtime_ns=3333)
        with mock.patch.object(module, "_WINDOWS_STAT", True):
            self.assertTrue(module._trusted_open_identity(path, fd))
            self.assertEqual(module._fd_identity(fd),
                             (4, 21, 100, 800, 1999))
            for key, value in (("st_birthtime_ns", 4444),
                               ("st_ino", 22), ("st_dev", 7),
                               ("st_mtime_ns", 801), ("st_size", 101)):
                altered = SimpleNamespace(**{**vars(path), key: value})
                self.assertFalse(module._trusted_open_identity(altered, fd))
            no_birth = SimpleNamespace(**{k: v for k, v in vars(path).items()
                                          if k != "st_birthtime_ns"})
            self.assertFalse(module._trusted_open_identity(no_birth, fd))
            float_birth = SimpleNamespace(**{**vars(path), "st_birthtime_ns": 3333.0})
            self.assertFalse(module._trusted_open_identity(float_birth, fd))

    def test_posix_path_stat_and_fd_change_time_remain_strict(self):
        path = SimpleNamespace(st_dev=1, st_ino=9, st_size=12,
                               st_mtime_ns=100, st_ctime_ns=777)
        fd = SimpleNamespace(**vars(path))
        with mock.patch.object(module, "_WINDOWS_STAT", False):
            self.assertTrue(module._trusted_open_identity(path, fd))
            changed = SimpleNamespace(**{**vars(path), "st_ctime_ns": 778})
            self.assertFalse(module._trusted_open_identity(changed, fd))
        after = SimpleNamespace(**{**vars(fd), "st_ctime_ns": 778})
        self.assertNotEqual(module._fd_identity(fd), module._fd_identity(after))



if __name__ == "__main__":
    unittest.main()
