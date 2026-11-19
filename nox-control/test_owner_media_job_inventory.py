import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('media_inventory_tested', Path(__file__).with_name('owner_media_job_inventory.py'))
m = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(m)
RUNTIME = Path(__file__).with_name('owner_media_runtime.py')
JOB = '1' * 32


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.patch = mock.patch.multiple(m, DIRECTORY=self.directory, RUNTIME=RUNTIME)
        self.patch.start(); self.addCleanup(self.patch.stop)

    def write_job(self, state='COMPLETED'):
        path = self.directory / (JOB + '.json')
        path.write_text(json.dumps({'schema': 'NOX_OWNER_MEDIA_JOB_V1', 'id': JOB, 'state': state,
                                   'request': {'prompt': 'private text never export'}, 'reason': 'private failure'}))
        path.chmod(0o600)
        return path

    def test_valid_json_and_persistent_ca8_lock_are_distinguished(self):
        self.write_job()
        lock = self.directory / (JOB + '.lock'); lock.write_bytes(b''); lock.chmod(0o600)
        result = m.inspect()
        self.assertTrue(result['observation_complete'])
        self.assertEqual(result['category_counts'], {'JOB_JSON': 1, 'JOB_LOCK': 1})
        self.assertEqual(result['strict_smoke51_predicate_failures'], 1)
        row = next(x for x in result['entries'] if x['category'] == 'JOB_LOCK')
        self.assertTrue(row['companion_json_name_present']); self.assertTrue(row['regular_owner600_empty_single_link'])
        self.assertEqual(result['parsed_state_counts'], {'COMPLETED': 1})
        self.assertTrue(result['directory_metadata_stable'])

    def test_private_names_body_unknown_state_and_symlink_target_never_export(self):
        self.write_job('private unknown state')
        (self.directory / 'private diary name').write_text('private unrelated contents')
        (self.directory / 'foreign-link').symlink_to('/private/unknown-target')
        result = m.inspect(); output = json.dumps(result)
        for word in ('private', 'diary', 'unknown-target', JOB):
            self.assertNotIn(word, output)
        self.assertEqual(result['parsed_state_counts'], {'OTHER_STATE': 1})
        self.assertEqual(result['strict_smoke51_predicate_failures'], 2)

    def test_atomic_temp_and_incomplete_json_remain_observations_not_admission(self):
        path = self.directory / (JOB + '.json'); path.write_bytes(b'{'); path.chmod(0o600)
        (self.directory / '.media-abcdefgh').write_bytes(b'private')
        result = m.inspect()
        self.assertFalse(result['generation_admission_authorized'])
        self.assertEqual(result['category_counts']['RUNTIME_ATOMIC_TEMP'], 1)
        self.assertEqual(result['json_records_not_parsed'], 1)
        self.assertEqual(next(x for x in result['entries'] if x['category']=='JOB_JSON')['read_state'], 'INVALID_OR_PARTIAL_JSON')

    def test_total_read_budget_and_metadata_entry_bound_are_enforced(self):
        self.write_job()
        with mock.patch.object(m, 'MAX_TOTAL_JSON', 1):
            result = m.inspect()
        self.assertEqual(result['json_bytes_read'], 0)
        self.assertEqual(result['json_records_not_parsed'], 1)
        with mock.patch.object(m, 'MAX_ENTRIES', 0):
            result = m.inspect()
        self.assertEqual(result['reason'], 'HOLD_MEDIA_JOB_INVENTORY_ENTRY_BOUND')

    def test_source_mismatch_prevents_directory_scan(self):
        with mock.patch.object(m, 'RUNTIME_SHA', '0' * 64), mock.patch.object(m.os, 'scandir') as scan:
            result = m.inspect()
        self.assertEqual(result['reason'], 'HOLD_MEDIA_JOB_INVENTORY_RUNTIME_PIN')
        scan.assert_not_called()

    def test_deadline_inside_json_read_is_not_swallowed(self):
        self.write_job(); original = m.read_regular
        def fail(path, limit):
            if path == RUNTIME:
                return original(path, limit)
            raise m.Deadline('HOLD_MEDIA_JOB_INVENTORY_DEADLINE')
        with mock.patch.object(m, 'read_regular', side_effect=fail):
            result = m.inspect()
        self.assertFalse(result['observation_complete'])
        self.assertEqual(result['reason'], 'HOLD_MEDIA_JOB_INVENTORY_DEADLINE')


if __name__ == '__main__':
    unittest.main()
