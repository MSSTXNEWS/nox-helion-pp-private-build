"""NOX V16 WOW source-first regressions for the ORIGINAL single secondary scene.

Only source-level checks; installed EXE, native events and GPU E07 remain HOLD.
Run: python -m unittest discover -s tests/e06 -p test_wow_motion_route_contract_r04.py -v
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
W = ROOT / "integrations" / "wow200"
LOADER = W / "runtime" / "loader.mjs"
CATALOG = ROOT / "proposals" / "NOX-PACK01-50" / "catalog.json"


class WowMotionRouteContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = LOADER.read_text(encoding="utf-8")
        cls.catalog = json.loads(CATALOG.read_text(encoding="utf-8"))

    def test_reduced_motion_dominates_user_max_profile(self):
        self.assertIn("const effectiveMode=()=>mr?.matches?'REDUCED':mod.value;", self.js)
        self.assertIn("mode:effectiveMode(),reducedMotion:!!mr?.matches", self.js)

    def test_scene_and_first50_share_the_same_profile_switch(self):
        self.assertIn("const actual=effectiveMode();", self.js)
        self.assertIn("scene?.setMode(actual)", self.js)
        self.assertIn("pack?.setMode(actual.toLowerCase())", self.js)
        self.assertIn("mod.onchange=applyMode", self.js)

    def test_os_change_recomputes_existing_profile(self):
        self.assertIn("mr?.addEventListener?.('change',applyMode)", self.js)
        self.assertNotIn("mod.onchange=()=>scene?.setMode(mod.value)", self.js)

    def test_first50_receives_os_motion_profile_on_first_mount(self):
        self.assertIn("pack.setMode((window.matchMedia?.(", self.js)
        self.assertIn("'REDUCED':mod.value).toLowerCase());", self.js)

    def test_catalog_is_checked_before_rendering_any_cards(self):
        self.assertLess(self.js.index("catalog?.version!"), self.js.index("for(const action of catalog.actions)"))
        self.assertIn("new Set(catalog.actions.map(x=>x?.routeId)).size!==50", self.js)
        self.assertIn("x.taskId!=='NIP01-'+String(i+1).padStart(2,'0')", self.js)
        self.assertIn("!Number.isInteger(x.owner)||x.owner<1||x.owner>6", self.js)

    def test_pack01_exact_real_source_catalog(self):
        self.assertEqual(self.catalog["version"], "NOX-INTEGRATION-PACK-01")
        rows = self.catalog["actions"]
        self.assertEqual(len(rows), 50)
        self.assertEqual([r["taskId"] for r in rows],
                         [f"NIP01-{n:02d}" for n in range(1, 51)])
        self.assertEqual(len(set(r["routeId"] for r in rows)), 50)
        self.assertTrue(all(type(r["owner"]) is int and 1 <= r["owner"] <= 6 for r in rows))

    def test_no_page_owned_privileged_execution_or_false_e07(self):
        self.assertIn("no", self.js[:400].lower())
        self.assertIn("sourceOnly:true", self.js)
        self.assertIn("releaseAccepted:false", self.js)
        self.assertIn("window.parent.postMessage({type:'nox.creative.navigate.v1'", self.js)
        self.assertNotIn("window.chrome.webview.postMessage({action:'packInvoke'", self.js)
        self.assertNotIn("event.evidence_verified=true", self.js)


if __name__ == "__main__":
    unittest.main()
