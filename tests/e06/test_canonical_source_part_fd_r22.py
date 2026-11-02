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
            pins = tuple(hashlib.sha1(b"blob " + str(len(p)).encode() + b"\\0" + p).hexdigest()
                         for p in parts)
            with mock.patch.object(original, "EXPECTED_SIZE", len(archive_bytes)), \\
                 mock.patch.object(original, "EXPECTED_PART_SIZES", tuple(map(len, parts))), \\
                 mock.patch.object(original, "EXPECTED_PART_GIT_BLOBS", pins), \\
                 mock.patch.object(original, "EXPECTED_SHA256", hashlib.sha256(archive_bytes).hexdigest()):
                self.assertEqual(original.audit(real, 1)["file_count"], 1)
                with self.assertRaisesRegex(ValueError, "SOURCE_PART_PARENT_REPARSE"):
                    original.audit(root / "redirect", 1)


if __name__ == "__main__":
    unittest.main()
