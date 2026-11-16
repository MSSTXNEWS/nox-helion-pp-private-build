import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch


class NativeStageStopGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'nox'

    def load_stage(self):
        source_path = Path(__file__).with_name('owner_native_stage.py')
        source = source_path.read_text()
        token = 'BUNDLE=__NOX_BUNDLE_JSON__'
        self.assertIn(token, source)
        source = source.replace(token, 'BUNDLE={}', 1)
        namespace = {'__name__': 'owner_native_stage_test'}
        with patch.dict(os.environ, {
            'NOX_OWNER_SOURCE_SHA': 'a' * 40,
            'NOX_OWNER_REQUEST_ID': '123',
        }):
            exec(compile(source, str(source_path), 'exec'), namespace)
        namespace['ROOT'] = self.root
        namespace['STATE'] = self.root / 'state'
        namespace['SCRIPTS'] = self.root / 'scripts'
        namespace['BACKUP'] = self.root / 'backup/owner_maintenance/123'
        namespace['WORKSPACE_STOP'] = self.root.parent / 'workspace/NOX_STOP'
        namespace['STOP_PATHS'] = (
            self.root / 'STOP', self.root / 'STOP.flag', self.root / 'stop.flag',
            self.root / '.stop', self.root / 'program/STOP', namespace['STATE'] / 'STOP',
            namespace['STATE'] / 'STOP.flag', namespace['WORKSPACE_STOP'],
        )
        namespace['OWNER_MAINTENANCE_FLAG'] = namespace['STATE'] / 'OWNER_MAINTENANCE.flag'
        return namespace

    def assert_no_stage_writes(self, namespace):
        self.assertFalse((namespace['STATE'] / 'owner_maintenance_123.json').exists())
        self.assertFalse(namespace['BACKUP'].exists())

    def test_all_canonical_stop_aliases_block_before_stage_writes(self):
        namespace = self.load_stage()
        stop_paths = (
            self.root / 'STOP', self.root / 'STOP.flag', self.root / 'stop.flag',
            self.root / '.stop', self.root / 'program/STOP',
            self.root / 'state/STOP', self.root / 'state/STOP.flag',
            namespace['WORKSPACE_STOP'],
        )
        for stop in stop_paths:
            with self.subTest(path=stop.name):
                if stop.exists():
                    stop.unlink()
                stop.parent.mkdir(parents=True, exist_ok=True)
                stop.write_text('manual stop')
                with self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER_STOP_ACTIVE'):
                    namespace['main']()
                self.assert_no_stage_writes(namespace)
                stop.unlink()

    def test_model_update_blocks_before_receipt_or_backup(self):
        namespace = self.load_stage()
        maintenance = namespace['STATE'] / 'OWNER_MAINTENANCE.flag'
        maintenance.parent.mkdir(parents=True)
        maintenance.write_text('OWNER_MODEL_UPDATE')
        with self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER_MODEL_UPDATE_ACTIVE'):
            namespace['main']()
        self.assertFalse((namespace['STATE'] / 'owner_maintenance_123.json').exists())
        self.assertFalse(namespace['BACKUP'].exists())

    def test_unknown_owner_lease_blocks_before_state_or_backup_write(self):
        namespace = self.load_stage()
        with self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER_LEASE_UNKNOWN'):
            namespace['main']()
        self.assertFalse(namespace['STATE'].exists())
        self.assertFalse(namespace['BACKUP'].exists())

    def test_mid_operation_stop_restores_hold_and_never_starts_trainer(self):
        namespace = self.load_stage()
        state = namespace['STATE']
        state.mkdir(parents=True)
        namespace['BACKUP'].mkdir(parents=True)
        hold = state / 'TRAIN_HOLD.flag'
        hold.write_text('MANUAL_HOLD')
        attempts = state / 'train_volta_t866u.attempts'
        attempts.write_text('7\\n')
        calls = {'gate': 0}

        def owner_gate_with_stop_arriving_mid_operation():
            calls['gate'] += 1
            if calls['gate'] == 2:
                (self.root / 'STOP').write_text('MODEL_UPDATE')
            namespace['stage_gate'](namespace['STOP_PATHS'], namespace['OWNER_MAINTENANCE_FLAG'], 'OWNER_CAS_VERIFIED')
            # Test-only admission fixture: production lease remains UNKNOWN.
            return None

        namespace['require_stage_admission'] = owner_gate_with_stop_arriving_mid_operation
        start = Mock(side_effect=AssertionError('trainer start must remain blocked'))
        namespace['command'] = start
        with self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER_STOP_ACTIVE'):
            namespace['release_hold_and_start_trainer']()
        self.assertEqual(calls['gate'], 2)
        self.assertEqual(hold.read_text(), 'MANUAL_HOLD')
        self.assertEqual(attempts.read_text(), '7\\n')
        start.assert_not_called()

    def test_stop_after_initial_admission_blocks_before_hold_rename(self):
        namespace = self.load_stage()
        state = namespace['STATE']
        state.mkdir(parents=True)
        namespace['BACKUP'].mkdir(parents=True)
        hold = state / 'TRAIN_HOLD.flag'
        hold.write_text('MANUAL_HOLD')
        attempts = state / 'train_volta_t866u.attempts'
        attempts.write_text('7\\n')
        original_backup = namespace['backup']

        def backup_then_activate_stop(path):
            data = original_backup(path)
            if Path(path) == hold:
                stop = namespace['STOP_PATHS'][0]
                stop.parent.mkdir(parents=True, exist_ok=True)
                stop.write_text('manual stop')
            return data

        namespace['backup'] = backup_then_activate_stop
        namespace['require_stage_admission'] = lambda: namespace['stage_gate'](
            namespace['STOP_PATHS'], namespace['OWNER_MAINTENANCE_FLAG'], 'OWNER_CAS_VERIFIED'
        )
        start = Mock(side_effect=AssertionError('trainer start must remain blocked'))
        namespace['command'] = start
        with self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER_STOP_ACTIVE'):
            namespace['release_hold_and_start_trainer']()
        archived = state / 'TRAIN_HOLD.resumed_by_owner_123'
        self.assertEqual(hold.read_text(), 'MANUAL_HOLD')
        self.assertFalse(archived.exists())
        self.assertEqual(attempts.read_text(), '7\\n')
        self.assertFalse((state / 'owner_maintenance_123.json').exists())
        start.assert_not_called()


if __name__ == '__main__':
    unittest.main()
