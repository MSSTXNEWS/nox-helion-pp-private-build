"""Synthetic private metadata fixtures; never load training or native main()."""
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

PATH = Path(__file__).with_name('owner_qwen_execution_successor.py')
spec = importlib.util.spec_from_file_location('successor_under_test', PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patches = []
        for key, value in {'ROOT': self.root, 'STATE': self.root / 'state', 'SCRIPTS': self.root / 'scripts',
                'OUTPUT': self.root / 'output', 'AREA': self.root / 'state/revisions',
                'CONFIG': self.root / 'config/revision.json', 'ADMISSION': self.root / 'state/admission.json',
                'WRAPPER': self.root / 'scripts/wrapper.sh', 'GUARD_CONFIG': self.root / 'config/guard.json',
                'GUARD_STATUS': self.root / 'state/guard.json', 'OWNER_UID': os.geteuid()}.items():
            self.p(key, value)
        for path in (m.STATE, m.SCRIPTS, m.OUTPUT, m.AREA, m.CONFIG.parent):
            path.mkdir(parents=True, exist_ok=True)
        self.now = time.time()
        self.old_pid = {'pid': 1025, 'start_ticks': 9999, 'boot_id': 'a' * 36}
        self.pid = {'pid': 2025, 'start_ticks': 19999, 'boot_id': 'a' * 36}
        self.lineage = {'schema': 'fixture', 'entry_sha256': m.ORIGIN['previous_entry_sha256'],
            'contract_sha256': m.ORIGINAL_SOURCES['owner_qwen_training_contract.py'],
            'memfd_source_sha256': m.ORIGINAL_SOURCES['owner_qwen_memfd.py'], 'scientific': {'lr': 5e-5},
            'tokenized_corpus': {'splits': [{'split': 'holdout', 'accepted_rows': 16}]}}
        self.state25 = {'successful_total': 25, 'attempted_total': 25, 'skipped_total': 0, 'data_cursor': 200,
            'initial_holdout_loss': 1.5, 'last_holdout_loss': 1.3, 'holdout_evaluated_successful_total': 10,
            'update_evidence': [{'step': i, 'adapter_sha_after': sha(str(i).encode())} for i in range(1, 26)]}
        self.original_manifest, raw, state_raw = self.write_checkpoint(m.ORIGINAL_ANCHOR['directory'], self.state25, self.old_pid)
        self.p('ORIGINAL_ANCHOR', dict(m.ORIGINAL_ANCHOR, manifest_sha256=sha(raw), student_state_sha256=sha(state_raw)))
        profile = {'successful_updates_goal': 1000, 'base_directory': '/public/base', 'output_directory': str(m.OUTPUT),
                   'train_sha256': '1' * 64, 'holdout_sha256': '2' * 64, 'dataset_manifest_sha256': '3' * 64}
        self.origin_admission = {'request': m.ORIGIN_WINDOW['request'], 'source_sha': m.ORIGIN_WINDOW['source_sha'],
            'student_profile': profile, 'sources': {str(m.SCRIPTS / k): v for k, v in m.ORIGINAL_SOURCES.items()},
            'initial_request': '6907283384', 'accepted_previous_window': 'accepted6'}
        self.old_desc = {'schema': 'NOX_QWEN_EXECUTION_REVISION_DESCRIPTOR_V1',
            'request': m.PREDECESSOR['reference']['request'], 'source_sha': m.PREDECESSOR['reference']['source_sha'],
            'created_at': self.now - 500, 'origin': copy.deepcopy(m.ORIGIN), 'anchor': copy.deepcopy(m.ORIGINAL_ANCHOR),
            'scheduler': dict(m.SCHEDULER), 'runtime_sources': {m.ENTRY: m.PREDECESSOR['runtime_entry_sha256'],
                m.SELF: m.PREDECESSOR['verifier_sha256']},
            'consumer_sources': {k: '6' * 64 for k in m.CONSUMERS},
            'activation_issuer_sha256': m.PREDECESSOR['activation_issuer_sha256'],
            'bootstrap': {'expires_at': self.now + 3100, 'hold_sha256': m.OLD_HOLD_SHA, 'pause_sha256': m.OLD_PAUSE_SHA}}
        old_desc_raw = m.encode(self.old_desc)
        self.old_admission = copy.deepcopy(self.origin_admission)
        self.old_admission.update(request=self.old_desc['request'], source_sha=self.old_desc['source_sha'],
            created_at=self.old_desc['created_at'], previous_request=m.ORIGIN_WINDOW['request'],
            previous_admission_sha256=m.ORIGIN['previous_admission_sha256'])
        self.old_admission['sources'].update({str(m.SCRIPTS / k): v for k, v in self.old_desc['runtime_sources'].items()})
        self.old_admission['execution_revision'] = {'schema': 'NOX_QWEN_EXECUTION_REFERENCE_V1',
            'request': self.old_desc['request'], 'source_sha': self.old_desc['source_sha'], 'descriptor_sha256': sha(old_desc_raw)}
        self.old_admission_raw = m.encode(self.old_admission)
        self.p('make_wrapper', lambda a, h: ('fixture-wrapper ' + a['request'] + ' ' + h + '\n').encode())
        self.old_wrapper = m.make_wrapper(self.old_admission, sha(self.old_admission_raw))
        self.old_receipt = {'schema': 'NOX_QWEN_EXECUTION_REVISION_ADMISSION_V1',
            'state': 'EXECUTION_REVISION_INSTALLED_EVALUATION_REQUIRED', 'request': self.old_desc['request'],
            'source_sha': self.old_desc['source_sha'], 'descriptor_sha256': sha(old_desc_raw),
            'previous_admission_sha256': m.ORIGIN['previous_admission_sha256'], 'new_admission_sha256': sha(self.old_admission_raw),
            'wrapper_sha256': sha(self.old_wrapper), 'origin_window': dict(m.ORIGIN_WINDOW),
            'origin_lineage_sha256': m.ORIGIN['lineage_sha256'], 'anchor_checkpoint_manifest_sha256': m.ORIGINAL_ANCHOR['manifest_sha256'],
            'runtime_sources': dict(self.old_desc['runtime_sources'])}
        old_receipt_raw = m.encode(self.old_receipt)
        predecessor = dict(m.PREDECESSOR, descriptor_sha256=sha(old_desc_raw), admission_sha256=sha(self.old_admission_raw),
            reference=dict(m.PREDECESSOR['reference'], receipt_sha256=sha(old_receipt_raw)))
        self.p('PREDECESSOR', predecessor)
        self.ref = {'request': '90001', 'source_sha': 'a' * 40, 'receipt_sha256': 'b' * 64}
        self.folder = m.AREA / self.ref['request']; self.folder.mkdir()
        old_folder = m.AREA / predecessor['reference']['request']; old_folder.mkdir()
        self.private(old_folder / 'descriptor.json', old_desc_raw)
        self.private(old_folder / 'admission_receipt.json', old_receipt_raw)
        self.private(self.folder / 'predecessor_admission.json', self.old_admission_raw)
        self.private(self.folder / 'predecessor_wrapper.sh', self.old_wrapper)
        self.signature = {'successful_total': 25, 'attempted_total': 25, 'skipped_total': 0,
            'data_cursor': 200, 'optimizer_step': 25, 'adapter_tensor_sha256': sha(b'25'),
            'optimizer_state_sha256': '4' * 64, 'scheduler_state_sha256': '5' * 64,
            'scaler_state_sha256': '6' * 64, 'rng_state_sha256': '7' * 64}
        self.predecessor_state = copy.deepcopy(self.state25)
        old_witness = {'schema': m.WITNESS_SCHEMA, 'execution_binding': m.predecessor_binding(), 'kind': 'BOOTSTRAP_RESTORE',
            'process_identity': self.old_pid, 'evaluated_successful_total': 25,
            'started_at': self.now - 405, 'finished_at': self.now - 400, 'holdout_examples': 16, 'holdout_loss': 1.22,
            'restored_checkpoint': {k: m.ORIGINAL_ANCHOR[k] for k in ('directory', 'manifest_sha256', 'student_state_sha256', 'successful_total')},
            'before': dict(self.signature), 'after': dict(self.signature)}
        self.predecessor_state.update(last_holdout_loss=1.22, holdout_evaluated_successful_total=25,
            execution_binding=m.predecessor_binding(), last_evaluation_witness=old_witness)
        self.predecessor_manifest, raw, state_raw = self.write_checkpoint(m.ANCHOR['directory'], self.predecessor_state, self.old_pid)
        self.p('ANCHOR', dict(m.ANCHOR, manifest_sha256=sha(raw), student_state_sha256=sha(state_raw)))
        self.desc = {'schema': m.DESCRIPTOR_SCHEMA, 'request': self.ref['request'], 'source_sha': self.ref['source_sha'],
            'created_at': self.now - 20, 'origin': copy.deepcopy(m.ORIGIN), 'anchor': dict(m.ANCHOR),
            'predecessor': copy.deepcopy(m.PREDECESSOR), 'retained_anchors': [dict(m.ORIGINAL_ANCHOR), dict(m.ANCHOR)],
            'runtime_sources': {m.ENTRY: 'f' * 64, m.SELF: '1' * 64},
            'consumer_sources': {name: '2' * 64 for name in m.CONSUMERS}, 'activation_issuer_sha256': '3' * 64,
            'activation_watcher_sha256': 'a' * 64, 'scheduler': dict(m.SCHEDULER),
            'bootstrap': {'expires_at': self.now + 3580, 'hold_sha256': m.PREDECESSOR_HOLD_SHA, 'pause_sha256': None}}
        self.origin_ctx = {'admission': self.origin_admission, 'raw': m.encode(self.origin_admission), 'wrapper': b'origin',
            'lineage': self.lineage, 'certificate': {'update_evidence': self.state25['update_evidence'][:6]},
            'contract': types.SimpleNamespace(), 'observer': types.SimpleNamespace(update_chain=self.update_chain),
            'helper': types.SimpleNamespace(), 'window': types.SimpleNamespace()}
        self.ctx = {'execution': {'reference': self.ref, 'descriptor': self.desc, 'descriptor_sha256': 'c' * 64,
            'admission_sha256': 'd' * 64, 'wrapper_sha256': 'e' * 64, 'runtime_entry_sha256': 'f' * 64,
            'verifier_sha256': '1' * 64, 'directory': self.folder}, 'lineage': self.lineage,
            'certificate': self.origin_ctx['certificate'], 'observer': self.origin_ctx['observer'],
            'contract': self.origin_ctx['contract'], 'raw': b'admission', 'wrapper': b'wrapper', 'output': m.OUTPUT,
            'retained_anchors': copy.deepcopy(self.desc['retained_anchors'])}

    def p(self, key, value):
        item = patch.object(m, key, value); item.start(); self.patches.append(item)

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.tmp.cleanup()

    @staticmethod
    def private(path, raw):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); path.chmod(0o600)

    @staticmethod
    def update_chain(state, contract):
        if len(state['update_evidence']) != state['successful_total']:
            raise m.Hold('HOLD_FIXTURE_CHAIN')
        return {'adapter_tensor_sha256': state['update_evidence'][-1]['adapter_sha_after']}

    def write_checkpoint(self, name, state, process):
        folder = m.OUTPUT / name; folder.mkdir(exist_ok=True)
        files = {}
        for filename in m.REQUIRED | {'README.md'}:
            raw = m.encode(state) if filename == 'student_state.json' else m.encode(self.lineage) if filename == 'lineage.json' else b'opaque-payload'
            (folder / filename).write_bytes(raw); files[filename] = sha(raw)
        manifest = {'schema': 'NOX_QWEN35_9B_CHECKPOINT_V1', 'directory': name,
            'lineage_sha256': m.ORIGIN['lineage_sha256'], 'files_sha256': files,
            'successful_total': state['successful_total'], 'attempted_total': state['attempted_total'],
            'holdout_evaluated_successful_total': state['holdout_evaluated_successful_total'],
            'holdout_loss': state['last_holdout_loss'], 'adapter_tensor_sha256': state['update_evidence'][-1]['adapter_sha_after'],
            'process_identity': process}
        if 'execution_binding' in state: manifest['execution_binding'] = state['execution_binding']
        raw = m.encode(manifest); (folder / 'checkpoint_manifest.json').write_bytes(raw)
        return manifest, raw, (folder / 'student_state.json').read_bytes()

    def fresh(self, good=25, evaluated=25, kind='BOOTSTRAP_RESTORE'):
        state = copy.deepcopy(self.predecessor_state)
        sig = dict(self.signature, successful_total=evaluated, attempted_total=evaluated,
                   data_cursor=evaluated * 8, optimizer_step=evaluated, adapter_tensor_sha256=sha(str(evaluated).encode()))
        witness = {'schema': m.WITNESS_SCHEMA, 'execution_binding': m.execution_binding(self.ctx), 'kind': kind,
            'process_identity': self.pid, 'evaluated_successful_total': evaluated,
            'started_at': self.now - 5, 'finished_at': self.now - 4, 'holdout_examples': 16, 'holdout_loss': 1.22,
            'restored_checkpoint': {k: m.ANCHOR[k] for k in ('directory', 'manifest_sha256', 'student_state_sha256', 'successful_total')},
            'before': sig, 'after': dict(sig)}
        state.update(successful_total=good, attempted_total=good, skipped_total=0, data_cursor=good * 8,
            update_evidence=[{'step': i, 'adapter_sha_after': sha(str(i).encode())} for i in range(1, good + 1)],
            execution_binding=m.execution_binding(self.ctx), last_evaluation_witness=witness,
            holdout_evaluated_successful_total=evaluated)
        name = 'checkpoint-u%08d-a%08d-g%020d' % (good, good, 900)
        manifest, raw, state_raw = self.write_checkpoint(name, state, self.pid)
        return manifest, state, raw, state_raw

    def activation(self, manifest, state, raw, state_raw):
        value = {'schema': m.ACTIVATION_SCHEMA, 'state': 'FRESH_EVALUATION_ACCEPTED_OPTIMIZER_ADMITTED',
            'execution_binding': m.execution_binding(self.ctx), 'issuer_source_sha256': self.desc['activation_issuer_sha256'],
            'issued_at': self.now - 1, 'initial_process_identity': self.pid,
            'checkpoint': {'directory': manifest['directory'], 'manifest_sha256': sha(raw), 'student_state_sha256': sha(state_raw),
                'verified_files': 10, 'verified_bytes': 519905811, 'full_files_sha256_verified': True},
            'evaluation_witness': state['last_evaluation_witness'], 'preserved_guard_policy_sha256': '8' * 64,
            'guard_state_sha256': '9' * 64, 'previous_flags_archived': True}
        path = self.folder / 'activation.json'; self.private(path, m.encode(value)); return path, value


