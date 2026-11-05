"""B06 G4: WebView2 physical reduced-motion is not gated by unrelated OS toggle.

SOURCE_ONLY: no synthetic E07 PASS or user accessibility change is performed.
"""
from pathlib import Path
import importlib.util
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
PATH=ROOT/"coordination/e07/probe_final_same_setup.py"
sys.path.insert(0,str(PATH.parent))
spec=importlib.util.spec_from_file_location("nox_b06_webview2_motion",PATH)
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

GOOD={
    "status":"PASS",
    "scope":"INSTALLED_WEBVIEW2_MEDIA_CSS_WAAPI_NOT_OS_SETTING_ALONE",
    "media_reduced":True,
    "visible_nodes":20,
    "d02_visible_nodes":10,
    "d02_scope_count":1,
    "css_animated":0,
    "css_transitions":0,
    "waapi_running":0,
}


class B06WebView2MotionGate(unittest.TestCase):
    def test_direct_cdp_pass_is_independent_of_os_animations_pref(self):
        self.assertTrue(probe._physical_webview2_motion_verified(dict(GOOD)))
        text=PATH.read_text(encoding="utf-8")
        visual=text.split("os_animation=probe_windows_animation_setting()",1)[1]
        visual=visual.split("    else:\n        # This receipt",1)[0]
        self.assertIn("webview_motion=probe_webview_motion()",visual)
        self.assertIn("motion_verified=_physical_webview2_motion_verified(webview_motion)",visual)
        self.assertNotIn('if os_animation.get("os_ui_animations_enabled") is False:',visual)
        self.assertIn('if motion_verified:',visual)
        self.assertIn("INSTALLED_WEBVIEW2_MEDIA_CSS_WAAPI_PHYSICAL",visual)

    def test_no_fake_motion_pass_on_os_pref_only_or_bad_cdp(self):
        self.assertFalse(probe._physical_webview2_motion_verified(None))
        for key,bad in (
            ("status","HOLD"),("scope","OS_SETTING_ONLY"),
            ("media_reduced",False),("visible_nodes",0),
            ("d02_visible_nodes",4),("d02_scope_count",2),
            ("css_animated",1),("css_transitions",1),("waapi_running",1),
            ("visible_nodes",True),("d02_scope_count",True)
        ):
            with self.subTest(key=key,bad=bad):
                witness=dict(GOOD);witness[key]=bad
                self.assertFalse(probe._physical_webview2_motion_verified(witness))


if __name__=="__main__":
    unittest.main()
