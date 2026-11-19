import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import time
import types
import unittest
from unittest.mock import patch
import zlib

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('log_space_probe_test_module', HERE / 'owner_log_space_probe.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class LogProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.logs = self.root / 'logs'; self.logs.mkdir()
        self.patchers = [patch.object(m, 'ROOT', self.root),
            patch.object(m, 'ROOTS', (('NOX_LOGS', self.logs, 2),)),
            patch.object(m, 'stopped', return_value=False), patch.object(m, 'RATE', 10**12)]
        for item in self.patchers:
            item.start(); self.addCleanup(item.stop)

    def log(self, name='train_volta_t866u.log.3', data=None):
        path = self.logs / name; path.parent.mkdir(parents=True, exist_ok=True)
        data = data if data is not None else b'SYNTHETIC PRIVATE TRAINING TEXT\n' * 4000
        path.write_bytes(data)
        os.utime(path, (time.time() - 7200, time.time() - 7200))
        row = m.metadata('NOX_LOGS', path, path.stat(), time.time())
        row.update(duplicate_inode_alias=False, active_reference_before=False, process_visibility_before='PARTIAL')
        return path, data, row

    def test_known_scope_rotation_and_fresh_ctime_are_explicit(self):
        _, _, row = self.log()
        self.assertEqual(row['known_label'], 'TRAINER_LOG')
        self.assertTrue(row['historical_diagnostics_protected'])
        self.assertTrue(row['old_rotation_for_estimation'])
        self.assertLess(row['ctime_age_seconds'], 20)
        _, _, nested = self.log('private_user/train_volta_t866u.log.3')
        self.assertIsNone(nested['known_label'])
        _, _, current = self.log('train_volta_t866u.log')
        self.assertFalse(current['rotation'])
        _, _, packed = self.log('train_volta_t866u.log.3.gz')
        self.assertTrue(packed['already_compressed'])

    def test_inventory_bounds_rows_and_deduplicates_allocated_inodes(self):
        path, _, _ = self.log()
        os.link(path, self.logs / 'proxy.log.3')
        (self.logs / 'link.log.4').symlink_to(path)
        rows, report = m.inventory(time.monotonic() + 2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(row['duplicate_inode_alias'] for row in rows), 1)
        self.assertEqual(report['groups']['NOX_LOGS']['allocated_bytes'], path.stat().st_blocks * 512)
        self.assertEqual(report['counts']['symlinks_skipped'], 1)
        for index in range(140):
            self.log('unknown_%d.log.3' % index, b'x')
        rows, report = m.inventory(time.monotonic() + 2)
        self.assertEqual(len(rows), m.MAX_ROWS)
        self.assertTrue(report['rows_truncated'])

    def test_full_gzip_count_hash_and_partial_visibility_without_writes(self):
        path, raw, row = self.log()
        before = path.read_bytes()
        value = m.estimate(row, time.monotonic() + 2, {'bytes': 0})
        gz = zlib.compressobj(level=1, wbits=31)
        expected = gz.compress(raw) + gz.flush()
        self.assertEqual(value['state'], 'FULL_STABLE_GZIP_SIZE_MEASURED')
        self.assertEqual(value['gzip_stream_bytes'], len(expected))
        self.assertEqual(value['full_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(value['process_visibility'], 'PARTIAL')
        self.assertFalse(value['deletion_authorized'])
        self.assertFalse(value['compressed_copy_written'])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(self.logs.iterdir()), [path])
        self.assertNotIn(raw[:20].decode(), json.dumps(value))

    def test_active_or_nonknown_or_multilink_log_never_read(self):
        _, _, row = self.log()
        for mutation in ({'active_reference_before': True}, {'known_label': None}, {'link_count': 2}, {'already_compressed': True}):
            with patch.object(m, 'open_path', side_effect=AssertionError('content open forbidden')):
                value = m.estimate({**row, **mutation}, time.monotonic() + 2, {'bytes': 0})
            self.assertEqual(value['state'], 'NOT_ESTIMATED')

    def test_atomic_name_replacement_invalidates_full_estimate(self):
        path, raw, row = self.log()
        original = os.read; replaced = False
        def read(fd, count):
            nonlocal replaced
            data = original(fd, count)
            if data and not replaced:
                replacement = path.with_name('temporary')
                replacement.write_bytes(raw); os.replace(replacement, path); replaced = True
            return data
        with patch.object(os, 'read', read):
            value = m.estimate(row, time.monotonic() + 2, {'bytes': 0})
        self.assertEqual(value['state'], 'ESTIMATE_HELD_OR_PARTIAL')
        self.assertNotIn('full_sha256', value)
        self.assertNotIn('estimated_allocated_delta_upper_bound', value)

    def test_deadline_and_byte_budget_return_partial_without_content_export(self):
        _, _, row = self.log()
        value = m.estimate(row, time.monotonic() - 1, {'bytes': 0})
        self.assertEqual(value['state'], 'ESTIMATE_HELD_OR_PARTIAL')
        value = m.estimate(row, time.monotonic() + 1, {'bytes': m.MAX_INPUT})
        self.assertEqual(value['reason'], 'CONTENT_BYTE_BUDGET')

    def test_proc_helper_pin_and_total_raw_metadata_bound(self):
        bundle = {m.HELPER: base64.b64encode((HERE / m.HELPER).read_bytes()).decode()}
        with patch.object(m, 'BUNDLE', bundle):
            meter = {'bytes': 0}; helper = m.proc_helper(meter)
        path = self.root / 'pseudo'; path.write_bytes(b'A' * 100)
        directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with patch.object(m, 'MAX_METADATA', 32):
                with self.assertRaises(helper.ProbeBudget):
                    helper.read_at(directory, 'pseudo', 200)
            self.assertEqual(meter['bytes'], 32)
        finally:
            os.close(directory)
        with patch.object(m, 'BUNDLE', {m.HELPER: base64.b64encode(b'bad').decode()}):
            with self.assertRaisesRegex(m.ProbeHold, 'PROC_HELPER_PIN'):
                m.proc_helper({'bytes': 0})

    def test_public_projection_keeps_unknown_paths_private_and_no_fake_reclaim(self):
        self.log()
        hidden = 'private_filename_contains_chat_topic.log.3'
        self.log(hidden, b'PRIVATE LOG TEXT')
        scan = {'complete': False, 'scope': 'CURRENT_PROC_MOUNT_VISIBLE_PROCESSES', 'pids_seen': 1,
                'counts': {}, 'errors': [{'pid': 123, 'errors': [{'errno': 13}]}], 'references': {},
                'uid_or_namespace_exclusions_applied': False}
        with patch.object(m, 'proc_helper', return_value=types.SimpleNamespace()), patch.object(m, 'process_scan', return_value=scan):
            public, private = m.analyze()
        self.assertNotIn(hidden, json.dumps(public))
        self.assertIn(hidden, json.dumps(private))
        self.assertNotIn('PRIVATE LOG TEXT', json.dumps(private))
        self.assertEqual(public['actual_freed_bytes'], 0)
        self.assertFalse(public['deletion_authorized'])
        self.assertGreater(public['estimated_reclaim_upper_bound_bytes'], 0)
        self.assertTrue(all(not row['fd_maps_absence_verified'] for row in public['rows']))
        self.assertLess(len(m.encoded(public)), m.MAX_METADATA)

    def test_private_receipt_is_0600_verified_exclusive_and_not_log_backup(self):
        parent = self.root / 'state/owner_storage'; parent.mkdir(parents=True, mode=0o700)
        value = {'rows': [{'_path': '/private/unknown.log.3', 'logical_bytes': 1}], 'actual_freed_bytes': 0}
        path, sha = m.private_receipt(value, '1234567890', 'a' * 40)
        path = Path(path)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), sha)
        with self.assertRaises(FileExistsError):
            m.private_receipt(value, '1234567890', 'a' * 40)
        parent.chmod(0o755)
        with self.assertRaisesRegex(m.ProbeHold, 'RECEIPT_DIRECTORY'):
            m.private_receipt(value, '1234567891', 'a' * 40)


if __name__ == '__main__':
    unittest.main()
