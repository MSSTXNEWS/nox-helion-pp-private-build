"""Focused synthetic files; actual frozen full reader, no native/model call."""
import ast
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import time
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch


HERE = Path(__file__).parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p = load('successor_full_proof_test_module', HERE / 'owner_qwen_successor_checkpoint_proof.py')
fixtures = load('successor_full_proof_fixtures', HERE / 'test_owner_qwen_execution_successor.py')
s = fixtures.m
core = load('successor_full_proof_real_issuer', HERE / 'owner_qwen_successor_install_v2.py')
observer = load('successor_full_proof_real_chain', HERE / 'owner_qwen_training_observe.py')
CONTRACT_PATH = HERE / 'pinned/qwen_original_v1/owner_qwen_training_contract.py'
assert hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest() == s.ORIGINAL_SOURCES['owner_qwen_training_contract.py']
contract = load('successor_full_proof_real_contract', CONTRACT_PATH)


class ProofTests(fixtures.Fixture):
    def write_checkpoint(self, name, state, process):
        for index, row in enumerate(state['update_evidence']):
            if 'step' in row:
                row.clear()
                row.update(optimizer_step_before=index, optimizer_step_after=index + 1,
                    adapter_sha_before=fixtures.sha(str(index).encode()),
                    adapter_sha_after=fixtures.sha(str(index + 1).encode()),
                    amp_skipped=False, finite_gradients=True, loss=1.0,
                    training_example_sha256=[fixtures.sha(('sample-%s-%s' % (index, j)).encode()) for j in range(8)])
        return super().write_checkpoint(name, state, process)

    def setUp(self):
        super().setUp()
        self.ctx['context'] = self.ref
        self.ctx['config_sha256'] = '8' * 64
        self.ctx['execution']['runtime_entry_sha256'] = p.STUDENT_SHA
        self.ctx['execution']['verifier_sha256'] = p.SHARED_SHA
        self.desc['runtime_sources'][s.ENTRY] = p.STUDENT_SHA
        self.desc['runtime_sources'][s.SELF] = p.SHARED_SHA
        self.desc['activation_issuer_sha256'] = p.INSTALLER_SHA
        self.ctx['contract'] = contract
        self.ctx['observer'] = types.SimpleNamespace(REQUIRED=s.REQUIRED, update_chain=observer.update_chain)
        self.live = {'service': {'state': 'RUNNING', 'pid': self.pid['pid'] - 1}, 'process_identity': self.pid}
        for obj, key, value in ((p, 'OWNER_UID', os.geteuid()), (p, 'ANCHOR_SHA', s.ANCHOR['manifest_sha256']),
                (core, 'OUTPUT', s.OUTPUT), (core, 'ORIGIN_LINEAGE', contract.canonical_sha(self.lineage))):
            self.extra_patch(obj, key, value)
        self.extra_patch(core, 'no_flags', Mock())
        self.extra_patch(core, 'trainer', Mock(return_value=self.live))
        self.extra_patch(p, 'native_modules', lambda: (core, s))
        self.extra_patch(p, 'checked_context', Mock(return_value=self.ctx))
        # The initial same-counter permit is real shared-schema metadata. Its
        # payload is not reread by the observation, exactly as in production.
        activation_manifest, activation_state, raw, state_raw = self.fresh()
        self.activation(activation_manifest, activation_state, raw, state_raw)
        self.manifest, self.saved, self.raw, self.state_raw = self.fresh(good=30)
        self.folder_current = s.OUTPUT / self.manifest['directory']
        (self.folder_current / 'adapter_model.safetensors').write_bytes(b'new-adapter-payload')
        self.manifest['files_sha256']['adapter_model.safetensors'] = fixtures.sha(b'new-adapter-payload')
        self.seal()

    def extra_patch(self, obj, key, value):
        item = patch.object(obj, key, value); item.start(); self.patches.append(item)

    def seal(self):
        self.raw = s.encode(self.manifest)
        (self.folder_current / 'checkpoint_manifest.json').write_bytes(self.raw)
        self.private(s.OUTPUT / 'latest_checkpoint.json', s.encode({
            'directory': self.manifest['directory'], 'manifest_sha256': fixtures.sha(self.raw)}))

    def run_observation(self):
        original_open = os.open

        def read_only_open(path, flags, *args, **kwargs):
            self.assertFalse(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            return original_open(path, flags, *args, **kwargs)

        with patch.object(os, 'open', side_effect=read_only_open):
            return p.observe()

    def test_real_full_reader_binds_ten_files_and_current_execution_without_writes(self):
        before = {str(x.relative_to(self.root)): x.read_bytes() for x in self.root.rglob('*') if x.is_file()}
        with patch.object(core, 'full_checkpoint', wraps=core.full_checkpoint) as full:
            result = self.run_observation()
        self.assertEqual(full.call_count, 1)
        self.assertEqual(result['checkpoint']['verified_files'], 10)
        self.assertEqual(result['checkpoint']['verified_bytes'], sum((self.folder_current / n).stat().st_size
            for n in self.manifest['files_sha256']))
        self.assertTrue(result['new_optimizer_updates_full_verified'])
        self.assertEqual(result['new_execution_optimizer_updates_verified'], 5)
        self.assertTrue(result['same_live_admitted_process_before_after'])
        self.assertFalse(result['tensor_hashes_recomputed_by_observer'])
        self.assertFalse(result['evaluation']['periodic_evaluation_after25_verified'])
        self.assertFalse(result['anchor']['payload_rehashed_this_observation'])
        self.assertNotIn('training_example_sha256', json.dumps(result))
        self.assertNotIn('new-adapter-payload', json.dumps(result))
        self.assertEqual(before, {str(x.relative_to(self.root)): x.read_bytes() for x in self.root.rglob('*') if x.is_file()})

    def test_retained_or_same_counter_checkpoint_cannot_claim_new_updates(self):
        with patch.object(core, 'full_checkpoint', wraps=core.full_checkpoint) as full:
            for manifest, raw in ((self.predecessor_manifest, s.encode(self.predecessor_manifest)),
                                  (self.fresh()[0], self.fresh()[2])):
                self.private(s.OUTPUT / 'latest_checkpoint.json', s.encode({
                    'directory': manifest['directory'], 'manifest_sha256': fixtures.sha(raw)}))
                with self.assertRaisesRegex((s.Hold, p.Hold), 'CHECKPOINT_EXECUTION_BINDING|NEW_CURRENT_CHECKPOINT_REQUIRED'):
                    p.observe()
            self.assertEqual(full.call_count, 0)

    def test_missing_activation_or_dead_trainer_stops_before_payload_hash(self):
        with patch.object(core, 'full_checkpoint', wraps=core.full_checkpoint) as full:
            with patch.object(s, 'activation_status', return_value={'active': False}):
                with self.assertRaisesRegex(p.Hold, 'ACTIVATION_REQUIRED'):
                    p.observe()
            with patch.object(core, 'trainer', return_value={'service': {'state': 'FATAL', 'pid': None}, 'process_identity': None}):
                with self.assertRaisesRegex(p.Hold, 'LIVE_PROCESS'):
                    p.observe()
            self.assertEqual(full.call_count, 0)

    def test_corrupt_optimizer_payload_is_rejected_by_actual_core_full_sha(self):
        (self.folder_current / 'optimizer.pt').write_bytes(b'corrupt-optimizer')
        with self.assertRaisesRegex(RuntimeError, 'CHECKPOINT_FULL_SHA'):
            self.run_observation()

    def test_initial_prefix_or_adapter_no_change_cannot_be_promoted(self):
        self.saved['update_evidence'][8]['loss'] = 0.9  # valid row, changed historical prefix
        raw = s.encode(self.saved)
        (self.folder_current / 'student_state.json').write_bytes(raw)
        self.manifest['files_sha256']['student_state.json'] = fixtures.sha(raw); self.seal()
        with self.assertRaisesRegex(p.Hold, 'PREFIX_CHANGED'):
            p.observe()
        self.saved['update_evidence'][8]['loss'] = 1.0
        raw = s.encode(self.saved)
        (self.folder_current / 'student_state.json').write_bytes(raw)
        self.manifest['files_sha256']['student_state.json'] = fixtures.sha(raw)
        self.manifest['files_sha256']['adapter_model.safetensors'] = self.predecessor_manifest['files_sha256']['adapter_model.safetensors']
        self.seal()
        with self.assertRaisesRegex(p.Hold, 'ADAPTER_UNCHANGED'):
            p.observe()

    def test_completed_hash_does_not_hide_pointer_pid_boot_or_permission_races(self):
        full = core.full_checkpoint

        def changed_pointer(*args, **kwargs):
            result = full(*args, **kwargs)
            self.private(s.OUTPUT / 'latest_checkpoint.json', s.encode({'directory': s.ANCHOR['directory'],
                'manifest_sha256': s.ANCHOR['manifest_sha256']}))
            return result

        with patch.object(core, 'full_checkpoint', side_effect=changed_pointer):
            with self.assertRaisesRegex(p.Hold, 'FINAL_CHECKPOINT_CHANGED'):
                p.observe()
        self.seal()
        for delta in ({'pid': self.pid['pid'] + 1}, {'start_ticks': self.pid['start_ticks'] + 1}, {'boot_id': 'b' * 36}):
            changed = dict(self.live, process_identity=dict(self.pid, **delta))
            with patch.object(core, 'trainer', side_effect=[self.live, changed]):
                with self.assertRaisesRegex(p.Hold, 'PROCESS_CHANGED'):
                    p.observe()
        initial = s.activation_status(self.ctx)
        with patch.object(s, 'activation_status', side_effect=[initial, dict(initial, permit_sha256='b' * 64)]):
            with self.assertRaisesRegex(p.Hold, 'PERMISSION_CHANGED'):
                p.observe()

    def test_full_reader_bound_and_stop_do_not_produce_partial_success(self):
        with patch.object(core, 'GIB', 100):
            with self.assertRaisesRegex(RuntimeError, 'CHECKPOINT_FILE_OWNER|CHECKPOINT_BYTE_BOUND'):
                p.observe()
        core.no_flags.side_effect = RuntimeError('HOLD_FIXTURE_STOP')
        with self.assertRaisesRegex(RuntimeError, 'HOLD_FIXTURE_STOP'):
            p.observe()

    def test_real_periodic_witness_is_reported_separately_from_saved_updates(self):
        self.manifest, self.saved, _, _ = self.fresh(good=35, evaluated=35, kind='PERIODIC')
        self.folder_current = s.OUTPUT / self.manifest['directory']
        (self.folder_current / 'adapter_model.safetensors').write_bytes(b'new-periodic-adapter')
        self.manifest['files_sha256']['adapter_model.safetensors'] = fixtures.sha(b'new-periodic-adapter')
        self.seal()
        result = p.observe()
        self.assertTrue(result['evaluation']['periodic_evaluation_after25_verified'])
        self.assertEqual(result['evaluation']['evaluated_successful_total'], 35)
        self.assertEqual(result['new_execution_optimizer_updates_verified'], 10)


class ScopeTests(unittest.TestCase):
    def test_sources_are_exact_and_no_native_action_or_pickle_model_calls_exist(self):
        self.assertEqual(p.INSTALLER_SHA, hashlib.sha256((HERE / 'owner_qwen_successor_install_v2.py').read_bytes()).hexdigest())
        self.assertEqual(p.SHARED_SHA, hashlib.sha256((HERE / 'owner_qwen_execution_successor.py').read_bytes()).hexdigest())
        raw = (HERE / 'owner_qwen_successor_checkpoint_proof.py').read_text()
        tree = ast.parse(raw)
        attrs = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertFalse(attrs & {'write_bytes', 'write_text', 'unlink', 'rename', 'replace', 'flock', 'tick',
            'finalize_same_process', 'start_dispatcher', 'stop_dispatcher', 'owned_pause', 'loads', 'save'})
        self.assertNotIn('torch', raw)
        self.assertNotIn('pickle', raw)
        self.assertEqual(p.OUTER_SECONDS, 75)
        self.assertEqual(p.BYTE_BOUND, 1024 ** 3)

    def test_deadline_or_unverified_error_emits_no_success_or_sensitive_text(self):
        for failure in (p.Deadline(), RuntimeError('private URL/token/content')):
            output = io.StringIO()
            with patch.object(p, 'observe', side_effect=failure), redirect_stdout(output):
                self.assertEqual(p.main(), 2)
            text = output.getvalue()
            self.assertIn('NOX_MAINT_REPAIR_COMPLETE=false', text)
            self.assertNotIn('private URL', text)
            value = json.loads(text.splitlines()[0].removeprefix(p.PREFIX))['verification']
            self.assertFalse(value['full_checkpoint_files_verified'])
            self.assertFalse(value['new_optimizer_updates_full_verified'])


if __name__ == '__main__':
    unittest.main()
