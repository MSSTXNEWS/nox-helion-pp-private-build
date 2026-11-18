"""Read-only readiness must distinguish saved quality, source pins and resources."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('resume_preflight', Path(__file__).with_name('owner_training_resume_preflight.py'))
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class ResumePreflightTests(unittest.TestCase):
    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(value, sort_keys=True).encode()
        path.write_bytes(raw)
        return preflight.digest(raw)

    def context_fixture(self, directory, *, unknown_consumer=False):
        root = Path(directory)
        area = root / 'state/execution'
        reference = {'request': '6916464880', 'source_sha': 'a' * 40}
        pins = {}
        for name in preflight.CONSUMERS | {preflight.ENTRY, preflight.SHARED}:
            path = root / 'scripts' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'PRIVATE_SOURCE_CONTENT_DO_NOT_IMPORT')
            pins[name] = preflight.digest(path.read_bytes())
        consumers = {name: pins[name] for name in preflight.CONSUMERS}
        if unknown_consumer:
            consumers['../../private_credentials'] = '0' * 64
        runtime = {name: pins[name] for name in (preflight.SHARED, preflight.ENTRY)}
        descriptor = {'schema': 'NOX_QWEN_EXECUTION_SUCCESSOR_DESCRIPTOR_V1', **reference,
                      'consumer_sources': consumers, 'runtime_sources': runtime}
        descriptor_pin = self.write(area / 'descriptor.json', descriptor)
        admission_pin = self.write(root / 'state/owner_training_admission.json', {'private': 'PRIVATE_RECORD'})
        wrapper = root / 'scripts/run_train_volta_t866u.sh'
        wrapper.write_bytes(b'PRIVATE_WRAPPER_ARGUMENTS')
        receipt = {'schema': 'NOX_QWEN_EXECUTION_SUCCESSOR_ADMISSION_V1', **reference,
            'state': 'EXECUTION_REVISION_INSTALLED_EVALUATION_REQUIRED', 'descriptor_sha256': descriptor_pin,
            'runtime_sources': runtime, 'new_admission_sha256': admission_pin,
            'wrapper_sha256': preflight.digest(wrapper.read_bytes())}
        reference['receipt_sha256'] = self.write(area / 'admission_receipt.json', receipt)
        self.write(root / 'config/owner_qwen_execution_revision.json', {
            'schema': 'NOX_QWEN_EXECUTION_REVISION_CONFIG_V1', 'enabled': True,
            'source_sha256': pins[preflight.SHARED], 'execution_revision': reference})
        return root, area, reference, pins

    def test_guard_projection_keeps_exact_saved_quality_without_claiming_live_permission(self):
        raw = {'state': 'INHIBITED', 'sampled_at': 10,
            'bindings': {'execution_revision': preflight.REFERENCE, 'private': 'SECRET'},
            'policy_state': {'inhibit': True, 'reason': 'HOLDOUT_REGRESSION',
                'regression_streak': 2, 'best_holdout_loss': 1.2216, 'last_successful_updates': 55,
                'last_evaluation_update': 55, 'latched_at': 9.5, 'private': 'SECRET'},
            'checkpoint': {'successful_updates': 55, 'holdout_loss': 1.4, 'messages': 'SECRET'}}
        result = preflight.guard_projection(raw, 100)
        self.assertEqual(result['policy_state']['reason'], 'HOLDOUT_REGRESSION')
        self.assertEqual(result['policy_state']['regression_streak'], 2)
        self.assertEqual(result['checkpoint']['holdout_loss'], 1.4)
        self.assertFalse(result['sample_is_fresh'])
        self.assertFalse(result['saved_state_is_live_optimizer_permission'])
        self.assertNotIn('SECRET', json.dumps(result))
        raw.update(state={'private': 'SECRET'}, sampled_at=10 ** 500)
        raw['policy_state'].update(reason=['SECRET'], regression_streak=True,
                                   last_successful_updates=1.5, best_holdout_loss=float('nan'))
        negative = preflight.guard_projection(raw, 100)
        self.assertEqual(negative['state'], 'UNRECOGNIZED_ENUM')
        self.assertEqual(negative['policy_state']['reason'], 'UNRECOGNIZED_ENUM')
        self.assertNotIn('regression_streak', negative['policy_state'])
        self.assertNotIn('last_successful_updates', negative['policy_state'])
        self.assertNotIn('best_holdout_loss', negative['policy_state'])

    def test_current_seal_reports_changed_consumer_without_rewriting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root, area, reference, pins = self.context_fixture(directory)
            dispatcher = root / 'scripts/nox_dispatcher_t855u.py'
            dispatcher.write_bytes(b'CURRENT_DIFFERENT_PRIVATE_SOURCE')
            with patch.object(preflight, 'ROOT', root), patch.object(preflight, 'AREA', area), \
                    patch.object(preflight, 'REFERENCE', reference), patch.object(preflight, 'REQUIREMENT_PINS', pins):
                result = preflight.context_projection()
            self.assertEqual(dispatcher.read_bytes(), b'CURRENT_DIFFERENT_PRIVATE_SOURCE')
        self.assertTrue(result['sealed_metadata_chain_verified'])
        self.assertFalse(result['all_declared_sources_match'])
        self.assertFalse(result['source_comparisons']['nox_dispatcher_t855u.py']['matches'])
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_unlisted_consumer_never_selects_an_arbitrary_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root, area, reference, pins = self.context_fixture(directory, unknown_consumer=True)
            with patch.object(preflight, 'ROOT', root), patch.object(preflight, 'AREA', area), \
                    patch.object(preflight, 'REFERENCE', reference), patch.object(preflight, 'REQUIREMENT_PINS', pins), \
                    patch.object(preflight, 'source_fact') as source:
                result = preflight.context_projection()
            source.assert_not_called()
        self.assertEqual(result['state'], 'CURRENT_SEAL_UNVERIFIED')
        self.assertFalse(result['sealed_metadata_chain_verified'])
        self.assertNotIn('private_credentials', json.dumps(result))

    def test_unknown_checkpoint_pointer_is_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.write(output / 'latest_checkpoint.json', {'directory': '../../PRIVATE_SECRET', 'manifest_sha256': '0' * 64})
            original = preflight.read
            with patch.object(preflight, 'OUTPUT', output), patch.object(preflight, 'read', wraps=original) as read:
                result = preflight.checkpoint_projection()
            self.assertEqual([call.args[0] for call in read.call_args_list], [output / 'latest_checkpoint.json'])
        self.assertEqual(result['state'], 'CHECKPOINT_METADATA_UNVERIFIED')
        self.assertEqual(result['payload_files_read'], 0)
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_reader_rejects_nonfinite_duplicate_and_unsafe_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / 'data'
            for raw in (b'{"x":NaN}', b'{"x":1,"x":2}'):
                data.write_bytes(raw)
                with self.assertRaises(preflight.ReadHold):
                    preflight.document(data)
            data.unlink()
            data.symlink_to('/etc/passwd')
            with self.assertRaises(OSError):
                preflight.read(data)
            data.unlink()
            os.mkfifo(data)
            with self.assertRaises(preflight.ReadHold):
                preflight.read(data)

    def test_barriers_distinguish_quality_source_and_physical_capacity(self):
        result = {'guard': {'state': 'INHIBITED', 'sample_is_fresh': False,
                'execution_reference_matches': True,
                'policy_state': {'inhibit': True, 'reason': 'HOLDOUT_REGRESSION',
                                 'disk_early_threshold_bytes': 12 * preflight.GIB}},
            'context': {'sealed_metadata_chain_verified': True, 'all_declared_sources_match': False},
            'requirements': {'source_pins_verified': True},
            'resources': {'raw_cgroup_headroom_bytes': 6 * preflight.GIB,
                          'disk_free_bytes': 17 * preflight.GIB, 'gpu1_free_mib': 4757},
            'checkpoint': {'state': 'CP55_METADATA_SHA_VERIFIED'}}
        findings = preflight.barriers(result)
        self.assertIn('STORED_GUARD_INHIBITED_HOLDOUT_REGRESSION', findings)
        self.assertIn('SEALED_RUNTIME_OR_CONSUMER_SOURCES_UNVERIFIED', findings)
        self.assertIn('RAW_CGROUP_HEADROOM_INSUFFICIENT_OR_UNKNOWN', findings)
        self.assertIn('GPU1_HEADROOM_INSUFFICIENT_OR_UNKNOWN', findings)
        self.assertNotIn('CHECKPOINT_DISK_HEADROOM_INSUFFICIENT_OR_UNKNOWN', findings)


    def ready_evidence(self, now):
        files = []
        for index, name in enumerate(preflight.CHECKPOINT_FILES):
            files.append({'name': name, 'bytes': 100 + index, 'sha256': f'{index + 1:064x}'})
        bundle = preflight.digest(json.dumps(files, sort_keys=True, separators=(',', ':')).encode())
        return {
            'resources': {
                'sampled_at_unix': now, 'telemetry_complete': True,
                'chat_inflight_observed': True, 'chat_inflight': False,
                'raw_cgroup_headroom_bytes': preflight.FULL_RESTAGE_BYTES,
                'disk_free_bytes': 12 * preflight.GIB, 'required_disk_bytes': 10 * preflight.GIB,
                'gpu1_free_mib': preflight.GPU1_FLOOR_MIB,
            },
            'checkpoint': {
                'pointer_sha256': 'a' * 64, 'manifest_sha256': 'b' * 64,
                'payload_files': files, 'payload_hashes_verified': True,
                'optimizer_scaler_rng_verified': True, 'bundle_sha256': bundle,
            },
            'holdout': {
                'dataset_sha256': 'c' * 64, 'sample_sha256': 'd' * 64,
                'sampled_at_unix': now, 'fresh': True, 'best_loss': 1.0,
                'candidate_loss': 0.9, 'regression_streak': 0,
                'guard_state': 'MONITORING', 'inhibit': False,
            },
            'source_seal': {'all_pins_match': True},
            'owner_control': {
                'stop_state_verified': True, 'stop_clear': True,
                'single_fenced_lease': True, 'lease_fresh': True,
                'handoff_verified': True,
                'pid_start_ticks': [{'role': 'lease_owner', 'pid': 123, 'start_ticks': 456, 'verified': True}],
                'trainer_stopped': True,
            },
            'rollback': {
                'immutable_pre_run_checkpoint_sha256': bundle,
                'independent_backup_sha256': 'e' * 64,
                'backup_verified': True, 'restore_probe_sha256': 'f' * 64,
                'restore_probe_passed': True, 'fresh': True,
            },
        }

    def test_default_admission_is_hold_and_never_issues_permission(self):
        decision = preflight.assess_admission({}, time.time())
        self.assertEqual(decision['state'], 'HOLD')
        self.assertTrue(decision['blockers'])
        self.assertFalse(decision['all_gates_pass'])
        self.assertTrue(decision['owner_gate_required'])
        self.assertFalse(decision['training_permission_issued'])

    def test_complete_evidence_still_requires_separate_owner_gate(self):
        now = time.time()
        decision = preflight.assess_admission(self.ready_evidence(now), now)
        self.assertEqual(decision, {
            'state': 'OWNER_GATE_REQUIRED', 'blockers': [],
            'all_gates_pass': True, 'owner_gate_required': True,
            'training_permission_issued': False,
        })

    def test_stale_or_unsafe_gate_evidence_fails_closed(self):
        now = time.time()
        mutations = (
            ('resource age', lambda e: e['resources'].update(sampled_at_unix=now - 31)),
            ('resource floor', lambda e: e['resources'].update(raw_cgroup_headroom_bytes=preflight.FULL_RESTAGE_BYTES - 1)),
            ('checkpoint omission', lambda e: e['checkpoint'].update(payload_files=e['checkpoint']['payload_files'][:-1])),
            ('holdout regression', lambda e: e['holdout'].update(regression_streak=2, candidate_loss=1.2)),
            ('STOP', lambda e: e['owner_control'].update(stop_clear=False)),
            ('unfenced lease', lambda e: e['owner_control'].update(single_fenced_lease=False)),
            ('PID reuse', lambda e: e['owner_control']['pid_start_ticks'][0].update(verified=False)),
            ('rollback missing', lambda e: e['rollback'].update(backup_verified=False)),
            ('source mismatch', lambda e: e['source_seal'].update(all_pins_match=False)),
        )
        for label, mutate in mutations:
            with self.subTest(gate=label):
                evidence = json.loads(json.dumps(self.ready_evidence(now)))
                mutate(evidence)
                decision = preflight.assess_admission(evidence, now)
                self.assertEqual(decision['state'], 'HOLD')
                self.assertFalse(decision['all_gates_pass'])
                self.assertFalse(decision['training_permission_issued'])

    def test_checkpoint_projection_hashes_every_required_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            cp = output / preflight.CP55
            cp.mkdir()
            hashes = {}
            for name in preflight.CHECKPOINT_FILES:
                payload = ('payload:' + name).encode()
                (cp / name).write_bytes(payload)
                hashes[name] = preflight.digest(payload)
            manifest_raw = json.dumps({'files_sha256': hashes}, sort_keys=True).encode()
            (cp / 'checkpoint_manifest.json').write_bytes(manifest_raw)
            manifest_sha = preflight.digest(manifest_raw)
            pointer_raw = json.dumps({'directory': preflight.CP55, 'manifest_sha256': manifest_sha},
                                     sort_keys=True).encode()
            (output / 'latest_checkpoint.json').write_bytes(pointer_raw)
            with patch.object(preflight, 'OUTPUT', output), \
                 patch.object(preflight, 'CP55_POINTER', preflight.digest(pointer_raw)), \
                 patch.object(preflight, 'CP55_MANIFEST', manifest_sha):
                result = preflight._checkpoint_payloads(time.time())
                self.assertTrue(result['payload_hashes_verified'])
                self.assertTrue(result['optimizer_scaler_rng_verified'])
                self.assertEqual({row['name'] for row in result['payload_files']}, set(preflight.CHECKPOINT_FILES))
                (cp / 'optimizer.pt').write_bytes(b'changed')
                changed = preflight._checkpoint_payloads(time.time())
        self.assertFalse(changed['payload_hashes_verified'])
        self.assertEqual(changed['state'], 'CHECKPOINT_PAYLOADS_UNVERIFIED')

    def test_holdout_requires_fresh_hashes_and_zero_regression_streak(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            now = time.time()
            self.write(root / 'state/owner_qwen_training_guard.json', {
                'state': 'MONITORING',
                'policy_state': {'holdout_dataset_sha256': 'a' * 64, 'holdout_sample_sha256': 'b' * 64,
                    'holdout_sampled_at': now, 'best_holdout_loss': 0.8,
                    'regression_streak': 0, 'inhibit': False},
                'checkpoint': {'holdout_loss': 0.7},
            })
            with patch.object(preflight, 'ROOT', root):
                result = preflight._holdout_projection(now)
            self.assertTrue(result['fresh'])
            self.assertEqual(result['dataset_sha256'], 'a' * 64)
            self.assertEqual(result['candidate_loss'], 0.7)
            with patch.object(preflight, 'ROOT', root):
                self.write(root / 'state/owner_qwen_training_guard.json', {
                    'state': 'INHIBITED', 'policy_state': {'regression_streak': 2},
                    'checkpoint': {'holdout_loss': 1.2},
                })
                stale = preflight._holdout_projection(now)
            self.assertFalse(stale['fresh'])
            self.assertIsNone(stale['sample_sha256'])

    def test_streaming_hash_is_bounded_and_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            leaf = root / 'payload'
            leaf.write_bytes(b'abc')
            self.assertEqual(preflight.file_digest(leaf, 3),
                             {'bytes': 3, 'sha256': preflight.digest(b'abc')})
            with self.assertRaises(preflight.ReadHold):
                preflight.file_digest(leaf, 2)
            link = root / 'link'
            link.symlink_to(leaf)
            with self.assertRaises(OSError):
                preflight.file_digest(link, 10)

    def test_receipt_write_is_private_atomic_and_once_per_request(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = {
                'schema': preflight.ADMISSION_SCHEMA, 'owner_request_id': '123',
                'state': 'HOLD', 'training_permission_issued': False,
                'decision': {'training_permission_issued': False},
            }
            result = preflight.write_admission_receipt(receipt, Path(directory))
            path = Path(result['path'])
            self.assertEqual(path.read_bytes(), json.dumps(receipt, sort_keys=True,
                separators=(',', ':'), allow_nan=False).encode())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(result['sha256'], preflight.digest(path.read_bytes()))
            with self.assertRaises(FileExistsError):
                preflight.write_admission_receipt(receipt, Path(directory))



    def test_owner_control_requires_one_unexpired_fenced_lease_and_pid_ticks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            now = time.time()
            lease = {
                'schema': 'NOX_OWNER_TRAINING_LEASE_V1', 'owner_request_id': '123',
                'source_sha256': 'a' * 40, 'state': 'ACTIVE', 'fenced': True,
                'fencing_token': 7, 'active_lease_count': 1, 'lease_id': 'lease-123',
                'sampled_at_unix': now, 'issued_at_unix': now - 2,
                'expires_at_unix': now + 30, 'owner_pid': 456,
                'owner_pid_start_ticks': 789, 'handoff_verified': True,
                'trainer_state': 'STOPPED', 'training_process_count': 0,
            }
            self.write(root / 'state/owner_training_lease.json', lease)
            with patch.object(preflight, 'LEASE_EVIDENCE', root / 'state/owner_training_lease.json'), \
                 patch.object(preflight, 'STOP_FLAGS', ()), \
                 patch.object(preflight, '_proc_start_ticks', return_value=789):
                good = preflight._owner_control_projection('123', 'a' * 40, now)
                self.assertTrue(good['single_fenced_lease'])
                self.assertTrue(good['handoff_verified'])
                self.assertTrue(good['trainer_stopped'])
                self.assertTrue(good['pid_start_ticks'][0]['verified'])
            lease['owner_pid_start_ticks'] = 790
            self.write(root / 'state/owner_training_lease.json', lease)
            with patch.object(preflight, 'LEASE_EVIDENCE', root / 'state/owner_training_lease.json'), \
                 patch.object(preflight, 'STOP_FLAGS', ()), \
                 patch.object(preflight, '_proc_start_ticks', return_value=789):
                mismatched = preflight._owner_control_projection('123', 'a' * 40, now)
            self.assertFalse(mismatched['single_fenced_lease'])
            self.assertEqual(mismatched['pid_start_ticks'], [])

    def test_rollback_projection_rehashes_independent_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            now = time.time()
            backup = root / 'state/training_backups/123/checkpoint.bundle'
            backup.parent.mkdir(parents=True)
            backup.write_bytes(b'immutable rollback bytes')
            bundle = 'a' * 64
            self.write(root / 'state/training_rollback_evidence.json', {
                'schema': 'NOX_TRAINING_ROLLBACK_EVIDENCE_V1', 'owner_request_id': '123',
                'sampled_at_unix': now, 'immutable_pre_run_checkpoint_sha256': bundle,
                'independent_backup_path': 'state/training_backups/123/checkpoint.bundle',
                'independent_backup_sha256': preflight.digest(backup.read_bytes()),
                'restore_probe_sha256': 'b' * 64, 'restore_probe_passed': True,
            })
            with patch.object(preflight, 'ROOT', root), \
                 patch.object(preflight, 'ROLLBACK_EVIDENCE', root / 'state/training_rollback_evidence.json'):
                good = preflight._rollback_projection('123', {'bundle_sha256': bundle}, now)
                self.assertTrue(good['backup_verified'])
                self.assertTrue(good['restore_probe_passed'])
                backup.write_bytes(b'changed bytes')
                bad = preflight._rollback_projection('123', {'bundle_sha256': bundle}, now)
            self.assertFalse(bad['backup_verified'])

    def test_stop_flag_is_never_reported_clear(self):
        with tempfile.TemporaryDirectory() as directory:
            stop = Path(directory) / 'STOP'
            stop.write_text('hold')
            with patch.object(preflight, 'ROOT', Path(directory)), \
                 patch.object(preflight, 'STOP_FLAGS', (stop,)):
                result = preflight._stop_projection()
        self.assertTrue(result['stop_state_verified'])
        self.assertFalse(result['stop_clear'])
        self.assertEqual(result['active_stop_flags'], ['STOP'])



if __name__ == '__main__':
    unittest.main()
