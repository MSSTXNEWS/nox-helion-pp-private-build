import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('drive_prepare', Path(__file__).with_name('owner_drive_ram_prepare.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PrepareTests(unittest.TestCase):
    def test_real_crypto_and_private_key_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / 'state'
            with patch.object(m, 'STATE', state), patch.dict(os.environ, {
                    'NOX_OWNER_REQUEST_ID': '12345', 'NOX_OWNER_SOURCE_SHA': 'a' * 40}), \
                    patch.object(m, 'candidate_pythons', return_value=[sys.executable]):
                result = m.prepare()
                replay = m.prepare()
            self.assertEqual(result, replay)
            self.assertEqual(result['state'], 'PUBLIC_KEY_READY')
            self.assertTrue(result['capability']['aes_256_gcm_roundtrip'])
            self.assertTrue(result['capability']['rsa_oaep_sha256_roundtrip'])
            self.assertEqual(result['rsa_bits'], 4096)
            self.assertIn('BEGIN PUBLIC KEY', result['public_key_pem'])
            self.assertNotIn('PRIVATE KEY', json.dumps(result))
            self.assertFalse(result['private_key_exported'])
            key = state / 'keys/12345/private_key.pem'
            self.assertEqual(stat.S_IMODE(key.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(key.parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(key.parent.parent.stat().st_mode), 0o700)

    def test_missing_native_crypto_reports_capability_without_installation(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(m, 'STATE', Path(folder) / 'state'), patch.dict(os.environ, {
                    'NOX_OWNER_REQUEST_ID': '12345', 'NOX_OWNER_SOURCE_SHA': 'a' * 40}), \
                    patch.object(m, 'candidate_pythons', return_value=[sys.executable]), \
                    patch.object(m, 'crypto_command', return_value={'available': False, 'error_class': 'ModuleNotFoundError'}):
                result = m.prepare()
            self.assertEqual(result['state'], 'HOLD_CRYPTO_UNAVAILABLE')
            self.assertFalse(result['packages_installed'])
            self.assertFalse(list(Path(folder).rglob('private_key.pem')))

    def test_fifo_private_input_cannot_hang(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fifo'
            os.mkfifo(path, 0o600)
            start = time.monotonic()
            with self.assertRaisesRegex(RuntimeError, 'PRIVATE_FILE'):
                m.read_private(path)
            self.assertLess(time.monotonic() - start, 0.1)

    def test_public_manifest_contains_only_hashes_for_drive_ids(self):
        manifest = json.loads(Path(__file__).with_name('owner_drive_ram_assets.json').read_text())
        self.assertEqual(m.hashlib.sha256(m.canonical(manifest)).hexdigest(), m.MANIFEST_SHA256)
        self.assertEqual(sum(asset['bytes'] for asset in manifest['assets']), 920362008)
        for asset in manifest['assets']:
            self.assertEqual(sum(part['bytes'] for part in asset['parts']), asset['bytes'])
            for part in asset['parts']:
                self.assertEqual(set(part), {'ordinal', 'bytes', 'drive_id_sha256'})
                self.assertRegex(part['drive_id_sha256'], '^[a-f0-9]{64}$')


if __name__ == '__main__':
    unittest.main()
