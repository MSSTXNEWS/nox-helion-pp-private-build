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

    def test_current_release_requires_real_webview_evidence(self):
        source=(ROOT/"coordination/e07/probe_final_same_setup.py").read_text(encoding="utf-8")
        self.assertIn('webview_motion.get("status")=="PASS"',source)
        self.assertIn('"reduced_motion":"HOLD"',source)


if __name__=="__main__":
    unittest.main()
