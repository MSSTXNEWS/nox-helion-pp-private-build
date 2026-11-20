"""Focused fail-closed 6A04 GPU utilization/admission regression."""
import importlib.util
from pathlib import Path
import unittest

p = Path(__file__).with_name("nox_dispatcher_advisor.py")
spec = importlib.util.spec_from_file_location("nox_dispatcher_advisor", p)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def snapshot():
    return {"stop_active": False, "onehost": {"healthy": True, "chat_waiting": False,
                                             "chat_p95_ms": 200, "chat_budget_ms": 300,
                                             "chat_metrics_age_sec": 1},
            "s03": {"readback_verified": True},
            "trainer": {"running": True, "checkpoint_recent": True},
            "gpu": {"temperature_c": 58, "temperature_sensor_valid": True,
                    "utilization_pct": 15, "vram_used_mib": 10000,
                    "vram_total_mib": 16000, "age_sec": 1},
            "cpu_io": {"cpu_busy_pct": 40, "io_wait_pct": 2, "age_sec": 1},
            "disk": {"free_gib": 100}}


def codes(s):
    return [x["code"] for x in mod.assess(s)]


class GpuSourceEvidenceTests(unittest.TestCase):
    def test_observed_upper_bound_is_not_admission(self):
        result = mod.assess(snapshot())
        self.assertEqual([x["code"] for x in result], ["GPU_RESIDUAL_OBSERVED_NOT_ADMITTED"])
        self.assertIn("70", result[0]["advice"])
        self.assertIn("no admission", result[0]["advice"])

    def test_missing_host_or_vram_stays_hold(self):
        for field in ("cpu_io",):
            with self.subTest(field=field):
                s=snapshot(); s.pop(field)
                self.assertEqual(codes(s), ["GPU_RESIDUAL_UNVERIFIED"])
        s=snapshot(); s["gpu"]["vram_used_mib"]=20000
        self.assertEqual(codes(s), ["GPU_RESIDUAL_UNVERIFIED"])

    def test_chat_has_priority(self):
        s=snapshot(); s["onehost"]["chat_waiting"]=True
        self.assertEqual(codes(s), ["CHAT_PRIORITY"])
        s=snapshot(); s["onehost"]["chat_p95_ms"]=400
        self.assertEqual(codes(s), ["GPU_CHAT_PRIORITY"])

    def test_cpu_io_pressure_blocks(self):
        s=snapshot(); s["cpu_io"]["io_wait_pct"]=20
        self.assertEqual(codes(s), ["GPU_HOST_PIPELINE_PRESSURE"])

    def test_missing_owner_stop_outranks_budget(self):
        s=snapshot(); s.pop("stop_active")
        self.assertEqual(codes(s), ["STOP_STATE_UNVERIFIED"])

    def test_stale_gpu_and_latency_held(self):
        s=snapshot(); s["gpu"]["age_sec"]=40
        self.assertEqual(codes(s), ["GPU_RESIDUAL_UNVERIFIED"])
        s=snapshot(); s["onehost"]["chat_metrics_age_sec"]=40
        self.assertEqual(codes(s), ["GPU_RESIDUAL_UNVERIFIED"])

    def test_missing_or_invalid_utilization_fails_closed(self):
        values=(None, -1, True, "15", 101, float("nan"),
                float("inf"), 10**500)
        for value in values:
            with self.subTest(value=str(value)[:35]):
                s=snapshot(); s["gpu"]["utilization_pct"]=value
                self.assertEqual(codes(s), ["GPU_UTILIZATION_UNVERIFIED"])
        s=snapshot(); s["gpu"].pop("utilization_pct")
        self.assertEqual(codes(s), ["GPU_UTILIZATION_UNVERIFIED"])

    def test_giant_host_and_vram_telemetry_is_a_hold(self):
        # JSON permits arbitrary-size integers; math.isfinite on them raises
        # OverflowError. No malformed metric may crash owner telemetry.
        for section, field in (
                ("gpu", "vram_used_mib"),
                ("gpu", "vram_total_mib"),
                ("gpu", "age_sec"),
                ("cpu_io", "cpu_busy_pct"),
                ("cpu_io", "io_wait_pct"),
                ("cpu_io", "age_sec"),
                ("onehost", "chat_p95_ms"),
                ("onehost", "chat_budget_ms"),
                ("onehost", "chat_metrics_age_sec")):
            with self.subTest(section=section, field=field):
                s = snapshot()
                s[section][field] = 10**500
                self.assertEqual(codes(s), ["GPU_RESIDUAL_UNVERIFIED"])

    def test_high_valid_utilization_is_not_admission(self):
        s=snapshot(); s["gpu"]["utilization_pct"]=100
        self.assertEqual(codes(s), ["NO_UNVERIFIED_TUNING"])


if __name__ == "__main__":
    unittest.main()
