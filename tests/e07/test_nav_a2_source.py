"""Source checks for one immutable NAV A2 Windows E07 candidate (not a release)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "coordination" / "e07"))
import independent_setup_e07 as e07
import probe_final_same_setup as final


class NavA2Source(unittest.TestCase):
    def test_exact_physical_e06_candidate(self):
        self.assertEqual(e07.NAV_A2_SOURCE_SHA,
                         "ee7908e8fa88cd7efc7f4404bbd270e44d1d4caa")
        self.assertEqual(e07.NAV_A2_SETUP_SHA,
                         "9583682515ba665ae36ce608cebb2f46c63542dce4f8c112ca1d0213afa24269")
        self.assertEqual(e07.NAV_A2_SETUP_SIZE, 169665532)
        self.assertEqual(e07.NAV_A2_BUILD_ID, "NOX-V16-2dc194d7dcae0be37c2bb54f")
        self.assertEqual(e07.NAV_A2_OWNED_COUNT, 1011)
        self.assertNotEqual(e07.NAV_A2_SETUP_SHA, e07.F842_D02_SETUP_SHA)

    def test_physical_script_requires_unique_real_five_button_dock(self):
        script = final._uia_script(12345, "VISUAL", png=Path("proof.png"))
        for fragment in ("function PrimaryDock", "ControlType]::Button",
                         "PRIMARY_DOCK_NOT_UNIQUE", "$clusters.Count -ne 1",
                         "function GridMatches", "foreach($columns in @(5,3,2))",
                         "$clusters.Count -ne 1", "function FiveRects",
                         "BUTTON_'+$name+'_NOT_UNIQUE"):
            self.assertIn(fragment, script)
        reason = "E07_FINAL_UIA_VISUAL_PRIMARY_DOCK_NOT_UNIQUE_HOLD"
        self.assertEqual(final._bounded_uia_failure(reason, "VISUAL"), reason)
        self.assertEqual(final._bounded_uia_failure(reason, "INSTALL"),
                         "E07_FINAL_UIA_INSTALL_PROCESS_EXIT_HOLD")

    def test_workflow_pins_real_artifact_not_older_candidate(self):
        flow = (ROOT / ".github" / "workflows" /
                "nox-express-independent-e07-nav-a2.yml").read_text(encoding="utf-8")
        for fragment in ("run-id: 41904124025",
                         "nox-v16-e06-onehost-diagnostic-41904124025",
                         "--artifact-kind d02-nav-a2",
                         "INDEPENDENT_E07_NOT_ACCEPTED",
                         "E07_INDEPENDENT_PHYSICAL_HOLD_NOT_RELEASE"):
            self.assertIn(fragment, flow)
        self.assertNotIn("41895699906", flow)


if __name__ == "__main__":
    unittest.main()
