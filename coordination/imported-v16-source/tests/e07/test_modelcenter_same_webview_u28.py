"""E07 real ModelCenter witness must match ORIGINAL OneHost implementation.
Source-only guard: no navigation-to-functional or permission PASS.
"""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/"coordination/e07/probe_final_same_setup.py"
OWNER=ROOT/"coordination/e06/MainWindow.NativeP02.cs"
sys.path.insert(0,str(SRC.parent))
spec=importlib.util.spec_from_file_location("e07_original_model_page",SRC)
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

class OriginalSameWebViewModelCenter(unittest.TestCase):
    def test_native_owner_uses_same_trusted_webview_page(self):
        native=OWNER.read_text(encoding="utf-8")
        self.assertIn('web.Navigate("https://nox.local/creative/modelcenter/index.html")',native)
        self.assertIn('action=="openModelCenter"',native)
        self.assertIn('route != "chat.stop" && !await ConfirmP02NativeAsync(',native)
    def test_real_original_hwnd_page_witness_is_not_an_external_wpf_window(self):
        script=probe._uia_script(12345,"MODEL_WINDOW")
        self.assertIn("if($op -eq 'MODEL_WINDOW')",script)
        self.assertIn("NOX · MODEL CORE",script)
        self.assertIn("$v.ControlType -eq [System.Windows.Automation.ControlType]::Document",script)
        self.assertIn("$name -ceq 'Модели'",script)
        self.assertIn("modelPageVisible=$seen",script)
        self.assertIn("sameOriginalHwndAlive=",script)
        self.assertNotIn("NOX HELION · MODEL CENTER",script)
        self.assertNotIn("$desktop.FindAll",script)
        self.assertNotIn("$wp.Close()",script)
    def test_model_page_is_only_navigation_not_model_download_or_permissions(self):
        source=SRC.read_text(encoding="utf-8")
        block=source.split("    def models_check():",1)[1].split("    def learn_check():",1)[0]
        self.assertIn("E07_FINAL_MODELS_ORIGINAL_WEBVIEW_PAGE_HOLD",block)
        self.assertIn('nonrelease_action_observation(action,detail)',source)
        self.assertIn('"model_pull":"NOT_TESTED"',block)
        self.assertIn('"model_download_queue":"NOT_TESTED"',block)
        self.assertNotIn('"permissions_verified":"PASS"',block)

if __name__=="__main__":
    unittest.main()