class ProvenanceTests(Fixture):
    def test_descriptor_requires_exact_successor_and_both_retained_anchors(self):
        self.assertEqual(m.descriptor(self.desc), self.desc)
        for change in (lambda d: d.update(anchor=dict(m.ORIGINAL_ANCHOR)),
                       lambda d: d['retained_anchors'].pop(0),
                       lambda d: d['predecessor']['reference'].update(request='7'),
                       lambda d: d['scheduler'].update(guard_update_gap=20),
                       lambda d: d['bootstrap'].update(expires_at=self.now + 9000),
                       lambda d: d['bootstrap'].update(pause_sha256=m.OLD_PAUSE_SHA)):
            d = copy.deepcopy(self.desc); change(d)
            with self.assertRaises(m.Hold): m.descriptor(d)

    def test_successor_admission_preserves_science_and_explicit_predecessor(self):
        before = copy.deepcopy(self.old_admission)
        new = m.make_admission(before, self.desc, 'a' * 64, self.now)
        self.assertEqual(before, self.old_admission)
        self.assertEqual(new['student_profile'], before['student_profile'])
        self.assertEqual(new['previous_request'], m.PREDECESSOR['reference']['request'])
        self.assertEqual(new['previous_admission_sha256'], m.PREDECESSOR['admission_sha256'])
        self.assertEqual(new['predecessor_execution_revision'], m.PREDECESSOR['reference'])
        self.assertEqual(new['sources'][str(m.SCRIPTS / 'qwen_student_training_entry.py')], m.ORIGIN['previous_entry_sha256'])
        with self.assertRaises(m.Hold): m.make_admission(self.origin_admission, self.desc, 'a' * 64, self.now)

    def test_predecessor_reads_sealed_old_evidence_not_current_sources(self):
        value = m.predecessor_evidence(self.folder, self.origin_ctx)
        self.assertEqual(value['admission'], self.old_admission)
        self.assertEqual(value['execution_binding'], m.predecessor_binding())
        # These live files are deliberately different; the old proof reads only its private immutable snapshots.
        (m.SCRIPTS / m.ENTRY).write_bytes(b'new-live-student')
        self.assertEqual(m.predecessor_evidence(self.folder, self.origin_ctx)['raw'], self.old_admission_raw)
        self.private(self.folder / 'predecessor_admission.json', b'{}')
        with self.assertRaises(m.Hold): m.predecessor_evidence(self.folder, self.origin_ctx)

    def test_old_activation_or_foreign_wrapper_blocks_successor_context(self):
        path = m.AREA / m.PREDECESSOR['reference']['request'] / 'activation.json'
        self.private(path, b'{}')
        with self.assertRaises(m.Hold): m.predecessor_evidence(self.folder, self.origin_ctx)
        path.unlink()
        self.private(self.folder / 'predecessor_wrapper.sh', b'foreign')
        with self.assertRaises(m.Hold): m.predecessor_evidence(self.folder, self.origin_ctx)

    def test_private_metadata_rejects_symlink_mode_and_nonfinite_json(self):
        path = self.folder / 'predecessor_admission.json'; path.chmod(0o644)
        with self.assertRaises(m.Hold): m.predecessor_evidence(self.folder, self.origin_ctx)
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}'):
            with self.assertRaises(m.Hold): m.parse(raw)
        link = self.root / 'link'; link.symlink_to(path)
        with self.assertRaises(m.Hold): m.read(link)


