"""Guard-reader tests using synthetic source/state, with no native actions."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('qwen_media_guard_tests', HERE / 'owner_qwen_media_guard.py')
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
CONTEXT = {'request': '123', 'source_sha': 'a' * 40, 'receipt_sha256': 'b' * 64}


class GuardReaderTests(unittest.TestCase):
    def reader(self, enabled=True, reason=None):
        config = {'enabled': True, 'resume_training_after_media': enabled, 'window_admission': dict(CONTEXT)}
        handback = types.SimpleNamespace(configuration=Mock(return_value=config),
            actions=types.SimpleNamespace(admission=dict(CONTEXT)),
            resource_gate=Mock(return_value={'gpu1_free_mib': 32000}), release_flags=Mock(return_value='released'))
        reader = M.Reader(types.SimpleNamespace(BOUND=handback))
        guard = types.SimpleNamespace(resume_block_reason=Mock(return_value=reason))
        reader.checked_guard = Mock(return_value=guard)
        return reader, handback, guard

    def test_completed_six_never_consults_guard_or_releases_flags(self):
        reader, handback, guard = self.reader(False)
        self.assertEqual(reader.admission()['state'], 'COMPLETED_SIX_UNAFFECTED')
        guard.resume_block_reason.assert_not_called()
        with self.assertRaisesRegex(M.GuardHold, 'COMPLETED_WINDOW_HAS_NO_HANDOFF'):
            reader.release_flags('a' * 32, {'TRAIN_HOLD.flag': b'keep'})
        handback.release_flags.assert_not_called()

    def test_fresh_guard_none_allows_existing_resource_gate_and_release(self):
        reader, handback, guard = self.reader()
        budget = reader.resource_gate()
        self.assertEqual(budget['gpu1_free_mib'], 32000)
        self.assertEqual(budget['persistent_training_guard']['state'], 'FRESH_GUARD_ADMITS_RESUME')
        self.assertEqual(reader.release_flags('a' * 32, {'hold': b'own'}), 'released')
        self.assertEqual(guard.resume_block_reason.call_count, 2)
        guard.resume_block_reason.assert_called_with(CONTEXT)
        handback.release_flags.assert_called_once_with('a' * 32, {'hold': b'own'})

    def test_inhibit_appearing_after_resource_gate_blocks_last_flag_release(self):
        reader, handback, guard = self.reader()
        guard.resume_block_reason.side_effect = [None, 'HOLD_QWEN_GUARD_QUALITY_INHIBIT']
        reader.resource_gate()
        with self.assertRaisesRegex(M.GuardHold, 'QUALITY_INHIBIT'):
            reader.release_flags('a' * 32, {'hold': b'own'})
        handback.release_flags.assert_not_called()

    def test_missing_stale_disk_and_foreign_state_all_preserve_flags(self):
        for code in ('WAIT_QWEN_GUARD_STATE_MISSING', 'WAIT_QWEN_GUARD_STATE_STALE',
                     'HOLD_QWEN_GUARD_DISK_INHIBIT', 'HOLD_QWEN_GUARD_CONTEXT_CHANGED'):
            with self.subTest(code=code):
                reader, handback, _ = self.reader(reason=code)
                with self.assertRaisesRegex(M.GuardHold, code):
                    reader.release_flags('a' * 32, {'hold': b'own'})
                handback.release_flags.assert_not_called()

    def test_unexpected_guard_result_and_private_exception_are_sanitized(self):
        for reason in (False, '', 'private prompt or credential', {'allow': True}):
            reader, handback, _ = self.reader(reason=reason)
            with self.assertRaisesRegex(M.GuardHold, 'HOLD_QWEN_MEDIA_GUARD_RESULT'):
                reader.release_flags('a' * 32, {})
            handback.release_flags.assert_not_called()
        reader, _, guard = self.reader()
        guard.resume_block_reason.side_effect = RuntimeError('PRIVATE_FIXTURE')
        with self.assertRaisesRegex(M.GuardHold, '^HOLD_QWEN_MEDIA_GUARD_UNVERIFIED$'):
            reader.admission()

    def test_actual_admission_must_equal_private_handoff_configuration(self):
        reader, handback, guard = self.reader()
        handback.actions.admission['request'] = '456'
        with self.assertRaisesRegex(M.GuardHold, 'ADMISSION_CONTEXT'):
            reader.release_flags('a' * 32, {})
        guard.resume_block_reason.assert_not_called(); handback.release_flags.assert_not_called()

    def test_changed_guard_code_cannot_execute_before_pin_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); base = root / 'base.py'; guard = root / 'guard.py'; marker = root / 'executed'
            base.write_bytes(b'base source')
            guard.write_text('open(' + repr(str(marker)) + ', "w").write("ran")')
            handback = types.SimpleNamespace(resource_gate=Mock(), release_flags=Mock())
            reader = M.Reader(types.SimpleNamespace(BOUND=handback))
            with patch.object(M, 'BASE_PATH', base), patch.object(M, 'BASE_SHA', hashlib.sha256(base.read_bytes()).hexdigest()), \
                 patch.object(M, 'GUARD_PATH', guard), patch.object(M, 'GUARD_SHA', '0' * 64):
                with self.assertRaisesRegex(M.GuardHold, 'SOURCE_PIN'):
                    reader.checked_guard()
            self.assertFalse(marker.exists())


if __name__ == '__main__':
    unittest.main()
