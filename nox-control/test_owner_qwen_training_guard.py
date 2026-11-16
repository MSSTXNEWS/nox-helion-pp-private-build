"""Pause ownership, committed evidence and handback gates; no native actions."""
from contextlib import ExitStack
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


M = load(HERE / 'owner_qwen_training_guard.py', 'qwen_guard_test')
F = load(HERE / 'test_owner_qwen_training_observe.py', 'qwen_guard_fixtures')
PARAMETERS = 43_278_336
CHECKPOINT_BYTES = 519_882_866
CONTEXT = {'request': '123456', 'source_sha': 'a' * 40, 'receipt_sha256': 'b' * 64}
SOURCE_SHA = hashlib.sha256(Path(M.__file__).read_bytes()).hexdigest()


def checkpoint(good=6, evaluated=6, loss=1.3):
    return {'successful_updates': good, 'evaluated_at_update': evaluated,
            'holdout_loss': loss, 'observed_file_bytes': CHECKPOINT_BYTES}


def step(prior=None, *, good=6, evaluated=6, loss=1.3, free=20 * M.GIB, now=100):
    return M.policy_step(prior, checkpoint(good, evaluated, loss), free, PARAMETERS, now,
                         M.DEFAULT_POLICY, 1.3)


class PolicyTests(unittest.TestCase):
    def test_transient_checkpoint_allocation_recovers_without_pause(self):
        base = step()
        low = base['disk_early_threshold_bytes'] - M.MIB
        # A large one-sample drop is not extrapolated as continuous consumption.
        sample = step(base, free=low, now=105)
        self.assertFalse(sample['inhibit'])
        restored = step(sample, free=20 * M.GIB, now=110)
        self.assertFalse(restored['inhibit'])
        self.assertIsNone(restored['low_since'])

    def test_two_five_second_low_readings_latch_before_native_floor(self):
        base = step()
        low = base['disk_early_threshold_bytes'] - M.MIB
        first = step(base, free=low, now=105)
        too_soon = step(first, free=low, now=109.99)
        self.assertFalse(too_soon['inhibit'])
        second = step(too_soon, free=low, now=110)
        self.assertEqual(second['reason'], 'DISK_EARLY_MARGIN')
        self.assertGreater(low, 10 * M.GIB)
        self.assertEqual(second['checkpoint_budget_bytes'], 826_671_104)
        self.assertTrue(step(second, now=115)['inhibit'])

    def test_little_headroom_does_not_wait_for_second_sample(self):
        base = step()
        result = step(free=base['disk_urgent_threshold_bytes'])
        self.assertEqual(result['reason'], 'DISK_EARLY_MARGIN')
        self.assertFalse(result['floor_already_crossed'])

    def test_stale_saved_evaluation_at_fifteen_verified_updates(self):
        self.assertFalse(step(good=20)['inhibit'])
        result = step(good=21)
        self.assertEqual(result['reason'], 'EVALUATION_STALE')
        self.assertEqual(result['evaluation_age_updates'], 15)

    def test_only_distinct_actual_evaluations_advance_patience(self):
        first = step(good=10, evaluated=10, loss=1.5)
        self.assertEqual(first['regression_streak'], 1)
        repeated = step(first, good=15, evaluated=10, loss=1.5, now=105)
        self.assertEqual(repeated['regression_streak'], 1)
        same_step_reloaded = step(repeated, good=15, evaluated=10, loss=1.5001, now=110)
        self.assertEqual(same_step_reloaded['regression_streak'], 1)
        second = step(same_step_reloaded, good=20, evaluated=20, loss=1.45, now=115)
        self.assertEqual(second['reason'], 'HOLDOUT_REGRESSION')
        self.assertEqual(second['observed_distinct_evaluations'], 2)

    def test_missed_evaluation_and_improvement_reset_observed_streak(self):
        first = step(good=10, evaluated=10, loss=1.5)
        unseen = step(first, good=20, evaluated=15, loss=1.6, now=105)
        self.assertEqual(unseen['regression_streak'], 0)
        self.assertFalse(unseen['inhibit'])
        improved = step(first, good=15, evaluated=15, loss=1.1, now=105)
        self.assertEqual(improved['regression_streak'], 0)
        self.assertEqual(improved['best_holdout_loss'], 1.1)

    def test_complete_cap_is_not_another_pause_or_a_training_optimum(self):
        done = step(good=1000, evaluated=1000, free=1, loss=1.7)
        self.assertTrue(done['complete'])
        self.assertFalse(done['inhibit'])
        self.assertTrue(done['floor_already_crossed'])


class FileAndBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        F.QwenObservationTests.setUpClass()

    def setUp(self):
        self.fixture = F.QwenObservationTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = Path(self.fixture.temp.name)
        self.state = self.root / 'state'; self.state.mkdir()
        (self.root / 'config').mkdir()
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        for name, value in {'ROOT': self.root, 'STATE': self.state, 'OUTPUT': self.fixture.output,
            'CONFIG': self.root / 'config/owner_qwen_training_guard.json',
            'STATUS': self.state / 'owner_qwen_training_guard.json',
            'ADMISSION': self.state / 'owner_training_admission.json',
            'MAINTENANCE': self.state / 'owner_maintenance.lock',
            'MAINTENANCE_FLAG': self.state / 'OWNER_MAINTENANCE.flag',
            'HOLD': self.state / 'TRAIN_HOLD.flag', 'PAUSE': self.state / 'TRAIN_PAUSE_REQUEST.flag'}.items():
            self.stack.enter_context(patch.object(M, name, value))
        M.MAINTENANCE.write_bytes(b'')
        self.write_config()
        self.pointer = M.encode({'student_profile': {'successful_updates_goal': 1000}})
        M.ADMISSION.write_bytes(self.pointer)
        lineage, state, _, _, self.directory = self.fixture.fixture(good=6, skipped=0)
        self.ctx = {'output': self.fixture.output, 'observer': F.OBS, 'lineage': lineage,
            'lineage_sha256': self.fixture.contract.canonical_sha(lineage), 'contract': self.fixture.contract,
            'certificate': {'update_evidence': state['update_evidence'], 'final_holdout_loss': 1.0},
            'context': CONTEXT, 'admission_sha256': M.digest(self.pointer), 'wrapper_sha256': 'd' * 64,
            'raw': self.pointer}
        self.context_mock = self.stack.enter_context(patch.object(M, 'context_evidence', return_value=self.ctx))
        self.free_mock = self.stack.enter_context(patch.object(M, 'disk_free', return_value=20 * M.GIB))

    def write_config(self):
        M.CONFIG.write_bytes(M.encode(M.configuration(CONTEXT, SOURCE_SHA)))
        M.CONFIG.chmod(0o600)

    def guard(self):
        return M.Guard(SOURCE_SHA)

    def test_small_metadata_hashes_do_not_claim_tensor_payload_verified(self):
        result = M.checkpoint_metadata(self.ctx)
        self.assertTrue(result['metadata_hashes_verified'])
        self.assertFalse(result['all_checkpoint_file_hashes_verified'])
        self.assertEqual(result['successful_updates'], 6)
        raw = (self.directory / 'student_state.json').read_bytes()
        (self.directory / 'student_state.json').write_bytes(raw + b' ')
        with self.assertRaisesRegex(M.GuardHold, 'CHECKPOINT_METADATA_SHA'):
            M.checkpoint_metadata(self.ctx)

    def test_initial_six_does_nothing_even_without_guard_config(self):
        M.ADMISSION.write_bytes(M.encode({'student_profile': {'successful_updates_goal': 6}}))
        M.CONFIG.unlink()
        result = self.guard().tick()
        self.assertEqual(result['state'], 'NON_TARGET_WINDOW_NO_ACTION')
        self.context_mock.assert_not_called()
        self.assertFalse(M.STATUS.exists()); self.assertFalse(M.PAUSE.exists())

    def test_unsealed_context_cannot_create_state_or_flag(self):
        self.context_mock.side_effect = M.GuardHold('HOLD_QWEN_GUARD_SEALED_WINDOW1000')
        self.free_mock.return_value = 1
        self.assertEqual(self.guard().tick()['state'], 'HELD')
        self.assertFalse(M.STATUS.exists()); self.assertFalse(M.PAUSE.exists())

    def test_maintenance_exclusive_prevents_state_and_pause_writes(self):
        fd = os.open(M.MAINTENANCE, os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.guard().tick()['state'], 'WAIT_OWNER_MAINTENANCE')
        finally:
            os.close(fd)
        self.assertFalse(M.STATUS.exists()); self.assertFalse(M.PAUSE.exists())

    def test_foreign_pause_is_preserved_while_own_inhibit_is_durable(self):
        M.PAUSE.write_bytes(b'NOX_MEDIA_OWNER_TOKEN\n')
        self.free_mock.return_value = 1
        result = self.guard().tick()
        self.assertEqual(result['pause_flag'], 'EXISTING_PAUSE_PRESERVED')
        self.assertEqual(M.PAUSE.read_bytes(), b'NOX_MEDIA_OWNER_TOKEN\n')
        state, _ = M.document(M.STATUS)
        self.assertTrue(state['policy_state']['inhibit'])
        self.assertFalse(state['checkpoint_after_pause_verified'])
        self.assertEqual(M.STATUS.stat().st_mode & 0o777, 0o600)

    def test_own_pause_is_exclusive_persistent_and_does_not_mean_saved(self):
        self.free_mock.return_value = 1
        guard = self.guard(); result = guard.tick()
        self.assertEqual(result['pause_flag'], 'OWN_PAUSE_REQUESTED')
        token = M.PAUSE.read_bytes(); self.assertTrue(token.startswith(b'NOX_QWEN_GUARD_PAUSE_V1 '))
        self.assertEqual(M.PAUSE.stat().st_mode & 0o777, 0o600)
        self.free_mock.return_value = 20 * M.GIB; guard.last_poll = None
        self.assertTrue(guard.tick()['inhibit'])
        self.assertEqual(M.PAUSE.read_bytes(), token)
        self.assertEqual(M.resume_block_reason(CONTEXT), 'HOLD_QWEN_GUARD_DISK_EARLY_MARGIN')

    def test_resume_is_readonly_and_does_not_reacquire_maintenance(self):
        self.assertEqual(self.guard().tick()['state'], 'MONITORING')
        before = M.STATUS.read_bytes()
        fd = os.open(M.MAINTENANCE, os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(M.fcntl, 'flock', side_effect=AssertionError('recursive flock')):
                self.assertIsNone(M.resume_block_reason(CONTEXT))
        finally:
            os.close(fd)
        self.assertEqual(M.STATUS.read_bytes(), before)
        self.assertFalse(M.PAUSE.exists())

    def test_resume_rejects_missing_stale_mismatched_or_changed_checkpoint(self):
        self.assertEqual(M.resume_block_reason(CONTEXT), 'HOLD_QWEN_GUARD_STATE_MISSING')
        self.guard().tick()
        raw = M.STATUS.read_bytes(); row = json.loads(raw)
        row['sampled_at'] = time.time() - 31
        M.STATUS.write_bytes(M.encode(row))
        self.assertEqual(M.resume_block_reason(CONTEXT), 'HOLD_QWEN_GUARD_STATE_STALE')
        M.STATUS.write_bytes(raw)
        other = dict(CONTEXT, receipt_sha256='e' * 64)
        self.assertEqual(M.resume_block_reason(other), 'HOLD_QWEN_GUARD_CONTEXT_MISMATCH')
        row = json.loads(raw); row['checkpoint']['pointer_sha256'] = 'f' * 64
        M.STATUS.write_bytes(M.encode(row))
        self.assertEqual(M.resume_block_reason(CONTEXT), 'HOLD_QWEN_GUARD_STATE_CHECKPOINT_PENDING')

    def test_resume_requires_full_early_margin_even_before_two_low_ticks(self):
        self.guard().tick()
        row = json.loads(M.STATUS.read_bytes())
        self.free_mock.return_value = row['policy_state']['disk_early_threshold_bytes'] - 1
        self.assertEqual(M.resume_block_reason(CONTEXT), 'HOLD_QWEN_GUARD_RESUME_MARGIN_OR_QUALITY')

    def test_hook_keeps_previous_status_and_does_not_spawn_executor(self):
        prior = Mock(return_value='previous-status')
        ns = {'write_status': prior}
        guard = M.bind_dispatcher(ns, SOURCE_SHA)
        guard.tick = Mock(return_value={'state': 'not-native'})
        self.assertEqual(ns['write_status']({'task': 1}), 'previous-status')
        prior.assert_called_once_with({'task': 1}); guard.tick.assert_called_once_with()
        self.assertIs(M.bind_dispatcher(ns, SOURCE_SHA), guard)

    def test_nonfinite_and_special_file_are_rejected_without_blocking(self):
        path = self.root / 'bad.json'; path.write_text('{"value":1e999}')
        with self.assertRaises(ValueError):
            M.document(path)
        path.unlink(); os.mkfifo(path)
        with self.assertRaisesRegex(M.GuardHold, 'FILE_BOUND'):
            M.read(path)


if __name__ == '__main__':
    unittest.main()
