"""K04 source regression: existing NOX WPF projector, no second browser server.
These are source assertions only, NOT Windows/projector physical acceptance.
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
class ProjectorSourceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.host = (ROOT/"integrations/creative/bridge/CreativeHostBridge.cs").read_text("utf-8")
        cls.theater = (ROOT/"integrations/creative/web/theater.js").read_text("utf-8")
        cls.stage = (ROOT/"integrations/creative/stage_creative.py").read_text("utf-8")
    def test_native_monitor_selection_is_in_existing_host(self):
        for key in ("EnumDisplayMonitors","GetMonitorInfoW","SetWindowPos",
                    "MonitorFromWindow","WM_DISPLAYCHANGE","DISPLAY_HOLD",
                    "AttachNoxProjectorControls(theater,viewer)"):
            self.assertIn(key,self.host)
    def test_player_is_still_one_unprivileged_webview(self):
        self.assertIn("FindNoxTheaterViewer(projector)",self.host)
        self.assertIn("IsWebMessageEnabled=false",self.host)
        self.assertIn("CoreWebView2HostResourceAccessKind.DenyCors",self.host)
        self.assertIn("nativeConsent(routeId)",self.host)
        self.assertIn("nox-projects.invalid",self.host)
        self.assertNotIn("HttpListener",self.host)
        self.assertNotIn("window.getScreenDetails",self.theater)
    def test_source_stage_still_includes_existing_bridge(self):
        self.assertIn("bridge.write_bytes(sidecar.read_bytes());record(bridge)",self.stage)
        self.assertIn("CREATIVE_ALREADY_STAGED_OR_CONFLICT",self.stage)
        self.assertIn("if bridge.is_file():bridge.unlink()",self.stage)
    def test_video_format_and_existing_subtitles(self):
        self.assertIn("MEDIA_HOLD:",self.theater)
        self.assertIn("function chooseSubtitle(file)",self.theater)
        self.assertIn("window.addEventListener('beforeunload'",self.theater)
    def test_disconnect_falls_back_and_closes_hook(self):
        self.assertIn("CREATIVE_PROJECTOR_DISPLAY_DISCONNECTED",self.host)
        self.assertIn("source.RemoveHook(hook)",self.host)
if __name__=="__main__":unittest.main()
