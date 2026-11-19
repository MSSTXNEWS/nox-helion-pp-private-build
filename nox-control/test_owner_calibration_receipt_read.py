import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import types
import unittest
from unittest.mock import patch

import owner_calibration_receipt_read as entry


class FakeStatus:
    ROOT = Path('/unused')

    def __init__(self, pointer, receipt=None):
        self.pointer = pointer
        self.receipt = receipt
        self.admissions = []
        self.snapshots = []
        self.reject = False

    def context_value(self, value):
        if not isinstance(value, dict) or set(value) != {'request', 'source_sha', 'receipt_sha256'}:
            raise ValueError('bad context')
        return dict(value)

    def document(self, path, maximum=262144):
        if path.name == 'owner_training_admission.json':
            return copy.deepcopy(self.pointer), 'a'*64
        if self.receipt is None:
            raise FileNotFoundError()
        return copy.deepcopy(self.receipt), 'b'*64

    def admission(self, context):
        self.admissions.append(context)
        if self.reject:
            raise RuntimeError('HOLD_TRAINING_STATUS_SOURCE_CHANGED')
        return {}, self.pointer

    def snapshot(self, context):
        self.snapshots.append(context)
        return {'schema': 'NOX_OWNER_CURRENT_TRAINING_EVIDENCE_V1', 'state': 'HELD_AFTER_FAILURE',
                'global_step': 5, 'optimizer_steps': 0, 'positive_optimizer_steps_verified': False,
                'private': 'SECRET', 'current_run': None}


