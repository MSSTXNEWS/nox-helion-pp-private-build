"""Synthetic boundary tests: never start a native trainer or contact services."""
import ast
import copy
import hashlib
import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('qwen_activate_tests', HERE / 'owner_qwen_guard_activate_entry.py')
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)


class ActivationTests(unittest.TestCase):
    def test_window_transformation_changes_only_reviewed_mode_literal(self):
        raw = (b'#!/usr/bin/env python3\nMODE = "ADVANCE6"  # Reviewed transition after native first-five observation.\n'
               b'def main():\n    return MODE\n')
        pins = {**M.PINS, M.WINDOW: hashlib.sha256(raw).hexdigest()}
        with patch.object(M, 'PINS', pins):
            changed = M.transform_window(raw)
            self.assertEqual(changed.replace(b'"ADVANCE1000"', b'"ADVANCE6"'), raw)
            with self.assertRaisesRegex(RuntimeError, 'WINDOW_PREIMAGE'):
                M.transform_window(raw + b'\n')

    def test_explicit_sealed_guard_context_required(self):
        for invalid in (None, {}, {'request': '1'},
                {'request': True, 'source_sha': 'a' * 40, 'receipt_sha256': 'b' * 64},
                {'request': '1', 'source_sha': 'a' * 40, 'receipt_sha256': 'b' * 64, 'latest': True}):
            with self.subTest(value=invalid), self.assertRaisesRegex(RuntimeError, 'SEALED_CONTEXT'):
                M.context(invalid)
        value = {'request': '1', 'source_sha': 'a' * 40, 'receipt_sha256': 'b' * 64}
        self.assertEqual(M.context(value), value)

    @staticmethod
    def baseline():
        return {'successful_optimizer_steps': 6, 'attempted_steps': 6, 'skipped_steps': 0,
                'pointer_sha256': 'a' * 64, 'manifest_sha256': 'b' * 64, 'student_state_sha256': 'c' * 64,
                'progress': {'successful_optimizer_steps': 6, 'attempted_steps': 6, 'skipped_steps': 0}}

    def test_checkpoint_or_progress_advance_blocks_activation(self):
        baseline = self.baseline(); M.no_observed_advance(baseline, copy.deepcopy(baseline))
        for key, value in (('successful_optimizer_steps', 7), ('attempted_steps', 7), ('skipped_steps', 1),
                           ('pointer_sha256', 'd' * 64), ('manifest_sha256', 'd' * 64)):
            changed = copy.deepcopy(baseline); changed[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, 'UPDATES_BEFORE_GUARD'):
                M.no_observed_advance(baseline, changed)
        changed = copy.deepcopy(baseline); changed['progress'].update(successful_optimizer_steps=7, attempted_steps=7)
        with self.assertRaisesRegex(RuntimeError, 'PROGRESS_BEFORE_GUARD'):
            M.no_observed_advance(baseline, changed)

    def test_configs_stop_between_atomic_writes_keeps_partial_guard_and_media_old(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); guard, media = root / 'guard.json', root / 'media.json'
            guard.write_bytes(b'old guard'); media.write_bytes(b'old media')
            previous = {guard: guard.read_bytes(), media: media.read_bytes()}
            calls = []
            def atomic(path, raw):
                calls.append(path); path.write_bytes(raw); path.chmod(0o600)
            h = types.SimpleNamespace(owner_stop=Mock(side_effect=[False, True]), atomic=atomic)
            with patch.object(M, 'GUARD_CONFIG', guard), patch.object(M, 'MEDIA_CONFIG', media):
                with self.assertRaisesRegex(RuntimeError, 'CONFIG_CHANGED_BEFORE_WRITE'):
                    M.commit_configurations(h, previous, {'enabled': True}, {'resume': True})
            self.assertEqual(calls, [guard])
            self.assertEqual(guard.read_bytes(), M.encode({'enabled': True}))
            self.assertEqual(media.read_bytes(), b'old media')

    def test_foreign_config_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); guard, media = root / 'guard.json', root / 'media.json'
            guard.write_bytes(b'foreign'); media.write_bytes(b'old media')
            h = types.SimpleNamespace(owner_stop=Mock(return_value=False), atomic=Mock())
            with patch.object(M, 'GUARD_CONFIG', guard), patch.object(M, 'MEDIA_CONFIG', media):
                with self.assertRaisesRegex(RuntimeError, 'CONFIG_CHANGED_BEFORE_WRITE'):
                    M.commit_configurations(h, {guard: b'old guard', media: b'old media'}, {}, {})
            h.atomic.assert_not_called(); self.assertEqual(guard.read_bytes(), b'foreign')

    def test_poststart_lock_retries_only_busy_with_finite_deadline(self):
        with patch.object(M, 'acquire', side_effect=[BlockingIOError(), BlockingIOError(), 99]) as acquire, \
             patch.object(M.time, 'monotonic', side_effect=[10., 10.1, 10.3]), patch.object(M.time, 'sleep') as sleep:
            self.assertEqual(M.acquire_after_start(Path('/synthetic/maintenance')), 99)
            self.assertEqual(acquire.call_count, 3); self.assertEqual(sleep.call_count, 2)
        with patch.object(M, 'acquire', side_effect=RuntimeError('HOLD_FOREIGN_LOCK')), patch.object(M.time, 'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, 'HOLD_FOREIGN_LOCK'):
                M.acquire_after_start(Path('/synthetic/maintenance'))
            sleep.assert_not_called()
        with patch.object(M, 'acquire', side_effect=BlockingIOError()), \
             patch.object(M.time, 'monotonic', side_effect=[10., 16.01]), patch.object(M.time, 'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, 'MAINTENANCE_REACQUIRE_TIMEOUT'):
                M.acquire_after_start(Path('/synthetic/maintenance'))
            sleep.assert_not_called()

    def pause_fixture(self, root, *, request='123', source='a' * 40):
        admission, wrapper = root / 'admission.json', root / 'wrapper.sh'
        h = types.SimpleNamespace(ADMISSION=admission, WRAPPER=wrapper, PINS={'trainer.py': 'b' * 64})
        pointer = {'request': request, 'source_sha': source, 'initial_request': '6907283384',
                   'previous_request': M.SIX['request'], 'sources': {str(M.SCRIPTS / 'trainer.py'): 'b' * 64},
                   'student_profile': {'successful_updates_goal': 1000}}
        admission.write_bytes(M.encode(pointer)); wrapper.write_bytes(b'exact wrapper')
        window = types.SimpleNamespace(arguments=Mock(return_value=['fixed']), wrapper=Mock(return_value=b'exact wrapper'))
        return h, window, pointer

    def test_pause_is_owned_exclusive_and_never_clears_foreign(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); h, window, _ = self.pause_fixture(root)
            with patch.object(M, 'STATE', root):
                first = M.own_pause(h, window, '123', 'a' * 40, 'HOLD_TEST')
                self.assertEqual(first['state'], 'OWN_ACTIVATION_CHECKPOINT_PAUSE_REQUESTED')
                path = root / 'TRAIN_PAUSE_REQUEST.flag'; path.write_bytes(b'foreign owner pause')
                second = M.own_pause(h, window, '123', 'a' * 40, 'HOLD_TEST')
                self.assertEqual(second['state'], 'EXISTING_PAUSE_PRESERVED')
                self.assertEqual(path.read_bytes(), b'foreign owner pause')

    def test_changed_admission_cannot_receive_our_pause(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); h, window, _ = self.pause_fixture(root, request='456')
            with patch.object(M, 'STATE', root), self.assertRaisesRegex(RuntimeError, 'PAUSE_SCOPE_CHANGED'):
                M.own_pause(h, window, '123', 'a' * 40, 'HOLD_TEST')
            self.assertFalse((root / 'TRAIN_PAUSE_REQUEST.flag').exists())

    def test_source_has_one_normal_window_start_and_no_manual_guard_writer(self):
        tree = ast.parse((HERE / 'owner_qwen_guard_activate_entry.py').read_text())
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        self.assertFalse(any(isinstance(node.func, ast.Attribute) and node.func.attr == 'tick' for node in calls))
        self.assertEqual(sum(isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                             and node.func.value.id == 'window' and node.func.attr == 'main' for node in calls), 1)
        self.assertFalse(any(isinstance(node.func, ast.Attribute) and node.func.attr in ('kill', 'killpg', 'unlink') for node in calls))

    def test_final_service_exit_cannot_report_guarded_continuation_success(self):
        """Run the finite coordinator with synthetic files and no services."""
        with tempfile.TemporaryDirectory() as folder, contextlib.ExitStack() as stack:
            root = Path(folder); state = root / 'state'; scripts = root / 'scripts'; output = root / 'output'
            config_dir = root / 'config'
            for path in (state, scripts, output, config_dir):
                path.mkdir()
            guard_path = config_dir / 'guard.json'; media_path = config_dir / 'media.json'
            guard_state = state / 'guard.json'; lease = state / 'lease'; lease.touch()
            old_guard = {'enabled': False}; new_guard = {'enabled': True}
            old_media = {'enabled': True, 'resume_training_after_media': False, 'window_admission': M.SIX}
            guard_path.write_bytes(M.encode(old_guard)); media_path.write_bytes(M.encode(old_media))
            guard_path.chmod(0o600); media_path.chmod(0o600)
            admission, wrapper = state / 'admission.json', scripts / 'wrapper.sh'
            admission.write_bytes(b'new admission'); wrapper.write_bytes(b'new wrapper')
            new_context = {'request': '123', 'source_sha': 'a' * 40, 'receipt_sha256': 'b' * 64}
            ctx = {'raw': b'new admission', 'wrapper': b'new wrapper', 'contract': object()}
            def atomic(path, raw):
                path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); path.chmod(0o600)
            h = types.SimpleNamespace(atomic=atomic, owner_stop=Mock(return_value=False), HOLD=state / 'hold',
                                      ADMISSION=admission, WRAPPER=wrapper,
                                      service=Mock(return_value={'state': 'FATAL', 'pid': None}))
            window = types.SimpleNamespace(main=Mock(return_value=0), context=Mock(return_value=ctx),
                                           process_chain=Mock(return_value={'processes': [], 'gpu_release_verified': False}))
            guard_row = {'sampled_at': 1000.0, 'state': 'MONITORING', 'bindings': {}, 'checkpoint': {}, 'policy_state': {}}
            def guard_context(_):
                guard_state.write_bytes(M.encode(guard_row)); guard_state.chmod(0o600)
            guard = types.SimpleNamespace(configuration=lambda context,pin,enabled: new_guard if enabled else old_guard,
                checked_config=Mock(return_value=(new_guard, 'c' * 64)), context_evidence=guard_context,
                resume_block_reason=Mock(return_value=None))
            actions = types.SimpleNamespace(configuration=Mock(return_value=old_media), admission=new_context,
                                            context=Mock(return_value={'mode': 'RUNNING_WINDOW1000'}))
            media = types.SimpleNamespace(Admission=Mock(return_value=actions), completed_six=Mock(return_value={
                'acceptance_sha256': M.SIX_ACCEPTANCE, 'checkpoint_manifest_sha256': M.SIX_MANIFEST}))
            trainer = {'service': {'state': 'RUNNING', 'pid': 20},
                       'process': {'pid': 21, 'ppid': 20, 'start_ticks': 200}}
            patched = {'ROOT': root, 'STATE': state, 'SCRIPTS': scripts, 'OUTPUT': output,
                       'GUARD_CONFIG': guard_path, 'MEDIA_CONFIG': media_path, 'GUARD_STATE': guard_state,
                       'DISABLED_CONFIG_SHA': M.sha(M.encode(old_guard)), 'MEDIA_CONFIG_SHA': M.sha(M.encode(old_media))}
            for key,value in patched.items():
                stack.enter_context(patch.object(M, key, value))
            stack.enter_context(patch.dict(os.environ, NOX_OWNER_REQUEST_ID='123', NOX_OWNER_SOURCE_SHA='a' * 40))
            stack.enter_context(patch.object(M, 'window_module', return_value=(window, h, 'd' * 64)))
            stack.enter_context(patch.object(M, 'load', side_effect=[guard, media, object(), object()]))
            stack.enter_context(patch.object(M, 'acquire', side_effect=lambda _: os.open(lease, os.O_RDONLY)))
            stack.enter_context(patch.object(M, 'sources'))
            stack.enter_context(patch.object(M, 'installed_guard_proof'))
            stack.enter_context(patch.object(M, 'controller', return_value={'pid': 10, 'start_ticks': 100}))
            stack.enter_context(patch.object(M, 'trainer_snapshot', return_value=trainer))
            stack.enter_context(patch.object(M, 'counters', return_value=self.baseline()))
            stack.enter_context(patch.object(M, 'new_window', return_value=(new_context, {}, ctx)))
            pause = stack.enter_context(patch.object(M, 'own_pause', return_value={'state': 'OWN_ACTIVATION_CHECKPOINT_PAUSE_REQUESTED'}))
            stack.enter_context(patch.object(M.time, 'time', return_value=1000.0))
            output_stream = io.StringIO()
            with contextlib.redirect_stdout(output_stream):
                rc = M.main({'request': '456', 'source_sha': 'e' * 40, 'receipt_sha256': 'f' * 64})
            result = json.loads((state / 'owner_qwen_guard_activate_123.json').read_bytes())
            self.assertEqual(rc, 2)
            self.assertEqual(result['state'], 'HOLD_QWEN_GUARDED_WINDOW_ACTIVATION')
            self.assertEqual(result['reason'], 'HOLD_QWEN_ACTIVATE_FINAL_TRAINER_EXIT')
            self.assertEqual(result['checkpoint_pause']['state'], 'OWN_ACTIVATION_CHECKPOINT_PAUSE_REQUESTED')
            pause.assert_called_once(); window.main.assert_called_once()
            self.assertIn('NOX_MAINT_REPAIR_COMPLETE=false', output_stream.getvalue())


if __name__ == '__main__':
    unittest.main()
