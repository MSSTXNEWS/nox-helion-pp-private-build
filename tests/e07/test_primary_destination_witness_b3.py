"""Regression for strict original UIA route component diagnostics; no GUI/mock release."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "coordination" / "e07"))
from independent_setup_e07 import Hold, classify_readonly_primary_navigation_witness as classify
ACTIONS = ("INSTALL","MODELS","LEARN","SETTINGS")
def item(action, *, before=False, after=True, heading=True, focus=1):
    return {"action": action, "invoked": True, "sameHwndAlive": True,
            "beforeDestination": before, "afterDestination": after,
            "beforeHeadingVisible": False, "afterHeadingVisible": heading,
            "beforeFocusedControls": 0, "afterFocusedControls": focus}
def witness(**kwargs):
    return {"schema": "NOX-E07-PRIMARY-NAV-v3",
            "actions": [item(name, **kwargs) for name in ACTIONS]}
class RouteComponentWitness(unittest.TestCase):
    def test_all_visible_focus_strict_only_navigation(self):
        result=classify(witness())
        self.assertEqual(result["navigation_verified"],"PASS")
        self.assertEqual(result["actions_invoked"],4)
        self.assertFalse(result["release_accepted"])
        self.assertEqual(result["per_action"]["MODELS"]["destination_components"]["after_focused_controls"],1)
        self.assertEqual(result["per_action"]["INSTALL"]["function_verified"],"NOT_TESTED")
    def test_heading_absent_means_no_route_pass(self):
        r=classify(witness(after=False,heading=False))
        self.assertEqual(r["navigation_verified"],"HOLD")
        self.assertFalse(r["per_action"]["LEARN"]["destination_components"]["after_heading_visible"])
    def test_keyboard_focus_absent_means_no_route_pass(self):
        r=classify(witness(after=False,focus=0))
        self.assertEqual(r["navigation_verified"],"HOLD")
        self.assertEqual(r["per_action"]["SETTINGS"]["destination_components"]["after_focused_controls"],0)
    def test_forged_positive_heading_without_focus_rejected(self):
        with self.assertRaises(Hold): classify(witness(after=True,focus=0))
    def test_forged_positive_focus_without_heading_rejected(self):
        with self.assertRaises(Hold): classify(witness(after=True,heading=False))
    def test_bool_not_accepted_as_focus_count(self):
        w=witness();w["actions"][0]["afterFocusedControls"]=True
        with self.assertRaises(Hold):classify(w)
    def test_unexpected_raw_fields_rejected(self):
        w=witness();w["actions"][0]["local_username"]="nope"
        with self.assertRaises(Hold):classify(w)
    def test_previous_v2_remains_strict(self):
        w={"schema":"NOX-E07-PRIMARY-NAV-v2","actions":[
          {k:v for k,v in item(n).items() if k in {
             "action","invoked","sameHwndAlive","beforeDestination","afterDestination"}}
          for n in ACTIONS]}
        self.assertEqual(classify(w)["navigation_verified"],"PASS")
        self.assertNotIn("destination_components",classify(w)["per_action"]["CHAT"] if "CHAT" in classify(w)["per_action"] else classify(w)["per_action"]["INSTALL"])
    def test_not_yet_e07_because_nav(self):
        w=witness(after=False,focus=0)
        self.assertFalse(classify(w)["release_accepted"])
if __name__=="__main__":unittest.main()
