"""6A04: status must not turn missing sensor data into zero GPU load.

Load only the pure status functions via AST: no FastAPI, model or server required.
"""
import ast
import math
from pathlib import Path
import time
import unittest


def load_status():
    source = Path(__file__).with_name("bridge").joinpath("nox_webapi.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    keep = [node for node in tree.body if isinstance(node, ast.FunctionDef) and
            node.name in ("_gpu_utilization_percent", "_verified_gpu_sensor_values", "_status_flat")]
    assert len(keep) == 3
    ns = {"math": math, "time": time, "M": {
        "t": time.time(), "gpu": [], "cpu": 15, "ram": (5, 12), "disk": (10, 20)
    }}
    exec(compile(ast.Module(body=keep, type_ignores=[]), "<nox_status_6a04>", "exec"), ns)
    return ns


def sample(util):
    return {"util": util, "mem_used_gib": 3.0, "mem_total_gib": 16.0,
            "temp_c": 58, "power_w": 85}


class WebGpuStatusTests(unittest.TestCase):
    def test_two_verified_gpus_average_without_invented_idle(self):
        ns = load_status()
        ns["M"]["gpu"] = [sample(10), sample(30)]
        result = ns["_status_flat"]()
        self.assertEqual(result["gpu_percent"], 20.0)
        self.assertEqual(result["vram_used_gb"], 6.0)
        self.assertTrue(result["fresh"])

    def test_unknown_sensor_does_not_become_zero(self):
        ns = load_status()
        ns["M"]["gpu"] = [sample(15), sample(None)]
        result = ns["_status_flat"]()
        self.assertIsNone(result["gpu_percent"])
        self.assertEqual(result["vram_used_gb"], 6.0)

    def test_missing_sensors_are_unknown_not_faked_as_zero_or_hotspot(self):
        ns = load_status()
        ns["M"]["gpu"] = [sample(10), sample(30)]
        result = ns["_status_flat"]()
        self.assertEqual(result["gpu_temperature_c"], 58)
        self.assertEqual(result["gpu_power_w"], 170)
        self.assertIsNone(result["gpu_hotspot_c"])  # no hotspot sensor queried

        missing_temp = sample(30)
        missing_temp["temp_c"] = None
        ns["M"]["gpu"] = [sample(10), missing_temp]
        result = ns["_status_flat"]()
        self.assertIsNone(result["gpu_temperature_c"])
        self.assertEqual(result["gpu_power_w"], 170)
        self.assertIsNone(result["gpu_hotspot_c"])

        missing_power = sample(30)
        missing_power["power_w"] = None
        ns["M"]["gpu"] = [sample(10), missing_power]
        result = ns["_status_flat"]()
        self.assertEqual(result["gpu_temperature_c"], 58)
        self.assertIsNone(result["gpu_power_w"])

        extreme = sample(30)
        extreme["power_w"] = 10 ** 500
        extreme["temp_c"] = float("nan")
        ns["M"]["gpu"] = [extreme]
        result = ns["_status_flat"]()
        self.assertIsNone(result["gpu_temperature_c"])
        self.assertIsNone(result["gpu_power_w"])

    def test_stale_or_future_telemetry_never_reports_live_capacity(self):
        ns = load_status()
        ns["M"]["gpu"] = [sample(0), sample(25)]
        for sample_time in (time.time() - 31, time.time() + 120, 0):
            with self.subTest(sample_time=sample_time):
                ns["M"]["t"] = sample_time
                result = ns["_status_flat"]()
                self.assertFalse(result["fresh"])
                self.assertIsNone(result["gpu_percent"])
                self.assertIsNone(result["vram_used_gb"])
                self.assertIsNone(result["vram_total_gb"])
                self.assertIsNone(result["gpu_temperature_c"])
                self.assertIsNone(result["gpu_power_w"])
                self.assertIsNone(result["cpu_percent"])
                self.assertIsNone(result["ram_percent"])
                self.assertIsNone(result["disk_free_gib"])
                self.assertEqual(result["gpus"], [])

    def test_invalid_sampler_timestamps_fail_closed_without_status_crash(self):
        ns = load_status()
        ns["M"]["gpu"] = [sample(12), sample(36)]
        for sample_time in (None, True, "bad", "1740000000", {}, [],
                            float("nan"), float("inf"), float("-inf"),
                            10**500, 1e308, -1e308):
            with self.subTest(sample_time=str(sample_time)[:24]):
                ns["M"]["t"] = sample_time
                result = ns["_status_flat"]()
                self.assertFalse(result["fresh"])
                self.assertIsNone(result["timestamp"])
                self.assertIsNone(result["timestamp_utc"])
                for key in ("gpu_percent", "vram_used_gb", "vram_total_gb",
                            "gpu_temperature_c", "gpu_power_w", "cpu_percent",
                            "ram_percent", "disk_free_gib"):
                    self.assertIsNone(result[key])
                self.assertEqual(result["gpus"], [])

    def test_malformed_and_extreme_readings_fail_closed(self):
        ns = load_status()
        for value in (None, True, False, "0", -1, 100.01,
                      float("nan"), float("inf"), 10**500):
            with self.subTest(value=str(value)[:24]):
                self.assertIsNone(ns["_gpu_utilization_percent"]([sample(value)]))
        self.assertIsNone(ns["_gpu_utilization_percent"]([]))
        self.assertIsNone(ns["_gpu_utilization_percent"]([{}]))
        self.assertIsNone(ns["_gpu_utilization_percent"]("[]"))
        self.assertEqual(ns["_gpu_utilization_percent"]([sample(0)]), 0.0)


if __name__ == "__main__":
    unittest.main()
