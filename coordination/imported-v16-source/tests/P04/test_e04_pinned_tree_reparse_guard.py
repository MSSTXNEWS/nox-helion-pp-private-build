"""E04 CPU-only actual-module tests for pinned model/checkpoint tree reparse checks.

Synthetic lstat attributes simulate Windows junctions for cross-platform unit
coverage. These tests do NOT establish real Windows reparse or GPU acceptance.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "train_qlora.py"
spec = importlib.util.spec_from_file_location("nox_e04_pinned_tree_guard", SOURCE)
assert spec is not None and spec.loader is not None
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class _SyntheticReparseStat:
    def __init__(self, real_info):
        self._real_info = real_info
        self.st_file_attributes = stat.FILE_ATTRIBUTE_REPARSE_POINT

    def __getattr__(self, name):
        return getattr(self._real_info, name)


class PinnedTreeReparseGuardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.file = self.root / "model.safetensors"
        self.file.write_bytes(b"CPU-only tree fixture")

    def synthetic_reparse(self, target):
        original_lstat = Path.lstat

        def simulated_lstat(path, *args, **kwargs):
            result = original_lstat(path, *args, **kwargs)
            return _SyntheticReparseStat(result) if path == target else result

        return patch.object(Path, "lstat", simulated_lstat)

    def test_regular_tree_digest_unchanged(self):
        rel = b"model.safetensors"
        expected = hashlib.sha256()
        expected.update(len(rel).to_bytes(4, "big"))
        expected.update(rel)
        expected.update(hashlib.sha256(self.file.read_bytes()).digest())
        self.assertEqual(worker.sha256_tree(self.root), expected.hexdigest())

    def test_windows_reparse_root_rejected_by_simulated_flag(self):
        with self.synthetic_reparse(self.root):
            with self.assertRaisesRegex(ValueError, "TREE_ROOT_NOT_REGULAR_DIRECTORY"):
                worker.sha256_tree(self.root)

    def test_windows_reparse_file_rejected_by_simulated_flag(self):
        with self.synthetic_reparse(self.file):
            with self.assertRaisesRegex(ValueError, "REPARSE_POINT_IN_PINNED_TREE"):
                worker.sha256_tree(self.root)

    def test_windows_reparse_directory_rejected_by_simulated_flag(self):
        directory = self.root / "nested"
        directory.mkdir()
        (directory / "more.safetensors").write_bytes(b"fixture")
        with self.synthetic_reparse(directory):
            with self.assertRaisesRegex(ValueError, "REPARSE_POINT_IN_PINNED_TREE"):
                worker.sha256_tree(self.root)

    def test_regular_file_cannot_be_tree_root(self):
        with self.assertRaisesRegex(ValueError, "TREE_ROOT_NOT_REGULAR_DIRECTORY"):
            worker.sha256_tree(self.file)

    def test_file_symlink_remains_rejected(self):
        link = self.root / "alias"
        try:
            link.symlink_to(self.file)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        with self.assertRaisesRegex(ValueError, "SYMLINK_IN_PINNED_TREE"):
            worker.sha256_tree(self.root)

    def test_root_symlink_remains_rejected(self):
        link = self.root.parent / (self.root.name + "-link")
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        self.addCleanup(link.unlink)
        with self.assertRaisesRegex(ValueError, "TREE_ROOT_NOT_REGULAR_DIRECTORY"):
            worker.sha256_tree(link)

    def test_empty_tree_remains_rejected(self):
        self.file.unlink()
        with self.assertRaisesRegex(ValueError, "EMPTY_PINNED_TREE"):
            worker.sha256_tree(self.root)


if __name__ == "__main__":
    unittest.main()