class ReceiptReadTests(unittest.TestCase):
    def test_projection_keeps_exact_scaler_counts_but_no_ciphertext_logs_or_paths(self):
        fake = FakeStatus({})
        record = {'schema': 'NOX_OWNER_TRAINING_RESUME_V1', 'state': 'HOLD_TRAINING_AMP_CALIBRATION',
            'training_started': True, 'error': 'HOLD_AMP_CALIBRATION_TERMINAL_SCOPE',
            'ciphertext': 'SECRET_CIPHER', 'raw_log': 'SECRET_LOG', 'path': '/SECRET_PATH',
            'steps': [{'kind': 'saved_optimizer_and_scaler_numeric_projection', 'data': {
                'schema': 'NOX_OWNER_SAVED_AMP_STATE_V1', 'state': 'SAVED_ZERO_UPDATE_OPTIMIZER_AND_SCALER_VERIFIED',
                'optimizer_parameter_count': 42, 'optimizer_parameter_counts': [42, 0],
                'optimizer_empty_parameter_groups': 1, 'optimizer_state_entries': 0,
                'scaler': {'scale': 2048.0, 'growth_factor': 2.0, 'backoff_factor': .5,
                           'growth_interval': 2000, 'growth_tracker': 0, 'private': 'SECRET'},
                'files_sha256': {'/SECRET': 'SECRET'}, 'cuda_initialized': False, 'files_modified': False}}]}
        projected = entry.receipt_projection(fake, 'calibration', record)
        self.assertNotIn('SECRET', json.dumps(projected))
        proof = projected['saved_scaler_numeric_proof']
        self.assertEqual(proof['optimizer_parameter_counts'], [42, 0])
        self.assertEqual(proof['scaler']['scale'], 2048.0)
        self.assertTrue(projected['training_started'])

    def test_exact_receipts_reject_other_attempt_and_preserve_full_hash(self):
        fake = FakeStatus({}, {'schema': 'NOX_OWNER_TRAINING_RESUME_V1',
            'request': '1', 'source_sha': entry.TARGET_SOURCE})
        public, private = entry.read_receipts(fake)
        self.assertFalse(private)
        for row in public.values():
            self.assertEqual(row['sha256'], 'b'*64)
            self.assertEqual(row['read_state'], 'HOLD')
            self.assertEqual(row['reason'], 'HOLD_CALIBRATION_RECEIPT_READ_SCOPE')

    def test_original_pointer_uses_sealed_origin_even_if_new_attempt_exists(self):
        fake = FakeStatus({'request': entry.ORIGIN['request'], 'source_sha': entry.ORIGIN['source_sha']})
        result = entry.current_training(fake, {'calibration': ({'state': 'HOLD'}, 'b'*64)})
        self.assertEqual(result['context'], entry.ORIGIN)
        self.assertEqual(fake.admissions, [entry.ORIGIN, entry.ORIGIN])
        self.assertNotIn('SECRET', json.dumps(result))

    def test_failed_current_attempt_can_be_observed_without_continuation_claim(self):
        pointer = {'request': entry.TARGET_REQUEST, 'source_sha': entry.TARGET_SOURCE, 'max_steps': 20}
        fake = FakeStatus(pointer)
        value = {'admission': pointer, 'state': 'HOLD_TRAINING_AMP_CALIBRATION'}
        result = entry.current_training(fake, {'calibration': (value, 'b'*64)})
        self.assertEqual(result['state'], 'VERIFIED_CURRENT_CONTEXT_READ_ONLY')
        self.assertEqual(result['context']['receipt_sha256'], 'b'*64)
        self.assertFalse(result['continuation_admitted_by_reader'])
        self.assertEqual(result['training']['optimizer_steps'], 0)
        self.assertFalse(result['global_process_coverage_verified'])

    def test_admission_mismatch_and_source_rejection_do_not_call_snapshot(self):
        pointer = {'request': entry.TARGET_REQUEST, 'source_sha': entry.TARGET_SOURCE, 'max_steps': 20}
        fake = FakeStatus(pointer)
        result = entry.current_training(fake, {'calibration': ({'admission': {}}, 'b'*64)})
        self.assertEqual(result['reason'], 'HOLD_CALIBRATION_RECEIPT_CURRENT_ADMISSION')
        self.assertFalse(fake.admissions)
        fake.reject = True
        result = entry.current_training(fake, {'calibration': ({'admission': pointer}, 'b'*64)})
        self.assertEqual(result['reason'], 'HOLD_TRAINING_STATUS_SOURCE_CHANGED')
        self.assertFalse(fake.snapshots)

    def test_later_pointer_change_invalidates_observation(self):
        fake = FakeStatus({'request': entry.ORIGIN['request'], 'source_sha': entry.ORIGIN['source_sha']})
        original = fake.document
        calls = 0
        def changed(*args):
            nonlocal calls
            calls += 1
            value, sha = original(*args)
            return value, sha if calls == 1 else 'c'*64
        fake.document = changed
        result = entry.current_training(fake, {})
        self.assertEqual(result['reason'], 'HOLD_CALIBRATION_RECEIPT_POINTER_CHANGED')
        self.assertNotIn('context', result)
        self.assertNotIn('training', result)

    def test_all_bundle_bytes_are_checked_before_any_module_executes(self):
        first = b"raise AssertionError('MUST_NOT_EXECUTE')\n"
        pins = {'owner_native_repair': hashlib.sha256(first).hexdigest(), 'owner_training_status': '0'*64}
        bundle = {'owner_native_repair.py': base64.b64encode(first).decode(),
                  'owner_training_status.py': base64.b64encode(b'pass\n').decode()}
        with patch.object(entry, 'PINS', pins), patch.object(entry, 'BUNDLE', bundle):
            with self.assertRaisesRegex(RuntimeError, '^HOLD_CALIBRATION_RECEIPT_READ_BUNDLE$'):
                entry.dependencies()

    def test_actual_pinned_modules_load_without_invoking_any_main(self):
        bundle = {name+'.py': base64.b64encode(Path(name+'.py').read_bytes()).decode() for name in entry.PINS}
        with patch.object(entry, 'BUNDLE', bundle):
            status, helper = entry.dependencies()
        self.assertEqual(status.SCHEMA, 'NOX_OWNER_CURRENT_TRAINING_EVIDENCE_V1')
        self.assertEqual(helper.SERVICE, 'nox-train-volta-t866u')
        self.assertEqual(hashlib.sha256(Path('owner_training_status.py').read_bytes()).hexdigest(), entry.PINS['owner_training_status'])


if __name__ == '__main__':
    unittest.main()
