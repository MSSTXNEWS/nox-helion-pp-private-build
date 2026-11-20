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
            node.name in ("_gpu_utilization_percent", "_status_flat")]
    assert len(keep) == 2
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
