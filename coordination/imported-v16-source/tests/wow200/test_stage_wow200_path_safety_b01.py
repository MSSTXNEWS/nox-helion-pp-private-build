"""B01 targeted SOURCE_ONLY regression for original WOW200 source/owner safety.

No NSIS execution, installed payload, permission grant or release acceptance.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


MODULE = Path(__file__).resolve().parents[2] / "integrations/wow200/stage_wow200.py"
spec = importlib.util.spec_from_file_location("nox_original_wow200_stage_b01", MODULE)
assert spec is not None and spec.loader is not None
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)


class Wow200StagePathSafetyB01(unittest.TestCase):
    def test_regular_file_and_new_target_under_plain_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "safe").mkdir()
            file = root / "safe" / "home.html"
            file.write_bytes(b"original")
            self.assertTrue(owner._plain_stage_path(file))
            self.assertTrue(owner._plain_stage_path(root / "safe" / "new" / "asset.mjs"))

    def test_regular_file_as_parent_never_counts_as_missing_target(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder) / "not-a-directory"
            parent.write_bytes(b"owned")
            self.assertFalse(owner._plain_stage_path(parent / "invisible.bin"))

    def test_linked_source_parent_rejected_before_stage(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "real").mkdir()
            link = root / "alias"
            try:
                link.symlink_to(root / "real", target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("runner lacks symlink creation privilege")
            self.assertFalse(owner._plain_stage_path(link / "asset.mjs"))

    def test_html_write_requires_same_inode_exact_preimage(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "index.html"
            path.write_bytes(b"original")
            info = path.lstat()
            ident = (info.st_dev, info.st_ino)
            owner._write_owned_html_only(path, b"original", b"approved", ident)
            self.assertEqual(path.read_bytes(), b"approved")
            with self.assertRaisesRegex(ValueError, "OWNER_CHANGED"):
                owner._write_owned_html_only(path, b"original", b"foreign", ident)
            self.assertEqual(path.read_bytes(), b"approved")

    def test_html_write_rejects_replacement_inode(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "index.html"
            path.write_bytes(b"original")
            old = path.lstat()
            path.unlink()
            path.write_bytes(b"original")
            with self.assertRaisesRegex(ValueError, "OWNER_CHANGED"):
                owner._write_owned_html_only(path, b"original", b"modified",
                                             (old.st_dev, old.st_ino))
            self.assertEqual(path.read_bytes(), b"original")

    def test_exclusive_creation_preserves_foreign_preexisting_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "owned.mjs"
            path.write_bytes(b"foreign")
            with self.assertRaises(FileExistsError):
                with path.open("xb") as stream:
                    stream.write(b"approved")
            self.assertEqual(path.read_bytes(), b"foreign")


if __name__ == "__main__":
    unittest.main()