class CheckpointTests(Fixture):
    def test_exact_predecessor_is_only_an_initial_anchor_not_current_execution(self):
        with self.assertRaises(m.Hold): m.checkpoint_binding(self.ctx, self.predecessor_manifest, self.predecessor_state)
        proof = m.checkpoint_binding(self.ctx, self.predecessor_manifest, self.predecessor_state, allow_initial_anchor=True)
        self.assertTrue(proof['initial_anchor']); self.assertFalse(proof['current_execution'])
        self.assertFalse(proof['legacy_anchor']); self.assertFalse(proof['full_tensor_files_verified'])
        self.assertEqual(proof['anchor_kind'], 'PREDECESSOR_EVALUATION')
        self.assertEqual(proof['predecessor_reference'], m.PREDECESSOR['reference'])
        with self.assertRaises(m.Hold): m.checkpoint_binding(self.ctx, self.original_manifest, self.state25, allow_initial_anchor=True)

    def test_other_predecessor_checkpoint_or_relabeling_is_rejected(self):
        other, _, _ = self.write_checkpoint('checkpoint-u00000025-a00000025-g00000000000000000400', self.predecessor_state, self.old_pid)
        with self.assertRaises(m.Hold): m.checkpoint_binding(self.ctx, other, self.predecessor_state, allow_initial_anchor=True)
        changed = copy.deepcopy(self.predecessor_state)
        changed['execution_binding'] = m.execution_binding(self.ctx)
        changed['last_evaluation_witness']['execution_binding'] = m.execution_binding(self.ctx)
        manifest, _, _ = self.write_checkpoint(m.ANCHOR['directory'], changed, self.old_pid)
        with self.assertRaises(m.Hold): m.bootstrap_evaluation_proof(self.ctx, manifest, changed)

    def test_fresh_same_counter_restore_preserves_predecessor_full_state_signatures(self):
        manifest, state, _, _ = self.fresh()
        proof = m.bootstrap_evaluation_proof(self.ctx, manifest, state)
        self.assertTrue(proof['current_execution']); self.assertFalse(proof['initial_anchor'])
        self.assertEqual(proof['optimizer_updates_during_bootstrap'], 0)
        self.assertFalse(proof['full_tensor_files_verified'])
        self.assertEqual(m.retained_anchors(self.ctx), [m.ORIGINAL_ANCHOR, m.ANCHOR])

    def test_fresh_bootstrap_rejects_old_restore_reference_process_or_timestamp(self):
        for change in (lambda w: w.update(restored_checkpoint={k: m.ORIGINAL_ANCHOR[k] for k in ('directory', 'manifest_sha256', 'student_state_sha256', 'successful_total')}),
                       lambda w: w.update(process_identity=self.old_pid),
                       lambda w: w.update(started_at=self.now - 200, finished_at=self.now - 199)):
            manifest, state, _, _ = self.fresh(); change(state['last_evaluation_witness'])
            manifest, _, _ = self.write_checkpoint(manifest['directory'], state, state['last_evaluation_witness']['process_identity'])
            with self.assertRaises(m.Hold): m.bootstrap_evaluation_proof(self.ctx, manifest, state)

    def test_changed_optimizer_rng_counters_or_update_chain_are_rejected(self):
        for key in ('optimizer_state_sha256', 'scheduler_state_sha256', 'scaler_state_sha256', 'rng_state_sha256'):
            manifest, state, _, _ = self.fresh()
            for side in ('before', 'after'): state['last_evaluation_witness'][side][key] = 'e' * 64
            manifest, _, _ = self.write_checkpoint(manifest['directory'], state, self.pid)
            with self.assertRaises(m.Hold): m.bootstrap_evaluation_proof(self.ctx, manifest, state)
        manifest, state, _, _ = self.fresh(good=26)
        with self.assertRaises(m.Hold): m.bootstrap_evaluation_proof(self.ctx, manifest, state)
        manifest, state, _, _ = self.fresh()
        state['update_evidence'][7]['adapter_sha_after'] = 'e' * 64
        manifest, _, _ = self.write_checkpoint(manifest['directory'], state, self.pid)
        with self.assertRaises(m.Hold): m.bootstrap_evaluation_proof(self.ctx, manifest, state)

    def test_later_checkpoint_preserves_actual_earlier_evaluation_and_amp_skips(self):
        manifest, state, _, _ = self.fresh(good=30, evaluated=25)
        self.assertTrue(m.checkpoint_binding(self.ctx, manifest, state)['current_execution'])
        manifest, state, _, _ = self.fresh()
        state['attempted_total'] += 1; state['skipped_total'] += 1
        manifest, _, _ = self.write_checkpoint(manifest['directory'], state, self.pid)
        self.assertTrue(m.checkpoint_binding(self.ctx, manifest, state)['verified'])
        with patch.object(m, '_self_process_identity', return_value=self.pid):
            with self.assertRaises(m.Hold): m.wait_for_optimizer_permission(self.ctx, manifest, state, timeout=1)

    def test_current_metadata_is_hash_bound_without_claiming_payload_read(self):
        manifest, state, _, _ = self.fresh()
        (m.OUTPUT / manifest['directory'] / 'student_state.json').write_bytes(b'{}')
        with self.assertRaises(m.Hold): m.checkpoint_binding(self.ctx, manifest, state)


