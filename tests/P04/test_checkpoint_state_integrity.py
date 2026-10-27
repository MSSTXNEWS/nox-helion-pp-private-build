"""Offline full-state checkpoint identity tests; never train/download weights."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

WORKER = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "train_qlora.py"

def source():
    spec = importlib.util.spec_from_file_location("nox_p04_checkpoint_test", WORKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

class CheckpointGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = source()

    def make_checkpoint(self, folder):
        root = folder / "checkpoints"
        checkpoint = root / "checkpoint-4"
        checkpoint.mkdir(parents=True)
        (checkpoint / "trainer_state.json").write_text(json.dumps({"global_step": 4}), encoding="utf-8")
        for name in ("adapter_model.safetensors", "optimizer.pt", "scheduler.pt", "rng_state.pth"):
            (checkpoint / name).write_bytes(("fixture:" + name).encode("ascii"))
        return root, checkpoint

    def test_complete_checkpoint_and_exact_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, chk = self.make_checkpoint(Path(tmp))
            step, digest = self.w.validated_checkpoint(root, chk)
            self.assertEqual(step, 4)
            self.assertEqual(len(digest), 64)
            (chk / "scheduler.pt").write_bytes(b"new scheduler fixture")
            self.assertNotEqual(self.w.validated_checkpoint(root, chk)[1], digest)

    def test_missing_optimizer_and_rng_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, chk = self.make_checkpoint(Path(tmp))
            (chk / "optimizer.pt").unlink()
            with self.assertRaises(ValueError):
                self.w.validated_checkpoint(root, chk)
            (chk / "optimizer.pt").write_bytes(b"fixture")
            (chk / "rng_state.pth").unlink()
            with self.assertRaises(ValueError):
                self.w.validated_checkpoint(root, chk)

    def test_trainer_step_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, chk = self.make_checkpoint(Path(tmp))
            (chk / "trainer_state.json").write_text('{"global_step":5}', encoding="utf-8")
            with self.assertRaises(ValueError):
                self.w.validated_checkpoint(root, chk)

if __name__ == "__main__":
    unittest.main()
