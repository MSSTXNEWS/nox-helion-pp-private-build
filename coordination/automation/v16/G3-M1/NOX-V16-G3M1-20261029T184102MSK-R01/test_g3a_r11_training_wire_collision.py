"""G3-A R11 source-only contract regressions: no real GPU or training."""
import importlib.util
import pathlib
import threading
import unittest

SOURCE = pathlib.Path(__file__).with_name("p04_training_native_binding_g3m1.py")
spec = importlib.util.spec_from_file_location("g3a_r11_p04_source", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class G3AR11TrainingWireCollision(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.receipt = "a" * 64

        def owner_action(route):
            def invoke(session, payload):
                self.calls.append((route, payload))
                return {"route": route, "ownerReceiptSha256": self.receipt}
            return invoke

        self.binding = mod.ExistingP04TrainingBinding(
            owner_receipt_sha256=self.receipt,
            owner_lease=threading.RLock(),
            native_authorize=lambda *_: True,
            owner_model_and_rights=lambda *_: True,
            existing_backend_ready=lambda: True,
            existing_start=owner_action("training.start"),
            existing_evaluate=owner_action("training.evaluate"),
            verify_owner_ack=lambda *_: True,
        )

    def test_g3a_r11_start_rejects_top_level_normalized_json_key_collision(self):
        with self.assertRaisesRegex(mod.P04NativeTrainingHold, "JSON_PROPERTY_COLLISION"):
            self.binding.start("native", {"1": "approved", 1: "overridden"})
        self.assertEqual(self.calls, [])

    def test_g3a_r11_evaluate_rejects_nested_normalized_json_key_collision(self):
        with self.assertRaisesRegex(mod.P04NativeTrainingHold, "JSON_PROPERTY_COLLISION"):
            self.binding.evaluate("native", {"model": {"0": "checkpoint-A", 0: "checkpoint-B"}})
        self.assertEqual(self.calls, [])

    def test_g3a_r11_ack_nested_property_collision_rejected(self):
        self.binding._callbacks["training.start"] = lambda *_: {
            "route": "training.start", "ownerReceiptSha256": self.receipt,
            "metadata": {"1": "attested", 1: "unattested"},
        }
        with self.assertRaisesRegex(mod.P04NativeTrainingHold, "JSON_PROPERTY_COLLISION"):
            self.binding.start("native", {"jobId": "safe"})
        # The native callback was invoked, but an invalid ACK is never accepted.

    def test_g3a_r11_valid_nested_unicode_payload_preserves_values(self):
        ack = self.binding.evaluate("native", {"dataset": {"owner": "принято", "revision": "r1"}})
        self.assertEqual(ack["route"], "training.evaluate")
        self.assertEqual(self.calls, [("training.evaluate", {"dataset": {"owner": "принято", "revision": "r1"}})])

    def test_g3a_r11_invalid_number_still_rejected_before_native_action(self):
        with self.assertRaises(mod.P04NativeTrainingHold):
            self.binding.start("native", {"value": float("inf")})
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
