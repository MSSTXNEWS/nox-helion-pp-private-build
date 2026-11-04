"""Read-only WebView2 physical Reduced Motion receipt cannot be forged."""
from pathlib import Path
import importlib.util
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
TARGET=ROOT/"coordination/e07/probe_webview_motion.py"
sys.path.insert(0,str(TARGET.parent))
spec=importlib.util.spec_from_file_location("nox_webview_cdp_motion",TARGET)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PhysicalWebviewMotion(unittest.TestCase):
    def good(self):
        return {"schema":module.SCHEMA,"media_reduced":True,
                "home_active":True,"primary_controls":5,
                "visible_nodes":60,"css_animated":0,
                "css_transitions":0,"waapi_running":0}

    def test_only_live_schema_bounded_positive_is_accepted(self):
        item=module.validate(self.good())
        self.assertEqual(item["status"],"PASS")
        self.assertTrue(item["media_reduced"])

    def test_media_off_and_live_animation_always_hold(self):
        for key,val in (("media_reduced",False),("home_active",False),
                        ("primary_controls",4),("visible_nodes",0),
                        ("css_animated",1),("css_transitions",1),
                        ("waapi_running",1)):
            with self.subTest(key=key):
                raw=self.good();raw[key]=val
                with self.assertRaises(module.e07.Hold):
                    module.validate(raw)

    def test_source_prohibits_emulation_and_external_endpoints(self):
        source=TARGET.read_text(encoding="utf-8")
        self.assertNotIn("Emulation.setEmulatedMedia",source)
        self.assertNotIn("Runtime.callFunctionOn",source)
        self.assertIn("http://127.0.0.1:9222/json/list",source)
        self.assertIn("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",source)
        self.assertIn("https://nox.local/",source)
        self.assertNotIn("file:///",source)
        self.assertIn("'PAGE_NOT_UNIQUE'",source)

    def test_selects_exactly_one_real_active_home_not_first_tab(self):
        inactive=self.good();inactive["home_active"]=False
        self.assertEqual(
            module.select_unique_home_observation([inactive,self.good()])["status"],
            "PASS")
        self.assertEqual(
            module.select_unique_home_observation([self.good(),inactive])["status"],
            "PASS")

    def test_duplicate_live_home_and_no_home_fail_closed(self):
        inactive=self.good();inactive["home_active"]=False
        for candidates in ([],[inactive],[self.good(),self.good()],
                           [self.good()]*5,[None],[inactive]*2):
            with self.subTest(candidates=len(candidates)):
                with self.assertRaises(module.e07.Hold):
                    module.select_unique_home_observation(candidates)

    def test_one_live_home_must_still_pass_original_real_media_contract(self):
        for key,value in (("media_reduced",False),
                          ("primary_controls",4),
                          ("css_animated",1),("css_transitions",1),
                          ("waapi_running",1)):
            raw=self.good();raw[key]=value
            inactive=self.good();inactive["home_active"]=False
            with self.subTest(key=key):
                with self.assertRaises(module.e07.Hold):
                    module.select_unique_home_observation([inactive,raw])

    def test_cdp_target_discovery_is_strict_readonly_and_bounded(self):
        source=TARGET.read_text(encoding="utf-8")
        self.assertIn("https://nox.local/index.html",source)
        self.assertIn("https://nox.local/",source)
        self.assertIn("foreach($page in $pages)",source)
        self.assertIn("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",source)
        self.assertIn("NON_LOOPBACK_CDP",source)
        self.assertIn("PAGE_NOT_UNIQUE",source)
        self.assertIn("Runtime.evaluate",source)
        self.assertIn("getComputedStyle",source)
        self.assertIn("matchMedia('(prefers-reduced-motion: reduce)')",source)
        self.assertNotIn("Emulation.setEmulatedMedia",source)
        self.assertNotIn("--force-prefers-reduced-motion",source)

    def test_current_release_requires_real_webview_evidence(self):
        source=(ROOT/"coordination/e07/probe_final_same_setup.py").read_text(encoding="utf-8")
        self.assertIn('webview_motion.get("status")=="PASS"',source)
        self.assertIn('"reduced_motion":"HOLD"',source)


if __name__=="__main__":
    unittest.main()
