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
from unittest.mock import patch

PATH = Path(__file__).with_name('owner_qwen_execution_revision.py')
spec = importlib.util.spec_from_file_location('revision_under_test', PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def hash_of(value):
    return hashlib.sha256(value).hexdigest()


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        values = {'ROOT': self.root, 'STATE': self.root / 'state', 'SCRIPTS': self.root / 'scripts',
            'OUTPUT': self.root / 'output', 'AREA': self.root / 'state/revisions',
            'CONFIG': self.root / 'config/revision.json', 'ADMISSION': self.root / 'state/admission.json',
            'WRAPPER': self.root / 'scripts/wrapper.sh', 'GUARD_CONFIG': self.root / 'config/guard.json',
            'GUARD_STATUS': self.root / 'state/guard.json', 'OWNER_UID': os.geteuid()}
        self.patches = [patch.object(m, key, value) for key, value in values.items()]
        for item in self.patches:
            item.start()
        for key in ('STATE', 'SCRIPTS', 'OUTPUT', 'AREA'):
            getattr(m, key).mkdir(parents=True, exist_ok=True)
        self.ref = {'request': '80001', 'source_sha': 'a' * 40, 'receipt_sha256': 'b' * 64}
        self.pid = {'pid': 1234, 'start_ticks': 555, 'boot_id': 'a' * 8 + '-' + 'b' * 4 + '-' + 'c' * 4 + '-' + 'd' * 4 + '-' + 'e' * 12}
        self.lineage = {'schema': 'fixture', 'entry_sha256': m.ORIGIN['previous_entry_sha256'],
            'contract_sha256': m.ORIGINAL_SOURCES['owner_qwen_training_contract.py'],
            'memfd_source_sha256': m.ORIGINAL_SOURCES['owner_qwen_memfd.py'], 'scientific': {'lr': 5e-5},
            'tokenized_corpus': {'splits': [{'split': 'holdout', 'accepted_rows': 16}]}}
        self.old_state = {'successful_total': 25, 'attempted_total': 25, 'skipped_total': 0,
            'data_cursor': 200, 'initial_holdout_loss': 1.5, 'last_holdout_loss': 1.3,
            'holdout_evaluated_successful_total': 10,
            'update_evidence': [{'step': i, 'adapter_sha_after': hash_of(str(i).encode())} for i in range(1, 26)]}
        self.adapter = self.old_state['update_evidence'][-1]['adapter_sha_after']
        old_manifest, old_raw, old_state_raw = self.write_checkpoint(m.ANCHOR['directory'], self.old_state)
        anchor = dict(m.ANCHOR, manifest_sha256=hash_of(old_raw), student_state_sha256=hash_of(old_state_raw))
        self.anchor_patch = patch.object(m, 'ANCHOR', anchor)
        self.anchor_patch.start()
        self.desc = self.descriptor()
        self.ctx = {'execution': {'reference': self.ref, 'descriptor': self.desc,
            'descriptor_sha256': 'c' * 64, 'admission_sha256': 'd' * 64, 'wrapper_sha256': 'e' * 64,
            'runtime_entry_sha256': 'f' * 64, 'verifier_sha256': '1' * 64,
            'directory': m.AREA / self.ref['request']}, 'lineage': self.lineage,
            'certificate': {'update_evidence': self.old_state['update_evidence'][:6]},
            'observer': types.SimpleNamespace(update_chain=self.update_chain),
            'contract': types.SimpleNamespace(), 'raw': b'admission', 'wrapper': b'wrapper', 'output': m.OUTPUT}
        self.ctx['execution']['directory'].mkdir(parents=True)
        self.manifest = old_manifest

    def tearDown(self):
        self.anchor_patch.stop()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    @staticmethod
    def update_chain(state, contract):
        if len(state['update_evidence']) != state['successful_total']:
            raise m.Hold('HOLD_FIXTURE_CHAIN')
        return {'adapter_tensor_sha256': state['update_evidence'][-1]['adapter_sha_after']}

    def descriptor(self):
        now = time.time()
        return {'schema': m.DESCRIPTOR_SCHEMA, 'request': self.ref['request'], 'source_sha': self.ref['source_sha'],
            'created_at': now - 10, 'origin': copy.deepcopy(m.ORIGIN), 'runtime_sources': {m.ENTRY: 'f' * 64, m.SELF: '1' * 64},
            'consumer_sources': {name: '2' * 64 for name in m.CONSUMERS}, 'activation_issuer_sha256': '3' * 64,
            'anchor': dict(m.ANCHOR), 'scheduler': dict(m.SCHEDULER),
            'bootstrap': {'expires_at': now + 500, 'hold_sha256': m.OLD_HOLD_SHA, 'pause_sha256': m.OLD_PAUSE_SHA}}

    def write_checkpoint(self, name, state):
        folder = m.OUTPUT / name
        folder.mkdir(parents=True, exist_ok=True)
        files = {}
        for filename in m.REQUIRED | {'README.md'}:
            raw = m.encode(state) if filename == 'student_state.json' else m.encode(self.lineage) if filename == 'lineage.json' else b'opaque-payload'
            (folder / filename).write_bytes(raw)
            files[filename] = hash_of(raw)
        manifest = {'schema': 'NOX_QWEN35_9B_CHECKPOINT_V1', 'directory': name,
            'lineage_sha256': m.ORIGIN['lineage_sha256'], 'files_sha256': files,
            'successful_total': state['successful_total'], 'attempted_total': state['attempted_total'],
            'holdout_evaluated_successful_total': state['holdout_evaluated_successful_total'],
            'holdout_loss': state['last_holdout_loss'], 'adapter_tensor_sha256': state['update_evidence'][-1]['adapter_sha_after'],
            'process_identity': self.pid}
        if 'execution_binding' in state:
            manifest['execution_binding'] = state['execution_binding']
        raw = m.encode(manifest)
        (folder / 'checkpoint_manifest.json').write_bytes(raw)
        return manifest, raw, (folder / 'student_state.json').read_bytes()

    def witness(self, *, good=25, kind='BOOTSTRAP_RESTORE'):
        signature = {'successful_total': good, 'attempted_total': good, 'skipped_total': 0,
            'data_cursor': good * 8, 'optimizer_step': good, 'adapter_tensor_sha256': hash_of(str(good).encode()),
            'optimizer_state_sha256': '4' * 64, 'scheduler_state_sha256': '5' * 64,
            'scaler_state_sha256': '6' * 64, 'rng_state_sha256': '7' * 64}
        return {'schema': m.WITNESS_SCHEMA, 'execution_binding': m.execution_binding(self.ctx), 'kind': kind,
            'process_identity': self.pid, 'evaluated_successful_total': good, 'started_at': time.time() - 3,
            'finished_at': time.time() - 2, 'holdout_examples': 16, 'holdout_loss': 1.2,
            'restored_checkpoint': {key: m.ANCHOR[key] for key in ('directory', 'manifest_sha256', 'student_state_sha256', 'successful_total')},
            'before': signature, 'after': dict(signature)}

    def new_checkpoint(self, *, good=25, evaluated=25, kind='BOOTSTRAP_RESTORE'):
        state = copy.deepcopy(self.old_state)
        state.update(successful_total=good, attempted_total=good, data_cursor=good * 8,
            update_evidence=[{'step': i, 'adapter_sha_after': hash_of(str(i).encode())} for i in range(1, good + 1)],
            holdout_evaluated_successful_total=evaluated, last_holdout_loss=1.2,
            execution_binding=m.execution_binding(self.ctx), last_evaluation_witness=self.witness(good=evaluated, kind=kind))
        name = 'checkpoint-u%08d-a%08d-g%020d' % (good, good, 999)
        manifest, raw, state_raw = self.write_checkpoint(name, state)
        return manifest, state, raw, state_raw

    def activation(self, manifest, state, raw, state_raw):
        value = {'schema': m.ACTIVATION_SCHEMA, 'state': 'FRESH_EVALUATION_ACCEPTED_OPTIMIZER_ADMITTED',
            'execution_binding': m.execution_binding(self.ctx), 'issuer_source_sha256': self.desc['activation_issuer_sha256'],
            'issued_at': time.time() - 1, 'initial_process_identity': self.pid,
            'checkpoint': {'directory': manifest['directory'], 'manifest_sha256': hash_of(raw),
                'student_state_sha256': hash_of(state_raw), 'verified_files': 10,
                'verified_bytes': 520000000, 'full_files_sha256_verified': True},
            'evaluation_witness': state['last_evaluation_witness'], 'preserved_guard_policy_sha256': '8' * 64,
            'guard_state_sha256': '9' * 64, 'previous_flags_archived': True}
        path = self.ctx['execution']['directory'] / 'activation.json'
        path.write_bytes(m.encode(value)); path.chmod(0o600)
        return path, value


class ProvenanceTests(Fixture):
    def test_descriptor_rejects_old_anchor_policy_change_and_unknown_consumer(self):
        self.assertEqual(m.descriptor(self.desc), self.desc)
        for mutate in (lambda v: v['anchor'].update(successful_total=10),
                       lambda v: v['scheduler'].update(guard_update_gap=20),
                       lambda v: v['consumer_sources'].update({'foreign.py': 'a' * 64})):
            changed = copy.deepcopy(self.desc); mutate(changed)
            with self.assertRaises(m.Hold): m.descriptor(changed)

    def test_admission_adds_explicit_revision_without_rewriting_original_source_map(self):
        old_sources = {str(m.SCRIPTS / name): pin for name, pin in m.ORIGINAL_SOURCES.items() if name.endswith('.py')}
        previous = {'request': m.ORIGIN_WINDOW['request'], 'source_sha': m.ORIGIN_WINDOW['source_sha'],
            'student_profile': {'successful_updates_goal': 1000}, 'sources': old_sources,
            'initial_request': '6907283384', 'accepted_previous_window': 'accepted6'}
        old = copy.deepcopy(previous)
        new = m.make_admission(previous, self.desc, 'a' * 64, time.time())
        self.assertEqual(previous, old)
        self.assertEqual(new['student_profile'], previous['student_profile'])
        self.assertEqual(new['sources'][str(m.SCRIPTS / 'qwen_student_training_entry.py')], m.ORIGIN['previous_entry_sha256'])
        self.assertEqual(new['sources'][str(m.SCRIPTS / m.ENTRY)], self.desc['runtime_sources'][m.ENTRY])
        self.assertEqual(new['execution_revision']['descriptor_sha256'], 'a' * 64)

    def test_origin_resolution_allows_only_explicit_entry_revision(self):
        recomputed = copy.deepcopy(self.lineage); recomputed['entry_sha256'] = 'f' * 64
        self.assertEqual(m.resolve_origin_lineage(recomputed, self.ctx), self.lineage)
        recomputed['scientific']['lr'] = 1.0
        with self.assertRaises(m.Hold): m.resolve_origin_lineage(recomputed, self.ctx)

    def test_private_files_reject_symlinks_modes_and_byte_drift(self):
        path = self.root / 'private.json'; path.write_bytes(b'{}'); path.chmod(0o600)
        self.assertEqual(m.read(path, expected=hash_of(b'{}'), private=True), b'{}')
        path.chmod(0o644)
        with self.assertRaises(m.Hold): m.read(path, private=True)
        link = self.root / 'link'; link.symlink_to(path)
        with self.assertRaises(m.Hold): m.read(link)
        with self.assertRaises(m.Hold): m.read(path, expected='a' * 64)

    def test_duplicate_json_keys_and_nan_are_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}'):
            with self.assertRaises(m.Hold): m.parse(raw)


