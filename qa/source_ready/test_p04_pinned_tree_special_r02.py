"""NOX V16 §46 independent P04 QA; imports the REAL trainer module.

No product mutation, model, CUDA, credentials or network required.
On POSIX, existing owner source currently has two intentional RED cases:
FIFO and nested FIFO must be rejected by the pinned tree integrity gate.
Run: python -m unittest qa.source_ready.test_p04_pinned_tree_special_r02 -v
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
OWNER = ROOT / "Packages" / "P04" / "train_qlora.py"


def original_trainer_module():
    if not OWNER.is_file() or OWNER.is_symlink():
        raise RuntimeError("PINNED_OWNER_SOURCE_REQUIRED")
    spec = importlib.util.spec_from_file_location("nox_p04_qa_pinned_tree_r02", OWNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("ORIGINAL_P04_IMPORT_UNAVAILABLE")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class P04PinnedTreeSpecialFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = original_trainer_module()

    def test_regular_file_is_hashable(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "model.bin").write_bytes(b"real-owner-qa-source")
            got = self.owner.sha256_tree(p)
            self.assertEqual(len(got), 64)
            self.assertEqual(got, self.owner.sha256_tree(p))

    def test_changed_model_bytes_change_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            f = p / "model.bin"
            f.write_bytes(b"initial")
            before = self.owner.sha256_tree(p)
            f.write_bytes(b"changed")
            self.assertNotEqual(before, self.owner.sha256_tree(p))

    def test_empty_tree_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "EMPTY_PINNED_TREE"):
                self.owner.sha256_tree(Path(tmp))

    def test_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "model.bin").write_bytes(b"baseline")
            link = p / "linked.bin"
            try:
                link.symlink_to(p / "model.bin")
            except (OSError, NotImplementedError):
                self.skipTest("Symlink creation not allowed on this host")
            with self.assertRaisesRegex(ValueError, "SYMLINK"):
                self.owner.sha256_tree(p)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX named pipe required")
    def test_fifo_cannot_be_silently_excluded_from_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "model.bin").write_bytes(b"baseline")
            os.mkfifo(p / "unexpected.fifo")
            with self.assertRaisesRegex(ValueError, "SPECIAL_FILE|NONREGULAR"):
                self.owner.sha256_tree(p)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX named pipe required")
    def test_nested_fifo_cannot_be_silently_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "model.bin").write_bytes(b"baseline")
            nested = p / "weights"
            nested.mkdir()
            os.mkfifo(nested / "hidden.fifo")
            with self.assertRaisesRegex(ValueError, "SPECIAL_FILE|NONREGULAR"):
                self.owner.sha256_tree(p)


if __name__ == "__main__":
    unittest.main()
