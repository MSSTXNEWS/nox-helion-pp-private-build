"""Fail-closed exact UIA click navigation receipt tests (no physical Windows PASS)."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[2] / "coordination" / "e07" / "probe_five_primary_action.py"
spec = importlib.util.spec_from_file_location("probe_primary", PATH)
import sys
sys.path.insert(0, str(PATH.parent))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def witness():
    return {"five_primary_buttons": {"status": "PASS", "buttons_present": list(module.PRIMARY)},
            "ui_chat_action_probe": {"action": "CHAT", "actions_invoked": 1,
                 "method": "NATIVE_UIA_INVOKEPATTERN", "navigation_verified": "PASS",
                 "navigation_proof": "NEW_VISIBLE_UIA_CHAT_HEADING"},
            "ui_safe_primary_navigation": {"actions_invoked": 4, "navigation_verified": "PASS",
                "per_action": {name: {"button_actuated": "OBSERVED", "navigation_verified": "PASS",
                                      "function_verified": "NOT_TESTED"} for name in module.PRIMARY[1:]}}}


class FiveButtonGate(unittest.TestCase):
    def test_full_five_click_navigation_not_release(self):
        result = module.evaluate(witness())
        self.assertEqual(result["actions_invoked"], 5)
        self.assertFalse(result["release_accepted"])
        self.assertFalse(result["live_inference_verified"])

    def test_button_presence_not_click(self):
        r = witness(); r["ui_chat_action_probe"]["actions_invoked"] = 0
        with self.assertRaises(module.Hold): module.evaluate(r)

    def test_no_preexisting_heading_false_pass(self):
        r = witness(); r["ui_chat_action_probe"]["navigation_proof"] = "NONE"
        with self.assertRaises(module.Hold): module.evaluate(r)

    def test_missing_one_of_four(self):
        r = witness(); r["ui_safe_primary_navigation"]["per_action"]["SETTINGS"]["navigation_verified"] = "NOT_TESTED"
        with self.assertRaises(module.Hold): module.evaluate(r)

    def test_legacy_reports_not_settings(self):
        r = witness(); r["five_primary_buttons"]["buttons_present"][-1] = "REPORTS"
        with self.assertRaises(module.Hold): module.evaluate(r)

    def test_wrong_action_set(self):
        r = witness(); r["ui_safe_primary_navigation"]["per_action"]["REPORTS"] = r["ui_safe_primary_navigation"]["per_action"].pop("SETTINGS")
        with self.assertRaises(module.Hold): module.evaluate(r)

    def test_untrusted_function_verification(self):
        r = witness(); r["ui_safe_primary_navigation"]["per_action"]["INSTALL"]["function_verified"] = "PASS"
        with self.assertRaises(module.Hold): module.evaluate(r)

    def test_no_source_guess(self):
        with self.assertRaises(module.Hold):
            module.checked_source_setup(Path('/not/real'), 'bad', 'nope')

if __name__ == "__main__": unittest.main()
