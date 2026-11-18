"""Pure-source V6 embedded installer verification (no native server calls)."""
from __future__ import annotations
import base64
import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from owner_chat_terminal_guard_v6 import prepare as pure_prepare, EXPECTED_INPUT_SHA256


class IncrementalInstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        location = ROOT / 'package_ui_only_v2/owner_chat_ui_only_embedded_entry.py'
        spec = importlib.util.spec_from_file_location('_nox_v6_source_only', location)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_exact_source_bytes_match_independently_pinned_transform(self):
        old = (ROOT / 'nox-v24-chat-nonempty-current.js').read_bytes()
        self.assertEqual(hashlib.sha256(old).hexdigest(), EXPECTED_INPUT_SHA256)
        want = pure_prepare(old)
        bundled = base64.b64decode(self.module.BUNDLE['public_chat.js'], validate=True)
        self.assertEqual(bundled, want)
        self.assertEqual(len(bundled), 33756)
        self.assertEqual(hashlib.sha256(bundled).hexdigest(),
                         '55e4445443cd0d4cfa4d2a8775dcd8c7689890daad492b58e01c298691ac7e20')

    def test_exact_incremental_preimage_and_safe_install_scope(self):
        m = self.module
        self.assertEqual(m.UI_BEFORE_SHA, EXPECTED_INPUT_SHA256)
        self.assertEqual(m.SPEC['before_ui_sha256'], EXPECTED_INPUT_SHA256)
        self.assertEqual(m.SPEC['after_ui_sha256'], m.UI_AFTER_SHA)
        self.assertEqual(m.SPEC['asset_bytes'], {'before': 33602, 'after': 33756})
        self.assertFalse(m.SPEC['foreground_idle_required'])
        self.assertFalse(m.SPEC['policy_write_or_reload'])
        self.assertEqual(m.SPEC['assets']['public_chat.js'], m.UI_AFTER_SHA)
        self.assertEqual(set(m.SPEC['assets']), {'public_chat.js', 'official_auth.py', 'native_helpers.py'})


if __name__ == '__main__':
    unittest.main()
