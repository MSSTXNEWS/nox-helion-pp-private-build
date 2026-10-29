"""Real worker checkpoint preflight regressions; no CUDA or weights needed."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("nox_checkpoint_r27", ROOT / "Packages/P04/train_qlora.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class CheckpointResumeR27(unittest.TestCase):
    def make_checkpoint(self, folder):
        root = folder / "checkpoints"
        selected = root / "checkpoint-4"
        selected.mkdir(parents=True)
        (selected / "trainer_state.json").write_text(json.dumps({"global_step": 4}))
        for name in ("adapter_model.safetensors", "optimizer.pt", "scheduler.pt", "rng_state.pth"):
            (selected / name).write_bytes(b"offline-checkpoint-fixture")
        return root, selected

    def test_canonical_rng_and_checkpoint_preserve_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, selected = self.make_checkpoint(Path(tmp))
            step, digest = worker.validated_checkpoint(root, selected)
            self.assertEqual(step, 4)
            self.assertEqual(len(digest), 64)

    def test_backup_rng_cannot_replace_actual_resume_rng(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, selected = self.make_checkpoint(Path(tmp))
            (selected / "rng_state.pth").rename(selected / "rng_state_backup.pth")
            with self.assertRaisesRegex(ValueError, "RNG_MISSING"):
                worker.validated_checkpoint(root, selected)

    def test_mixed_rng_namespace_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, selected = self.make_checkpoint(Path(tmp))
            (selected / "rng_state_backup.pth").write_bytes(b"stale")
            with self.assertRaisesRegex(ValueError, "RNG_MISSING"):
                worker.validated_checkpoint(root, selected)

    def test_rank_rng_retains_reviewed_donor_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, selected = self.make_checkpoint(Path(tmp))
            (selected / "rng_state.pth").rename(selected / "rng_state_0.pth")
            self.assertEqual(worker.validated_checkpoint(root, selected)[0], 4)

    def test_checkpoint_root_symlink_rejected_before_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, selected = self.make_checkpoint(Path(tmp))
            alias = Path(tmp) / "alias"
            alias.symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "REPARSE_ANCESTOR"):
                worker.validated_checkpoint(alias, alias / selected.name)

    def test_selected_parent_alias_rejected_even_when_resolved_parent_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, selected = self.make_checkpoint(Path(tmp))
            alias = Path(tmp) / "alias"
            alias.symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "REPARSE_ANCESTOR"):
                worker.validated_checkpoint(root, alias / selected.name)


if __name__ == "__main__":
    unittest.main()
