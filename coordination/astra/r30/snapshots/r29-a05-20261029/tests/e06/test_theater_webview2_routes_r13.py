"""E06 source contract for the existing WPF WebView2 projector route (not Windows acceptance)."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
HTML=(ROOT/'integrations/creative/web/theater.html').read_text(encoding='utf-8')
SCRIPT=(ROOT/'integrations/creative/web/theater.js').read_text(encoding='utf-8')
HOST=(ROOT/'integrations/creative/bridge/CreativeHostBridge.cs').read_text(encoding='utf-8')

class TheaterRouteContract(unittest.TestCase):
    def test_existing_host_not_replaced(self):
        self.assertIn('Navigate("https://nox.local/creative/theater.html")',HOST)
        self.assertIn('SetVirtualHostNameToFolderMapping("nox.local"',HOST)
    def test_relative_assets_resolve_under_virtual_webview2_origin(self):
        self.assertIn('<script src="theater.js"></script>',HTML)
        self.assertIn("url('../menu_sections.png')",HTML)
        self.assertNotIn('/assets/NOX_HELION_MENU_8_SECTIONS_COLLAGE_APPROVED',HTML)
    def test_no_phantom_api_media_route(self):
        self.assertNotIn('/api/media/',SCRIPT)
        self.assertIn('URL.createObjectURL(file)',SCRIPT)
    def test_subtitle_controls_have_real_handlers(self):
        self.assertIn('id="subtitles"',HTML)
        self.assertIn('text/vtt',SCRIPT)
        self.assertIn("function toWebVtt",SCRIPT)
        self.assertIn("$('subtitles').onchange",SCRIPT)
    def test_projector_keyboard_and_feedback(self):
        self.assertIn("event.key==='F11'",SCRIPT)
        self.assertIn("event.key==='Escape'",SCRIPT)
        self.assertIn('document.exitFullscreen()',SCRIPT)
        self.assertIn('role="status"',HTML)
    def test_old_d02_core_not_edited(self):
        self.assertIn('menu_sections.png',HTML)
        self.assertNotIn('document.write(',SCRIPT)

if __name__=='__main__':
    unittest.main()
