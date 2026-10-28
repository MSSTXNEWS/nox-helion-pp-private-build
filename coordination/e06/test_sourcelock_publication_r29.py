import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

HERE = Path(__file__).resolve().parent

def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

inventory = load('source_deep_inventory')
verifier = load('verify_original_729_source')

class PublicationTests(unittest.TestCase):
    def fixture(self, root):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as archive:
            archive.writestr('source.txt', 'original source')
        payload = buf.getvalue()
        (root / 'fixture.part').write_bytes(payload)
        return patch.multiple(inventory, ROOT=root, PARTS=('fixture.part',),
                              EXPECTED_SIZE=len(payload), EXPECTED_SHA=hashlib.sha256(payload).hexdigest())

    def test_inventory_does_not_clobber_existing_zip_or_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_zip = root / 'e06-source-verified.zip'
            old_receipt = root / 'e06-source-inventory.json'
            old_zip.write_bytes(b'owner archive')
            old_receipt.write_bytes(b'owner receipt')
            with self.fixture(root), self.assertRaises(ValueError):
                inventory.main()
            self.assertEqual(old_zip.read_bytes(), b'owner archive')
            self.assertEqual(old_receipt.read_bytes(), b'owner receipt')

    def test_inventory_success_uses_scratch_zip_and_preserves_fixed_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixed = root / 'e06-source-verified.zip'
            fixed.write_bytes(b'owner archive')
            with self.fixture(root):
                inventory.main()
            self.assertEqual(fixed.read_bytes(), b'owner archive')
            receipt = json.loads((root / 'e06-source-inventory.json').read_text())
            self.assertEqual(receipt['source_member_count'], 1)
            self.assertEqual(receipt['members'][0]['sha256'], hashlib.sha256(b'original source').hexdigest())
            self.assertFalse(receipt['release_accepted'])

    def test_inventory_bad_hash_preserves_fixed_zip_and_publishes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixed = root / 'e06-source-verified.zip'
            fixed.write_bytes(b'owner archive')
            with self.fixture(root), patch.object(inventory, 'EXPECTED_SHA', '0'*64), self.assertRaises(SystemExit):
                inventory.main()
            self.assertEqual(fixed.read_bytes(), b'owner archive')
            self.assertFalse((root / 'e06-source-inventory.json').exists())

    def test_e06_fsync_failure_does_not_publish_partial_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'lock.json'
            argv = ['verify', '--parts-dir', tmp, '--out', str(out), '--run-id', 'R29-TEST-0001']
            with patch.object(sys, 'argv', argv), patch.object(verifier, 'verify_original', return_value={'status':'fixture'}), patch('os.fsync', side_effect=OSError('disk full')):
                self.assertEqual(verifier.main(), 2)
            self.assertFalse(out.exists())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_e06_success_publishes_complete_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'lock.json'
            receipt = {'status': 'fixture', 'releaseAccepted': False}
            argv = ['verify', '--parts-dir', tmp, '--out', str(out), '--run-id', 'R29-TEST-0001']
            with patch.object(sys, 'argv', argv), patch.object(verifier, 'verify_original', return_value=receipt):
                self.assertEqual(verifier.main(), 0)
            self.assertEqual(json.loads(out.read_text()), receipt)
            self.assertEqual(list(Path(tmp).iterdir()), [out])

if __name__ == '__main__':
    unittest.main()
