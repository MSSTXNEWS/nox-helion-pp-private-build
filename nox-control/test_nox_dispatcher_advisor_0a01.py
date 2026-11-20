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


if __name__ == "__main__":
    unittest.main()