class CheckpointTests(Fixture):
    def test_only_exact_old25_is_allowed_without_execution_witness(self):
        with self.assertRaises(m.Hold): m.checkpoint_binding(self.ctx, self.manifest, self.old_state)
        proof = m.checkpoint_binding(self.ctx, self.manifest, self.old_state, allow_initial_anchor=True)
        self.assertTrue(proof['legacy_anchor']); self.assertFalse(proof['full_tensor_files_verified'])
        changed = copy.deepcopy(self.old_state); changed['data_cursor'] += 1
        manifest, _, _ = self.write_checkpoint(m.ANCHOR['directory'], changed)
        with self.assertRaises(m.Hold): m.checkpoint_binding(self.ctx, manifest, changed, allow_initial_anchor=True)

    def test_bootstrap_samecounter_proof_preserves_all_update_history(self):
        manifest, state, _, _ = self.new_checkpoint()
        result = m.bootstrap_evaluation_proof(self.ctx, manifest, state)
        self.assertTrue(result['verified']); self.assertEqual(result['optimizer_updates_during_bootstrap'], 0)
        self.assertFalse(result['full_tensor_files_verified'])
        state['update_evidence'][9]['adapter_sha_after'] = 'e' * 64
        manifest, _, _ = self.write_checkpoint(manifest['directory'], state)
        with self.assertRaises(m.Hold): m.bootstrap_evaluation_proof(self.ctx, manifest, state)

    def test_later_checkpoint_may_retain_an_earlier_real_evaluation(self):
        manifest, state, _, _ = self.new_checkpoint(good=30, evaluated=25)
        proof = m.checkpoint_binding(self.ctx, manifest, state)
        self.assertEqual(proof['successful_total'], 30)
        self.assertEqual(proof['evaluated_successful_total'], 25)
        with self.assertRaises(m.Hold): m.bootstrap_evaluation_proof(self.ctx, manifest, state)

    def test_missing_witness_false_evaluation_or_mutated_rng_rejected(self):
        for mutate in (lambda s: s.pop('last_evaluation_witness'),
                       lambda s: s['last_evaluation_witness'].update(evaluated_successful_total=30),
                       lambda s: s['last_evaluation_witness']['after'].update(rng_state_sha256='0' * 64)):
            manifest, state, _, _ = self.new_checkpoint()
            mutate(state); manifest, _, _ = self.write_checkpoint(manifest['directory'], state)
            with self.assertRaises(m.Hold): m.checkpoint_binding(self.ctx, manifest, state)

    def test_on_disk_state_must_match_the_supplied_verified_object(self):
        manifest, state, _, _ = self.new_checkpoint()
        (m.OUTPUT / manifest['directory'] / 'student_state.json').write_bytes(b'{}')
        with self.assertRaises(m.Hold): m.checkpoint_binding(self.ctx, manifest, state)

    def test_evaluation_is_bound_to_the_actual_evaluated_adapter(self):
        manifest, state, _, _ = self.new_checkpoint(good=30, evaluated=25)
        state['last_evaluation_witness']['before']['adapter_tensor_sha256'] = 'e' * 64
        state['last_evaluation_witness']['after']['adapter_tensor_sha256'] = 'e' * 64
        manifest, _, _ = self.write_checkpoint(manifest['directory'], state)
        with self.assertRaises(m.Hold): m.checkpoint_binding(self.ctx, manifest, state)

    def test_amp_skips_after_evaluation_preserve_checkpoint_but_not_fresh_resume_gate(self):
        manifest, state, _, _ = self.new_checkpoint()
        state['attempted_total'] += 1; state['skipped_total'] += 1
        manifest, _, _ = self.write_checkpoint(manifest['directory'], state)
        self.assertTrue(m.checkpoint_binding(self.ctx, manifest, state)['verified'])
        with patch.object(m, '_self_process_identity', return_value=self.pid):
            with self.assertRaises(m.Hold): m.wait_for_optimizer_permission(self.ctx, manifest, state, timeout=1)


