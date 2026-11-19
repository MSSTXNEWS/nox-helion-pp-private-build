"""Exact after-exit flow with temp files and the frozen real full-SHA reader."""
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
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


p = load('after_exit_proof', HERE / 'owner_qwen_successor_checkpoint_proof_v2.py')
base = load('after_exit_existing_fixtures', HERE / 'test_owner_qwen_successor_checkpoint_proof.py')
s, core, contract, observer = base.s, base.core, base.contract, base.observer
guard = load('after_exit_real_guard', HERE / 'owner_qwen_successor_guard.py')
sha = base.fixtures.sha


class AfterExitTests(base.fixtures.Fixture):
    def write_checkpoint(self, name, state, process):
        for index, row in enumerate(state['update_evidence']):
            if 'step' in row:
                row.clear()
                row.update(optimizer_step_before=index, optimizer_step_after=index + 1,
                    adapter_sha_before=sha(str(index).encode()), adapter_sha_after=sha(str(index + 1).encode()),
                    amp_skipped=False, finite_gradients=True, loss=1.0,
                    training_example_sha256=[sha(('sample-%s-%s' % (index, j)).encode()) for j in range(8)])
        return super().write_checkpoint(name, state, process)

    def extra(self, obj, key, value):
        item = patch.object(obj, key, value); item.start(); self.patches.append(item)

    def setUp(self):
        super().setUp()
        self.ctx.update(context=self.ref, config_sha256='8' * 64, admission_sha256='d' * 64,
            wrapper_sha256='e' * 64, lineage_sha256=s.ORIGIN['lineage_sha256'], contract=contract,
            observer=types.SimpleNamespace(REQUIRED=s.REQUIRED, update_chain=observer.update_chain))
        self.ctx['execution'].update(runtime_entry_sha256=p.STUDENT_SHA, verifier_sha256=p.SHARED_SHA)
        self.desc['runtime_sources'].update({s.ENTRY: p.STUDENT_SHA, s.SELF: p.SHARED_SHA})
        self.desc.update(activation_issuer_sha256=p.INSTALLER_SHA, activation_watcher_sha256=p.WATCHER_SHA)
        self.desc['consumer_sources'][p.GUARD_NAME] = p.GUARD_SHA
        self.proc = self.root / 'proc'; (self.proc / 'sys/kernel/random').mkdir(parents=True)
        (self.proc / 'sys/kernel/random/boot_id').write_text(self.pid['boot_id'] + '\n')
        for obj, key, value in (
            (p, 'OWNER_UID', os.geteuid()), (p, 'ROOT', self.root), (p, 'STATE', s.STATE),
            (p, 'SCRIPTS', s.SCRIPTS), (p, 'PROC', self.proc), (p, 'EXPECTED_REFERENCE', self.ref),
            (p, 'EXPECTED_PROCESS', self.pid), (p, 'ANCHOR_SHA', s.ANCHOR['manifest_sha256']),
            (core, 'ROOT', self.root), (core, 'STATE', s.STATE), (core, 'OUTPUT', s.OUTPUT),
            (core, 'ORIGIN_LINEAGE', contract.canonical_sha(self.lineage)),
            (guard, 'ROOT', self.root), (guard, 'STATE', s.STATE), (guard, 'STATUS', s.GUARD_STATUS),
            (guard, 'CONFIG', s.GUARD_CONFIG)):
            self.extra(obj, key, value)
        self.extra(core, 'protected', Mock())
        self.extra(core, 'no_flags', Mock(side_effect=AssertionError('training no_flags must stay untouched')))
        self.dead = {'service': {'state': 'FATAL', 'pid': None}, 'process_identity': None}
        self.extra(core, 'trainer', Mock(return_value=self.dead))
        self.extra(p, 'native_modules', lambda: (core, s))
        self.extra(p, 'checked_context', Mock(return_value=self.ctx))
        self.extra(p, 'source', lambda path, pin: (HERE / 'owner_qwen_successor_guard.py').read_bytes())
        self.extra(p, 'load', lambda name, raw: guard)

        activation_manifest, activation_state, raw, state_raw = self.fresh()
        _, self.permit = self.activation(activation_manifest, activation_state, raw, state_raw)
        self.manifest, self.saved, _, _ = self.fresh(good=55, evaluated=55, kind='PERIODIC')
        self.saved['last_evaluation_witness'].update(started_at=self.now - .5, finished_at=self.now - .25)
        self.folder_current = s.OUTPUT / self.manifest['directory']
        (self.folder_current / 'adapter_model.safetensors').write_bytes(b'new-periodic-adapter')
        self.manifest['files_sha256']['adapter_model.safetensors'] = sha(b'new-periodic-adapter')
        self.seal()

        watcher_pid = dict(self.pid, pid=2024, start_ticks=19990)
        ready = {'schema': 'NOX_QWEN_SUCCESSOR_WATCHER_READY_V1', 'execution_revision': self.ref,
            'watcher_source_sha256': p.WATCHER_SHA, 'issuer_source_sha256': p.INSTALLER_SHA,
            'verifier_sha256': p.SHARED_SHA, 'start_capability': False,
            'process_identity': watcher_pid, 'armed_at': self.now - 15}
        self.private(self.folder / 'watcher_ready.json', s.encode(ready))
        start = {'schema': 'NOX_QWEN_SUCCESSOR_START_RECEIPT_V1', 'execution_revision': self.ref,
            'start_command_issued': True, 'start_command_returncode': 0,
            'trainer': {'service': {'state': 'RUNNING', 'pid': 2023}, 'process_identity': self.pid},
            'watcher_ready_sha256': sha(s.encode(ready)), 'started_at': self.now - 14, 'sampled_at': self.now - 13}
        self.private(self.folder / 'start_receipt.json', s.encode(start))
        result = {'schema': 'NOX_QWEN_SUCCESSOR_WATCHER_RESULT_V1', 'execution_revision': self.ref,
            'state': 'EXECUTION_REVISION_ACTIVE_FRESH_EVALUATION_VERIFIED', 'active': True,
            'optimizer_permission_issued': True, 'ordinary_guard_verified': True, 'finalizer_called_once': True,
            'watcher_source_sha256': p.WATCHER_SHA, 'process_identity': watcher_pid,
            'start_receipt_sha256': sha(s.encode(start)), 'finished_at': self.now - .75}
        self.private(self.folder / 'watcher_result.json', s.encode(result))
        self.extra(p, 'JOURNAL_PINS', {name: sha((self.folder / name).read_bytes()) for name in p.JOURNAL_PINS})

        self.config = {'source_sha256': p.GUARD_SHA, 'execution_revision': self.ref,
            'window_admission': dict(s.ORIGIN_WINDOW), 'policy': dict(s.GUARD_POLICY)}
        self.config_sha = sha(guard.encode(self.config))
        self.private(s.GUARD_CONFIG, guard.encode(self.config))
        self.extra(guard, 'checked_config', lambda **kwargs: (self.config, self.config_sha))
        quality = dict(p.EXPECTED_QUALITY, best_holdout_loss=1.0, latched_at=self.now - .1)
        self.extra(p, 'EXPECTED_QUALITY', quality)
        self.row = {'schema': guard.SCHEMA, 'bindings': guard.bindings(self.config, self.config_sha, self.ctx),
            'sampled_at': self.now, 'state': 'INHIBITED', 'policy_state': dict(quality),
            'checkpoint': {'manifest_sha256': self.expected['manifest_sha256'],
                'student_state_sha256': self.expected['student_state_sha256'], 'pointer_sha256': self.expected['pointer_sha256'],
                'successful_updates': 55, 'attempted_updates': 55, 'skipped_updates': 0,
                'evaluated_at_update': 55, 'holdout_loss': self.saved['last_holdout_loss']}}
        self.private(s.GUARD_STATUS, guard.encode(self.row))
        values = {'TRAIN_HOLD.flag': ('OWNER_QWEN_WINDOW_FAILED request=' + self.ref['request'] + ' goal=1000\n').encode(),
                  'TRAIN_PAUSE_REQUEST.flag': guard.pause_token(self.row)}
        for name, raw in values.items(): self.private(s.STATE / name, raw)
        self.extra(p, 'FLAG_PINS', {name: (sha(raw), len(raw)) for name, raw in values.items()})

    def seal(self):
        state_raw = s.encode(self.saved)
        (self.folder_current / 'student_state.json').write_bytes(state_raw)
        self.manifest['files_sha256']['student_state.json'] = sha(state_raw)
        self.raw = s.encode(self.manifest)
        (self.folder_current / 'checkpoint_manifest.json').write_bytes(self.raw)
        self.pointer_raw = s.encode({'directory': self.manifest['directory'], 'manifest_sha256': sha(self.raw)})
        self.private(s.OUTPUT / 'latest_checkpoint.json', self.pointer_raw)
        self.expected = {'directory': self.manifest['directory'], 'pointer_sha256': sha(self.pointer_raw),
            'manifest_sha256': sha(self.raw), 'student_state_sha256': sha(state_raw),
            'successful_total': 55, 'attempted_total': 55, 'skipped_total': 0, 'evaluated_successful_total': 55,
            'verified_bytes': sum((self.folder_current / n).stat().st_size for n in self.manifest['files_sha256'])}
        self.extra(p, 'EXPECTED_CHECKPOINT', self.expected)

    def run_observation(self):
        real_open = os.open
        def readonly(path, flags, *args, **kwargs):
            self.assertFalse(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            return real_open(path, flags, *args, **kwargs)
        with patch.object(os, 'open', side_effect=readonly): return p.observe()

    def test_full_real_reader_after_exit_verifies_saved_updates_without_resume_or_writes(self):
        before = {str(x.relative_to(self.root)): x.read_bytes() for x in self.root.rglob('*') if x.is_file()}
        with patch.object(core, 'full_checkpoint', wraps=core.full_checkpoint) as full:
            out = self.run_observation()
        self.assertEqual(full.call_count, 1)
        self.assertEqual(out['checkpoint']['verified_files'], 10)
        self.assertEqual(out['new_execution_optimizer_updates_verified'], 30)
        self.assertTrue(out['full_checkpoint_files_verified'])
        self.assertTrue(out['new_optimizer_updates_full_verified'])
        self.assertTrue(out['admitted_child_absent_before_after'])
        self.assertFalse(out['same_live_admitted_process_before_after'])
        for key in ('permission_to_resume', 'training_continuation_authorized', 'current_process_present',
                    'current_optimizer_permission_verified', 'public_base_ram_retention_observed'):
            self.assertIs(out[key], False)
        self.assertNotIn('training_example_sha256', json.dumps(out))
        self.assertNotIn('new-periodic-adapter', json.dumps(out))
        self.assertEqual(before, {str(x.relative_to(self.root)): x.read_bytes() for x in self.root.rglob('*') if x.is_file()})
        core.no_flags.assert_not_called()

    def test_guard_heartbeat_and_free_space_change_do_not_weaken_quality_latch(self):
        real_full = core.full_checkpoint
        def advance(*args, **kwargs):
            result = real_full(*args, **kwargs)
            row = copy.deepcopy(self.row); row['sampled_at'] = time.time()
            row['policy_state'].update(last_free_bytes=15_000_000_000, last_sample_at=time.time())
            self.private(s.GUARD_STATUS, guard.encode(row)); return result
        with patch.object(core, 'full_checkpoint', side_effect=advance): out = p.observe()
        self.assertTrue(out['quality_guard']['semantic_state_preserved'])
        self.assertNotEqual(out['quality_guard']['before_sha256'], out['quality_guard']['after_sha256'])
        self.assertFalse(out['permission_to_resume'])

    def test_child_reappearance_after_hash_is_not_historical_success(self):
        live = {'service': {'state': 'RUNNING', 'pid': 2023}, 'process_identity': self.pid}
        core.trainer.side_effect = [self.dead, live]
        with self.assertRaisesRegex(p.Hold, 'TRAINER_NOT_STABLY_EXITED'): p.observe()

    def test_old_pid_present_or_reused_and_unknown_service_stop_before_hash(self):
        with patch.object(core, 'full_checkpoint', wraps=core.full_checkpoint) as full:
            (self.proc / str(self.pid['pid'])).mkdir()
            with self.assertRaisesRegex(p.Hold, 'WRITER_PID_PRESENT_OR_REUSED'): p.observe()
            (self.proc / str(self.pid['pid'])).rmdir()
            for state in ('RUNNING', 'STARTING', 'BACKOFF', 'UNKNOWN', 'STOPPING'):
                core.trainer.return_value = {'service': {'state': state, 'pid': None}, 'process_identity': None}
                with self.assertRaisesRegex(p.Hold, 'TRAINER_NOT_STABLY_EXITED'): p.observe()
            self.assertEqual(full.call_count, 0)

    def test_each_flag_change_or_removal_during_hash_stops_without_success(self):
        real_full = core.full_checkpoint
        for name in p.FLAG_PINS:
            path = s.STATE / name; raw = path.read_bytes()
            for action in ('content', 'mode', 'remove', 'same_bytes_new_inode'):
                self.private(path, raw)
                def changed(*args, **kwargs):
                    if action == 'content': path.write_bytes(b'foreign')
                    elif action == 'mode': path.chmod(0o644)
                    elif action == 'remove': path.unlink()
                    else:
                        temp = path.with_suffix('.replacement'); self.private(temp, raw); os.replace(temp, path)
                    return real_full(*args, **kwargs)
                with self.subTest(name=name, action=action), patch.object(core, 'full_checkpoint', side_effect=changed):
                    with self.assertRaises((p.Hold, s.Hold, FileNotFoundError)): p.observe()
                self.private(path, raw)

    def test_global_owner_stop_remains_checked_inside_real_full_reader(self):
        real_full = core.full_checkpoint
        def stopped(*args, **kwargs):
            (self.root / 'STOP').write_bytes(b'owner'); return real_full(*args, **kwargs)
        with patch.object(core, 'full_checkpoint', side_effect=stopped):
            with self.assertRaisesRegex(RuntimeError, 'OWNER_STOP'): p.observe()

    def test_pointer_drift_after_full_hash_is_not_reported_success(self):
        real_full = core.full_checkpoint
        def changed(*args, **kwargs):
            result = real_full(*args, **kwargs)
            self.private(s.OUTPUT / 'latest_checkpoint.json', s.encode({'directory': s.ANCHOR['directory'],
                'manifest_sha256': s.ANCHOR['manifest_sha256']})); return result
        with patch.object(core, 'full_checkpoint', side_effect=changed):
            with self.assertRaisesRegex(p.Hold, 'FINAL_CHECKPOINT_CHANGED'): p.observe()

    def test_config_source_change_is_detected_by_final_context_gate(self):
        p.checked_context.side_effect = [self.ctx, s.Hold('HOLD_QWEN_REVISION_FILE_SHA')]
        with self.assertRaisesRegex(s.Hold, 'FILE_SHA'): p.observe()

    def test_wrong_immutable_start_or_missing_permit_stops_before_hash(self):
        with patch.object(core, 'full_checkpoint', wraps=core.full_checkpoint) as full:
            path = self.folder / 'start_receipt.json'; old = path.read_bytes()
            path.write_bytes(old + b' ')
            with self.assertRaisesRegex(p.Hold, 'PRIVATE_RECORD_CHANGED'): p.observe()
            self.private(path, old)
            (self.folder / 'activation.json').unlink()
            with self.assertRaisesRegex(p.Hold, 'ACTIVATION_REQUIRED'): p.observe()
            self.assertEqual(full.call_count, 0)

    def test_guard_unlatched_foreign_reference_stale_or_wrong_checkpoint_is_rejected(self):
        variants = [lambda r: r['policy_state'].update(inhibit=False),
            lambda r: r['policy_state'].update(reason='EVALUATION_STALE'),
            lambda r: r['bindings']['execution_revision'].update(request='999'),
            lambda r: r.update(sampled_at=time.time() - 31),
            lambda r: r['checkpoint'].update(manifest_sha256='e' * 64)]
        for change in variants:
            row = copy.deepcopy(self.row); change(row); self.private(s.GUARD_STATUS, guard.encode(row))
            with self.assertRaises((p.Hold, guard.GuardHold)): p.observe()

    def test_corrupt_optimizer_fails_real_payload_sha_without_deserialization(self):
        (self.folder_current / 'optimizer.pt').write_bytes(b'corrupt')
        self.expected['verified_bytes'] = sum((self.folder_current / n).stat().st_size for n in self.manifest['files_sha256'])
        with self.assertRaisesRegex(RuntimeError, 'CHECKPOINT_FULL_SHA'): p.observe()

    def test_exact_source_graph_context_is_preserved_independently_of_dead_process(self):
        function = load('after_exit_unpatched_source', HERE / 'owner_qwen_successor_checkpoint_proof_v2.py')
        with patch.object(function, 'EXPECTED_REFERENCE', self.ref), patch.object(function, 'ANCHOR_SHA', s.ANCHOR['manifest_sha256']), \
             patch.object(s, 'current_context', return_value=self.ctx):
            self.assertEqual(function.checked_context(core, s), self.ctx)
            self.desc['runtime_sources'][s.ENTRY] = 'e' * 64
            self.ctx['execution']['runtime_entry_sha256'] = 'e' * 64
            with self.assertRaisesRegex(function.Hold, 'CURRENT_GRAPH'): function.checked_context(core, s)


class ScopeTests(unittest.TestCase):
    def test_exact_native_pins_unchanged_core_and_readonly_scope(self):
        self.assertEqual(p.INSTALLER_SHA, sha((HERE / 'owner_qwen_successor_install_v2.py').read_bytes()))
        self.assertEqual(p.SHARED_SHA, sha((HERE / 'owner_qwen_execution_successor.py').read_bytes()))
        self.assertEqual(p.GUARD_SHA, sha((HERE / 'owner_qwen_successor_guard.py').read_bytes()))
        self.assertEqual(sha((HERE / 'owner_qwen_successor_checkpoint_proof.py').read_bytes()),
            'c0c8ab4bd8716535e13a6d8b8f192787b9c6af77d45fe7b3ca33e0ad38d4117b')
        raw = (HERE / 'owner_qwen_successor_checkpoint_proof_v2.py').read_text(); tree = ast.parse(raw)
        attrs = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertFalse(attrs & {'write_bytes', 'write_text', 'unlink', 'rename', 'replace', 'flock', 'tick',
            'finalize_same_process', 'start_dispatcher', 'stop_dispatcher', 'owned_pause', 'save', 'kill'})
        self.assertNotIn('core.no_flags(', raw)
        self.assertEqual(p.OUTER_SECONDS, 75); self.assertEqual(p.BYTE_BOUND, 1024 ** 3)
        self.assertEqual(p.EXPECTED_CHECKPOINT['successful_total'], 55)

    def test_deadline_and_private_error_never_claim_proof_or_resume(self):
        for error in (p.Deadline(), RuntimeError('private token/body/URL')):
            output = io.StringIO()
            with patch.object(p, 'observe', side_effect=error), redirect_stdout(output): self.assertEqual(p.main(), 2)
            self.assertNotIn('private token', output.getvalue())
            result = json.loads(output.getvalue().splitlines()[0].removeprefix(p.PREFIX))['verification']
            self.assertFalse(result['full_checkpoint_files_verified'])
            self.assertFalse(result['permission_to_resume'])
            self.assertFalse(result['training_continuation_authorized'])
            self.assertIn('NOX_MAINT_REPAIR_COMPLETE=false', output.getvalue())


if __name__ == '__main__': unittest.main()
