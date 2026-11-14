"""NOX SourceLock: reject symlink/junction receipt parents before any output.

Tests the real existing module, without opening original binary parts or
creating any output receipt. Windows NTFS junction integration remains E07.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "coordination/e06/verify_original_729_source.py"
spec = importlib.util.spec_from_file_location("nox_729_receipt_source_guard", SOURCE)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SourceLockOutputParentTests(unittest.TestCase):
    def test_normal_output_parent_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "receipts"
            folder.mkdir()
            module._trusted_output_parent(folder / "first.json")

    def test_existing_output_parent_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "safe").mkdir()
            link = root / "redirected"
            try:
                link.symlink_to(root / "safe", target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(str(exc))
            with self.assertRaisesRegex(module.SourceHold, "OUTPUT_PARENT_REPARSE_OR_UNSAFE"):
                module._trusted_output_parent(link / "forbidden.json")
            self.assertEqual(list((root / "safe").iterdir()), [])

    def test_intermediate_ancestor_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "real" / "nested").mkdir(parents=True)
            link = root / "mid"
            try:
                link.symlink_to(root / "real", target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(str(exc))
            with self.assertRaisesRegex(module.SourceHold, "OUTPUT_PARENT_REPARSE_OR_UNSAFE"):
                module._trusted_output_parent(link / "nested" / "receipt.json")

    def test_not_a_directory_ancestor_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            node = Path(tmp) / "fake"
            node.write_bytes(b"owner")
            with self.assertRaisesRegex(module.SourceHold, "OUTPUT_PARENT_REPARSE_OR_UNSAFE"):
                module._trusted_output_parent(node / "receipt.json")


if __name__ == "__main__":
    unittest.main()
