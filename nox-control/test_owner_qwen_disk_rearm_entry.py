"""Exact disk-latch, checkpoint, no-clobber and single-start fixtures only."""
import copy
from contextlib import ExitStack
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

import owner_qwen_disk_rearm_entry as E
import owner_qwen_training_guard as G
import owner_qwen_training_status as S
import test_owner_qwen_training_observe as F


def window_helper():
    path = Path('/tmp/nox_qwen_window_entry_4d5.py')
    assert E.digest(path.read_bytes()) == E.PINS['owner_qwen_window_entry.py']
    spec = importlib.util.spec_from_file_location('_disk_rearm_window_fixture', path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def fixture_policy():
    cp = {'successful_updates': 10, 'evaluated_at_update': 8, 'holdout_loss': E.LOSS,
          'observed_file_bytes': E.TEN_BYTES}
    p = G.policy_step(None, cp, E.REARM_FREE, 43_278_336, E.LATCHED_AT, G.DEFAULT_POLICY, 1.3033105581998825)
    p.update(inhibit=True, reason='DISK_EARLY_MARGIN', latched_at=E.LATCHED_AT,
             last_sample_at=E.LATCHED_AT + 5)
    row = {'schema': G.SCHEMA, 'bindings': {'source_sha256': E.PINS[E.GUARD_NAME]},
           'sampled_at': E.LATCHED_AT + 5, 'policy_state': p, 'checkpoint': cp, 'state': 'INHIBITED',
           'pause_flag': 'EXISTING_HOLD_PRESERVED', 'checkpoint_after_pause_verified': False,
           'scope': 'HASH_BOUND_CHECKPOINT_METADATA_AND_PAUSE_REQUEST_ONLY'}
    return row, cp


class PolicyTests(unittest.TestCase):
    def rearm(self, row, cp, free=E.REARM_FREE, policy=None):
        return E.policy_rearm(G, row, cp, free, 43_278_336, E.LATCHED_AT + 10,
                              policy or G.DEFAULT_POLICY, 1.3033105581998825)

    def test_actual_current_free_fails_but_exact_two_budget_boundary_preserves_quality(self):
        row, cp = fixture_policy(); prior = copy.deepcopy(row)
        self.assertEqual(E.REARM_FREE, 13_485_867_008)
        for free in (12_008_218_624, E.REARM_FREE - 1, True):
            with self.assertRaisesRegex(RuntimeError, 'TWO_CHECKPOINT_BUDGETS_REQUIRED'):
                self.rearm(row, cp, free)
        updated = self.rearm(row, cp)
        self.assertEqual(row, prior)
        self.assertFalse(updated['policy_state']['inhibit'])
        for key in set(row['policy_state']) - E.RESET_FIELDS - E.SAMPLE_FIELDS:
            self.assertEqual(row['policy_state'][key], updated['policy_state'][key])
        self.assertEqual(updated['policy_state']['disk_floor_bytes'], 10 * 1024 ** 3)
        self.assertEqual(updated['checkpoint'], cp)
        self.assertEqual(updated['bindings'], row['bindings'])

    def test_other_reason_or_quality_counter_is_never_cleared(self):
        base, cp = fixture_policy()
        for change in ({'reason': 'EVALUATION_STALE'}, {'reason': 'HOLDOUT_REGRESSION'},
                       {'regression_streak': 2}, {'latched_at': E.LATCHED_AT + 1},
                       {'best_holdout_loss': 0.5}, {'last_evaluation_update': 7},
                       {'complete': True}, {'last_successful_updates': 11}):
            row = copy.deepcopy(base); row['policy_state'].update(change)
            with self.assertRaisesRegex(RuntimeError, 'EXACT_DISK_LATCH_REQUIRED'):
                self.rearm(row, cp)

    def test_native_quality_and_threshold_policy_is_rechecked_after_unlatching_trial(self):
        row, cp = fixture_policy()
        with self.assertRaisesRegex(RuntimeError, 'QUALITY_OR_POLICY_NOT_PERMISSIVE'):
            self.rearm(row, cp, policy={**G.DEFAULT_POLICY, 'stale_successful_updates': 1})
        with self.assertRaisesRegex(G.GuardHold, 'POLICY_SCOPE'):
            self.rearm(row, cp, policy={**G.DEFAULT_POLICY, 'native_disk_floor_bytes': 1})
        self.assertTrue(row['policy_state']['inhibit'])


class FileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.state = self.root / 'state'; self.state.mkdir()
        self.backup = self.root / 'backup'; self.backup.mkdir(mode=0o700)
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(E, 'STATE', self.state))
        self.window = window_helper()

    def put(self, path, raw):
        path.write_bytes(raw); path.chmod(0o600); return path

    def test_foreign_flag_and_dangling_global_stop_remain_blocking(self):
        row, _ = fixture_policy()
        pause = G.pause_token(row)
        hold = ('OWNER_QWEN_WINDOW_FAILED request=' + E.CONTEXT['request'] + ' goal=1000\n').encode()
        pins = {'TRAIN_PAUSE_REQUEST.flag': E.digest(pause), 'TRAIN_HOLD.flag': E.digest(hold)}
        for name, raw in (('TRAIN_PAUSE_REQUEST.flag', pause), ('TRAIN_HOLD.flag', hold)):
            self.put(self.state / name, raw)
        guard = types.SimpleNamespace(owner_stop=lambda: (self.root / 'STOP').exists() or (self.root / 'STOP').is_symlink(),
                                      pause_token=G.pause_token)
        with patch.object(E, 'FLAGS', pins):
            self.assertEqual(set(E.flags(guard, row)), set(pins))
            self.put(self.state / 'TRAIN_HOLD.flag', b'OWNER_OTHER_REQUEST\n')
            with self.assertRaisesRegex(RuntimeError, 'OWNED_FLAGS_CHANGED'): E.flags(guard, row)
            (self.root / 'STOP').symlink_to(self.root / 'not-there')
            with self.assertRaisesRegex(RuntimeError, 'GLOBAL_STOP'): E.flags(guard, row)
        self.assertEqual((self.state / 'TRAIN_HOLD.flag').read_bytes(), b'OWNER_OTHER_REQUEST\n')

    def test_private_restore_copy_readback_precedes_any_move(self):
        target = self.backup / 'before.json'; E.create_private(target, b'{"private":true}\n')
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError): E.create_private(target, b'replacement')
        self.assertEqual(target.read_bytes(), b'{"private":true}\n')

    def test_rearmed_state_is_published_atomically_without_clobber_or_partial_write(self):
        saved = self.backup / 'rearmed_guard.json'; E.create_private(saved, b'COMPLETE-STATE')
        destination = self.state / 'owner_qwen_training_guard.json'
        E.publish_private_copy(saved, destination, b'COMPLETE-STATE')
        self.assertEqual(saved.stat().st_ino, destination.stat().st_ino)
        destination.unlink(); self.put(destination, b'FOREIGN-STATE')
        with self.assertRaises(FileExistsError):
            E.publish_private_copy(saved, destination, b'COMPLETE-STATE')
        self.assertEqual(destination.read_bytes(), b'FOREIGN-STATE')
        self.assertEqual(saved.read_bytes(), b'COMPLETE-STATE')

    def test_postrename_failure_retains_original_inode_and_rollback_restores_it(self):
        name = 'TRAIN_PAUSE_REQUEST.flag'; target = self.put(self.state / name, b'OWNED')
        before = target.stat(); archive = self.backup / ('released-' + name)
        with patch.object(E, 'sync_dir', side_effect=OSError('synthetic fsync failure')):
            with self.assertRaises(OSError):
                E.moved_file(self.window, target, archive, b'OWNED', E.ident(before, moved=True))
        self.assertFalse(target.exists()); self.assertEqual(archive.stat().st_ino, before.st_ino)
        result = E.rollback(self.window, self.backup, {name}, None)
        self.assertTrue(result['complete']); self.assertEqual(target.stat().st_ino, before.st_ino)
        self.assertEqual(archive.read_bytes(), b'OWNED')

    def test_prestart_rollback_preserves_new_foreign_flag_and_newer_guard(self):
        status = self.state / 'owner_qwen_training_guard.json'
        self.put(self.backup / 'original_guard.json', b'OLD-GUARD')
        self.put(self.backup / 'guard_before.json', b'OLD-GUARD')
        self.put(status, b'FOREIGN-GUARD')
        for name in E.FLAGS:
            self.put(self.backup / ('released-' + name), b'ARCHIVED-OWNED')
        self.put(self.state / 'TRAIN_PAUSE_REQUEST.flag', b'FOREIGN-PAUSE')
        result = E.rollback(self.window, self.backup, {'guard', *E.FLAGS}, b'NEW-OWNED-GUARD')
        self.assertFalse(result['complete'])
        self.assertEqual(status.read_bytes(), b'FOREIGN-GUARD')
        self.assertEqual((self.state / 'TRAIN_PAUSE_REQUEST.flag').read_bytes(), b'FOREIGN-PAUSE')
        self.assertEqual((self.state / 'TRAIN_HOLD.flag').read_bytes(), b'ARCHIVED-OWNED')
        self.assertEqual((self.backup / 'original_guard.json').read_bytes(), b'OLD-GUARD')

    def test_uncommitted_move_intent_keeps_original_files(self):
        raw = b'OLD-GUARD'
        self.put(self.state / 'owner_qwen_training_guard.json', raw)
        self.put(self.backup / 'guard_before.json', raw)
        name = 'TRAIN_PAUSE_REQUEST.flag'; self.put(self.state / name, b'OWN')
        with patch.object(E, 'FLAGS', {name: E.digest(b'OWN')}):
            result = E.rollback(self.window, self.backup, {'guard', name}, b'REARMED')
        self.assertTrue(result['complete']); self.assertEqual(result['guard'], 'UNCHANGED')
        self.assertEqual((self.state / name).read_bytes(), b'OWN')

    def test_completed_prestart_rollback_restores_both_flags_and_old_guard_without_loss(self):
        self.put(self.backup / 'original_guard.json', b'OLD-GUARD')
        self.put(self.backup / 'guard_before.json', b'OLD-GUARD')
        self.put(self.state / 'owner_qwen_training_guard.json', b'OWN-REARMED')
        for name in E.FLAGS: self.put(self.backup / ('released-' + name), name.encode())
        result = E.rollback(self.window, self.backup, {'guard', *E.FLAGS}, b'OWN-REARMED')
        self.assertTrue(result['complete'])
        self.assertEqual((self.state / 'owner_qwen_training_guard.json').read_bytes(), b'OLD-GUARD')
        self.assertEqual((self.backup / 'rearmed_guard_at_rollback.json').read_bytes(), b'OWN-REARMED')
        for name in E.FLAGS: self.assertEqual((self.state / name).read_bytes(), name.encode())

    def test_start_is_once_after_real_forge_release_and_durable_intent(self):
        lock = self.put(self.state / 'forge_training.lock', b'')
        fd = E.acquire(lock); result = {'start_command_issued': False}; events = []
        def release(): os.close(fd); events.append('released')
        def saved():
            self.assertTrue(result['start_intent_recorded']); self.assertFalse(result['start_command_issued']); events.append('saved')
        def command(args, timeout):
            probe = E.acquire(lock); os.close(probe)
            self.assertEqual(events, ['released', 'gate', 'saved', 'stop'])
            self.assertEqual(args, ['supervisorctl', 'start', 'fixed-slot']); events.append('start')
            return types.SimpleNamespace(returncode=0)
        helper = types.SimpleNamespace(command=command, SERVICE='fixed-slot')
        E.issue_start_once(helper, release, lambda: events.append('gate'), lambda: events.append('stop'), saved, result)
        self.assertTrue(result['start_command_issued'])
        with self.assertRaisesRegex(RuntimeError, 'START_ALREADY_ATTEMPTED'):
            E.issue_start_once(helper, release, lambda: None, lambda: None, saved, result)
        self.assertEqual(events.count('start'), 1)

    def test_stop_after_durable_intent_prevents_command_and_is_prestart_failure(self):
        result = {'start_command_issued': False}; helper = types.SimpleNamespace(command=Mock(), SERVICE='fixed-slot')
        with self.assertRaisesRegex(RuntimeError, 'GLOBAL_STOP'):
            E.issue_start_once(helper, lambda: None, lambda: None,
                              lambda: E.require(False, 'GLOBAL_STOP'), lambda: None, result)
        self.assertTrue(result['start_intent_recorded']); self.assertFalse(result['start_command_issued'])
        helper.command.assert_not_called()

    def test_ambiguous_start_failure_is_marked_issued_and_never_replayed(self):
        result = {'start_command_issued': False}
        helper = types.SimpleNamespace(command=Mock(side_effect=TimeoutError()), SERVICE='fixed-slot')
        with self.assertRaises(TimeoutError):
            E.issue_start_once(helper, lambda: None, lambda: None, lambda: None, lambda: None, result)
        self.assertTrue(result['start_command_issued'])
        with self.assertRaisesRegex(RuntimeError, 'START_ALREADY_ATTEMPTED'):
            E.issue_start_once(helper, lambda: None, lambda: None, lambda: None, lambda: None, result)
        self.assertEqual(helper.command.call_count, 1)


class CheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): F.QwenObservationTests.setUpClass()

    def setUp(self):
        self.fixture = F.QwenObservationTests(); self.fixture.setUp(); self.addCleanup(self.fixture.tearDown)
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        lineage, saved, manifest, terminal, directory = self.fixture.fixture(good=10, skipped=0)
        (directory / 'update_extra.json').write_bytes(b'{}')
        manifest['files_sha256']['update_extra.json'] = F.sha(b'{}')
        manifest_sha = F.write(directory / 'checkpoint_manifest.json', manifest)
        pointer_sha = F.write(self.fixture.output / 'latest_checkpoint.json', {'directory': directory.name, 'manifest_sha256': manifest_sha})
        terminal.update(state='EXISTING_TRAINER_HOLD_OR_PAUSE', reload_verified=True, checkpoint_manifest_sha256=manifest_sha)
        terminal_sha = F.write(self.fixture.output / 'owner_last_result.json', terminal)
        certificate = {'update_evidence': saved['update_evidence'][:6]}
        six_sha = F.write(self.fixture.output / 'owner_acceptance.json', certificate)
        baseline = {**S.BASELINE, 'adapter_tensor_sha256': F.sha(b'tensor5')}
        self.stack.enter_context(patch.object(S, 'BASELINE', baseline))
        size = sum((directory / n).stat().st_size for n in manifest['files_sha256'])
        for name, value in {'OUTPUT': self.fixture.output, 'TEN_DIRECTORY': directory.name, 'TEN_MANIFEST': manifest_sha,
                            'TEN_POINTER': pointer_sha, 'TEN_TERMINAL': terminal_sha, 'TEN_BYTES': size, 'SIX_SHA': six_sha}.items():
            self.stack.enter_context(patch.object(E, name, value))
        self.flags = {'fixed': 'owned-paused'}
        self.flag_mock = self.stack.enter_context(patch.object(E, 'flags', return_value=self.flags))
        self.ctx = {'observer': F.OBS, 'contract': self.fixture.contract, 'lineage': lineage, 'certificate': certificate}
        self.directory = directory

    def test_full_hash_verifies_all_ten_and_rejects_modified_optimizer(self):
        proof, _, _ = E.full_checkpoint(None, S, self.ctx, self.flags)
        self.assertTrue(proof['full_checkpoint_file_sha256_verified']); self.assertEqual(proof['verified_files'], 10)
        self.assertEqual(proof['successful_updates'], 10); self.assertGreater(self.flag_mock.call_count, 10)
        (self.directory / 'optimizer.pt').write_bytes(b'corrupted optimizer')
        with self.assertRaisesRegex(RuntimeError, 'FULL_HASH_SHA'):
            E.full_checkpoint(None, S, self.ctx, self.flags)

    def test_stop_or_foreign_pause_during_hash_is_not_bypassed(self):
        self.flag_mock.side_effect = RuntimeError('HOLD_QWEN_DISK_REARM_GLOBAL_STOP')
        original = F.OBS.read
        with self.assertRaisesRegex(RuntimeError, 'GLOBAL_STOP'):
            E.full_checkpoint(None, S, self.ctx, self.flags)
        self.assertIs(F.OBS.read, original)


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / 'state'; (self.state / 'dispatcher').mkdir(parents=True)
        (self.state / 'train_wants_gpu1').write_bytes(b'1')
        self.path = self.state / 'dispatcher/state.json'; self.path.write_text('{"tasks":{}}')
        self.scope = patch.object(E, 'STATE', self.state); self.scope.start(); self.addCleanup(self.scope.stop)
        self.guard = types.SimpleNamespace(owner_stop=lambda: False, disk_free=lambda: E.REARM_FREE)
        self.runtime = types.SimpleNamespace(gpu1=Mock(return_value={'free_mib': 31000}),
            queue_ids=Mock(return_value={'queue_running': [], 'queue_pending': []}))
        self.values = {'memory.max': str(128 * 1024 ** 3).encode(), 'memory.current': str(56 * 1024 ** 3).encode()}
        self.obs = types.SimpleNamespace(proc_bytes=lambda path, maximum: self.values[path.name])

    def test_actual_cgroup_headroom_boundary_and_unknown_limit_fail_closed(self):
        good = E.resource_check(self.guard, self.runtime, self.obs)
        self.assertEqual(good['cgroup_headroom_bytes'], 72 * 1024 ** 3)
        self.values['memory.current'] = str(56 * 1024 ** 3 + 1).encode()
        with self.assertRaisesRegex(RuntimeError, 'RAM_72_GIB_REQUIRED'):
            E.resource_check(self.guard, self.runtime, self.obs)
        self.values['memory.max'] = b'max'
        with self.assertRaisesRegex(RuntimeError, 'CGROUP_LIMIT_UNKNOWN'):
            E.resource_check(self.guard, self.runtime, self.obs)

    def test_existing_media_engine_or_pending_gpu1_task_prevents_resume(self):
        self.runtime.queue_ids.return_value = {'queue_running': ['existing-id'], 'queue_pending': []}
        with self.assertRaisesRegex(RuntimeError, 'MEDIA_ENGINE_ACTIVE'):
            E.resource_check(self.guard, self.runtime, self.obs)
        self.runtime.queue_ids.return_value = {'queue_running': [], 'queue_pending': []}
        self.path.write_text('{"tasks":{"existing":{"status":"pending","locks":["gpu1"]}}}')
        with self.assertRaisesRegex(RuntimeError, 'GPU1_TASK_PENDING'):
            E.resource_check(self.guard, self.runtime, self.obs)
        self.assertEqual(json.loads(self.path.read_text())['tasks']['existing']['status'], 'pending')


if __name__ == '__main__': unittest.main()
