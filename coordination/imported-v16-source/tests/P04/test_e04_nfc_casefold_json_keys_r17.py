"""P04 real-source regression for NFC/casefold JSON property identity (CPU-only)."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("nox_p04_qlora_r17", ROOT / "Packages/P04/train_qlora.py")
p04 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p04)


class P04JsonPropertyParityRegression(unittest.TestCase):
    def parse_file(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "lock.json"
            file.write_text(payload, encoding="utf-8")
            return p04.read_object(file)

    def test_manifest_root_case_collision(self):
        with self.assertRaisesRegex(ValueError, "INPUT_JSON_DUPLICATE_KEY"):
            self.parse_file('{"license_id":"L1","LICENSE_ID":"L2"}')

    def test_model_lock_nested_case_collision(self):
        with self.assertRaisesRegex(ValueError, "INPUT_JSON_DUPLICATE_KEY"):
            self.parse_file('{"model":{"owner_approval_id":"A","OWNER_APPROVAL_ID":"B"}}')

    def test_manifest_nfc_collision(self):
        with self.assertRaisesRegex(ValueError, "INPUT_JSON_DUPLICATE_KEY"):
            self.parse_file('{"nom\\u00e9":"A","nome\\u0301":"B"}')

    def test_rights_attestation_case_collision(self):
        with self.assertRaisesRegex(ValueError, "RIGHTS_VERIFIER_DUPLICATE_KEY"):
            p04.parse_rights_verifier_response('{"status":"VERIFIED","STATUS":"DENIED"}')

    def test_rights_attestation_nested_nfc_collision(self):
        with self.assertRaisesRegex(ValueError, "RIGHTS_VERIFIER_DUPLICATE_KEY"):
            p04.parse_rights_verifier_response('{"meta":{"nom\\u00e9":"A","nome\\u0301":"B"}}')

    def test_training_record_case_collision(self):
        with self.assertRaisesRegex(ValueError, "TRAIN_JSON_DUPLICATE_KEY_1"):
            p04.parse_dataset_record('{"text":"ok","TEXT":"injected"}', "TRAIN", 1)

    def test_holdout_nested_case_collision(self):
        with self.assertRaisesRegex(ValueError, "HOLDOUT_JSON_DUPLICATE_KEY_2"):
            p04.parse_dataset_record(
                '{"messages":[{"role":"assistant","content":"ok","CONTENT":"injected"}]}',
                "HOLDOUT", 2)

    def test_exact_duplicate_still_blocked(self):
        with self.assertRaisesRegex(ValueError, "RIGHTS_VERIFIER_DUPLICATE_KEY"):
            p04.parse_rights_verifier_response('{"status":"A","status":"B"}')

    def test_distinct_valid_fields_preserved(self):
        self.assertEqual(self.parse_file('{"dataset_id":"A","license_id":"B"}'),
                         {"dataset_id": "A", "license_id": "B"})
        self.assertEqual(p04.parse_dataset_record('{"text":"Hello"}', "TRAIN", 1),
                         {"text": "Hello"})

    def test_previous_r16_identity_type_gate_retained(self):
        revision = "a" * 40
        for approval, model_id in ((True, "model"), (123, "model"), ("APPROVED", " ")):
            lock = {"schema": "nox-model-lock-v1", "license_status": "APPROVED",
                    "owner_approval_id": approval, "model_id": model_id,
                    "revision": revision, "snapshot_sha256": "b" * 64}
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "model-lock.json"
                path.write_text(json.dumps(lock), encoding="utf-8")
                with mock.patch.object(p04, "sha256_tree", side_effect=AssertionError("hash before rights gate")):
                    with self.assertRaises(ValueError):
                        p04.verify_model_lock(path, Path(directory), revision)


if __name__ == "__main__":
    unittest.main()
