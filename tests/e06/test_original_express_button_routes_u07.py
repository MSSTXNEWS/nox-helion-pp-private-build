"""Regression: bind EXPRESS primary actions to real immutable R11 HOME buttons.
Source-only test, never proof of installed UIA, IPC or E07 acceptance.
"""
import hashlib
import importlib.util
import io
from pathlib import Path
import re
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
source = ROOT / 'coordination/express/stage_original_five_primary.py'
spec = importlib.util.spec_from_file_location('nox_u07_primary', source)
assert spec and spec.loader
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)
EXPECTED = {
    'CHAT': '.nav button[data-screen="chat"]',
    'INSTALL': 'button#install-app',
    'MODELS': 'button#model-center',
    'LEARN': '.nav button[data-screen="control"]',
    'SETTINGS': 'button.tile[data-menu-index="7"]',
}

class OriginalButtonRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        joined = b''.join((ROOT / 'donors/P01_C07' / f'P01_C07_{i:02d}.part').read_bytes()
                          for i in range(28))
        with zipfile.ZipFile(io.BytesIO(joined)) as donor:
            if donor.testzip() is not None: raise AssertionError('C07_ZIP_CRC_HOLD')
            cls.home = donor.read('R11/Assets/index.html')
        assert hashlib.sha256(cls.home).hexdigest() == stage.ORIGINAL_SHA256
        assert len(cls.home) == stage.ORIGINAL_BYTES

    def test_original_has_only_skip_anchor_and_real_existing_buttons(self):
        html = self.home.decode('utf-8-sig')
        self.assertEqual(len(re.findall(r'<a\s+[^>]*href=', html, re.I)), 1)
        self.assertEqual(len(re.findall(r'<button(?:\s|>)', html, re.I)), 42)
        nav = re.search(r'<nav class="nav"[^>]*>(.*?)</nav>', html, re.S)
        self.assertIsNotNone(nav)
        for name, selector in EXPECTED.items():
            if 'data-menu-index' in selector:
                # Actual R11 creates eight source-locked tiles dynamically.
                # Index seven is the existing system/settings direction, not
                # a fabricated missing #settings button or a report action.
                self.assertIn("b.dataset.menuIndex=String(i)", html)
                self.assertIn("'СИСТЕМА'", html)
                self.assertIn("'Настройки, файлы и безопасность'", html)
                continue
            if 'data-screen' in selector:
                attr = selector.split('data-screen=', 1)[1].strip('[]')
                count = len(re.findall(r'<button\b[^>]*data-screen=' + re.escape(attr), nav.group(1)))
            else:
                identifier = selector.split('#', 1)[1]
                count = len(re.findall(r'<button\b[^>]*id="' + re.escape(identifier) + '"', html))
            self.assertEqual(count, 1, name)

    def test_original_buttons_are_delegated_without_direct_ipc_or_false_ack(self):
        js = stage.INSERT
        self.assertIn('function findOriginalControl(name){', js)
        self.assertIn('const original=findOriginalControl(name)||findOriginalScreen(name);', js)
        self.assertIn('!event.isTrusted', js)
        self.assertIn('matches.length!==1', js)
        self.assertIn('!button.disabled', js)
        self.assertIn('original.click();', js)
        self.assertNotIn("window.chrome.webview.postMessage({action:", js)
        for name, selector in EXPECTED.items():
            self.assertIn(name + ":'" + selector + "'", js)
        self.assertNotIn('data-nox-primary="REPORTS"', js)
        self.assertIn('data-nox-primary="SETTINGS"', js)
        derived, proof = stage.publish(self.home)
        self.assertEqual(derived.count(b'data-nox-primary='), 5)
        self.assertEqual(proof['installed_ui_automation'], 'NOT_RUN')
        self.assertFalse(proof['release_accepted'])

if __name__ == '__main__': unittest.main()