class PermissionTests(Fixture):
    def test_missing_permit_is_pending_then_expired_not_permission(self):
        self.assertTrue(m.activation_status(self.ctx)['bootstrap_pending'])
        self.ctx['execution']['descriptor']['bootstrap']['expires_at'] = time.time() - 1
        value = m.activation_status(self.ctx)
        self.assertFalse(value['active']); self.assertFalse(value['bootstrap_pending'])

    def test_activation_is_an_immutable_metadata_anchor_not_live_process_proof(self):
        manifest, state, raw, state_raw = self.new_checkpoint()
        path, value = self.activation(manifest, state, raw, state_raw)
        active = m.activation_status(self.ctx)
        self.assertTrue(active['active']); self.assertEqual(active['initial_process_identity'], self.pid)
        value['initial_process_identity'] = dict(value['initial_process_identity'], pid=9999)
        path.write_bytes(m.encode(value))
        with self.assertRaises(m.Hold): m.activation_status(self.ctx)

    def test_runtime_requires_both_activation_and_fresh_guard(self):
        manifest, state, raw, state_raw = self.new_checkpoint()
        self.activation(manifest, state, raw, state_raw)
        m.ADMISSION.write_bytes(self.ctx['raw']); m.WRAPPER.write_bytes(self.ctx['wrapper'])
        (m.OUTPUT / 'latest_checkpoint.json').write_bytes(m.encode({'directory': manifest['directory'], 'manifest_sha256': hash_of(raw)}))
        with patch.object(m, '_self_process_identity', return_value=self.pid), patch.object(m, '_guard_permission',
            side_effect=[m.Hold('HOLD_QWEN_REVISION_GUARD_NOT_PERMISSIVE'), 'g' * 64]) as guard, patch.object(m.time, 'sleep'):
            result = m.wait_for_optimizer_permission(self.ctx, manifest, state, timeout=1)
        self.assertEqual(guard.call_count, 2)
        self.assertIs(result['optimizer_allowed'], True)
        self.assertEqual(result['state'], 'OPTIMIZER_PERMISSION_VERIFIED')

    def test_foreign_pause_stops_wait_without_clearing_it(self):
        manifest, state, _, _ = self.new_checkpoint()
        flag = m.STATE / 'TRAIN_PAUSE_REQUEST.flag'; flag.write_bytes(b'foreign')
        with patch.object(m, '_self_process_identity', return_value=self.pid):
            with self.assertRaises(m.Hold): m.wait_for_optimizer_permission(self.ctx, manifest, state, timeout=1)
        self.assertEqual(flag.read_bytes(), b'foreign')

    def test_later_resume_does_not_reuse_initial_pid_as_current_identity(self):
        initial, initial_state, raw, state_raw = self.new_checkpoint()
        self.activation(initial, initial_state, raw, state_raw)
        self.pid = dict(self.pid, pid=2222, start_ticks=777)
        resumed, state, raw, _ = self.new_checkpoint(good=30, evaluated=30, kind='RESUME_RESTORE')
        m.ADMISSION.write_bytes(self.ctx['raw']); m.WRAPPER.write_bytes(self.ctx['wrapper'])
        (m.OUTPUT / 'latest_checkpoint.json').write_bytes(m.encode({'directory': resumed['directory'], 'manifest_sha256': hash_of(raw)}))
        with patch.object(m, '_self_process_identity', return_value=self.pid), patch.object(m, '_guard_permission', return_value='a' * 64):
            result = m.wait_for_optimizer_permission(self.ctx, resumed, state, timeout=1)
        self.assertEqual(result['process_identity']['pid'], 2222)
        self.assertTrue(result['optimizer_allowed'])


