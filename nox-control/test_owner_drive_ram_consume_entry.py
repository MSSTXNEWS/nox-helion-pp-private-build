import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).parent
source = (HERE / 'owner_drive_ram_consume_entry.py').read_text().replace('__NOX_BUNDLE_JSON__', '{}')
m = types.ModuleType('drive_consume_entry')
exec(compile(source, '<entry>', 'exec'), m.__dict__)


class EntryTests(unittest.TestCase):
    def test_all_dependency_pins_match_frozen_sources(self):
        for name, expected in m.PINS.items():
            self.assertEqual(hashlib.sha256((HERE / name).read_bytes()).hexdigest(), expected)

    def test_unknown_existing_helper_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            scripts = Path(folder)
            name = 'owner_drive_ram_bridge.py'
            path = scripts / name
            path.write_bytes(b'preserve unknown original')
            with patch.object(m, 'SCRIPTS', scripts):
                with self.assertRaisesRegex(RuntimeError, 'UNKNOWN_EXISTING_SOURCE'):
                    m.install(name, (HERE / name).read_bytes())
            self.assertEqual(path.read_bytes(), b'preserve unknown original')

    def test_exact_install_idempotent_and_no_hardlink_left(self):
        with tempfile.TemporaryDirectory() as folder:
            scripts = Path(folder)
            name = 'owner_drive_ram_bridge.py'
            data = (HERE / name).read_bytes()
            with patch.object(m, 'SCRIPTS', scripts):
                m.install(name, data)
                m.install(name, data)
            self.assertEqual((scripts / name).read_bytes(), data)
            self.assertEqual((scripts / name).stat().st_nlink, 1)

    def test_envelope_is_required_and_pinned_before_any_write(self):
        with patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '123', 'NOX_OWNER_SOURCE_SHA': 'a' * 40}), \
                patch.object(m, 'install') as install:
            with self.assertRaisesRegex(RuntimeError, 'ENVELOPE_NOT_PINNED'):
                m.main()
            install.assert_not_called()
        with patch.object(m, 'BUNDLE', {'envelope': base64.b64encode(b'substituted').decode()}):
            with self.assertRaisesRegex(RuntimeError, 'BUNDLE_PIN'):
                m.unpack('envelope', '0' * 64)


if __name__ == '__main__':
    unittest.main()
