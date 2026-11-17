"""Targeted real-TempFS transaction checks; no native services or HTTP."""
import copy
import importlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import native_v24_dialog_installer as base_module
import native_v24_dialog_transform as transform_module
import native_model_binding_installer as installer_module

HERE = Path(__file__).resolve().parent
INPUT = HERE.parent / 'resonance_native_20261118/source_inputs_private'
UI = HERE.parent / 'web29_original_chat_audit_20261117/source_v13/site/nox-ui.js'


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.base = importlib.reload(base_module)
        self.module = importlib.reload(installer_module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'nox'
        self.scripts = self.root / 'scripts'
        self.state = self.root / 'state'
        self.scripts.mkdir(parents=True)
        self.state.mkdir()
        for key, value in [('ROOT', self.root), ('SCRIPTS', self.scripts), ('STATE', self.state)]:
            setattr(self.base, key, value)
        for name in self.module.SOURCE_ORDER:
            path = self.scripts / name
            path.write_bytes((INPUT / name).read_bytes())
            path.chmod(0o600 if name == 'owner_chat_stream.py' else 0o644)
        self.module.configure()
        self.base.source_test_marker = True
        transform_module.UI_PATH = UI
        self.guard_calls = 0

    def quiescent(self):
        self.guard_calls += 1

    def transaction(self, request):
        transaction = self.module.BindingTransaction(request)
        transaction.prepare()
        return transaction

    def assert_originals(self, transaction):
        for name in self.module.SOURCE_ORDER:
            self.assertEqual((self.scripts / name).read_bytes(), transaction.original[name])
            info = (self.scripts / name).stat()
            self.assertEqual(info.st_mode, transaction.metadata[name]['mode'])
            self.assertEqual(info.st_uid, transaction.metadata[name]['uid'])
            self.assertEqual(info.st_gid, transaction.metadata[name]['gid'])

    def test_actual_five_file_apply_and_exact_source_restore(self):
        transaction = self.transaction('123001')
        transaction.replace(self.quiescent)
        for name, pins in transform_module.TRANSFORMS.items():
            raw = (self.scripts / name).read_bytes()
            self.assertEqual(self.base.digest(raw), pins['after_sha256'])
            self.assertEqual(len(raw), pins['after_bytes'])
        for name in self.module.NEW_ORDER:
            target = self.module.target(name)
            self.assertEqual(target.read_bytes(), self.module.ARTIFACTS[name])
            self.assertEqual(target.stat().st_nlink, 1)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertGreaterEqual(self.guard_calls, 5)
        transaction.undo(self.quiescent)
        self.assert_originals(transaction)
        self.assertTrue(all(self.module.absent(self.module.target(name)) for name in self.module.NEW_ORDER))
        self.assertEqual(set(transaction.new_removed), set(self.module.NEW_ORDER))

    def test_partial_new_file_effect_fsync_failure_restores_preoperation_state(self):
        transaction = self.transaction('123002')
        sync = self.base.sync_directory
        failed = False
        def failing_sync(path):
            nonlocal failed
            if not failed and path == self.scripts and transaction.new_created:
                failed = True
                raise OSError('synthetic fsync failure after owned link')
            sync(path)
        with mock.patch.object(self.base, 'sync_directory', side_effect=failing_sync):
            with self.assertRaises(OSError): transaction.replace(self.quiescent)
        self.assertTrue(failed)
        self.assertTrue(self.module.target(self.module.NEW_ORDER[0]).is_file())
        self.assertEqual(transaction.replaced, [])
        transaction.undo(self.quiescent)
        self.assert_originals(transaction)
        self.assertTrue(all(self.module.absent(self.module.target(name)) for name in self.module.NEW_ORDER))

    def test_unexpected_new_target_is_not_overwritten_or_deleted(self):
        transaction = self.transaction('123003')
        foreign = self.module.target(self.module.NEW_ORDER[1])
        foreign.write_bytes(b'foreign existing snapshot')
        foreign.chmod(0o600)
        with self.assertRaisesRegex(self.base.Hold, 'HOLD_NEW_ARTIFACT_APPEARED'):
            transaction.replace(self.quiescent)
        self.assertEqual(foreign.read_bytes(), b'foreign existing snapshot')
        self.assertEqual(transaction.new_created, [])
        self.assertEqual(transaction.replaced, [])
        self.assert_originals(transaction)

    def test_wrong_current_proxy_lifetime_or_config_fails_before_stop(self):
        pin = self.module.OLD_PROXY
        valid = {'process': {key: pin[key] for key in ('pid', 'start_ticks', 'argv_sha256', 'exe', 'cwd')},
                 'config': {'sha256': pin['config_sha256']}}
        for field in ('start_ticks', 'config_sha256'):
            with self.subTest(field=field):
                value = copy.deepcopy(valid)
                if field == 'start_ticks': value['process'][field] += 1
                else: value['config']['sha256'] = '0' * 64
                with mock.patch.object(self.module, '_original_service_identity', return_value=value):
                    with self.assertRaises(self.base.Hold): self.module.service_identity()
                self.assertFalse(self.module._stop_attempted)
        with mock.patch.object(self.module, '_original_service_identity', return_value=valid):
            self.assertEqual(self.module.service_identity(), valid)
        with mock.patch.object(self.base.subprocess, 'run', side_effect=AssertionError('unscoped service command')):
            with self.assertRaisesRegex(self.base.Hold, 'HOLD_COMMAND_SCOPE'):
                self.module.command(['supervisorctl', 'restart', 'model'])

    def test_final_receipt_requires_all_five_postimages(self):
        transaction = self.transaction('123004')
        transaction.replace(self.quiescent)
        report = {'completed': True, 'status': 'APPLIED_RELOADED_USE_PENDING',
                  'files_after': {name: {'sha256': pins['after_sha256'], 'bytes': pins['after_bytes']}
                                  for name, pins in transform_module.TRANSFORMS.items()}}
        self.assertIs(self.module.finalize_report(report)['installed'], True)
        with self.subTest('snapshot mode drift with exact same body'):
            changed = copy.deepcopy(report)
            self.module.target(self.module.NEW_ORDER[1]).chmod(0o644)
            result = self.module.finalize_report(changed)
            self.assertIsNone(result['installed'])
            self.assertIs(result['completed'], False)
        self.module.target(self.module.NEW_ORDER[1]).chmod(0o600)
        self.module.target(self.module.NEW_ORDER[1]).write_bytes(b'changed outside transaction')
        result = self.module.finalize_report(report)
        self.assertIsNone(result['installed'])
        self.assertIs(result['completed'], False)
        self.assertEqual(result['status'], 'HOLD_FIVE_FILE_FINAL_READBACK')


if __name__ == '__main__':
    unittest.main()