class CurrentContextTests(Fixture):
    def prepare_context(self):
        self.original_pins = {}
        for name in m.ORIGINAL_SOURCES:
            raw = ('immutable fixture ' + name).encode()
            (m.SCRIPTS / name).write_bytes(raw)
            self.original_pins[name] = hash_of(raw)
        for name in (m.ENTRY, m.SELF, *m.CONSUMERS, 'owner_qwen_revision_install.py'):
            (m.SCRIPTS / name).write_bytes(('approved source ' + name).encode())
        desc = self.descriptor()
        desc['runtime_sources'] = {name: hash_of((m.SCRIPTS / name).read_bytes()) for name in (m.ENTRY, m.SELF)}
        desc['consumer_sources'] = {name: hash_of((m.SCRIPTS / name).read_bytes()) for name in m.CONSUMERS}
        desc['activation_issuer_sha256'] = hash_of((m.SCRIPTS / 'owner_qwen_revision_install.py').read_bytes())
        profile = {'successful_updates_goal': 1000, 'base_directory': str(m.STATE / 'qwen_memfd'),
            'output_directory': str(m.OUTPUT), 'train_sha256': 'a' * 64, 'holdout_sha256': 'b' * 64,
            'dataset_manifest_sha256': 'c' * 64}
        previous = {'request': m.ORIGIN_WINDOW['request'], 'source_sha': m.ORIGIN_WINDOW['source_sha'],
            'student_profile': profile, 'sources': {str(m.SCRIPTS / k): v for k, v in self.original_pins.items() if k.endswith('.py')},
            'initial_request': '6907283384', 'accepted_previous_window': 'accepted6'}
        desc_raw = m.encode(desc)
        admission = m.make_admission(previous, desc, hash_of(desc_raw), time.time())
        admission_raw = m.encode(admission)
        receipt = {'schema': m.RECEIPT_SCHEMA, 'state': 'EXECUTION_REVISION_INSTALLED_EVALUATION_REQUIRED',
            'request': self.ref['request'], 'source_sha': self.ref['source_sha'], 'descriptor_sha256': hash_of(desc_raw),
            'previous_admission_sha256': m.ORIGIN['previous_admission_sha256'], 'new_admission_sha256': hash_of(admission_raw),
            'wrapper_sha256': hash_of(b'expected wrapper'), 'origin_window': dict(m.ORIGIN_WINDOW),
            'origin_lineage_sha256': m.ORIGIN['lineage_sha256'], 'anchor_checkpoint_manifest_sha256': m.ANCHOR['manifest_sha256'],
            'runtime_sources': desc['runtime_sources']}
        receipt_raw = m.encode(receipt)
        ref = dict(self.ref, receipt_sha256=hash_of(receipt_raw))
        config = {'schema': m.CONFIG_SCHEMA, 'enabled': True, 'source_sha256': desc['runtime_sources'][m.SELF], 'execution_revision': ref}
        folder = self.ctx['execution']['directory']
        for path, raw in ((folder / 'descriptor.json', desc_raw), (folder / 'admission_receipt.json', receipt_raw),
                          (m.CONFIG, m.encode(config)), (m.ADMISSION, admission_raw), (m.WRAPPER, b'expected wrapper')):
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); path.chmod(0o600)
        historical = {'admission': previous, 'raw': b'historical admission', 'wrapper': b'historical wrapper',
            'lineage': self.lineage, 'certificate': self.ctx['certificate'], 'contract': self.ctx['contract'],
            'observer': self.ctx['observer'], 'helper': object(), 'window': object()}
        return ref, historical

    def call_context(self, ref, historical):
        with patch.object(m, 'ORIGINAL_SOURCES', self.original_pins), patch.object(m, 'historical_context', return_value=historical), \
             patch.object(m, 'make_wrapper', return_value=b'expected wrapper'):
            return m.current_context(reference=ref)

    def test_live_sources_are_independent_from_historical_view(self):
        ref, historical = self.prepare_context()
        ctx = self.call_context(ref, historical)
        self.assertEqual(ctx['origin']['historical_raw'], b'historical admission')
        self.assertNotEqual(ctx['raw'], ctx['origin']['historical_raw'])
        self.assertEqual(ctx['argv'][2], str(m.SCRIPTS / m.ENTRY))
        (m.SCRIPTS / m.ENTRY).write_bytes(b'foreign newer source')
        with self.assertRaises(m.Hold): self.call_context(ref, historical)

    def test_issuer_and_every_consumer_have_actual_installed_source_pins(self):
        ref, historical = self.prepare_context()
        for name in ('owner_qwen_revision_install.py', 'owner_hermes_hydrate.py', 'nox_dispatcher_t855u.py'):
            path = m.SCRIPTS / name; old = path.read_bytes(); path.write_bytes(b'changed')
            with self.assertRaises(m.Hold): self.call_context(ref, historical)
            path.write_bytes(old)

    def test_admission_cannot_silently_change_profile_or_point_to_a_different_seal(self):
        ref, historical = self.prepare_context()
        with self.assertRaises(m.Hold): self.call_context(dict(ref, receipt_sha256='0' * 64), historical)
        pointer = json.loads(m.ADMISSION.read_bytes()); pointer['student_profile']['successful_updates_goal'] = 2000
        m.ADMISSION.write_bytes(m.encode(pointer))
        with self.assertRaises(m.Hold): self.call_context(ref, historical)


if __name__ == '__main__':
    unittest.main()
