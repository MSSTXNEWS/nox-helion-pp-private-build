"""Regression for ORIGINAL canonical 729-source archive reader, not E07."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

SOURCE = Path(__file__).resolve().parents[2] / "coordination/source-lock/verify_original_archive.py"
SPEC = importlib.util.spec_from_file_location("nox_original_archive_fd_r22", SOURCE)
original = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(original)


class CanonicalOriginalPartFd(unittest.TestCase):
    def test_regular_descriptor(self):
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "source_00.part"
            part.write_bytes(b"original")
            with original._trusted_part_stream(part) as reader:
                self.assertEqual(reader.read(), b"original")

    def test_symlinked_parent_is_denied(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real = root / "real"
            real.mkdir()
            (real / "source_00.part").write_bytes(b"original")
            try:
                (root / "redirect").symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(str(exc))
            with self.assertRaisesRegex(ValueError, "SOURCE_PART_PARENT_REPARSE"):
                with original._trusted_part_stream(root / "redirect/source_00.part") as reader:
                    reader.read()

    def test_symlink_switch_during_open_is_denied(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            part = root / "source_00.part"
            target = root / "other"
            part.write_bytes(b"original")
            target.write_bytes(b"original")
            real_open = os.open

            def swap(path, flags):
                if Path(path) == part:
                    part.unlink()
                    try:
                        part.symlink_to(target)
                    except (OSError, NotImplementedError) as exc:
                        self.skipTest(str(exc))
                return real_open(path, flags)

            with mock.patch.object(original.os, "open", side_effect=swap):
                with self.assertRaisesRegex(ValueError, "SOURCE_PART_UNTRUSTED_OPEN"):
                    with original._trusted_part_stream(part) as reader:
                        reader.read()

    def test_leaf_switched_after_read_denied(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            part = root / "source_00.part"
            part.write_bytes(b"original")
            with self.assertRaisesRegex(ValueError, "SOURCE_PART_CHANGED_DURING_READ"):
                with original._trusted_part_stream(part) as reader:
                    self.assertEqual(reader.read(), b"original")
                    part.rename(root / "old")
                    part.write_bytes(b"original")

    def test_inplace_write_after_read_denied(self):
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "source_00.part"
            part.write_bytes(b"original")
            with self.assertRaisesRegex(ValueError, "SOURCE_PART_CHANGED_DURING_READ"):
                with original._trusted_part_stream(part) as reader:
                    reader.read()
                    part.write_bytes(b"modified")

    def test_actual_archive_audit_denies_redirected_root_and_keeps_good_input(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("R11/file.txt", b"original")
        archive_bytes = data.getvalue()
        cuts = (len(archive_bytes)//3, 2*len(archive_bytes)//3)
        parts = (archive_bytes[:cuts[0]], archive_bytes[cuts[0]:cuts[1]],
                 archive_bytes[cuts[1]:])
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real = root / "real"
            real.mkdir()
            for name, content in zip(original.PARTS, parts):
                (real / name).write_bytes(content)
            try:
                (root / "redirect").symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(str(exc))
            pins = tuple(hashlib.sha1(b"blob " + str(len(p)).encode() + b"\0" + p).hexdigest()
                         for p in parts)
            with mock.patch.object(original, "EXPECTED_SIZE", len(archive_bytes)), \
                 mock.patch.object(original, "EXPECTED_PART_SIZES", tuple(map(len, parts))), \
                 mock.patch.object(original, "EXPECTED_PART_GIT_BLOBS", pins), \
                 mock.patch.object(original, "EXPECTED_SHA256", hashlib.sha256(archive_bytes).hexdigest()):
                self.assertEqual(original.audit(real, 1)["file_count"], 1)
                with self.assertRaisesRegex(ValueError, "SOURCE_PART_PARENT_REPARSE"):
                    original.audit(root / "redirect", 1)



class WindowsNamedDescriptorParity(unittest.TestCase):
    """Windows CPython path/descriptor ctime differ; birthtime remains pinned."""

    def _stat(self, *, birth=123, ctime=500, inode=17, size=8, mtime=42):
        from types import SimpleNamespace
        return SimpleNamespace(st_dev=9, st_ino=inode, st_size=size,
                               st_mtime_ns=mtime, st_ctime_ns=ctime,
                               st_birthtime_ns=birth)

    def test_windows_path_fd_ctime_differ_birthtime_equal_passes(self):
        with mock.patch.object(original, "_WINDOWS_STAT", True):
            self.assertTrue(original._same_named_descriptor(
                self._stat(ctime=100), self._stat(ctime=200)))

    def test_windows_name_swap_same_bytes_other_inode_or_birth_denied(self):
        with mock.patch.object(original, "_WINDOWS_STAT", True):
            reference = self._stat()
            self.assertFalse(original._same_named_descriptor(reference, self._stat(inode=18)))
            self.assertFalse(original._same_named_descriptor(reference, self._stat(birth=124)))
            self.assertFalse(original._same_named_descriptor(reference, self._stat(size=9)))
            self.assertFalse(original._same_named_descriptor(reference, self._stat(mtime=43)))

    def test_linux_ctime_mismatch_still_denied(self):
        with mock.patch.object(original, "_WINDOWS_STAT", False):
            self.assertFalse(original._same_named_descriptor(
                self._stat(ctime=100), self._stat(ctime=200)))

    def test_windows_missing_birthtime_fails_closed(self):
        with mock.patch.object(original, "_WINDOWS_STAT", True):
            from types import SimpleNamespace
            no_birth = SimpleNamespace(st_dev=9, st_ino=17, st_size=8,
                                       st_mtime_ns=42, st_ctime_ns=500)
            self.assertFalse(original._same_named_descriptor(no_birth, self._stat()))

if __name__ == "__main__":
    unittest.main()
