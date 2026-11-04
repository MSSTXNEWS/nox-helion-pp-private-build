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

    def test_visual_failure_does_not_suppress_real_function_observations(self):
        source=PATH.read_text(encoding="utf-8")
        body=source.split("def run(",1)[1]
        self.assertIn("visual_first_hold=None",body)
        self.assertIn("visual_first_hold=str(exc)",body)
        self.assertIn("actual_layout=_physical_adaptive_sized(sizes)",body)
        self.assertIn("screenshot_sha=e07.sha256(png) if actual_png else None",body)
        self.assertIn('"physical_capture":"PASS" if actual_png and visual_first_hold is None else "HOLD"',body)
        self.assertIn('"adaptive_layout":"PASS" if actual_layout else "HOLD"',body)
        self.assertIn('"reduced_motion":"HOLD"',body)
        self.assertIn("Restore original WPF HWND even when a UIA resize or button lookup fails.",source)
        self.assertIn(" } finally {",source)
        self.assertLess(body.index("visual_first_hold=None"),body.index("    actions={}"))
        self.assertNotIn('e07.require(e07.clean_file(png) and 20_000<=png.stat()',body)

    def test_one_failed_real_action_does_not_mask_other_action_results(self):
        import ast
        import textwrap
        source=PATH.read_text(encoding="utf-8")
        main=next(n for n in ast.parse(source).body
                  if isinstance(n,ast.FunctionDef) and n.name=="run")
        attempt=next(n for n in main.body
                     if isinstance(n,ast.FunctionDef) and n.name=="attempt")
        snippet=textwrap.indent(textwrap.dedent("".join(
            source.splitlines(keepends=True)[attempt.lineno-1:attempt.end_lineno])), "    ")
        namespace={"e07":module.e07,"subprocess":module.subprocess}
        exec("def owner():\n    actions={}\n"+
             snippet+"\n    return attempt,actions\n",namespace)
        attempt_fn,results=namespace["owner"]()
        def failed():
            raise module.e07.Hold("E07_FINAL_INSTALL_RESULT_HOLD")
        attempt_fn("INSTALL",failed)
        attempt_fn("MODELS",lambda:results.update({"MODELS":{
            "result":"HOLD","function_verified":"NOT_TESTED",
            "permissions_verified":"NOT_TESTED"}}))
        self.assertEqual(set(results),{"INSTALL","MODELS"})
        self.assertEqual(results["INSTALL"]["error_code"],
                         "E07_FINAL_INSTALL_RESULT_HOLD")
        self.assertEqual(results["INSTALL"]["result"],"HOLD")
        self.assertEqual(results["INSTALL"]["permissions_verified"],"NOT_TESTED")

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
