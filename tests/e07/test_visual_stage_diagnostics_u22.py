"""Regression for bounded, stage-specific E07 D02 UI Automation failures.

Evidence is diagnostic only: a failure classification never promotes a release.
"""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "coordination/e07/probe_final_same_setup.py"
sys.path.insert(0, str(TARGET.parent))
spec = importlib.util.spec_from_file_location("nox_e07_visual_stages", TARGET)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class PhysicalVisualFailureStages(unittest.TestCase):
    def test_stage_codes_survive_bounded_allowlist(self):
        for stage in ("RESIZE", "DOCK", "CAPTURE", "RESTORE"):
            with self.subTest(stage=stage):
                code = "E07_FINAL_UIA_VISUAL_VISUAL_STAGE_" + stage + "_HOLD"
                self.assertEqual(probe._bounded_uia_failure(code, "VISUAL"), code)

    def test_previous_known_codes_are_unchanged(self):
        for code in (
            "E07_FINAL_UIA_VISUAL_PRIMARY_DOCK_NOT_UNIQUE_HOLD",
            "E07_FINAL_UIA_VISUAL_RECT_HOLD",
            "E07_FINAL_UIA_VISUAL_PRINT_HOLD",
            "E07_FINAL_UIA_INSTALL_BUTTON_INSTALL_NOT_UNIQUE_HOLD",
        ):
            self.assertEqual(probe._bounded_uia_failure(
                code, "INSTALL" if "_INSTALL_" in code else "VISUAL"), code)

    def test_unknown_codes_and_sensitive_output_fail_closed(self):
        for unsafe in (
            "C:\\Users\\person\\secret.txt",
            "E07_FINAL_UIA_VISUAL_VISUAL_STAGE_UNKNOWN_HOLD",
            "E07_FINAL_UIA_VISUAL_VISUAL_STAGE_RESIZE_HOLD\\nsecond line",
        ):
            self.assertEqual(probe._bounded_uia_failure(unsafe, "VISUAL"),
                             "E07_FINAL_UIA_VISUAL_PROCESS_EXIT_HOLD")

    def test_visual_script_has_stage_tracking_and_restores_window(self):
        script = probe._uia_script(12345, "VISUAL", png=Path("screenshot.png"))
        for stage in ("RESIZE", "DOCK", "CAPTURE", "RESTORE"):
            self.assertIn("$__e07Stage='" + stage + "'", script)
        self.assertIn("Restore original WPF HWND", script)
        self.assertIn("VISUAL_STAGE_", script)

    def test_dock_respects_original_five_three_two_responsive_grid(self):
        script = probe._uia_script(12345, "VISUAL", png=Path("screenshot.png"))
        self.assertIn("function GridMatches($row,[int]$columns)",script)
        self.assertIn("foreach($columns in @(5,3,2))",script)
        self.assertIn("if(GridMatches $row $columns)",script)
        self.assertIn("$gap -lt -1 -or $gap -gt 45",script)
        self.assertIn("$gap -lt -1 -or $gap -gt 55",script)
        self.assertIn("if($clusters.Count -ne 1)",script)
        self.assertIn("if($null -eq $rects){throw 'PRIMARY_DOCK_NOT_UNIQUE'}",script)

    def test_identical_uia_wrappers_do_not_double_count_original_control(self):
        script=probe._uia_script(12345,"VISUAL",png=Path("screenshot.png"))
        self.assertIn("function SameElementSeen($items,$candidate)",script)
        self.assertIn("[System.Windows.Automation.Automation]::Compare($prior,$candidate)",script)
        self.assertIn("Failure to compare never implies identical elements",script)
        self.assertIn("if(-not (SameElementSeen -items ($seen[$name]) -candidate $el))",script)
        self.assertIn("if($seen[$n].Count -lt 1 -or $seen[$n].Count -gt 6)",script)
        self.assertIn("if($clusters.Count -ne 1)",script)

    def test_failed_dock_keeps_hold_and_bounded_real_resize_photo(self):
        script=probe._uia_script(12345,"VISUAL",png=Path("screenshot.png"))
        self.assertIn("SaveAdaptiveHold $width",script)
        self.assertIn("D02_ADAPTIVE_",script)
        self.assertIn("for($tryDock=0;$tryDock -lt 30;$tryDock++)",script)
        self.assertIn("if($null -eq $rects){throw 'PRIMARY_DOCK_NOT_UNIQUE'}",script)
        source=TARGET.read_text(encoding="utf-8")
        self.assertIn('"adaptive_failure_diagnostics":resize_diagnostics',source)

    def test_release_gate_stays_strict(self):
        gate = (ROOT / "coordination/e07/independent_setup_e07.py").read_text(
            encoding="utf-8")
        self.assertIn('visual.get("reduced_motion") == "PASS"', gate)
        self.assertIn('item.get("permissions_verified") == "PASS"', gate)


if __name__ == "__main__":
    unittest.main()
