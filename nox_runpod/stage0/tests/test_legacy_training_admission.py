import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from training_admission import AUTHORIZED_TARGET, admission_hold_reason


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manifest = Path(self.tmp.name) / "manifest.json"

    def authorized_env(self, document=None):
        body = document or {
            "status": "AUTHORIZED",
            "target_model": AUTHORIZED_TARGET,
            "trainable_base": True,
            "license_status": "VERIFIED",
            "source_revision": "a" * 40,
            "quantized_inference_only": False,
        }
        raw = json.dumps(body, sort_keys=True).encode()
        self.manifest.write_bytes(raw)
        return {
            "NOX_TRAINING_ADMISSION": "AUTHORIZED",
            "NOX_TRAINING_TARGET": AUTHORIZED_TARGET,
            "NOX_TRAINING_MANIFEST": str(self.manifest),
            "NOX_TRAINING_MANIFEST_SHA256": hashlib.sha256(raw).hexdigest(),
        }

    def test_default_is_hold(self):
        self.assertEqual(admission_hold_reason(env={}), "EXPLICIT_TRAINING_ADMISSION_REQUIRED")

    def test_stop_marker_overrides_authorization(self):
        env = self.authorized_env()
        marker = Path(self.tmp.name) / "STOP"
        marker.touch()
        self.assertEqual(admission_hold_reason(env, [marker]), "STOP_OR_MODEL_UPDATE_PRESENT")

    def test_legacy_target_is_never_admitted(self):
        env = self.authorized_env()
        env["NOX_TRAINING_TARGET"] = "NOX_9B_UNIFIED"
        self.assertEqual(admission_hold_reason(env, []), "TARGET_NOT_AUTHORIZED")

    def test_manifest_hash_must_match(self):
        env = self.authorized_env()
        env["NOX_TRAINING_MANIFEST_SHA256"] = "0" * 64
        self.assertEqual(admission_hold_reason(env, []), "MODEL_MANIFEST_SHA256_MISMATCH")

    def test_hold_and_quantized_manifests_are_rejected(self):
        env = self.authorized_env({"status": "HOLD"})
        self.assertEqual(admission_hold_reason(env, []), "MODEL_MANIFEST_NOT_AUTHORIZED")
        env = self.authorized_env({
            "status": "AUTHORIZED", "target_model": AUTHORIZED_TARGET,
            "trainable_base": True, "license_status": "VERIFIED",
            "source_revision": "a" * 40, "quantized_inference_only": True,
        })
        self.assertEqual(admission_hold_reason(env, []), "QUANTIZED_OR_INFERENCE_ONLY_BASE")

    def test_valid_pinned_trainable_manifest_passes(self):
        self.assertIsNone(admission_hold_reason(self.authorized_env(), []))

    def test_legacy_trainer_checks_gate_before_cuda_optimizer_or_checkpoint(self):
        stage0 = Path(__file__).resolve().parents[1]
        source = (stage0 / "a40_full_parameter_distill_cycle.py").read_text(encoding="utf-8")
        self.assertNotIn("STATE.mkdir(parents=True,exist_ok=True)\nDEST.mkdir", source)
        main = source[source.index("def main():"):]
        gate = main.index("admission_hold_reason")
        for forbidden in ("import torch", "torch.optim.Adafactor", "loss.backward()", "opt.step()", "save_pretrained"):
            self.assertLess(gate, main.index(forbidden))


if __name__ == "__main__":
    unittest.main()
