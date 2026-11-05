"""NOX V16 source-first audit: one D02/WOW owner, exact PACK01 catalog, motion modes.
These are source-level tests, NOT Windows installed/200-visual E07 acceptance.
"""
import json
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
WOW=ROOT/"integrations"/"wow200"/"runtime"/"loader.mjs"
PACK=ROOT/"proposals"/"NOX-PACK01-50"/"catalog.json"
BRIDGE=ROOT/"proposals"/"NOX-PACK01-50"/"native_bridge.py"

class OneHostWowSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code=WOW.read_text(encoding="utf-8")
        cls.rows=json.loads(PACK.read_text(encoding="utf-8"))

    def test_complete_canonical_50_source_routes(self):
        self.assertEqual(self.rows["version"],"NOX-INTEGRATION-PACK-01")
        routes=self.rows["actions"]
        self.assertEqual(len(routes),50)
        self.assertEqual(len({r["routeId"] for r in routes}),50)
        for i,r in enumerate(routes,1):
            self.assertEqual(r["taskId"],f"NIP01-{i:02d}")
            self.assertRegex(r["routeId"],r"^[a-z][a-z0-9]*(?:[._][a-z0-9]+)*$")
            self.assertIn(r["category"],{"chat","models","learning","voice","space"})
            self.assertIs(type(r["owner"]),int)
            self.assertTrue(1<=r["owner"]<=6)

    def test_runtime_validates_registry_before_ui_buttons(self):
        code=self.code
        self.assertIn("catalog?.version!=='NOX-INTEGRATION-PACK-01'",code)
        self.assertIn("new Set(catalog.actions.map(x=>x?.routeId)).size!==50",code)
        self.assertIn("x.taskId!=='NIP01-'+String(i+1).padStart(2,'0')",code)
        self.assertLess(code.index("catalog?.version!"),code.index("for(const action of catalog.actions)"))

    def test_reduced_motion_dominates_requested_max(self):
        self.assertIn("motion?.matches===true?'REDUCED'",self.code)
        self.assertIn("scene=mountUnifiedCinema(root,{mode:effective(),reducedMotion:motion?.matches===true})",self.code)
        self.assertIn("mod.onchange=applyMode",self.code)
        self.assertIn("motion.addEventListener('change',applyMode)",self.code)

    def test_motion_modes_reach_both_existing_visual_owners(self):
        self.assertIn("scene?.setMode(current)",self.code)
        self.assertIn("pack?.setMode(current.toLowerCase())",self.code)
        self.assertIn("pack.setMode(effective().toLowerCase())",self.code)
        self.assertEqual(self.code.count("mountUnifiedCinema(root,"),1)
        self.assertEqual(self.code.count("pack=mountCinematic(routes,catalog)"),1)

    def test_page_does_not_execute_privileged_native_action(self):
        self.assertIn("sourceOnly:true",self.code)
        self.assertIn("releaseAccepted:false",self.code)
        self.assertIn("window.parent.postMessage({type:'nox.creative.navigate.v1'",self.code)
        self.assertNotIn("action:'packInvoke'",self.code)

    def test_native_owner_requires_strict_integer_not_bool(self):
        code=BRIDGE.read_text(encoding="utf-8")
        self.assertIn('type(port.owner) is not int or port.owner != self.routes[route]["owner"]',code)
        self.assertNotIn('if port.owner != self.routes[route]["owner"]',code)
        self.assertIn('return port.call(session,frozen_payload)',code)

    def test_full_source_archive_was_not_replaced_by_mock(self):
        for part in ("source_00.part","source_01.part","source_02.part"):
            self.assertTrue((ROOT/part).is_file(),part)

if __name__=="__main__":
    unittest.main()
