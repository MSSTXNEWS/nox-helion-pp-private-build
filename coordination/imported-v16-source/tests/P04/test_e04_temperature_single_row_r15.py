"""Negative regressions for the real P04 NVIDIA temperature sensor gate.

CPU fixtures test parser semantics only; they DO NOT demonstrate GPU training.
Run: python -m unittest discover -s tests/P04 -p test_e04_temperature_single_row_r15.py
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import subprocess
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "train_qlora.py"
spec = importlib.util.spec_from_file_location("nox_p04_qlora_r15", MODULE_PATH)
assert spec is not None and spec.loader is not None
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class SingleGpuTemperatureRowTests(unittest.TestCase):
    def read(self, stdout, returncode=0):
        with patch.object(worker.subprocess, "run", return_value=SimpleNamespace(
            stdout=stdout, returncode=returncode)):
            return worker.gpu_temperature("nvidia-smi", "GPU-1234")

    def test_single_reading(self):
        self.assertEqual(self.read("59\n"), 59.0)

    def test_single_decimal_reading(self):
        self.assertEqual(self.read("59.5\n"), 59.5)

    def test_multi_gpu_rows_fail_closed(self):
        self.assertIsNone(self.read("59\n97\n"))

    def test_trailing_blank_second_row_fail_closed(self):
        self.assertIsNone(self.read("59\n\n"))

    def test_missing_reading(self):
        self.assertIsNone(self.read(""))

    def test_not_available_sensor(self):
        self.assertIsNone(self.read("N/A"))

    def test_vendor_failure(self):
        self.assertIsNone(self.read("59", returncode=1))

    def test_outside_thermal_range(self):
        self.assertIsNone(self.read("151"))

    def test_nonfinite_reading(self):
        self.assertIsNone(self.read("NaN"))

    def test_timeout_is_thermal_hold(self):
        with patch.object(worker.subprocess, "run", side_effect=subprocess.TimeoutExpired("nvidia-smi", 5)):
            self.assertIsNone(worker.gpu_temperature("nvidia-smi", "GPU-1234"))

    def test_telemetry_process_unavailable(self):
        with patch.object(worker.subprocess, "run", side_effect=OSError("missing")):
            self.assertIsNone(worker.gpu_temperature("nvidia-smi", "GPU-1234"))


if __name__ == "__main__":
    unittest.main()