class PermissionTests(Fixture):
    def test_missing_or_expired_activation_never_grants_permission(self):
        self.assertTrue(m.activation_status(self.ctx)['bootstrap_pending'])
        self.ctx['execution']['descriptor']['created_at'] = self.now - 4000
        self.ctx['execution']['descriptor']['bootstrap']['expires_at'] = self.now - 400
        value = m.activation_status(self.ctx)
        self.assertFalse(value['active']); self.assertFalse(value['bootstrap_pending'])

    def test_activation_binds_successor_checkpoint_reference_and_fresh_evaluation(self):
        manifest, state, raw, state_raw = self.fresh()
        path, value = self.activation(manifest, state, raw, state_raw)
        self.assertTrue(m.activation_status(self.ctx)['active'])
        changed = copy.deepcopy(value); changed['evaluation_witness'] = self.predecessor_state['last_evaluation_witness']
        self.private(path, m.encode(changed))
        with self.assertRaises(m.Hold): m.activation_status(self.ctx)
        changed = copy.deepcopy(value); changed['evaluation_witness']['restored_checkpoint']['manifest_sha256'] = m.ORIGINAL_ANCHOR['manifest_sha256']
        self.private(path, m.encode(changed))
        with self.assertRaises(m.Hold): m.activation_status(self.ctx)

    def test_permission_requires_live_process_actual_pointer_and_fresh_guard(self):
        manifest, state, raw, state_raw = self.fresh()
        self.activation(manifest, state, raw, state_raw)
        self.private(m.ADMISSION, self.ctx['raw']); self.private(m.WRAPPER, self.ctx['wrapper'])
        self.private(m.OUTPUT / 'latest_checkpoint.json', m.encode({'directory': manifest['directory'], 'manifest_sha256': sha(raw)}))
        with patch.object(m, '_self_process_identity', return_value=self.pid), patch.object(m, 'stop_active', return_value=False), \
                patch.object(m, '_guard_permission', return_value='a' * 64) as gate:
            value = m.wait_for_optimizer_permission(self.ctx, manifest, state, timeout=1)
            self.assertTrue(value['optimizer_allowed']); gate.assert_called_once_with(self.ctx, sha(raw))
        with patch.object(m, '_self_process_identity', return_value=self.old_pid):
            with self.assertRaises(m.Hold): m.wait_for_optimizer_permission(self.ctx, manifest, state, timeout=1)
        self.private(m.OUTPUT / 'latest_checkpoint.json', m.encode({'directory': m.ANCHOR['directory'], 'manifest_sha256': m.ANCHOR['manifest_sha256']}))
        with patch.object(m, '_self_process_identity', return_value=self.pid), patch.object(m, 'stop_active', return_value=False), \
                patch.object(m, '_guard_permission', return_value='a' * 64):
            with self.assertRaises(m.Hold): m.wait_for_optimizer_permission(self.ctx, manifest, state, timeout=1)

    def test_all_stop_flags_remain_blocking_and_wait_is_bounded(self):
        manifest, state, _, _ = self.fresh()
        self.private(m.ADMISSION, self.ctx['raw']); self.private(m.WRAPPER, self.ctx['wrapper'])
        with patch.object(m, '_self_process_identity', return_value=self.pid), patch.object(m, 'stop_active', return_value=True):
            with self.assertRaisesRegex(m.Hold, 'OWNER_STOP'): m.wait_for_optimizer_permission(self.ctx, manifest, state, timeout=1)
        with patch.object(m, '_self_process_identity', return_value=self.pid), patch.object(m, 'stop_active', return_value=False), \
                patch.object(m.time, 'monotonic', side_effect=[0, 2]):
            with self.assertRaisesRegex(m.Hold, 'WAIT_OPTIMIZER_PERMISSION_TIMEOUT'):
                m.wait_for_optimizer_permission(self.ctx, manifest, state, timeout=1)


