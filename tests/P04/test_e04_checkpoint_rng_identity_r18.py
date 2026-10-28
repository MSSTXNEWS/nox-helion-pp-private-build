"""R18: offline real-source P04 checkpoint RNG identity contract; NO_GPU, NO_EXE."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

FILE = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "train_qlora.py"
spec = importlib.util.spec_from_file_location("p04_rng_r18", FILE)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

class RngIdentity(unittest.TestCase):
    def check_rng(self, names, accepted):
        with tempfile.TemporaryDirectory() as tmp:
            chk = Path(tmp) / "checkpoints" / "checkpoint-7"
            chk.mkdir(parents=True)
            (chk / "trainer_state.json").write_text('{"global_step":7}', encoding="utf-8")
            for name in ("adapter_model.safetensors", "optimizer.pt", "scheduler.pt", *names):
                (chk / name).write_bytes(b"fixture-only")
            if accepted:
                step, tree_sha = worker.validated_checkpoint(chk.parent, chk)
                self.assertEqual(step, 7)
                self.assertRegex(tree_sha, r"^[0-9a-f]{64}$")
            else:
                with self.assertRaisesRegex(ValueError, "RESUME_CHECKPOINT_RNG_MISSING"):
                    worker.validated_checkpoint(chk.parent, chk)

    def test_canonical_rng(self): self.check_rng(["rng_state.pth"], True)
    def test_ranked_rng(self): self.check_rng(["rng_state_0.pth"], True)
    def test_missing_rng(self): self.check_rng([], False)
    def test_spoofed_rng(self): self.check_rng(["rng_state_backup.pth"], False)
    def test_ambiguous_rng(self): self.check_rng(["rng_state.pth", "rng_state_backup.pth"], False)

    def test_previous_r17_duplicate_json_guard_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            chk = Path(tmp) / "checkpoints" / "checkpoint-7"
            chk.mkdir(parents=True)
            (chk / "trainer_state.json").write_text(
                '{"global_step":7,"Global_Step":7}', encoding="utf-8")
            for name in ("adapter_model.safetensors", "optimizer.pt", "scheduler.pt", "rng_state.pth"):
                (chk / name).write_bytes(b"fixture")
            with self.assertRaisesRegex(ValueError, "INPUT_JSON_DUPLICATE_KEY"):
                worker.validated_checkpoint(chk.parent, chk)

if __name__ == "__main__": unittest.main()
