"""Source acceptance for ONE NOX V9 Home, not a Windows deployment claim."""
from pathlib import Path
import re
import unittest

HERE=Path(__file__).resolve().parent

class HomeV9(unittest.TestCase):
    def test_single_home_and_one_internal_analytics_route(self):
        s=(HERE/"forge_live_server_v6.py").read_text(encoding="utf-8")
        self.assertIn("('/', '/index.html', '/nox/chat')",s)
        self.assertIn("self.get(unified_page",s)
        self.assertIn("/forge/control",s)
        self.assertIn("'page_schema':'NOX-PRIME-HOME-V9'",s)
        self.assertIn("'chat_ui_sha256':chat_ui_sha256",s)

    def test_actual_d02_home_features_and_safe_controls(self):
        s=(HERE/"nox_unified_chat_v1.html").read_text(encoding="utf-8")
        self.assertIn('class="noxSun"',s)
        self.assertEqual(s.count('class="noxPlanet" data-core='),8)
        self.assertIn('id="noxTheme"',s)
        self.assertIn('id="noxGraphics"',s)
        self.assertIn('id="noxMotion"',s)
        self.assertIn('id="noxGpu"',s)
        self.assertIn('id="noxCpu"',s)
        self.assertIn('id="noxRam"',s)
        self.assertIn('"/api/status"',s)
        self.assertIn('"/api/nox/chat/stream"',s)
        self.assertIn('"/api/nox/history"',s)
        self.assertIn('"/api/nox/forge/status"',s)
        self.assertIn('id="stop"',s)
        self.assertIn('id="message"',s)
        self.assertIn('id="log"',s)
        self.assertNotIn('id="forgeImprove"',s)
        ids=re.findall(r'\bid="([a-zA-Z][a-zA-Z0-9_-]*)"',s)
        self.assertEqual(len(ids),len(set(ids)))
        referenced=re.findall(r'\$\("([a-zA-Z][a-zA-Z0-9_-]*)"\)',s)
        self.assertFalse(set(referenced)-set(ids))

    def test_boot_excludes_prior_hash_and_opens_new_root(self):
        s=(HERE/"NOX_PRIME_LIVE_V6_BOOT.ps1").read_text(encoding="utf-8")
        self.assertIn("$health.chat_ui_sha256 -eq $expectedUI",s)
        self.assertIn("$health.page_schema -eq \"NOX-PRIME-HOME-V9\"",s)
        self.assertIn("Start-Process ($selected+\"?nox=v9",s)
        self.assertNotIn('Start-Process ($selected+"nox/chat")',s)

if __name__=="__main__": unittest.main()
