"""SourceLock descriptor/path race regressions, not native Windows E07."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
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
                    part.rename(backup)
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
                    part.write_bytes(b"tampered")

    def test_nonregular_part_denied(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(module.SourceHold, "SOURCE_PART_UNTRUSTED_PATH"):
                with module._trusted_part_reader(Path(td)) as reader:
                    reader.read()


if __name__ == "__main__":
    unittest.main()
