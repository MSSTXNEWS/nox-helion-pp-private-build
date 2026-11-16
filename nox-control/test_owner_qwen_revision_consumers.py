"""Synthetic execution-revision consumer checks; no model, network or native control."""
from contextlib import ExitStack
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).parent


def load(name):
    spec = importlib.util.spec_from_file_location('_revision_test_' + name, HERE / (name + '.py'))
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


G = load('owner_qwen_revision_guard')
M = load('owner_qwen_revision_media_handoff')
R = load('owner_qwen_revision_media_guard')
T = load('owner_qwen_revision_handback_retry')
H = load('owner_hermes_revision_hydrate')
S = load('owner_qwen_revision_status')
V = load('owner_qwen_execution_revision')
F = load('test_owner_qwen_training_observe')
ORIGIN = {'request': '6908281920', 'source_sha': '3' * 40, 'receipt_sha256': '4' * 64}
REF = {'request': '6911000000', 'source_sha': 'a' * 40, 'receipt_sha256': 'b' * 64}
VERIFIER_SHA = 'c' * 64
PARAMETERS = 43_278_336


def cp(good=25, evaluated=10, loss=1.2653611116111279):
    return {'successful_updates': good, 'attempted_updates': good, 'skipped_updates': 0,
            'evaluated_at_update': evaluated, 'holdout_loss': loss, 'observed_file_bytes': 519902179,
            'manifest_sha256': 'd' * 64, 'student_state_sha256': 'e' * 64}


def old_policy():
    prior = G.policy_step(None, cp(10, 10), 20 * G.GIB, PARAMETERS, 100,
                          G.DEFAULT_POLICY, 1.3033105581998825)
    return G.policy_step(prior, cp(), 20 * G.GIB, PARAMETERS, 105, G.DEFAULT_POLICY, 1.3033105581998825)


def pending():
    return {'active': False, 'bootstrap_pending': True, 'deadline': 1000,
            'baseline_successful_total': 25, 'permit_sha256': None}


class ConfigTests(unittest.TestCase):
    def test_guard_renderer_preserves_historical_window_and_every_policy_field(self):
        before = G.configuration(ORIGIN, '1' * 64); original = copy.deepcopy(before)
        with patch.object(G, 'REVISION_VERIFIER_SHA', VERIFIER_SHA):
            after = G.make_revision_guard_config(before, REF, '2' * 64)
        self.assertEqual(before, original)
        self.assertEqual(after['window_admission'], ORIGIN)
        self.assertEqual(after['execution_revision'], REF)
        self.assertEqual(after['policy'], before['policy'])
        before['policy']['stale_successful_updates'] = 16
        with patch.object(G, 'REVISION_VERIFIER_SHA', VERIFIER_SHA), self.assertRaisesRegex(G.GuardHold, 'POLICY_SCOPE'):
            G.make_revision_guard_config(before, REF, '2' * 64)

    def test_media_renderer_does_not_change_main_runtime_or_historical_context(self):
        before = {'schema': M.CONFIG_SCHEMA, 'enabled': True, 'resume_training_after_media': True,
            'source_sha256': '1' * 64, 'dependencies': dict(M.DEPENDENCIES), 'runtime_sha256': M.MEDIA_SHA,
            'installer_sha256': M.INSTALLER_SHA, 'media_config_sha256': '2' * 64, 'window_admission': ORIGIN}
        with patch.object(M, 'REVISION_VERIFIER_SHA', VERIFIER_SHA):
            after = M.make_revision_media_config(before, REF, source_sha256='3' * 64)
        for key in ('dependencies', 'runtime_sha256', 'installer_sha256', 'media_config_sha256', 'window_admission'):
            self.assertEqual(after[key], before[key])
        self.assertNotIn('execution_revision', before)
        self.assertEqual(after['execution_revision'], REF)

    def test_hydrate_keeps_exact_public_content_aliases_and_72_3_gib_floors(self):
        before = {'schema': H.SCHEMA, 'context': ORIGIN, 'public_repository': H.REPO, 'public_revision': H.REVISION,
            'public_filename': H.NAME, 'bytes': H.SIZE, 'sha256': H.SHA, 'ram_path': str(H.WARM),
            'ssd_path': str(H.SSD), 'minimum_cgroup_headroom_bytes': 72 * H.GIB,
            'minimum_tmpfs_reserve_bytes': 3 * H.GIB, 'profile_pins': dict(H.PROFILE_PINS),
            'download_source_sha256': H.DOWNLOADER_SHA, 'hydrate_source_sha256': '1' * 64}
        with patch.object(H, 'REVISION_VERIFIER_SHA', VERIFIER_SHA):
            after = H.make_revision_hydrate_manifest(before, REF, source_sha256='2' * 64, runtime_entry_sha256='3' * 64)
            for field in ('sha256', 'bytes', 'public_revision', 'public_repository', 'ram_path', 'ssd_path',
                          'minimum_cgroup_headroom_bytes', 'minimum_tmpfs_reserve_bytes', 'download_source_sha256'):
                self.assertEqual(before[field], after[field])
            self.assertEqual(after['profile_pins'], {**H.PROFILE_PINS, H.REVISION_ENTRY: '3' * 64,
                                                   'owner_qwen_execution_revision.py': VERIFIER_SHA})
            before['minimum_tmpfs_reserve_bytes'] -= 1
            with self.assertRaisesRegex(H.Hold, 'REVISION_MANIFEST_PREIMAGE'):
                H.make_revision_hydrate_manifest(before, REF, source_sha256='2' * 64, runtime_entry_sha256='3' * 64)

    def test_status_anchor_is_explicit_and_old_anchor_is_not_reinterpreted(self):
        before = {'schema': S.CONFIG_SCHEMA, 'admission': ORIGIN}
        after = S.make_revision_status_config(before, REF)
        self.assertEqual(before['admission'], ORIGIN)
        self.assertEqual(after, {'schema': S.CONFIG_SCHEMA, 'admission': REF})


