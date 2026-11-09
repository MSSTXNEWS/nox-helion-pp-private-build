"""Read-only WebView2 physical Reduced Motion receipt cannot be forged."""
import base64
import json
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
                "visible_nodes":60,"d02_scope_count":1,
                "d02_visible_nodes":24,"css_animated":0,
                "css_transitions":0,"waapi_running":0}

    def test_only_live_schema_bounded_positive_is_accepted(self):
        item=module.validate(self.good())
        self.assertEqual(item["status"],"PASS")
        self.assertTrue(item["media_reduced"])
        self.assertEqual(item["d02_scope_count"],1)
        self.assertEqual(item["d02_visible_nodes"],24)

    def test_media_off_and_live_animation_always_hold(self):
        for key,val in (("media_reduced",False),("home_active",False),
                        ("primary_controls",4),("visible_nodes",0),
                        ("d02_scope_count",0),("d02_scope_count",2),
                        ("d02_visible_nodes",0),("d02_visible_nodes",4097),
                        ("visible_nodes",4097),
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

    def test_webview_computed_css_timing_must_fail_closed(self):
        source=TARGET.read_text(encoding="utf-8")
        self.assertIn("const activeTime=(value)=>{",source)
        self.assertIn("NOX_CDP_TIMING_UNVERIFIED",source)
        self.assertIn("if(!Number.isFinite(secondsOrMs)||secondsOrMs<0)",source)
        self.assertNotIn("Number.parseFloat(x)>0",source)
        self.assertIn("for(const part of parts)",source)

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
        self.assertIn(".nox-cinema-scope",source)
        self.assertIn("d02_scope_count:scopes.length",source)
        self.assertIn("visible_nodes:tooMany?4097:visible",source)
        self.assertIn("matchMedia('(prefers-reduced-motion: reduce)')",source)
        self.assertIn("location.origin!=='https://nox.local'",source)
        self.assertIn("location.pathname",source)
        self.assertIn("NOX_CDP_ORIGIN_DRIFT",source)
        # The previous fixture expected obsolete positive-rectangle logic.
        # Current original D02 rejects hidden/transparent/off-viewport nodes.
        self.assertIn("if(physicallyVisible(el,rect)){",source)
        self.assertIn("const physicallyVisible=(el,rect)=>{",source)
        self.assertIn("const width=Math.min(rect.right,innerWidth)",source)
        self.assertIn("const alpha=Number(style.opacity);",source)
        self.assertNotIn("if(rect.width<5||rect.height<5)continue;",source)
        self.assertIn("for(const pseudo of [null,'::before','::after'])",source)
        self.assertNotIn("Emulation.setEmulatedMedia",source)
        self.assertNotIn("--force-prefers-reduced-motion",source)


    def test_primary_dock_requires_five_unobscured_real_hit_targets(self):
        source=TARGET.read_text(encoding="utf-8")
        # Prevent regression to counting controls by presence, even when
        # hidden, disabled, clipped, or covered by a pointer-catching overlay.
        self.assertIn("buttons.length===5?buttons.filter(hitTargetVisible).length:0",source)
        self.assertIn("if(!button.isConnected||button.disabled||",source)
        self.assertIn("button.getAttribute('aria-disabled')==='true'",source)
        self.assertIn("r.right>innerWidth||r.bottom>innerHeight",source)
        self.assertIn("!physicallyVisible(button,r)",source)
        self.assertIn("getComputedStyle(ancestor).pointerEvents==='none'",source)
        self.assertIn("const hit=document.elementFromPoint(x,y);",source)
        self.assertIn("hit===button||button.contains(hit)",source)
        self.assertNotIn("primary_controls:buttons.length,d02_scope_count",source)
        self.assertNotIn("document.dispatchEvent",source)
        self.assertNotIn("button.click()",source)

    def test_ascii_framed_cdp_observation_still_requires_actual_media(self):
        make_wire = lambda obj: module.CDP_WIRE_PREFIX + base64.b64encode(
            json.dumps([obj], separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        self.assertEqual(module.decode_observation_wire(make_wire(self.good()))["status"], "PASS")
        blocked = self.good()
        blocked["media_reduced"] = False
        with self.assertRaises(module.e07.Hold):
            module.decode_observation_wire(make_wire(blocked))

    def test_ascii_cdp_transport_rejects_corruption_and_stdout_pollution(self):
        valid = module.CDP_WIRE_PREFIX + base64.b64encode(
            json.dumps([self.good()], separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        malformed = (
            "", "[]", valid + "WARNING: untrusted output",
            "WARNING: untrusted output\\n" + valid,
            module.CDP_WIRE_PREFIX + "!!!",
            module.CDP_WIRE_PREFIX + base64.b64encode(b"not json").decode("ascii"),
            module.CDP_WIRE_PREFIX + base64.b64encode(bytes([255])).decode("ascii"),
            module.CDP_WIRE_PREFIX + base64.b64encode(b"[]" * 5000).decode("ascii"),
        )
        for bad in malformed:
            with self.subTest(kind=bad[:30]):
                with self.assertRaises(module.e07.Hold):
                    module.decode_observation_wire(bad)

    def test_one_transport_bom_is_not_mistaken_for_untrusted_cdp_data(self):
        frame=module.CDP_WIRE_PREFIX+base64.b64encode(
            json.dumps([self.good()],separators=(",",":")).encode("utf-8")
        ).decode("ascii")
        self.assertEqual(module.decode_observation_wire(chr(0xfeff)+frame)["status"],"PASS")
        with self.assertRaises(module.e07.Hold):
            module.decode_observation_wire(chr(0xfeff)*2+frame)

    def test_ascii_receipt_keeps_real_readonly_cdp_and_no_media_simulation(self):
        source = TARGET.read_text(encoding="utf-8")
        self.assertIn("[Console]::Out.WriteLine('NOX_E07_CDP_V3:'", source)
        self.assertIn("[Convert]::ToBase64String", source)
        self.assertIn("base64.b64decode(wire[len(CDP_WIRE_PREFIX):], validate=True)", source)
        self.assertIn("json.loads(decoded.decode", source)
        self.assertNotIn("Emulation.setEmulatedMedia", source)
        self.assertNotIn("--force-prefers-reduced-motion", source)

    def test_current_release_requires_real_webview_evidence(self):
        source=(ROOT/"coordination/e07/probe_final_same_setup.py").read_text(encoding="utf-8")
        self.assertIn("def _physical_webview2_motion_verified(observation: object)",source)
        self.assertIn('observation.get("status") == "PASS"',source)
        self.assertIn('observation.get("media_reduced") is True',source)
        self.assertIn('observation.get("scope") == "INSTALLED_WEBVIEW2_MEDIA_CSS_WAAPI_NOT_OS_SETTING_ALONE"',source)
        self.assertIn("motion_verified=_physical_webview2_motion_verified(webview_motion)",source)
        self.assertIn('if motion_verified:',source)
        self.assertIn('visual["reduced_motion"]="PASS"',source)
        self.assertIn('"reduced_motion":"HOLD"',source)


if __name__=="__main__":
    unittest.main()
