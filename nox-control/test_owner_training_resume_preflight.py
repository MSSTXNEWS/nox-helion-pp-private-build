"""Read-only readiness must distinguish saved quality, source pins and resources."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
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


if __name__ == '__main__':
    unittest.main()