class BootstrapTests(unittest.TestCase):
    def test_fresh_metadata_does_not_clear_latch_or_change_quality_history(self):
        before = old_policy(); original = copy.deepcopy(before)
        decision, details = G.bootstrap_decision(before, cp(evaluated=25, loss=1.1), 20 * G.GIB,
            PARAMETERS, 110, G.DEFAULT_POLICY, 1.3033105581998825, pending())
        self.assertEqual(before, original)
        for key in ('inhibit', 'reason', 'latched_at', 'last_successful_updates', 'last_evaluation_update',
                    'best_holdout_loss', 'regression_streak', 'observed_distinct_evaluations'):
            self.assertEqual(decision[key], original[key])
        self.assertEqual(details['state'], 'BOOTSTRAP_EVALUATION')
        self.assertFalse(details['pause_required']); self.assertFalse(details['optimizer_permission'])

    def test_new_disk_hazard_is_not_hidden_by_sticky_stale_reason(self):
        decision, details = G.bootstrap_decision(old_policy(), cp(), 1, PARAMETERS, 110,
            G.DEFAULT_POLICY, 1.3, pending())
        self.assertTrue(decision['inhibit'])
        self.assertTrue(details['pause_required'])
        self.assertEqual(details['blocked_reason'], 'DISK_EARLY_MARGIN')

    def test_expired_bootstrap_and_unexpected_update_request_pause(self):
        for checkpoint, activation, expected in ((cp(), {**pending(), 'deadline': 109}, 'BOOTSTRAP_DEADLINE_OR_SCOPE'),
                (cp(good=26, evaluated=25), pending(), 'BOOTSTRAP_UNEXPECTED_OPTIMIZER_UPDATE')):
            with self.subTest(expected=expected):
                _, details = G.bootstrap_decision(old_policy(), checkpoint, 20 * G.GIB, PARAMETERS, 110,
                                                  G.DEFAULT_POLICY, 1.3, activation)
                self.assertTrue(details['pause_required']); self.assertEqual(details['blocked_reason'], expected)

    def test_new_regression_is_not_promoted_into_unaccepted_quality_history(self):
        prior = old_policy(); prior['regression_streak'] = 1
        result, details = G.bootstrap_decision(prior, cp(evaluated=25, loss=2), 20 * G.GIB,
                                               PARAMETERS, 110, G.DEFAULT_POLICY, 1.3, pending())
        self.assertEqual(details['blocked_reason'], 'HOLDOUT_REGRESSION')
        self.assertEqual(result['regression_streak'], 1)

    def test_resume_waits_before_reading_old_permissive_state_without_nested_flock(self):
        verifier = types.SimpleNamespace(activation_status=Mock(return_value=pending()))
        ctx = {'execution': {}, '_revision_verifier': verifier}
        with patch.object(G, 'owner_stop', return_value=False), patch.object(G, 'checked_config', return_value=({}, 'a' * 64)), \
                patch.object(G, 'context_evidence', return_value=ctx), \
                patch.object(G, 'previous_state', side_effect=AssertionError('must not trust an old MONITORING row')), \
                patch.object(G.fcntl, 'flock', side_effect=AssertionError('recursive lease')):
            self.assertEqual(G.resume_block_reason(REF), 'WAIT_QWEN_GUARD_EXECUTION_BOOTSTRAP')

    def test_real_tick_preserves_stale_pause_suppression_but_writes_new_disk_pause(self):
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            root = Path(temp); state = root / 'state'; state.mkdir(); (root / 'config').mkdir()
            for name, value in {'ROOT': root, 'STATE': state, 'OUTPUT': root, 'CONFIG': root / 'config/guard.json',
                    'STATUS': state / 'guard.json', 'ADMISSION': state / 'admission.json', 'PAUSE': state / 'pause',
                    'HOLD': state / 'hold', 'MAINTENANCE': state / 'maintenance.lock',
                    'MAINTENANCE_FLAG': state / 'maintenance.flag'}.items():
                stack.enter_context(patch.object(G, name, value))
            stack.enter_context(patch.object(G, 'REVISION_VERIFIER_SHA', VERIFIER_SHA))
            source = G.digest(Path(G.__file__).read_bytes())
            config = G.make_revision_guard_config(G.configuration(ORIGIN, '1' * 64), REF, source)
            G.CONFIG.write_bytes(G.encode(config)); G.CONFIG.chmod(0o600)
            raw = G.encode({'student_profile': {'successful_updates_goal': 1000}})
            G.ADMISSION.write_bytes(raw); G.MAINTENANCE.write_bytes(b'')
            ctx = {'raw': raw, 'admission_sha256': G.digest(raw), 'wrapper_sha256': '2' * 64,
                'lineage_sha256': '3' * 64, 'lineage': {'targets': {'parameters': PARAMETERS}},
                'certificate': {'final_holdout_loss': 1.3}, 'execution': {'reference': REF,
                    'descriptor_sha256': '4' * 64, 'verifier_sha256': VERIFIER_SHA},
                '_revision_verifier': types.SimpleNamespace(activation_status=lambda _: pending())}
            row = {'schema': G.SCHEMA, 'bindings': G.bindings(config, G.digest(G.CONFIG.read_bytes()), ctx),
                   'policy_state': old_policy(), 'state': 'BOOTSTRAP_EVALUATION', 'sampled_at': 105}
            G.STATUS.write_bytes(G.encode(row)); G.STATUS.chmod(0o600)
            stack.enter_context(patch.object(G, 'context_evidence', return_value=ctx))
            stack.enter_context(patch.object(G, 'checkpoint_metadata', return_value=cp()))
            free = stack.enter_context(patch.object(G, 'disk_free', return_value=20 * G.GIB))
            stack.enter_context(patch.object(G.time, 'time', return_value=110))
            guard = G.Guard(source)
            self.assertEqual(guard.tick()['state'], 'BOOTSTRAP_EVALUATION')
            self.assertFalse(G.PAUSE.exists())
            free.return_value = 1; guard.last_poll = None
            self.assertEqual(guard.tick()['state'], 'INHIBITED')
            self.assertTrue(G.PAUSE.read_bytes().startswith(b'NOX_QWEN_GUARD_PAUSE_V1'))


