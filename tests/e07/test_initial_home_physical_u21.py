"""Fail-closed evidence boundary: acquire actual first WPF frame BEFORE navigation.

Source-level tests only. Physical screenshot/VIEW/E07 still require Windows CI.
"""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
OWNER=ROOT/"coordination"/"e07"/"independent_setup_e07.py"
FLOW=ROOT/".github"/"workflows"/"nox-express-independent-e07-nav-a2.yml"

class InitialHomePhysicalPhoto(unittest.TestCase):
    def test_capture_precedes_chat_and_four_primary_navigation(self):
        source=OWNER.read_text(encoding="utf-8")
        start=source.index("def gui_hwnd(")
        block=source[start:source.index("\ndef original_wpf_hwnd(",start)] if "\ndef original_wpf_hwnd(" in source[start:] else source[start:source.index("\ndef native_store(",start)] if "\ndef native_store(" in source[start:] else source[start:source.index("\ndef lifecycle(",start)]
        self.assertLess(block.index("initial_home = initial_home_probe(handle)"),
                        block.index("observe_chat_input(handle)"))
        self.assertLess(block.index("initial_home = initial_home_probe(handle)"),
                        block.index("observe_readonly_primary_navigation(handle)"))
        self.assertIn('"initial_home_visual":initial_home',block)

    def test_one_source_bound_initial_photo_never_grants_visual_pass(self):
        source=OWNER.read_text(encoding="utf-8")
        self.assertIn('screenshot=final_probe_dir/"D02_HOME_PRENAV.png"',source)
        self.assertIn("photo=capture_window(hwnd,screenshot)",source)
        self.assertIn('"home_scene_verified":"NOT_TESTED"',source)
        self.assertIn('"visual_e07":"HOLD"',source)
        self.assertIn('"reduced_motion":"NOT_TESTED"',source)
        self.assertIn("initial_home_probe=physical_initial_home_probe if final_probe_dir is not None else None",source)

    def test_live_home_evidence_parent_is_created_before_installed_lifecycle(self):
        source=OWNER.read_text(encoding="utf-8")
        entry=source.index('physical_dir = evidence_parent / "same-setup-final"')
        guard=source.index('evidence_parent.mkdir(parents=True, exist_ok=True)')
        reparse=source.index('"E07_FINAL_EVIDENCE_PARENT_REPARSE_HOLD"')
        lifecycle=source.index('lifecycle(setup,result,frozen_source=source_sha,',entry)
        self.assertLess(reparse,guard)
        self.assertLess(guard,entry)
        self.assertLess(entry,lifecycle)
        self.assertIn('require(clean_dir(evidence_parent)',source)
        # Keep the missing/preexisting-photo diagnostic fail closed.
        self.assertIn('require(len(pre_nav_visual)==1,"E07_PRENAV_VISUAL_NOT_OBSERVED_HOLD")',source)
        self.assertIn('precomputed_visual=pre_nav_visual[0]',source)

    def test_windows_artifact_retains_original_home_photo(self):
        flow=FLOW.read_text(encoding="utf-8")
        self.assertIn("D02_HOME_PRENAV.png",flow)
        self.assertIn("test_initial_home_physical_u21.py",flow)
        self.assertIn("--artifact-kind d02-nav-a2",flow)
        self.assertIn("E07_INDEPENDENT_PHYSICAL_HOLD_NOT_RELEASE",flow)

if __name__=="__main__":
    unittest.main()
