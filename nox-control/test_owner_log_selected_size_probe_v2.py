import base64
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import zlib

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('selected_log_probe_v2_test', HERE / 'owner_log_selected_size_probe_v2.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class SelectedLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.logs = self.root / 'logs'; self.logs.mkdir()
        self.receipt = self.root / 'state/owner_storage/log_probe_6909108384.json'
        self.receipt.parent.mkdir(parents=True)
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.bundle = {name: base64.b64encode((HERE / name).read_bytes()).decode()
                       for name in (m.CORE_NAME, m.PROC_NAME)}
        self.stack.enter_context(patch.object(m, 'BUNDLE', self.bundle))
        self.core = m.dependencies()
        self.core.ROOT = self.root
        self.core.stopped = lambda: False
        for key, value in {'ROOT': self.root, 'INVENTORY': self.receipt, 'RATE': 10**12}.items():
            self.stack.enter_context(patch.object(m, key, value))
        self.paths, self.rows, self.payloads = [], [], []
        for index in range(3):
            path = self.logs / ('private_topic_%d.log' % index)
            raw = ('SYNTHETIC PRIVATE TEXT %d\n' % index).encode() * 4096
            path.write_bytes(raw); os.utime(path, (time.time() - 28800,) * 2)
            info = path.stat(); key = m.digest(str(path).encode())[:24]
            self.paths.append(path); self.payloads.append(raw)
            self.rows.append({'file_id': key, '_path': str(path), '_identity': list(self.core.identity(info)),
                'root_label': 'NOX_LOGS', 'logical_bytes': len(raw), 'allocated_bytes': info.st_blocks * 512,
                'uid': os.geteuid(), 'link_count': 1, 'historical_diagnostics_protected': False,
                'already_compressed': False, 'duplicate_inode_alias': False, 'device': info.st_dev,
                'inode': info.st_ino, 'known_label': None, 'rotation': False})
        self.stack.enter_context(patch.object(m, 'SELECTED', {r['file_id']: r['logical_bytes'] for r in self.rows}))
        self.document = {'schema': 'NOX_OWNER_LOG_SPACE_PROBE_V1', 'request': m.INVENTORY_REQUEST,
            'source_sha': m.INVENTORY_SOURCE, 'actual_freed_bytes': 0, 'deletion_authorized': False,
            'rows': self.rows}
        self.set_inventory()

    def set_inventory(self):
        raw = m.encoded(self.document); self.receipt.write_bytes(raw); self.receipt.chmod(0o600)
        self.stack.enter_context(patch.object(m, 'INVENTORY_SHA', m.digest(raw)))

    def test_exact_private_inventory_selects_only_fixed_ids_and_no_rotation_claim(self):
        rows = m.inventory_rows(self.core, time.monotonic() + 2)
        self.assertEqual([r['file_id'] for r in rows], [r['file_id'] for r in self.rows])
        self.assertTrue(all(r['known_label'] is None and r['rotation'] is False for r in rows))
        self.document['rows'].append(dict(self.rows[0])); self.set_inventory()
        with self.assertRaisesRegex(m.Hold, 'INVENTORY_SELECTION'):
            m.inventory_rows(self.core, time.monotonic() + 2)

    def test_wrong_receipt_pin_or_context_rejected_before_log_read(self):
        with patch.object(m, 'INVENTORY_SHA', '0' * 64), self.assertRaisesRegex(m.Hold, 'INVENTORY_SHA'):
            m.inventory_rows(self.core, time.monotonic() + 2)
        self.document['source_sha'] = 'b' * 40; self.set_inventory()
        with self.assertRaisesRegex(m.Hold, 'INVENTORY_CONTEXT'):
            m.inventory_rows(self.core, time.monotonic() + 2)

    def test_private_receipt_and_selected_parent_scope_enforced(self):
        self.receipt.chmod(0o644)
        with self.assertRaisesRegex(m.Hold, 'INVENTORY_SCOPE'):
            m.inventory_rows(self.core, time.monotonic() + 2)
        self.receipt.chmod(0o600)
        self.document['rows'][0]['_path'] = str(self.root / 'elsewhere.log'); self.set_inventory()
        with self.assertRaisesRegex(m.Hold, 'SELECTED_SCOPE'):
            m.inventory_rows(self.core, time.monotonic() + 2)

    def test_stable_unknown_nonrotation_gets_exact_gzip_count_and_hash_without_copy(self):
        row = {**self.rows[0], 'process_visibility_before': 'PARTIAL'}
        before_names = sorted(str(p) for p in self.root.rglob('*'))
        value = m.measure(self.core, row, time.monotonic() + 2, {'bytes': 0})
        compressor = zlib.compressobj(level=1, wbits=31)
        expected = compressor.compress(self.payloads[0]) + compressor.flush()
        self.assertEqual(value['state'], 'FULL_STABLE_GZIP_SIZE_MEASURED')
        self.assertEqual(value['gzip_stream_bytes'], len(expected))
        self.assertEqual(value['full_sha256'], hashlib.sha256(self.payloads[0]).hexdigest())
        self.assertEqual(value['process_visibility_before'], 'PARTIAL')
        self.assertFalse(value['age_proves_inactivity'])
        self.assertFalse(value['deletion_authorized'])
        self.assertFalse(value['compressed_copy_written'])
        self.assertEqual(before_names, sorted(str(p) for p in self.root.rglob('*')))
        self.assertEqual(self.paths[0].read_bytes(), self.payloads[0])
        self.assertNotIn('private_topic', json.dumps(value))
        self.assertNotIn('SYNTHETIC PRIVATE', json.dumps(value))

    def test_content_replacement_invalidates_hash_proof(self):
        original = os.read; changed = False
        def read(fd, count):
            nonlocal changed
            data = original(fd, count)
            if data and not changed:
                replacement = self.logs / 'swap'; replacement.write_bytes(self.payloads[0])
                os.replace(replacement, self.paths[0]); changed = True
            return data
        with patch.object(os, 'read', read):
            value = m.measure(self.core, self.rows[0], time.monotonic() + 2, {'bytes': 0})
        self.assertEqual(value['state'], 'ESTIMATE_HELD_OR_PARTIAL')
        self.assertNotIn('full_sha256', value)
        self.assertNotIn('estimated_allocated_delta_upper_bound', value)

    def test_active_reference_skips_content_and_budget_failures_are_bounded(self):
        with patch.object(self.core, 'open_path', side_effect=AssertionError('content must not open')):
            value = m.measure(self.core, {**self.rows[0], 'active_reference_before': True}, time.monotonic() + 2, {'bytes': 0})
        self.assertEqual(value['reason'], 'ACTIVE_REFERENCE_OBSERVED')
        value = m.measure(self.core, self.rows[0], time.monotonic() - 1, {'bytes': 0})
        self.assertEqual(value['state'], 'ESTIMATE_HELD_OR_PARTIAL')
        value = m.measure(self.core, self.rows[0], time.monotonic() + 2, {'bytes': m.MAX_CONTENT})
        self.assertIn('CONTENT_BUDGET', value['reason'])

    def test_symlink_parent_never_opens_arbitrary_target(self):
        actual = self.root / 'other'; self.logs.rename(actual); self.logs.symlink_to(actual, target_is_directory=True)
        value = m.measure(self.core, self.rows[0], time.monotonic() + 2, {'bytes': 0})
        self.assertEqual(value['state'], 'ESTIMATE_HELD_OR_PARTIAL')
        self.assertNotIn('full_sha256', value)

    def test_public_aggregate_partial_visibility_never_proves_deletion_or_exposes_paths(self):
        scan = {'complete': False, 'references': {}}
        with patch.object(self.core, 'process_scan', return_value=scan):
            result = m.analyze(self.core)
        self.assertEqual(result['full_stable_estimate_count'], 3)
        self.assertGreater(result['estimated_reclaim_upper_bound_bytes'], 0)
        self.assertEqual(result['actual_freed_bytes'], 0)
        self.assertEqual(result['metadata_receipts_written'], 0)
        self.assertFalse(result['deletion_authorized'])
        self.assertTrue(all(not row['fd_maps_absence_verified'] for row in result['rows']))
        self.assertNotIn('private_topic', json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_after_reference_excludes_nominal_gain_and_dependency_tampering_rejected(self):
        key = self.rows[0]['file_id']
        scans = [{'complete': False, 'references': {}},
                 {'complete': False, 'references': {key: [{'pid': 123, 'kind': 'FD', 'access': 'READ_ONLY'}]}}]
        with patch.object(self.core, 'process_scan', side_effect=scans):
            result = m.analyze(self.core)
        self.assertEqual(result['full_stable_estimate_count'], 2)
        bad = {**self.bundle, m.CORE_NAME: base64.b64encode(b'raise RuntimeError("not executed")').decode()}
        with patch.object(m, 'BUNDLE', bad), self.assertRaisesRegex(m.Hold, 'SOURCE_PIN'):
            m.dependencies()

    def test_ctime_only_refresh_uses_full_stable_hash_without_rewriting_inventory(self):
        old_receipt = self.receipt.read_bytes()
        old_identity = list(self.rows[0]['_identity'])
        time.sleep(.002)
        os.chmod(self.paths[0], self.paths[0].stat().st_mode & 0o777)
        self.assertNotEqual(self.paths[0].stat().st_ctime_ns, old_identity[4])
        value = m.measure(self.core, self.rows[0], time.monotonic() + 2, {'bytes': 0})
        self.assertEqual(value['state'], 'FULL_STABLE_GZIP_SIZE_MEASURED')
        self.assertEqual(value['preimage_drift_fields'], ['ctime_ns'])
        self.assertTrue(value['ctime_only_preimage_refresh_accepted'])
        self.assertEqual(value['full_sha256'], hashlib.sha256(self.payloads[0]).hexdigest())
        self.assertEqual(self.rows[0]['_identity'], old_identity)
        self.assertEqual(self.receipt.read_bytes(), old_receipt)
        self.assertFalse(value['deletion_authorized'])
        self.assertNotIn(str(self.paths[0]), json.dumps(value))

    def test_any_other_inventory_identity_drift_is_reported_and_held_before_content(self):
        original = tuple(self.rows[0]['_identity'])
        for index, label in enumerate(m.IDENTITY_FIELDS):
            if label == 'ctime_ns':
                continue
            with self.subTest(field=label):
                altered = list(original); altered[index] += 1; altered[4] += 1
                with patch.object(self.core, 'identity', return_value=tuple(altered)), \
                     patch.object(m.os, 'read', side_effect=AssertionError('content read forbidden')):
                    value = m.measure(self.core, dict(self.rows[0]), time.monotonic() + 2, {'bytes': 0})
                self.assertEqual(value['state'], 'ESTIMATE_HELD_OR_PARTIAL')
                self.assertEqual(value['reason'], 'HOLD_SELECTED_LOG_CURRENT_PREIMAGE_CHANGED')
                self.assertIn(label, value['preimage_drift_fields'])
                self.assertEqual(value['observed_preimage_metadata'][label], altered[index])
                self.assertEqual(value['expected_inventory_metadata'][label], original[index])
                self.assertEqual(value['content_bytes_read'], 0)
                self.assertFalse(value['ctime_only_preimage_refresh_accepted'])

    def test_ctime_drift_during_read_invalidates_the_refreshed_preimage(self):
        time.sleep(.002)
        os.chmod(self.paths[0], self.paths[0].stat().st_mode & 0o777)
        original = os.read; changed = False
        def read(fd, count):
            nonlocal changed
            raw = original(fd, count)
            if raw and not changed:
                time.sleep(.002)
                os.chmod(self.paths[0], self.paths[0].stat().st_mode & 0o777)
                changed = True
            return raw
        with patch.object(os, 'read', read):
            value = m.measure(self.core, self.rows[0], time.monotonic() + 2, {'bytes': 0})
        self.assertEqual(value['state'], 'ESTIMATE_HELD_OR_PARTIAL')
        self.assertTrue(value['ctime_only_preimage_refresh_accepted'])
        self.assertEqual(value['reason'], 'HOLD_SELECTED_LOG_CONTENT_CHANGED')
        self.assertNotIn('full_sha256', value)

    def test_final_observation_compares_fresh_preimage_not_obsolete_ctime(self):
        time.sleep(.002)
        for path in self.paths:
            os.chmod(path, path.stat().st_mode & 0o777)
        with patch.object(self.core, 'process_scan', return_value={'complete': False, 'references': {}}):
            value = m.analyze(self.core)
        self.assertEqual(value['schema'], 'NOX_OWNER_SELECTED_LOG_SIZE_PROBE_V2')
        self.assertEqual(value['ctime_only_refresh_count'], 3)
        self.assertEqual(value['full_stable_estimate_count'], 3)
        self.assertTrue(all(row['metadata_stable_after_observation'] for row in value['rows']))
        self.assertTrue(all(row['preimage_drift_fields'] == ['ctime_ns'] for row in value['rows']))
        self.assertTrue(all(not row['fd_maps_absence_verified'] for row in value['rows']))
        self.assertEqual(value['actual_freed_bytes'], 0)
        self.assertFalse(value['deletion_authorized'])


if __name__ == '__main__':
    unittest.main()
