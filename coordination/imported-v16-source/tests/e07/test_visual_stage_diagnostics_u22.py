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
    def test_native_uia_process_avoids_oversized_windows_command_line(self):
        source=TARGET.read_text(encoding="utf-8")
        function=source.split("def _run_ps(",1)[1].split("def ",1)[0]
        self.assertIn("tempfile.TemporaryDirectory",function)
        self.assertIn("utf-8-sig",function)
        self.assertIn("-File",function)
        self.assertIn('"-File",str(script_path)',function)

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
        self.assertIn("CopyFromScreen(",script)
        self.assertNotIn("::PrintWindow($handle",script)
        self.assertIn("if($__e07Operation -eq 'VISUAL'){",script)
        self.assertIn("$rects+=,($row[$name].rect)",script)
        self.assertNotIn("$row[$name].Current.BoundingRectangle",script)
        self.assertIn("$r=$dock[$name].rect",script)
        self.assertIn("return $dock[$name].element",script)
        self.assertIn("foreach($columns in @(5,3,2))",script)
        self.assertIn("if(GridMatches $row $columns)",script)
        self.assertIn("$gap -lt -1 -or $gap -gt 45",script)
        self.assertIn("$gap -lt -1 -or $gap -gt 55",script)
        self.assertIn("if($clusters.Count -ne 1)",script)
        self.assertIn("if($null -eq $rects){throw 'PRIMARY_DOCK_NOT_UNIQUE'}",script)

    def test_identical_uia_wrappers_do_not_double_count_original_control(self):
        script=probe._uia_script(12345,"VISUAL",png=Path("screenshot.png"))
        self.assertIn("function SameElementSeen($items,$candidate)",script)
        self.assertIn("[System.Windows.Automation.Automation]::Compare($prior.element,$candidate)",script)
        self.assertIn("Failure to compare never implies identical elements",script)
        self.assertIn("if(-not (SameElementSeen -items ($seen[$name]) -candidate $el))",script)
        self.assertIn("if($seen[$n].Count -lt 1 -or $seen[$n].Count -gt 6)",script)
        self.assertIn("if($clusters.Count -ne 1)",script)

    def test_partially_clipped_primary_never_admitted(self):
        # UIA can mark partly clipped buttons as IsOffscreen=False. The dock
        # must fit within the SAME original physical WPF window.
        script=probe._uia_script(12345,"VISUAL",png=Path("screenshot.png"))
        self.assertIn("function WithinOriginalHwnd($rect,$frame)",script)
        self.assertIn("$originalRoot=Root",script)
        self.assertIn("$frame=$originalRoot.Current.BoundingRectangle",script)
        self.assertIn("$a=Tree $originalRoot",script)
        self.assertIn("if(-not (WithinOriginalHwnd $rect $frame)){continue}",script)
        self.assertIn("$rect.Left -ge ($frame.Left - $pad)",script)
        self.assertIn("$rect.Top -ge ($frame.Top - $pad)",script)
        self.assertIn("$rect.Right -le ($frame.Right + $pad)",script)
        self.assertIn("$rect.Bottom -le ($frame.Bottom + $pad)",script)
        self.assertIn("if($clusters.Count -ne 1){throw 'PRIMARY_DOCK_NOT_UNIQUE'}",script)

    def test_visual_requires_unoccluded_original_hwnd_hit_target(self):
        # IsOffscreen=False alone does not prove the original button is exposed.
        # Exact real UIA FromPoint ancestry is mandatory; no mouse simulation.
        script=probe._uia_script(12345,"VISUAL",png=Path("screenshot.png"))
        self.assertIn("Add-Type -AssemblyName WindowsBase",script)
        self.assertIn("function HitTestOriginalPrimary($button,$bounds)",script)
        self.assertIn("[System.Windows.Automation.AutomationElement]::FromPoint(",script)
        self.assertIn("[System.Windows.Point]::new($cx,$cy)",script)
        self.assertIn("[System.Windows.Automation.TreeWalker]::RawViewWalker",script)
        self.assertIn("[System.Windows.Automation.Automation]::Compare($hit,$button)",script)
        self.assertIn("for($depth=0;$depth -lt 32",script)
        self.assertIn("if([NoxFinalWin32]::GetForegroundWindow() -ne $handle){throw 'PRINT'}",script)
        guard="if($__e07Operation -eq 'VISUAL' -and -not (HitTestOriginalPrimary $el $rect)){continue}"
        self.assertIn(guard,script)
        self.assertLess(script.index("if(-not (WithinOriginalHwnd $rect $frame)){continue}"),script.index(guard))
        self.assertLess(script.index(guard),script.index("if(-not (SameElementSeen -items"))
        self.assertNotIn("SetCursorPos(",script)

    def test_failed_dock_keeps_hold_and_bounded_real_resize_photo(self):
        script=probe._uia_script(12345,"VISUAL",png=Path("screenshot.png"))
        self.assertIn("SaveAdaptiveHold $width",script)
        self.assertIn("D02_ADAPTIVE_",script)
        self.assertIn("for($tryDock=0;$tryDock -lt 30;$tryDock++)",script)
        self.assertIn("if($null -eq $rects){throw 'PRIMARY_DOCK_NOT_UNIQUE'}",script)
        source=TARGET.read_text(encoding="utf-8")
        self.assertIn('"adaptive_failure_diagnostics":resize_diagnostics',source)

    def test_original_home_five_primary_ids_and_dom_identity_are_guarded(self):
        source=(ROOT / "coordination/express/stage_original_five_primary.py").read_text(encoding="utf-8")
        for name in ("CHAT","INSTALL","MODELS","LEARN","SETTINGS"):
            with self.subTest(name=name):
                marker='id="nox-express-primary-'+name.lower()+'" data-nox-primary="'+name+'"'
                self.assertEqual(source.count(marker),1)
        self.assertIn("function verifiedOriginalPrimaryDock(){",source)
        self.assertIn("button!==originalPrimaryButtons[i]",source)
        self.assertIn("document.querySelectorAll(",source)
        self.assertIn("if(!verifiedOriginalPrimaryDock()){",source)
        # All five original mounted UIA buttons must be visible, named
        # and keyboard reachable, not merely connected/labelled in the DOM.
        self.assertIn("button.getAttribute('aria-label')!==name",source)
        self.assertIn("button.getClientRects().length===0",source)
        self.assertIn("button.tabIndex!==0",source)
        self.assertIn("""button.closest('[hidden],[inert],[aria-hidden="true"],[aria-disabled="true"]')""",source)
        self.assertIn("""nav.closest('[hidden],[inert],[aria-hidden="true"],[aria-disabled="true"]')""",source)
        self.assertIn("document.elementFromPoint(",source)
        self.assertIn("rect.right>viewportWidth+.5",source)
        self.assertIn("rect.bottom>viewportHeight+.5",source)
        self.assertIn("if(!hit||(hit!==button&&!button.contains(hit)))return false;",source)
        self.assertIn("window.getComputedStyle(button)",source)
        self.assertIn("dockStyle.pointerEvents==='none'",source)
        self.assertIn("button.hasAttribute('role')",source)
        self.assertNotIn("Array.prototype.includes.call(primaryButtons,target)",source)

    def test_release_gate_stays_strict(self):
        gate = (ROOT / "coordination/e07/independent_setup_e07.py").read_text(
            encoding="utf-8")
        self.assertIn('visual.get("reduced_motion") == "PASS"', gate)
        self.assertIn('item.get("permissions_verified") == "PASS"', gate)


if __name__ == "__main__":
    unittest.main()
