"""B2 read-only first-failure receipt tests; NEVER evidence of physical UIA PASS."""
import importlib.util
from pathlib import Path
import sys
import unittest

PATH = Path(__file__).resolve().parents[2] / "coordination" / "e07" / "probe_five_primary_action.py"
sys.path.insert(0, str(PATH.parent))
spec = importlib.util.spec_from_file_location("nox_b2_ui_diagnostics", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FirstFailDiagnostics(unittest.TestCase):
    def test_underlying_navigation_error_survives_fail_closed_gate(self):
        witness = {
            "five_primary_buttons": {"status": "PASS", "buttons_present": list(module.PRIMARY)},
            "ui_chat_action_probe": {"actions_invoked": 1, "navigation_verified": "PASS"},
            "ui_safe_primary_navigation": {"status": "HOLD",
                                           "error": "E07_PRIMARY_NAV_PROCESS_HOLD",
                                           "navigation_verified": "NOT_TESTED"},
        }
        snapshot = module.bounded_primary_diagnostics(witness)
        self.assertEqual(snapshot["four_navigation"]["error_code"],
                         "E07_PRIMARY_NAV_PROCESS_HOLD")
        self.assertEqual(snapshot["four_navigation"]["actions_invoked"], 0)
        self.assertEqual(snapshot["chat"]["actions_invoked"], 1)
        self.assertEqual(snapshot["five_presence"]["present"], list(module.PRIMARY))
        with self.assertRaises(module.Hold):
            module.evaluate(witness)

    def test_secret_or_unbounded_error_never_emitted(self):
        witness = {"ui_safe_primary_navigation": {
            "error": "secret c:/users/private/path.json",
            "per_action": {"INSTALL": {"button_actuated": "OBSERVED",
                                       "navigation_verified": "PASS",
                                       "password": "never-serialize-this"}},
        }}
        snapshot = module.bounded_primary_diagnostics(witness)
        self.assertEqual(snapshot["four_navigation"]["error_code"], "NOT_REPORTED")
        self.assertEqual(snapshot["four_navigation"]["per_action"]["INSTALL"],
                         {"button_actuated": "OBSERVED", "navigation_verified": "PASS"})
        self.assertNotIn("never-serialize-this", str(snapshot))
        self.assertNotIn("private", str(snapshot))

    def test_untrusted_presence_and_bool_count_default_to_hold(self):
        snapshot = module.bounded_primary_diagnostics({
            "five_primary_buttons": {"status": "PASS", "buttons_present": None},
            "ui_chat_action_probe": {"actions_invoked": True,
                                     "navigation_verified": "FORGED_PASS"},
            "ui_safe_primary_navigation": {"actions_invoked": 1000,
                                           "navigation_verified": "PASS?"},
        })
        self.assertEqual(snapshot["five_presence"]["present"], [])
        self.assertEqual(snapshot["chat"]["actions_invoked"], 0)
        self.assertEqual(snapshot["chat"]["navigation_verified"], "NOT_TESTED")
        self.assertEqual(snapshot["four_navigation"]["actions_invoked"], 0)
        self.assertEqual(snapshot["four_navigation"]["navigation_verified"], "NOT_TESTED")

    def test_diagnostic_function_never_approves_release(self):
        snapshot = module.bounded_primary_diagnostics({})
        self.assertNotIn("release_accepted", snapshot)
        self.assertNotIn("five_primary", snapshot)
        self.assertEqual(snapshot["four_navigation"]["navigation_verified"], "NOT_TESTED")


if __name__ == "__main__":
    unittest.main()
