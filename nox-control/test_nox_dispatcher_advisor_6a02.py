"""6A02: catalog exhaustion never bypasses native owner lease/CAS or RAM gates."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "nox_dispatcher_advisor", Path(__file__).with_name("nox_dispatcher_advisor.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def snapshot():
    return {
        "stop_active": False, "onehost": {"healthy": True},
        "s03": {"readback_verified": True}, "trainer": {"running": False},
        "gpu": {"temperature_sensor_valid": True},
        "disk": {"free_gib": 90},
        "native_queue": {
            "admission_state": "NATIVE_QUEUE_REVIEWED_CATALOG_EXHAUSTED",
            "jobs_started": 0,
            "workers": [{"state": "RUNNING", "current_task": None}],
            "maintenance_busy": False, "active_claims": False,
            "resource_headroom_bytes": 3*1024**3,
        },
    }


def codes(data):
    return [row["code"] for row in mod.assess(data)]


class NativeRefillSourceGateTests(unittest.TestCase):
    def test_idle_without_lease_and_source_is_hold(self):
        result = mod.assess(snapshot())
        self.assertIn("NATIVE_REFILL_OWNER_HOLD", [r["code"] for r in result])
        self.assertNotIn("IDLE_NATIVE_CATALOG_EXHAUSTED", [r["code"] for r in result])
        self.assertTrue(all("Publish one" not in row["advice"] for row in result))

    def test_attested_still_requires_live_owner_review(self):
        s = snapshot()
        s["native_queue"].update(owner_lease_cas_verified=True,
                                 immutable_task_source_verified=True)
        self.assertIn("NATIVE_REFILL_OWNER_REVIEW_REQUIRED", codes(s))
        self.assertNotIn("NATIVE_REFILL_OWNER_HOLD", codes(s))

    def test_low_missing_or_bad_memory_is_not_admitted(self):
        for value in (None, 53_993_472, -1, 2.5*1024**3, True):
            with self.subTest(value=value):
                s = snapshot()
                s["native_queue"].update(owner_lease_cas_verified=True,
                                         immutable_task_source_verified=True,
                                         resource_headroom_bytes=value)
                self.assertIn("NATIVE_REFILL_OWNER_HOLD", codes(s))
                self.assertNotIn("NATIVE_REFILL_OWNER_REVIEW_REQUIRED", codes(s))

    def test_active_claim_or_missing_maintenance_clearance_is_hold(self):
        for field, value in (("active_claims", True), ("maintenance_busy", True),
                             ("maintenance_busy", None)):
            with self.subTest(field=field, value=value):
                s = snapshot()
                s["native_queue"].update(owner_lease_cas_verified=True,
                                         immutable_task_source_verified=True)
                s["native_queue"][field] = value
                self.assertIn("NATIVE_REFILL_OWNER_HOLD", codes(s))

    def test_missing_stop_is_higher_priority(self):
        s = snapshot()
        s.pop("stop_active")
        self.assertEqual(codes(s), ["STOP_STATE_UNVERIFIED"])


if __name__ == "__main__":
    unittest.main()
