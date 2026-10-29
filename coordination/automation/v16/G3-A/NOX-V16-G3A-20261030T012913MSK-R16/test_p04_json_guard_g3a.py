#!/usr/bin/env python3
"""P04 G3-A regression proposals; run in a repo checkout with current/owner-patched source.

Before manual #3 patch: four negative cases should FAIL and positive should PASS.
After owner adoption: all five must PASS. Not native/GPU/QA acceptance.
"""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SOURCE = Path(os.environ.get("NOX_P04_PROBE_PATH", str(ROOT / "Packages/P04/model_snapshot_probe.py")))
spec = importlib.util.spec_from_file_location("p04_probe_g3a_under_test", SOURCE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

class P04JsonSafetyG3A(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config('{"model_type":"llama"}')
        self.weights({"q.weight":{"dtype":"F32","shape":[1],"data_offsets":[0,4]}}, b"\x00" * 4)

    def config(self, raw):
        (self.root / "config.json").write_text(raw, encoding="utf-8")

    def weights(self, header, body):
        encoded = json.dumps(header, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        (self.root / "model.safetensors").write_bytes(
            len(encoded).to_bytes(8, "little") + encoded + body)

    def inspect(self):
        return probe.inspect(self.root, "a" * 40)

    def test_g3a_valid_local_only_remains_not_attested(self):
        report = self.inspect()
        self.assertEqual(report["status"], "LOCAL_FILES_PRESENT_ONLY")
        self.assertFalse(report["model_license_verified"])
        self.assertFalse(report["dataset_rights_verified"])
        self.assertFalse(report["gpu_training_verified"])

    def test_g3a_rejects_float_overflow_in_config(self):
        self.config('{"model_type":"llama","extra":1e9999}')
        report = self.inspect()
        self.assertEqual((report["status"], report["reason"]), ("HOLD", "MODEL_METADATA_INVALID"))

    def test_g3a_rejects_nested_escaped_surrogate(self):
        self.config(r'{"model_type":"llama","nested":{"key":"\ud800"}}')
        report = self.inspect()
        self.assertEqual((report["status"], report["reason"]), ("HOLD", "MODEL_METADATA_INVALID"))

    def test_g3a_rejects_surrogate_tensor_name(self):
        self.weights({"\ud800":{"dtype":"F32","shape":[1],"data_offsets":[0,4]}},
                     b"\x00" * 4)
        report = self.inspect()
        self.assertEqual((report["status"], report["reason"]),
                         ("HOLD", "MODEL_SAFETENSORS_HEADER_INVALID"))

    def test_g3a_rejects_zero_element_uint64_dim_overflow(self):
        self.weights({"q.weight":{"dtype":"F32","shape":[0,2**64],"data_offsets":[0,0]}},
                     b"")
        report = self.inspect()
        self.assertEqual((report["status"], report["reason"]),
                         ("HOLD", "MODEL_SAFETENSORS_HEADER_INVALID"))

if __name__ == "__main__":
    unittest.main()
