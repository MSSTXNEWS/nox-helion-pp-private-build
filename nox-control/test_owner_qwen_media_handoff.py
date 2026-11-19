"""Qwen-specific proof and callback tests; the unchanged queue engine has its own suite."""
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import types
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


M = load(HERE / 'owner_qwen_media_handoff.py', 'qwen_handoff_test')
F = load(HERE / 'test_owner_qwen_training_observe.py', 'qwen_observation_fixtures')
BASE = load(HERE / 'owner_media_training_handoff.py', 'qwen_handoff_engine_test')


class HandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        F.QwenObservationTests.setUpClass()

    def setUp(self):
        self.fixture = F.QwenObservationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def paused(self, good=6, new=0, manifest_same_process=False):
        lineage, state, manifest, terminal, directory = self.fixture.fixture(good=good)
        process = manifest['process_identity'] if manifest_same_process else {
            'pid': 555, 'start_ticks': 777, 'boot_id': '00000000-0000-0000-0000-000000000001'}
        terminal.update(state='EXISTING_TRAINER_HOLD_OR_PAUSE', reload_verified=True,
                        new_successful_optimizer_steps=new, process_identity=process)
        F.write(self.fixture.output / 'owner_last_result.json', terminal)
        ctx = {'output': self.fixture.output, 'lineage': lineage, 'contract': self.fixture.contract,
               'lineage_sha256': self.fixture.contract.canonical_sha(lineage),
               'certificate': {'update_evidence': state['update_evidence'][:6]}}
        actions = types.SimpleNamespace(context=lambda: ctx, obs=F.OBS)
        yielded = {'requested_at': time.time() - 1, 'qwen_student': {'pid': process['pid'], 'starttime': process['start_ticks']}}
        return actions, yielded, ctx, terminal, directory

    def test_zero_update_pause_preserves_previous_process_checkpoint(self):
        actions, yielded, _, _, _ = self.paused()
        proof = M.paused_checkpoint(actions, yielded)
        self.assertEqual(proof['step'], 6)
        self.assertEqual(proof['new_successful_optimizer_steps_in_window'], 0)
        self.assertFalse(proof['new_update_required_for_safe_pause'])
        self.assertTrue(proof['full_checkpoint_files_verified'])
        self.assertEqual(proof['files_verified'], 9)

    def test_positive_pause_requires_current_process_checkpoint(self):
        actions, yielded, _, _, _ = self.paused(good=7, new=1)
        with self.assertRaisesRegex(M.QwenHold, 'CURRENT_PROCESS_CHECKPOINT'):
            M.paused_checkpoint(actions, yielded)

    def test_positive_pause_accepts_full_hash_bound_committed_state(self):
        actions, yielded, _, _, _ = self.paused(good=7, new=1, manifest_same_process=True)
        proof = M.paused_checkpoint(actions, yielded)
        self.assertEqual(proof['step'], 7)
        self.assertEqual(proof['new_successful_optimizer_steps_in_window'], 1)

    def test_manual_stop_and_stale_pause_cannot_auto_resume(self):
        actions, yielded, _, terminal, _ = self.paused()
        terminal['state'] = 'MANUAL_OWNER_STOP'
        F.write(self.fixture.output / 'owner_last_result.json', terminal)
        with self.assertRaisesRegex(M.QwenHold, 'FRESH_CONTROLLED_PAUSE'):
            M.paused_checkpoint(actions, yielded)
        terminal['state'] = 'HOLD_TRAINING_STOP_REQUESTED'
        F.write(self.fixture.output / 'owner_last_result.json', terminal)
        yielded['requested_at'] = time.time() + 10
        with self.assertRaisesRegex(M.QwenHold, 'FRESH_CONTROLLED_PAUSE'):
            M.paused_checkpoint(actions, yielded)

    def test_changed_checkpoint_or_six_prefix_is_not_admitted(self):
        actions, yielded, ctx, _, directory = self.paused()
        ctx['certificate']['update_evidence'][0] = dict(ctx['certificate']['update_evidence'][0], adapter_sha_after='f' * 64)
        with self.assertRaisesRegex(M.QwenHold, 'CHECKPOINT_CHAIN'):
            M.paused_checkpoint(actions, yielded)
        (directory / 'optimizer.pt').write_bytes(b'changed optimizer')
        with self.assertRaisesRegex(F.OBS.Hold, 'FILE_SHA'):
            M.paused_checkpoint(actions, yielded)

    def handback(self, enabled, state='RUNNING'):
        runtime = types.SimpleNamespace(resume_training=Mock(), prepare_training=Mock(return_value={'active': False}),
            wait_training=Mock(), service_state=lambda _: {'state': state})
        namespace = {'ingest_owner_orders': lambda _: None, '_nox_owner_task_admitted': lambda _: True,
                     'owner_mentor': types.SimpleNamespace(verify_success=lambda *args: None)}
        actions = types.SimpleNamespace(configuration=lambda *args, **kwargs: {'enabled': enabled})
        return M.create_handback(BASE, namespace, runtime, actions), runtime, actions

    def test_disabled_active_qwen_never_requests_pause_or_old_restore(self):
        handback, runtime, _ = self.handback(False)
        with self.assertRaisesRegex(M.QwenHold, 'WAIT_QWEN_HANDOFF_NOT_ENABLED'):
            handback.prepare({'id': 'a' * 32})
        runtime.prepare_training.assert_not_called()

    def test_disabled_inactive_trainer_keeps_original_media_behavior(self):
        handback, runtime, _ = self.handback(False, 'EXITED')
        self.assertEqual(handback.prepare({'id': 'a' * 32}), {'active': False})
        runtime.prepare_training.assert_called_once()

    def test_heavy_service_check_uses_fixed_allowlist_not_media_whitelist(self):
        admission = M.Admission.__new__(M.Admission)
        command = Mock(return_value=types.SimpleNamespace(stdout='nox-agent-tuner-t858u STOPPED\n'))
        admission.h = types.SimpleNamespace(command=command)
        self.assertEqual(admission.heavy_service_state('nox-agent-tuner-t858u'), 'STOPPED')
        command.assert_called_once_with(['supervisorctl', 'status', 'nox-agent-tuner-t858u'], 5)
        with self.assertRaisesRegex(M.QwenHold, 'SERVICE_SCOPE'):
            admission.heavy_service_state('nox-proxy')

    def test_staging_process_with_previous_pid_telemetry_is_deferred(self):
        handback, runtime, actions = self.handback(True)
        actions.context = lambda: {'output': self.fixture.output, 'mode': 'RUNNING_WINDOW1000'}
        actions.trainer_process = lambda: {'pid': 555, 'starttime': 100}
        actions.obs = types.SimpleNamespace(document=lambda _: ({'state': 'NATIVE_STUDENT_UPDATE_OBSERVED',
            'pid': 444, 'time': time.time()}, {'mtime_ns': time.time_ns()}))
        with self.assertRaisesRegex(M.QwenHold, 'RESTORE_NOT_YET_OBSERVED'):
            handback.prepare({'id': 'a' * 32})
        runtime.prepare_training.assert_not_called()

    def complete_six(self):
        lineage, state, manifest, terminal, directory = self.fixture.fixture(good=6, skipped=0)
        terminal.update(state='STUDENT_RESTART_AND_UPDATES_VERIFIED', reload_verified=True,
                        new_successful_optimizer_steps=1)
        certificate_sha = F.write(self.fixture.output / 'owner_acceptance.json', terminal)
        F.write(self.fixture.output / 'owner_last_result.json', terminal)
        root = Path(self.fixture.temp.name); (root / 'state').mkdir()
        hold = root / 'state/TRAIN_HOLD.flag'
        hold.write_bytes(b'OWNER_QWEN_WINDOW_COMPLETE request=123 goal=6\n')
        admission = root / 'state/owner_training_admission.json'; admission.write_bytes(b'sealed-six')
        runtime = types.SimpleNamespace(service_state=lambda _: {'state': 'EXITED'})
        ctx = {'mode': 'COMPLETED_WINDOW6', 'output': self.fixture.output, 'lineage': lineage,
               'contract': self.fixture.contract, 'certificate': terminal, 'certificate_sha256': certificate_sha,
               'profile': {'successful_updates_goal': 6}, 'admission': {'request': '123'}, 'raw': b'sealed-six'}
        actions = types.SimpleNamespace(context=lambda: ctx, obs=F.OBS, runtime=runtime,
            h=types.SimpleNamespace(ADMISSION=admission, owner_stop=lambda: False),
            window=types.SimpleNamespace(arguments=lambda *args, **kwargs: ['reviewed-six'],
                completion_hold=lambda request, goal: ('OWNER_QWEN_WINDOW_COMPLETE request=' + request + ' goal=' + str(goal) + '\n').encode()))
        return actions, hold, directory, root

    def test_completed_six_admits_media_without_resume_or_flag_change(self):
        actions, hold, _, root = self.complete_six()
        before = hold.read_bytes()
        with patch.object(M, 'ROOT', root), patch.object(F.OBS, 'trainers', return_value=[]):
            value = M.completed_six(actions)
        self.assertFalse(value['active']); self.assertFalse(value['resume'])
        self.assertFalse(value['training_service_started'])
        self.assertEqual(value['qwen_completed_window'], 6)
        self.assertEqual(value['checkpoint_files_verified'], 9)
        self.assertEqual(hold.read_bytes(), before)

    def test_completed_six_rejects_active_trainer_foreign_hold_and_checkpoint_change(self):
        actions, hold, directory, root = self.complete_six()
        with patch.object(M, 'ROOT', root), patch.object(F.OBS, 'trainers', return_value=[]):
            actions.runtime.service_state = lambda _: {'state': 'RUNNING'}
            with self.assertRaisesRegex(M.QwenHold, 'TRAINER_NOT_COMPLETE'):
                M.completed_six(actions)
            actions.runtime.service_state = lambda _: {'state': 'EXITED'}
            hold.write_bytes(b'OWNER_MANUAL_HOLD\n')
            with self.assertRaisesRegex(M.QwenHold, 'COMPLETION_FLAGS'):
                M.completed_six(actions)
            hold.write_bytes(b'OWNER_QWEN_WINDOW_COMPLETE request=123 goal=6\n')
            (directory / 'optimizer.pt').write_bytes(b'corrupt')
            with self.assertRaisesRegex(F.OBS.Hold, 'FILE_SHA'):
                M.completed_six(actions)

    def test_pinned_dependency_is_verified_before_execution(self):
        root = Path(self.fixture.temp.name); scripts = root / 'scripts'; scripts.mkdir()
        marker = root / 'executed'
        (scripts / 'owner_media_training_handoff.py').write_text('open(' + repr(str(marker)) + ', "w").write("bad")')
        with patch.object(M, 'ROOT', root), self.assertRaisesRegex(M.QwenHold, 'DEPENDENCY_PIN'):
            M.load('owner_media_training_handoff.py')
        self.assertFalse(marker.exists())

    def test_exact_four_dependency_composition_binds_without_service_actions(self):
        root = Path(self.fixture.temp.name); scripts = root / 'scripts'; scripts.mkdir()
        sources = {
            'owner_media_training_handoff.py': HERE / 'owner_media_training_handoff.py',
            'owner_qwen_window_entry.py': Path('/tmp/nox_qwen_window_entry_4d5.py'),
            'owner_qwen_install_entry.py': Path('/tmp/nox_qwen_owner_qwen_install_entry.py'),
            'owner_qwen_training_observe.py': HERE / 'owner_qwen_training_observe.py',
        }
        for name, path in sources.items():
            raw = path.read_bytes(); self.assertEqual(M.digest(raw), M.DEPENDENCIES[name])
            (scripts / name).write_bytes(raw)
        runtime_path = scripts / 'owner_media_runtime.py'
        runtime_path.write_bytes((HERE / 'owner_media_runtime.py').read_bytes())
        runtime = types.SimpleNamespace(__file__=str(runtime_path), resume_training=Mock(),
            prepare_training=Mock(), wait_training=Mock(), service_state=Mock(), command=Mock())
        namespace = {'_owner_media_bound': True, '_owner_plans_bound': True, 'WORKERS': 6, 'HANDLERS': {},
            'ingest_owner_orders': Mock(), '_nox_owner_task_admitted': Mock(),
            'owner_mentor': types.SimpleNamespace(verify_success=Mock())}
        with patch.object(M, 'ROOT', root), patch.object(M, 'BOUND', None):
            M.bind_dispatcher(namespace, runtime)
            self.assertEqual(M.BOUND.source_pin, M.digest(Path(M.__file__).read_bytes()))
            self.assertIn('owner_media_resume', namespace['HANDLERS'])
        runtime.command.assert_not_called(); runtime.service_state.assert_not_called()


if __name__ == '__main__':
    unittest.main()
