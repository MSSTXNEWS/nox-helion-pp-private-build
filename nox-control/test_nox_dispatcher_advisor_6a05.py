"""6A05: malformed owner telemetry must fail closed without exceptions or false progress."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "nox_dispatcher_advisor", Path(__file__).with_name("nox_dispatcher_advisor.py")
)
advisor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(advisor)


def snapshot():
    return {
        "stop_active": False,
        "onehost": {"healthy": True},
        "s03": {"readback_verified": True},
        "trainer": {"running": False},
        "gpu": {"temperature_c": 58, "temperature_sensor_valid": True},
        "disk": {"free_gib": 15, "checkpoint_reserve_gib": 10},
    }


def codes(data):
    return [item["code"] for item in advisor.assess(data)]


class ReliableOwnerTelemetryTests(unittest.TestCase):
    def test_valid_evidence_remains_observation_only(self):
        self.assertEqual(codes(snapshot()), ["NO_UNVERIFIED_TUNING"])

    def test_invalid_disk_free_space_never_passes_as_capacity(self):
        for invalid in (True, False, "25", float("nan"), float("inf"), -1, 10**400, [], {}):
            with self.subTest(free=repr(invalid)):
                s = snapshot()
                s["disk"]["free_gib"] = invalid
                self.assertIn("DISK_TELEMETRY_UNVERIFIED", codes(s))

    def test_invalid_checkpoint_reserve_never_throws(self):
        for invalid in (True, "missing", float("nan"), float("-inf"), -1, 10**400, [], {}):
            with self.subTest(reserve=repr(invalid)):
                s = snapshot()
                s["disk"]["checkpoint_reserve_gib"] = invalid
                self.assertIn("DISK_TELEMETRY_UNVERIFIED", codes(s))

    def test_unknown_disk_and_real_pressure_preserved(self):
        s = snapshot()
        s["disk"]["free_gib"] = None
        self.assertIn("DISK_UNKNOWN", codes(s))
        s = snapshot()
        s["disk"]["free_gib"] = 4
        self.assertIn("DISK_CHECKPOINT_RESERVE", codes(s))

    def test_invalid_temperature_is_safety_hold(self):
        for invalid in (True, "58", float("nan"), float("inf"), -1, 10**400, [], {}):
            with self.subTest(temperature=repr(invalid)):
                s = snapshot()
                s["gpu"]["temperature_c"] = invalid
                self.assertIn("GPU_THERMAL_READING_INVALID", codes(s))
        s = snapshot()
        s["gpu"]["temperature_c"] = 70
        self.assertIn("GPU_THERMAL_LIMIT", codes(s))

    def test_owner_stop_still_precedes_bad_metrics(self):
        s = snapshot()
        s["stop_active"] = True
        s["disk"]["checkpoint_reserve_gib"] = "broken"
        self.assertEqual(codes(s), ["STOP_ACTIVE"])


if __name__ == "__main__":
    unittest.main()
