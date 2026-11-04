"""Regression: E07 must invoke the requested ORIGINAL Windows button.

This is a source-only guard. It does not count as physical E07 acceptance.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "coordination" / "e07"))
SPEC = importlib.util.spec_from_file_location(
    "probe_final_same_setup",
    ROOT / "coordination" / "e07" / "probe_final_same_setup.py")
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class FinalPrimaryDispatch(unittest.TestCase):
    def test_all_five_are_encoded_as_actual_requested_actions(self):
        for action in probe.PRIMARY:
            with self.subTest(action=action):
                script = probe._uia_script(12345, action)
                self.assertIn("$op='" + action + "'", script)
                self.assertIn("InvokePrimary '" + action + "'", script)
                self.assertNotIn("InvokePrimary ''", script)
                self.assertNotIn("__ACTION__", script)

    def test_runtime_entry_point_does_not_use_click_placeholder(self):
        import inspect
        source = inspect.getsource(probe.invoke_primary)
        self.assertIn("_uia_script(hwnd,action)", source)
        self.assertNotIn('_uia_script(hwnd,"CLICK")', source)

    def test_non_action_does_not_invoke_privileged_button(self):
        script = probe._uia_script(12345, "FX")
        self.assertIn("$op='FX'", script)
        self.assertNotIn("if($op -eq 'CLICK')", script)


if __name__ == "__main__":
    unittest.main()
