"""6A05: cgroup RAM and zero headroom must never be relabeled as host capacity.

One isolated source regression: pure functions only; no server or model access.
"""
import ast
import math
from pathlib import Path
import time
import unittest


def load_telemetry():
    source = Path(__file__).with_name("bridge").joinpath("nox_webapi.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {"_ram", "_gpu_utilization_percent", "_verified_gpu_sensor_values", "_status_flat"}
    funcs = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(funcs) == len(names)
    ns = {"math": math, "time": time,
          "M": {"t": time.time(), "gpu": [], "cpu": None, "ram": None, "disk": None}}
    exec(compile(ast.Module(body=funcs, type_ignores=[]), "<nox_ram_6a05>", "exec"), ns)
    return ns


class CgroupRamTelemetryTests(unittest.TestCase):
    def test_zero_free_disk_and_zero_cgroup_usage_are_real_zeros(self):
        ns = load_telemetry()
        readings = {
            "/sys/fs/cgroup/memory.current": "0",
            "/sys/fs/cgroup/memory.max": "2147483648",
        }
        ns["_read"] = readings.get
        ns["M"]["ram"] = ns["_ram"]()
        ns["M"]["disk"] = (0.0, 20.0)
        result = ns["_status_flat"]()
        self.assertEqual(ns["M"]["ram"], (0.0, 2.0))
        self.assertEqual(result["ram_percent"], 0.0)
        self.assertEqual(result["ram_used_gb"], 0.0)
        self.assertEqual(result["disk_free_gib"], 0.0)

    def test_malformed_bounded_cgroup_never_falls_back_to_host_ram(self):
        ns = load_telemetry()
        for used, maximum in (
            ("not-a-number", "2147483648"),
            ("-1", "2147483648"),
            ("9999999999", "2147483648"),
            ("0", "bad-limit"),
            (None, "2147483648"),
            ("0", None),
            ("0", "0"),
        ):
            with self.subTest(used=used, maximum=maximum):
                ns["_read"] = lambda path, a=used, b=maximum: (
                    a if path.endswith("memory.current") else
                    b if path.endswith("memory.max") else None)
                self.assertEqual(ns["_ram"](), (None, None))


if __name__ == "__main__":
    unittest.main()
