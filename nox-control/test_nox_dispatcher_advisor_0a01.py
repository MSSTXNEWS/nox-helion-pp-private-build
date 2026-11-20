"""Focused source regression for 0A01 owner STOP admission; no host access."""
import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).with_name("nox_dispatcher_advisor.py")
SPEC = importlib.util.spec_from_file_location("nox_dispatcher_advisor", MODULE_PATH)
advisor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(advisor)


class StopAdmissionTests(unittest.TestCase):
    def test_missing_stop_fail_closed_before_telemetry(self):
        findings = advisor.assess({"onehost": {"healthy": True}})
        self.assertEqual([x["code"] for x in findings], ["STOP_STATE_UNVERIFIED"])
        self.assertEqual(findings[0]["urgency"], "hold")

    def test_non_boolean_stop_values_fail_closed(self):
        for state in (None, 0, 1, "false", [], {}):
            with self.subTest(state=state):
                findings = advisor.assess({"stop_active": state})
                self.assertEqual([x["code"] for x in findings], ["STOP_STATE_UNVERIFIED"])

    def test_true_stop_remains_safety_stop(self):
        self.assertEqual([x["code"] for x in advisor.assess(
            {"stop_active": True, "trainer": {"ready_for_resume": True}}
        )], ["STOP_ACTIVE"])

    def test_explicit_false_reaches_original_telemetry_contract(self):
        findings = advisor.assess({"stop_active": False})
        self.assertEqual([x["code"] for x in findings], ["TELEMETRY_MISSING"])



class TrainingResumeAttestationTests(unittest.TestCase):
    """0A01: an untrusted ready_for_resume bit cannot authorize training."""

    @staticmethod
    def snapshot():
        return {
            "stop_active": False,
            "onehost": {"healthy": True},
            "s03": {"readback_verified": True},
            "trainer": {
                "running": False, "ready_for_resume": True,
                "checkpoint_recent": True,
            },
            "gpu": {
                "temperature_sensor_valid": True, "temperature_c": 60,
            },
            "disk": {"free_gib": 30, "checkpoint_reserve_gib": 10},
            "native_queue": {
                "maintenance_busy": False, "active_claims": False,
                "resource_headroom_bytes": 3 * 1024**3,
            },
        }

    def test_unattested_json_ready_flag_is_always_hold(self):
        s = self.snapshot()
        findings = advisor.assess(s)
        self.assertIn("TRAIN_RESUME_OWNER_HOLD", [x["code"] for x in findings])
        self.assertNotIn("TRAIN_RESUME_CANDIDATE", [x["code"] for x in findings])

    def test_attested_snapshot_remains_review_only(self):
        s = self.snapshot()
        findings = advisor.assess(s, owner_snapshot_verifier=lambda exact: exact is s)
        target = [x for x in findings if x["code"] == "TRAIN_RESUME_CANDIDATE"]
        self.assertEqual(len(target), 1)
        self.assertEqual(target[0]["urgency"], "review")
        self.assertIn("recheck", target[0]["advice"])

    def test_stale_s03_checkpoint_and_resource_hold(self):
        for path, val in (
            (("s03", "readback_verified"), False),
            (("trainer", "checkpoint_recent"), None),
            (("gpu", "temperature_c"), 70),
            (("gpu", "temperature_sensor_valid"), False),
            (("disk", "free_gib"), float("nan")),
            (("native_queue", "active_claims"), True),
            (("native_queue", "resource_headroom_bytes"), 29000000),
            (("native_queue", "maintenance_busy"), None),
        ):
            with self.subTest(path=path, val=val):
                s = self.snapshot()
                s[path[0]][path[1]] = val
                codes = [x["code"] for x in advisor.assess(
                    s, owner_snapshot_verifier=lambda exact: exact is s)]
                self.assertIn("TRAIN_RESUME_OWNER_HOLD", codes)
                self.assertNotIn("TRAIN_RESUME_CANDIDATE", codes)

    def test_failed_owner_verifier_is_hold(self):
        s = self.snapshot()
        def broken(_):
            raise RuntimeError("owner verification failed")
        for verifier in (None, lambda _: True if False else 1, broken):
            with self.subTest(verifier=verifier):
                codes = [x["code"] for x in advisor.assess(
                    s, owner_snapshot_verifier=verifier)]
                self.assertIn("TRAIN_RESUME_OWNER_HOLD", codes)

if __name__ == "__main__":
    unittest.main()
