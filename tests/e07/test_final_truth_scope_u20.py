"""E07 original physical functional observations cannot stand in for execution."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
PATH=ROOT/"coordination/e07/probe_final_same_setup.py"
sys.path.insert(0,str(PATH.parent))
spec=importlib.util.spec_from_file_location("nox_e07_real_function_scope",PATH)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class FunctionalTruth(unittest.TestCase):
    def test_navigation_preflight_and_window_are_not_native_owner_pass(self):
        observations={"install":"/app/server.py","modelCenter":"opened",
                      "learn":"preflight report","settings":"screen only"}
        for name in ("INSTALL","MODELS","LEARN","SETTINGS"):
            result=module.nonrelease_action_observation(name,observations)
            self.assertEqual(result["function_verified"],"NOT_TESTED")
            self.assertEqual(result["permissions_verified"],"NOT_TESTED")
            self.assertEqual(result["result"],"HOLD")
            self.assertEqual(result["observed_effect"],observations)
            self.assertEqual(len(result["receipt_sha256"]),64)
        for name,detail in (("UNAPPROVED",observations),("LEARN",{}),
                            ("SETTINGS",[])):
            with self.assertRaises(module.e07.Hold):
                module.nonrelease_action_observation(name,detail)

    def test_fx_failure_does_not_skip_other_functional_observations(self):
        source=PATH.read_text(encoding="utf-8")
        self.assertIn('fx={"fx_control":"HOLD","first_unmet_gate":str(exc)}',source)
        self.assertIn('fx["fx_control"]=="PASS" else "HOLD"',source)
        self.assertIn('"reduced_motion":"HOLD"',source)
        self.assertIn("nonrelease_action_observation(action,detail)",source)
        self.assertNotIn('"permissions_verified":"PASS"',source)
        self.assertNotIn('accepted("MODELS"',source)
        self.assertNotIn('accepted("LEARN"',source)

if __name__=="__main__":
    unittest.main()
