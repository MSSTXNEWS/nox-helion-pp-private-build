"""D05 R5 original Windows-GPU preflight JSON admission: fail closed on ambiguity.

This executes ExistingP04Background.preflight with an isolated subprocess stub.
SOURCE_ONLY: no CUDA device, model weights, native S03, or E07 are exercised.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.nox_selfbuilder.background_forge import ExistingP04Background


class D05GpuPreflightJsonTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.owner = object.__new__(ExistingP04Background)
        self.owner.p04 = root
        self.owner.python = Path(sys.executable)
        self.job = SimpleNamespace(profile="BALANCED", gpu_index=0)

    def inspect(self, output):
        response = SimpleNamespace(stdout=output, returncode=0)
        with patch("src.nox_selfbuilder.background_forge.os.name", "nt"), \
             patch("src.nox_selfbuilder.background_forge.subprocess.run", return_value=response):
            return self.owner.preflight(self.job)

    def test_genuine_hardware_only_response_remains_diagnostic(self):
        result = self.inspect(json.dumps({
            "status": "HARDWARE_READY_ONLY",
            "runtime_training_verified": False,
            "gpu": {"temperature_c": 72.5},
        }))
        self.assertEqual(result["status"], "HARDWARE_READY_ONLY")
        self.assertIs(result["runtime_training_verified"], False)

    def test_repeated_status_must_not_override_failed_gpu_preflight(self):
        result = self.inspect('{"status":"HOLD","status":"HARDWARE_READY_ONLY",'
                              '"runtime_training_verified":false}')
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "GPU_PREFLIGHT_AMBIGUOUS_JSON_HOLD")
        self.assertIs(result["activation_allowed"], False)

    def test_nested_case_aliased_gpu_telemetry_is_ambiguous(self):
        result = self.inspect('{"status":"HARDWARE_READY_ONLY",'
                              '"runtime_training_verified":false,'
                              '"gpu":{"temperature":77,"Temperature":null}}')
        self.assertEqual(result["reason"], "GPU_PREFLIGHT_AMBIGUOUS_JSON_HOLD")

    def test_nonfinite_gpu_telemetry_is_hold(self):
        for token in ("NaN", "Infinity", "1e999"):
            with self.subTest(token=token):
                result = self.inspect('{"status":"HARDWARE_READY_ONLY",'
                                      '"runtime_training_verified":false,'
                                      '"gpu":{"temperature":' + token + '}}')
                self.assertEqual(result["reason"], "GPU_PREFLIGHT_NONFINITE_HOLD")

    def test_corrupted_response_is_not_ready(self):
        result = self.inspect("{")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "GPU_TRAINING_HOLD")


if __name__ == "__main__":
    unittest.main()
