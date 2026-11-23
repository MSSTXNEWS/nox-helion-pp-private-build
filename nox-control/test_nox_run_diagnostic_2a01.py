#!/usr/bin/env python3
"""Offline focused regression: RELAY35 2A01 remains an explicit HOLD."""
import importlib.util
from pathlib import Path
from unittest import mock
import unittest

MODULE = Path(__file__).with_name("nox_run_diagnostic.py")
spec = importlib.util.spec_from_file_location("nox_run_diagnostic", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HardwareInventoryTest(unittest.TestCase):
    def test_bounded_host_facts_never_admit_execution(self):
        class Result:
            returncode = 0
            stdout = ""

        good_gpu = (
            "0, GPU-a, Tesla V100-SXM2-32GB, 00000000:00:05.0, 32510, 12000, 50, 550.54, 7.0, 3, 16\n"
            "1, GPU-b, Tesla V100-SXM2-32GB, 00000000:00:06.0, 32510, 12000, 52, 550.54, 7.0, 3, 16\n"
        )
        calls = []

        def fake_run(argv, **kwargs):
            self.assertEqual(kwargs["timeout"], 8)
            calls.append(argv)
            result = Result()
            result.stdout = good_gpu if "--query-gpu=" in argv[1] else "GPU0 GPU1\nGPU0 X NV2\nGPU1 NV2 X\n"
            return result

        with mock.patch.object(module.subprocess, "run", fake_run), \
             mock.patch.object(module.os, "statvfs", side_effect=OSError), \
             mock.patch.object(module.Path, "read_text", return_value="1000"):
            result = module.hardware_2a01_snapshot()
        self.assertEqual(len(result["gpu"]), 2)
        self.assertEqual(result["gpu0_to_gpu1_topology_class"], "NV2")
        self.assertEqual(result["cgroup"]["headroom_bytes"], 0)
        self.assertFalse(result["native_accepted"])
        self.assertFalse(result["may_activate"])
        self.assertIn("HOLD_2A01_MAYA_BUILD_PIN_UNVERIFIED", result["hold_codes"])
        self.assertIn("HOLD_2A01_SSD_IO_UNMEASURED", result["hold_codes"])
        self.assertEqual(len(calls), 2)

    def test_absent_driver_fail_closed(self):
        with mock.patch.object(module.subprocess, "run", side_effect=FileNotFoundError), \
             mock.patch.object(module.os, "statvfs", side_effect=OSError), \
             mock.patch.object(module.Path, "read_text", side_effect=OSError):
            result = module.hardware_2a01_snapshot()
        self.assertEqual(result["gpu"], [])
        self.assertIsNone(result["gpu0_to_gpu1_topology_class"])
        self.assertIsNone(result["cgroup"]["headroom_bytes"])
        self.assertFalse(result["native_accepted"])
        self.assertIn("HOLD_2A01_EXACT_TWO_GPU_FIELDS", result["hold_codes"])


if __name__ == "__main__":
    unittest.main()
