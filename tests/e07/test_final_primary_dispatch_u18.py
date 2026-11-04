"""Regression: E07 must invoke the requested ORIGINAL Windows button.

This is a source-only guard. It does not count as physical E07 acceptance.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

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

    def test_windows_uia_tree_returns_original_collection_not_flattened_array(self):
        # A PowerShell function implicitly enumerates an IEnumerable on return.
        # Returning Tree's AutomationElementCollection without unary comma
        # makes the original .Item(i) UIA lookup fail on installed Windows.
        for operation in ("VISUAL", "INSTALL", "MODELS", "LEARN", "SETTINGS"):
            with self.subTest(operation=operation):
                script = probe._uia_script(12345, operation)
                self.assertIn("return ,$a }", script)
                self.assertNotIn("return $a }", script)
                self.assertIn("$el=$a.Item($i)", script)
                self.assertIn("if($a.Count -gt 4096){throw 'TREE_LIMIT'}", script)

    def test_runtime_entry_point_does_not_use_click_placeholder(self):
        import inspect
        source = inspect.getsource(probe.invoke_primary)
        self.assertIn("_uia_script(hwnd,action)", source)
        self.assertNotIn('_uia_script(hwnd,"CLICK")', source)

    def test_original_d02_uses_five_quality_planets_without_fake_reduced_motion_pass(self):
        from pathlib import Path
        source = (ROOT/"coordination"/"e07"/"probe_final_same_setup.py").read_text(encoding="utf-8")
        witness = source.split("def run(", 1)[1]
        self.assertIn("probe_d02_quality_modes(hwnd)", witness)
        self.assertIn('fx.get("actual_invocations")==5', witness)
        self.assertIn('"reduced_motion":"HOLD"', witness)
        self.assertIn("OS_MEDIA_QUERY_NOT_PHYSICALLY_VERIFIED", witness)
        self.assertNotIn('_uia_script(hwnd,"FX")', witness)

    def test_bounded_phase_diagnostics_do_not_leak_windows_output(self):
        for phase in ("VISUAL", "INSTALL", "MODELS", "LEARN", "SETTINGS"):
            with self.subTest(phase=phase):
                failed = SimpleNamespace(returncode=1, stdout="", stderr="PRIVATE PATH OR TOKEN")
                with patch.object(probe.subprocess, "run", return_value=failed):
                    with self.assertRaisesRegex(probe.e07.Hold,
                        "E07_FINAL_UIA_" + phase + "_PROCESS_EXIT_HOLD") as raised:
                        probe._run_ps("test", phase=phase)
                    self.assertNotIn("PRIVATE", str(raised.exception))

    def test_uia_phase_is_strictly_allowlisted(self):
        with self.assertRaisesRegex(probe.e07.Hold, "E07_FINAL_UIA_PHASE_HOLD"):
            probe._run_ps("test", phase="INJECTED_NAME")

    def test_non_action_does_not_invoke_privileged_button(self):
        script = probe._uia_script(12345, "FX")
        self.assertIn("$op='FX'", script)
        self.assertNotIn("if($op -eq 'CLICK')", script)


if __name__ == "__main__":
    unittest.main()
