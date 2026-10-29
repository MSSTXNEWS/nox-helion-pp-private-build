"""NOX P04: real-module tests for model-lock rights identity shape.

No NVIDIA card, network, model weights or training data are required.
This test uses the production source's existing model tree hashing.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[2] / 'Packages' / 'P04' / 'train_qlora.py'
spec = importlib.util.spec_from_file_location('nox_p04_train_qlora_lock_test', SOURCE)
if spec is None or spec.loader is None:
    raise RuntimeError('P04_PRODUCTION_MODULE_UNAVAILABLE')
p04 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p04)


class P04ModelLockIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model = self.root / 'model'
        self.model.mkdir()
        (self.model / 'weights.bin').write_bytes(b'fixture-only; not a model or training')
        self.revision = 'a' * 40
        self.lock_path = self.root / 'model-lock.json'
        self.valid = {
            'schema': 'nox-model-lock-v1',
            'license_status': 'APPROVED',
            'owner_approval_id': 'signed-owner-permission-1',
            'model_id': 'approved-model-1',
            'revision': self.revision,
            'snapshot_sha256': p04.sha256_tree(self.model),
        }

    def verify(self, **updates):
        self.lock_path.write_text(json.dumps({**self.valid, **updates}), encoding='utf-8')
        return p04.verify_model_lock(self.lock_path, self.model, self.revision)

    def test_authorized_lock_retains_existing_behavior(self):
        self.assertEqual(self.verify()['model_id'], 'approved-model-1')

    def test_nonblank_owner_permission_identity_required(self):
        for invalid in (True, 123, 3.14, '', '   ', '\t\n', [], {}, None):
            with self.subTest(value=repr(invalid)):
                with self.assertRaisesRegex(ValueError, 'MODEL_LICENSE_OR_OWNER_APPROVAL_MISSING'):
                    self.verify(owner_approval_id=invalid)

    def test_nonblank_model_identity_required(self):
        for invalid in ('', '   ', '\n\t', True, 777, 1.5, [], {}, None):
            with self.subTest(value=repr(invalid)):
                with self.assertRaisesRegex(ValueError, 'MODEL_ID_MISSING'):
                    self.verify(model_id=invalid)

    def test_invalid_rights_identity_fails_before_tree_scan(self):
        for updates, error in (({'owner_approval_id': True}, 'MODEL_LICENSE_OR_OWNER_APPROVAL_MISSING'),
                               ({'model_id': '  '}, 'MODEL_ID_MISSING')):
            with self.subTest(updates=updates):
                self.lock_path.write_text(json.dumps({**self.valid, **updates}), encoding='utf-8')
                with patch.object(p04, 'sha256_tree', side_effect=AssertionError('tree scan should not run')):
                    with self.assertRaisesRegex(ValueError, error):
                        p04.verify_model_lock(self.lock_path, self.model, self.revision)

    def test_reject_unapproved_license_and_mismatched_model_digest(self):
        with self.assertRaisesRegex(ValueError, 'MODEL_LICENSE_OR_OWNER_APPROVAL_MISSING'):
            self.verify(license_status='DENIED')
        with self.assertRaisesRegex(ValueError, 'MODEL_SNAPSHOT_SHA256_MISMATCH'):
            self.verify(snapshot_sha256='0' * 64)


if __name__ == '__main__':
    unittest.main()