class CurrentContextTests(Fixture):
    def install_context(self):
        source_hashes = {}
        names = set(m.ORIGINAL_SOURCES) | {m.ENTRY, m.SELF, m.WATCHER, 'owner_qwen_revision_install.py'} | m.CONSUMERS
        for name in names:
            raw = ('fixture source ' + name + '\n').encode()
            (m.SCRIPTS / name).write_bytes(raw); source_hashes[name] = sha(raw)
        self.p('ORIGINAL_SOURCES', {name: source_hashes[name] for name in m.ORIGINAL_SOURCES})
        self.desc['runtime_sources'] = {m.ENTRY: source_hashes[m.ENTRY], m.SELF: source_hashes[m.SELF]}
        self.desc['consumer_sources'] = {name: source_hashes[name] for name in m.CONSUMERS}
        self.desc['activation_issuer_sha256'] = source_hashes['owner_qwen_revision_install.py']
        self.desc['activation_watcher_sha256'] = source_hashes[m.WATCHER]
        desc_raw = m.encode(self.desc)
        admission = m.make_admission(self.old_admission, self.desc, sha(desc_raw), self.now - 10)
        admission_raw = m.encode(admission); wrapper = m.make_wrapper(admission, sha(admission_raw))
        receipt = {'schema': m.RECEIPT_SCHEMA, 'state': 'EXECUTION_REVISION_INSTALLED_EVALUATION_REQUIRED',
            'request': self.ref['request'], 'source_sha': self.ref['source_sha'], 'descriptor_sha256': sha(desc_raw),
            'previous_admission_sha256': m.PREDECESSOR['admission_sha256'],
            'predecessor_execution_revision': copy.deepcopy(m.PREDECESSOR['reference']),
            'predecessor_descriptor_sha256': m.PREDECESSOR['descriptor_sha256'],
            'new_admission_sha256': sha(admission_raw), 'wrapper_sha256': sha(wrapper),
            'origin_window': dict(m.ORIGIN_WINDOW), 'origin_lineage_sha256': m.ORIGIN['lineage_sha256'],
            'anchor_checkpoint_manifest_sha256': m.ANCHOR['manifest_sha256'],
            'runtime_sources': dict(self.desc['runtime_sources']),
            'activation_watcher_sha256': self.desc['activation_watcher_sha256']}
        raw = m.encode(receipt); ref = dict(self.ref, receipt_sha256=sha(raw))
        config = {'schema': m.CONFIG_SCHEMA, 'enabled': True, 'source_sha256': source_hashes[m.SELF],
            'execution_revision': ref}
        self.private(m.CONFIG, m.encode(config)); self.private(m.ADMISSION, admission_raw)
        self.private(m.WRAPPER, wrapper); self.private(self.folder / 'descriptor.json', desc_raw)
        self.private(self.folder / 'admission_receipt.json', raw)
        self.p('historical_context', lambda folder: self.origin_ctx)
        return ref, receipt, config

    def test_current_context_separates_three_origins_and_checks_new_source_graph(self):
        ref, _, _ = self.install_context()
        ctx = m.current_context(ref)
        self.assertEqual(ctx['execution']['reference'], ref)
        self.assertEqual(ctx['predecessor']['reference'], m.PREDECESSOR['reference'])
        self.assertEqual(ctx['origin']['window_reference'], m.ORIGIN_WINDOW)
        self.assertEqual(ctx['retained_anchors'], [m.ORIGINAL_ANCHOR, m.ANCHOR])
        self.assertEqual(ctx['admission']['previous_admission_sha256'], m.PREDECESSOR['admission_sha256'])
        self.assertIn(str(m.SCRIPTS / m.ENTRY), ctx['argv'])
        (m.SCRIPTS / m.WATCHER).write_bytes(b'foreign watcher')
        with self.assertRaises(m.Hold): m.current_context(ref)

    def test_current_context_rejects_false_predecessor_even_with_new_receipt_hash(self):
        ref, receipt, config = self.install_context()
        receipt['predecessor_execution_revision']['request'] = '999'
        raw = m.encode(receipt); self.private(self.folder / 'admission_receipt.json', raw)
        config['execution_revision']['receipt_sha256'] = sha(raw)
        self.private(m.CONFIG, m.encode(config))
        with self.assertRaisesRegex(m.Hold, 'RECEIPT_BINDINGS'): m.current_context()

    def test_current_context_rejects_late_predecessor_activation_and_old_reference(self):
        ref, _, _ = self.install_context()
        with self.assertRaisesRegex(m.Hold, 'CONFIG_REFERENCE'): m.current_context(m.PREDECESSOR['reference'])
        self.private(m.AREA / m.PREDECESSOR['reference']['request'] / 'activation.json', b'{}')
        with self.assertRaisesRegex(m.Hold, 'PREDECESSOR_ALREADY_ACTIVATED'): m.current_context(ref)


if __name__ == '__main__':
    unittest.main()