class MediaTests(unittest.TestCase):
    def test_revision_context_never_calls_historical_window_as_current(self):
        actions = M.Admission.__new__(M.Admission)
        actions.admission = REF; actions.execution_revision = REF; actions.historical_window = ORIGIN
        actions.resume_after_media = True
        actions.window = types.SimpleNamespace(context=Mock(side_effect=AssertionError('historical masquerade')),
                                               arguments=Mock(side_effect=AssertionError('old basename')))
        process = {'pid': 123, 'start_ticks': 456, 'ppid': 122, 'exact_admitted_argv': True,
                   'cuda_visible_devices_1': True, 'supervisor_ancestry_verified': True}
        current = types.SimpleNamespace(trainers=Mock(return_value=[process]))
        ctx = {'context': REF, 'origin': {'window_reference': ORIGIN}, 'profile': {'successful_updates_goal': 1000},
            'observer': current, 'contract': types.SimpleNamespace(canonical_sha=lambda _: 'd' * 64),
            'lineage': {}, 'execution': {}, 'admission': {'request': REF['request']},
            'argv': ['python', 'qwen_student_training_entry_revision.py']}
        verifier = types.SimpleNamespace(current_context=Mock(return_value=ctx), activation_status=Mock(return_value=pending()))
        actions.runtime = types.SimpleNamespace(service_state=Mock(return_value={'state': 'RUNNING', 'pid': 122}))
        with patch.object(M, 'revision_module', return_value=verifier):
            with self.assertRaisesRegex(M.QwenHold, 'WAIT_QWEN_EXECUTION_BOOTSTRAP'):
                actions.trainer_process()
            actions.runtime.service_state.assert_not_called()
            verifier.activation_status.return_value = {'active': True}
            result = actions.trainer_process()
            self.assertEqual(result['pid'], 123)
            self.assertEqual(current.trainers.call_args.args[0], ctx['argv'])
        actions.window.context.assert_not_called(); actions.window.arguments.assert_not_called()

    def test_reader_uses_execution_reference_and_pending_wait_is_preserved(self):
        config = {'enabled': True, 'resume_training_after_media': True, 'window_admission': ORIGIN, 'execution_revision': REF}
        reader = R.Reader.__new__(R.Reader)
        reader.handback = types.SimpleNamespace(configuration=lambda: config, actions=types.SimpleNamespace(admission=REF))
        reader.source_sha256 = 'e' * 64
        guard = types.SimpleNamespace(resume_block_reason=Mock(return_value='WAIT_QWEN_GUARD_EXECUTION_BOOTSTRAP'))
        reader.checked_guard = lambda: guard
        with self.assertRaisesRegex(R.GuardHold, 'WAIT_QWEN_GUARD_EXECUTION_BOOTSTRAP'):
            reader.admission()
        guard.resume_block_reason.assert_called_once_with(REF)
        guard.resume_block_reason.return_value = None
        result = reader.admission()
        self.assertEqual(result['window_admission'], ORIGIN); self.assertEqual(result['execution_revision'], REF)

    def test_retry_preserves_quality_hold_and_existing_bootstrap_wait(self):
        for reason in ('HOLD_QWEN_GUARD_HOLDOUT_REGRESSION', 'HOLD_QWEN_GUARD_DISK_EARLY_MARGIN',
                       'WAIT_QWEN_GUARD_EXECUTION_BOOTSTRAP'):
            def original():
                raise R.GuardHold(reason)
            with self.assertRaisesRegex(R.GuardHold, '^' + reason + '$'):
                T.guard_admission(original, R.GuardHold)()


class StatusCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        F.QwenObservationTests.setUpClass()

    def setUp(self):
        self.fx = F.QwenObservationTests(); self.fx.setUp(); self.addCleanup(self.fx.tearDown)
        self.scope = ExitStack(); self.addCleanup(self.scope.close)
        self.scope.enter_context(patch.object(V, 'OUTPUT', self.fx.output))
        self.obs = F.OBS
        for name in ('_revision_context', '_revision_verifier'):
            if hasattr(self.obs, name): delattr(self.obs, name)
            self.addCleanup(lambda key=name: self.obs.__dict__.pop(key, None))

    def prepare(self, *, revised):
        lineage, saved, manifest, _, directory = self.fx.fixture(good=25, skipped=0)
        lineage['tokenized_corpus'] = {'splits': [{'split': 'holdout', 'accepted_rows': 16}]}
        F.write(directory / 'lineage.json', lineage)
        lineage_sha = self.fx.contract.canonical_sha(lineage)
        self.scope.enter_context(patch.object(V, 'ORIGIN', {**V.ORIGIN, 'lineage_sha256': lineage_sha}))
        self.scope.enter_context(patch.object(S, 'BASELINE', {**S.BASELINE, 'adapter_tensor_sha256': F.sha(b'tensor5')}))
        saved['data_cursor'] = 200
        ctx = {'lineage': lineage, 'certificate': {'update_evidence': saved['update_evidence'][:6]},
               'contract': self.fx.contract, 'observer': self.obs, 'context': REF,
               'execution': {'reference': REF, 'descriptor_sha256': '1' * 64, 'admission_sha256': '2' * 64,
                             'runtime_entry_sha256': '3' * 64, 'verifier_sha256': VERIFIER_SHA}}
        if revised:
            binding = V.execution_binding(ctx)
            before = {'successful_total': 25, 'attempted_total': 25, 'skipped_total': 0,
                      'data_cursor': 200, 'optimizer_step': 25, **{key: 'a' * 64 for key in V.SIGNATURE_HASHES}}
            before['adapter_tensor_sha256'] = manifest['adapter_tensor_sha256']
            saved['execution_binding'] = binding
            saved['last_evaluation_witness'] = {'schema': V.WITNESS_SCHEMA, 'execution_binding': binding,
                'kind': 'BOOTSTRAP_RESTORE', 'process_identity': manifest['process_identity'],
                'evaluated_successful_total': 25, 'started_at': 1, 'finished_at': 2, 'holdout_examples': 16,
                'holdout_loss': saved['last_holdout_loss'], 'restored_checkpoint': {'directory': directory.name,
                    'manifest_sha256': 'b' * 64, 'student_state_sha256': 'c' * 64, 'successful_total': 25},
                'before': before, 'after': copy.deepcopy(before)}
            manifest['execution_binding'] = binding
        else:
            saved['holdout_evaluated_successful_total'] = 10
            manifest['holdout_evaluated_successful_total'] = 10
        F.write(directory / 'student_state.json', saved)
        (directory / 'README.md').write_bytes(b'synthetic public adapter card')
        manifest['lineage_sha256'] = lineage_sha
        manifest['files_sha256'] = {p.name: F.sha(p.read_bytes()) for p in directory.iterdir() if p.name != 'checkpoint_manifest.json'}
        pin = F.write(directory / 'checkpoint_manifest.json', manifest)
        if not revised:
            self.scope.enter_context(patch.object(V, 'ANCHOR', {**V.ANCHOR, 'directory': directory.name,
                'manifest_sha256': pin, 'student_state_sha256': manifest['files_sha256']['student_state.json']}))
        self.obs._revision_context, self.obs._revision_verifier = ctx, V
        return lineage, saved, manifest, directory, pin

    def test_pending_origin25_is_verified_saved_progress_not_new_execution(self):
        lineage, _, _, directory, pin = self.prepare(revised=False)
        with patch.object(V, 'activation_status', return_value=pending()):
            proof, _, _ = S.checkpoint(self.obs, self.fx.contract, lineage, directory.name, pin, time.monotonic() + 5)
        self.assertEqual(proof['successful_optimizer_steps'], 25)
        self.assertTrue(proof['historical_checkpoint_only'])
        self.assertFalse(proof['execution_revision_checkpoint_verified'])
        with patch.object(V, 'activation_status', return_value={'active': True}), self.assertRaisesRegex(V.Hold, 'LEGACY_CHECKPOINT_NOT_EXACT_ANCHOR'):
            S.checkpoint(self.obs, self.fx.contract, lineage, directory.name, pin, time.monotonic() + 5)

    def test_full_current_checkpoint_checks_execution_witness_and_optimizer_bytes(self):
        lineage, _, _, directory, pin = self.prepare(revised=True)
        with patch.object(V, 'activation_status', return_value=pending()):
            proof, _, _ = S.checkpoint(self.obs, self.fx.contract, lineage, directory.name, pin, time.monotonic() + 5)
            self.assertEqual(proof['checkpoint_file_count'], 10)
            self.assertTrue(proof['execution_revision_checkpoint_verified'])
            self.assertTrue(proof['evaluation_witness_verified'])
            (directory / 'optimizer.pt').write_bytes(b'foreign optimizer')
            with self.assertRaisesRegex(Exception, 'FILE_SHA'):
                S.checkpoint(self.obs, self.fx.contract, lineage, directory.name, pin, time.monotonic() + 5)

    def test_hash_valid_but_changed_evaluation_state_is_rejected(self):
        lineage, saved, manifest, directory, _ = self.prepare(revised=True)
        saved['last_evaluation_witness']['after']['data_cursor'] += 1
        manifest['files_sha256']['student_state.json'] = F.write(directory / 'student_state.json', saved)
        pin = F.write(directory / 'checkpoint_manifest.json', manifest)
        with patch.object(V, 'activation_status', return_value=pending()), self.assertRaisesRegex(V.Hold, 'EVALUATION_CHANGED_TRAINING_STATE'):
            S.checkpoint(self.obs, self.fx.contract, lineage, directory.name, pin, time.monotonic() + 5)


if __name__ == '__main__':
    unittest.main()
