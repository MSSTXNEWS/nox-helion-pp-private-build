"""Source-only regression for real 91a6 physical screenshot boundary."""
from pathlib import Path
import importlib.util
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
PATH=ROOT/"coordination/e07/probe_91a6_real_visual_u17.py"
sys.path.insert(0,str(PATH.parent))
spec=importlib.util.spec_from_file_location("nox_91a6_visual_u17",PATH)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class SourceVisualProof(unittest.TestCase):
    def test_screenshot_evidence_not_full_visual_approval(self):
        e07=module.e07
        good={"schema":module.SCHEMA,"source_sha":e07.NEW_D02_SOURCE_SHA,
          "setup_sha256":e07.NEW_D02_SETUP_SHA,"release_accepted":False,
          "visual_e07":"HOLD","adaptive_layout":"NOT_TESTED",
          "reduced_motion":"NOT_TESTED",
          "photo":{"physical_capture":"PASS","sha256":"a"*64},
          "fx":{"fx_control":"PASS"},"original_wpf_ipc":"PASS",
          "update":"PASS","rollback":"PASS","uninstall":"PASS"}
        self.assertTrue(module.is_real_visual_witness(good))
        for field,value in (("release_accepted",True),("visual_e07","PASS"),
                            ("adaptive_layout","PASS"),("reduced_motion","PASS"),
                            ("setup_sha256","b"*64),("source_sha","b"*40),
                            ("photo",None),("fx",None),("original_wpf_ipc","HOLD"),
                            ("update","HOLD"),("rollback","HOLD"),("uninstall","HOLD")):
            bad={**good,field:value}
            self.assertFalse(module.is_real_visual_witness(bad),field)
        original=PATH.read_text(encoding="utf-8")
        for token in ('candidate="d02-91a6"','capture_window(hwnd, a.png)',
                      'probe_d02_quality_modes(hwnd)','e07.lifecycle(',
                      'e07.sha256(a.png) == screenshots[0].get("sha256")'):
            self.assertIn(token,original)
        self.assertNotIn('result["visual_e07"] = "PASS"',original)
        self.assertIn('photo_errors[0] if photo_errors else', original)
        self.assertIn('fx_errors[0] if fx_errors else', original)
        self.assertIn('result["physical_capture"] = "PASS"', original)
        self.assertIn('result["witness_status"] = "PASS"', original)
        self.assertIn('return 0 if result["witness_status"] == "PASS" else 2', original)
    def test_five_actual_d02_graphic_planets_not_legacy_fx(self):
        # Original active D02 dock has five named graphical mode buttons.
        names=module.QUALITY_NAMES
        self.assertEqual(names,("MAX WOW — ПОЛНЫЙ","ECO — ЭКОНОМ",
                                "MINI START — МИНИ","AUTO — АДАПТИВНО",
                                "CINEMA — КИНО"))
        valid={"schema":"NOX-D02-QUALITY-UIA-v1",
               "actions":[{"name":name,"invoked":True,"pressed":True,
                           "same_hwnd":True} for name in names]}
        self.assertEqual(module.validate_quality_witness(valid)["fx_control"],"PASS")
        for index in range(len(names)):
            for key,value in (("invoked",False),("pressed",False),
                              ("same_hwnd",False),("name","FX BALANCED")):
                altered={"schema":valid["schema"],"actions":[dict(a) for a in valid["actions"]]}
                altered["actions"][index][key]=value
                with self.assertRaises(module.e07.Hold):
                    module.validate_quality_witness(altered)
        with self.assertRaises(module.e07.Hold):
            module.validate_quality_witness({"schema":"NOX-D02-QUALITY-UIA-v1","actions":[]})

if __name__=="__main__":
    unittest.main()
