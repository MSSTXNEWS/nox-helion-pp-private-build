"""P04 one existing sha256_tree: reject FIFO/special filesystem nodes.

Offline stdlib tests, no model weights, CUDA, OS install or new trainer.
"""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "train_qlora.py"
spec = importlib.util.spec_from_file_location("nox_p04_special_tree", SCRIPT)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class P04PinnedTreeSafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "model"
        self.root.mkdir()
        (self.root / "adapter_model.safetensors").write_bytes(b"fixture weights")

    def test_regular_tree_digest_is_stable(self):
        self.assertEqual(worker.sha256_tree(self.root), worker.sha256_tree(self.root))

    def test_regular_file_change_changes_digest(self):
        before = worker.sha256_tree(self.root)
        (self.root / "adapter_model.safetensors").write_bytes(b"changed fixture")
        self.assertNotEqual(before, worker.sha256_tree(self.root))

    def test_empty_subdirectory_does_not_change_digest(self):
        before = worker.sha256_tree(self.root)
        (self.root / "empty-dir").mkdir()
        self.assertEqual(before, worker.sha256_tree(self.root))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO not supported by host OS")
    def test_fifo_is_rejected_not_silently_ignored(self):
        os.mkfifo(self.root / "untrusted.fifo")
        with self.assertRaisesRegex(ValueError, "SPECIAL_FILE_IN_PINNED_TREE"):
            worker.sha256_tree(self.root)

    def test_symlink_is_still_rejected(self):
        link = self.root / "external"
        try:
            link.symlink_to(self.root / "adapter_model.safetensors")
        except (OSError, NotImplementedError):
            self.skipTest("host disallows symlinks")
        with self.assertRaisesRegex(ValueError, "SYMLINK_IN_PINNED_TREE"):
            worker.sha256_tree(self.root)

    def test_complete_checkpoint_still_hashes(self):
        root = Path(self.temp.name) / "checkpoints"
        chk = root / "checkpoint-4"
        chk.mkdir(parents=True)
        (chk / "trainer_state.json").write_text(json.dumps({"global_step": 4}))
        for name in ("adapter_model.safetensors", "optimizer.pt", "scheduler.pt", "rng_state.pth"):
            (chk / name).write_bytes(b"verified synthetic fixture")
        step, digest = worker.validated_checkpoint(root, chk)
        self.assertEqual(step, 4)
        self.assertEqual(digest, worker.sha256_tree(chk))


if __name__ == "__main__":
    unittest.main()
