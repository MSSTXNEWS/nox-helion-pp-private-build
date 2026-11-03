"""R72: actual canonical installed WPF probe must not pass before browser survives NAV_OK."""
from __future__ import annotations
import ast
import math
from pathlib import Path
import unittest

SOURCE=Path(__file__).resolve().parents[2]/"coordination/e06/t06_samevm_installed_smoke.py"

def source_helper():
    text=SOURCE.read_text(encoding="utf-8")
    tree=ast.parse(text,filename=str(SOURCE))
    helper=next((n for n in tree.body if isinstance(n,ast.FunctionDef)
                 and n.name=="wpf_gui_stability_step"),None)
    if helper is None:raise AssertionError("REAL_WPF_STABILITY_HELPER_MISSING")
    context={"math":math,"WPF_GUI_STABLE_READY_SECONDS":8.0}
    exec(compile(ast.Module(body=[helper],type_ignores=[]),str(SOURCE),"exec"),context)
    return context["wpf_gui_stability_step"],text

class LiveWpfStableGuiTests(unittest.TestCase):
    def setUp(self):self.step,self.source=source_helper()
    def test_old_immediate_nav_acceptance_is_not_retained(self):
        probe=self.source.split("def live_original_wpf_probe(",1)[1].split("\ndef main(",1)[0]
        self.assertIn("wpf_gui_stability_step(",probe)
        self.assertIn("alive_at_proof and stable_window_pass and",probe)
    def test_nav_ok_first_frame_does_not_pass(self):
        start,ok=self.step(None,0.0,ready=True)
        self.assertFalse(ok)
        _,ok=self.step(start,0.7,ready=True)
        self.assertFalse(ok)
    def test_real_browser_failure_after_five_seconds_is_hold(self):
        start,_=self.step(None,0.0,ready=True)
        start,ok=self.step(start,5.0,ready=True)
        self.assertFalse(ok)
        start,ok=self.step(start,5.05,ready=False)
        self.assertIsNone(start);self.assertFalse(ok)
    def test_uninterrupted_live_pid_hwnd_eight_seconds(self):
        start,_=self.step(None,0.0,ready=True)
        _,ok=self.step(start,7.99,ready=True)
        self.assertFalse(ok)
        _,ok=self.step(start,8.01,ready=True)
        self.assertTrue(ok)
    def test_missing_hwnd_resets_window(self):
        start,_=self.step(None,10.0,ready=True)
        start,_=self.step(start,17.0,ready=False)
        self.assertIsNone(start)
        _,ok=self.step(start,18.0,ready=True)
        self.assertFalse(ok)
    def test_monotonic_regression_holds(self):
        start,ok=self.step(12.0,11.0,ready=True)
        self.assertIsNone(start);self.assertFalse(ok)
    def test_nonfinite_times_hold(self):
        for now in (float("nan"),float("inf"),float("-inf")):
            with self.subTest(now=now):
                start,ok=self.step(None,now,ready=True)
                self.assertIsNone(start);self.assertFalse(ok)

if __name__=="__main__":unittest.main()
