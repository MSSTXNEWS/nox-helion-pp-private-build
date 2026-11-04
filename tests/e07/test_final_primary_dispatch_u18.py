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

    def test_independent_same_hwnd_gdi_diagnostic_never_grants_visual_release(self):
        code = (ROOT / "coordination" / "e07" / "probe_final_same_setup.py").read_text(encoding="utf-8")
        self.assertIn("from probe_v6_visual_physical_u01 import capture_window", code)
        self.assertIn("photo=capture_window(hwnd,png)", code)
        self.assertIn("SAME_WPF_PHYSICAL_CAPTURE_NOT_VISUAL_ACCEPTANCE", code)
        self.assertIn('diagnostic_photo={"scope":"SAME_WPF_PHYSICAL_CAPTURE_HOLD"}', code)
        self.assertIn('"physical_capture":"PASS" if actual_png and visual_first_hold is None else "HOLD"', code)
        self.assertIn('"reduced_motion":"HOLD"', code)
        self.assertIn('"diagnostic_photo":diagnostic_photo', code)

    def test_original_d02_uses_five_quality_planets_without_fake_reduced_motion_pass(self):
        from pathlib import Path
        source = (ROOT/"coordination"/"e07"/"probe_final_same_setup.py").read_text(encoding="utf-8")
        witness = source.split("def run(", 1)[1]
        self.assertIn("probe_d02_quality_modes(hwnd)", witness)
        self.assertIn('fx.get("actual_invocations")==5', witness)
        self.assertIn('"reduced_motion":"HOLD"', witness)
        # Drive C34 lesson: tests track the CURRENT producer contract, not
        # an obsolete literal after adding a read-only OS animation probe.
        # The actual WebView2 media query is still unverified: never PASS.
        self.assertIn("OS_SETTING_OBSERVED_WEBVIEW2_MEDIA_QUERY_NOT_PHYSICALLY_VERIFIED", witness)
        self.assertIn("probe_windows_animation_setting()", witness)
        self.assertIn('"os_animation_observation":os_animation', witness)
        self.assertNotIn('"reduced_motion":"PASS"', witness)
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

    def test_specific_real_uia_first_failure_is_bounded_no_raw_output(self):
        for phase in ("VISUAL", "INSTALL", "MODELS", "LEARN", "SETTINGS"):
            expected = "E07_FINAL_UIA_" + phase + "_BUTTON_CHAT_NOT_UNIQUE_HOLD"
            self.assertEqual(
                probe._bounded_uia_failure(expected + "\\r\\n", phase),
                "E07_FINAL_UIA_" + phase + "_PROCESS_EXIT_HOLD")
            self.assertEqual(probe._bounded_uia_failure(expected + "\r\n", phase), expected)
            self.assertEqual(
                probe._bounded_uia_failure(
                    "E07_FINAL_UIA_" + phase + "_NO_ROOT_HOLD", phase),
                "E07_FINAL_UIA_" + phase + "_NO_ROOT_HOLD")
            for private in (
                    "C:\\Users\\runner\\private.txt",
                    "E07_FINAL_UIA_" + phase + "_UNKNOWN_UNAUTHORIZED_HOLD",
                    expected + "\nTOKEN_DO_NOT_LOG",
                    "A" * 300,
                    "E07_FINAL_UIA_ANOTHER_PHASE_NO_ROOT_HOLD"):
                with self.subTest(phase=phase, private=private[:18]):
                    self.assertEqual(
                        probe._bounded_uia_failure(private, phase),
                        "E07_FINAL_UIA_" + phase + "_PROCESS_EXIT_HOLD")

    def test_produced_ps_has_failclosed_trap_before_real_uia(self):
        for phase in ("VISUAL", "INSTALL", "MODELS", "LEARN", "SETTINGS"):
            script = probe._uia_script(12345, phase)
            self.assertIn("$__e07Operation='" + phase + "'", script)
            self.assertIn("trap {", script)
            self.assertIn("Write-Output $reason", script)
            self.assertIn("exit 2", script)
            self.assertIn("Add-Type -AssemblyName UIAutomationClient", script)

    def test_uia_phase_is_strictly_allowlisted(self):
        with self.assertRaisesRegex(probe.e07.Hold, "E07_FINAL_UIA_PHASE_HOLD"):
            probe._run_ps("test", phase="INJECTED_NAME")

    def test_visual_resize_targets_remain_two_distinct_typed_dimensions(self):
        # PowerShell nested literal arrays may flatten; typed objects retain dimensions.
        script = probe._uia_script(12345, "VISUAL", png=Path("test.png"))
        self.assertIn("[pscustomobject]@{width=1044;height=788}", script)
        self.assertIn("[pscustomobject]@{width=800;height=600}", script)
        self.assertIn("$width=[int]$size.width", script)
        self.assertIn("$height=[int]$size.height", script)
        self.assertIn("requested=@($width,$height)", script)
        self.assertNotIn("foreach($size in @(@(1044,788),@(800,600)))", script)

    def test_visual_resizes_on_screen_but_restores_exact_original_wpf_placement(self):
        # Native WPF can start partly outside GitHub's virtual desktop; do
        # not measure 1044x788 and 800x600 at an inherited offscreen origin.
        # This changes ONLY probe coordinates, never app layouts/permissions.
        script = probe._uia_script(12345, "VISUAL", png=Path("test.png"))
        self.assertIn("MoveWindow($handle,0,0,$width,$height,$true)",script)
        self.assertNotIn("MoveWindow($handle,$ox,$oy,$width,$height,$true)",script)
        self.assertIn("MoveWindow($handle,$ox,$oy,$ow,$oh,$true)",script)
        self.assertIn("finally {",script)
        self.assertIn("NoOverlap $rects",script)
        self.assertIn("if($null -eq $rects){throw 'PRIMARY_DOCK_NOT_UNIQUE'}",script)

    def test_primary_buttons_use_same_strict_visible_geometry_as_original(self):
        script=probe._uia_script(12345,"VISUAL",png=Path("test.png"))
        self.assertIn("$b.Width -ge 20 -and $b.Height -ge 12",script)
        self.assertNotIn("$b.Width -ge 14 -and $b.Height -ge 10",script)
        self.assertIn("BUTTON_'+$name+'_NOT_UNIQUE",script)

    def test_final_capture_uses_valid_rect_and_checks_the_window(self):
        script = probe._uia_script(12345, "VISUAL", png=Path("test.png"))
        self.assertNotIn("New-Object NoxFinalWin32+RECT", script)
        self.assertEqual(script.count("[NoxFinalWin32+RECT]::new()"), 3)
        self.assertIn("if(-not [NoxFinalWin32]::GetWindowRect($handle,[ref]$rr)){throw 'RECT'}", script)
        self.assertIn("[System.Drawing.Bitmap]::new([int]$w,[int]$h)", script)

    def test_non_action_does_not_invoke_privileged_button(self):
        script = probe._uia_script(12345, "FX")
        self.assertIn("$op='FX'", script)
        self.assertNotIn("if($op -eq 'CLICK')", script)


if __name__ == "__main__":
    unittest.main()
