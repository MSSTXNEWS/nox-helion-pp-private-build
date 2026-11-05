"""Fail-closed external GPU entrypoint contracts, source-only (not GPU evidence)."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "nox_selfbuilder"))
from external_gpu_train_gate import require_external_gpu_train

ACK = {"status": "SELFLEARN_ACK"}
SHA = "ab" * 32


class ExternalGpuTrainGateR98(unittest.TestCase):
    def test_real_structurally_valid_inputs_are_only_ready(self):
        self.assertEqual(require_external_gpu_train(ack=ACK, gpu_present=True, weights_sha256=SHA),
                         {"status": "READY", "code": "GPU_TRAIN_GATES_OK"})

    def test_missing_or_untrusted_ack_is_hold(self):
        for ack in (None, {}, {"status": "HOLD"}, "SELFLEARN_ACK", {"status": True}):
            with self.subTest(ack=ack):
                self.assertEqual(require_external_gpu_train(ack=ack, gpu_present=True,
                                                           weights_sha256=SHA)["code"],
                                 "GPU_TRAIN_ACK_REQUIRED")

    def test_only_actual_boolean_true_admits_gpu(self):
        for value in (False, None, 0, 1, "false", "true", [], [True], {"gpu": True}):
            with self.subTest(value=value):
                self.assertEqual(require_external_gpu_train(ack=ACK, gpu_present=value,
                                                           weights_sha256=SHA)["code"],
                                 "EXTERNAL_GPU_MISSING")

    def test_only_lowercase_hex_sha256_is_accepted(self):
        bad = (None, 123, True, "", "a" * 63, "a" * 65, "z" * 64,
               "G" * 64, "AB" * 32, "a" * 63 + "!", " " + "a" * 63)
        for value in bad:
            with self.subTest(value=value):
                self.assertEqual(require_external_gpu_train(ack=ACK, gpu_present=True,
                                                           weights_sha256=value)["code"],
                                 "WEIGHTS_SHA_REQUIRED")


if __name__ == "__main__":
    unittest.main()
