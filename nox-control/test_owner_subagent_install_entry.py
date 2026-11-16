import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import owner_subagent_install_entry as entry
import owner_subagent_dispatcher as binding


class InstallSafetyTests(unittest.TestCase):
    def test_training_hold_exports_only_hash_metadata_and_exact_failure_request(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            flag = state/'TRAIN_HOLD.flag'
            with patch.object(entry, 'STATE', state):
                flag.write_bytes(b'OWNER_HYBRID_FAILED request=6906453807\n')
                row = entry.training_hold_observation()
                self.assertEqual(row['classification'], 'OWNER_HYBRID_FAILED')
                self.assertEqual(row['request'], '6906453807')
                self.assertEqual(row['sha256'], entry.digest(flag.read_bytes()))
                flag.write_bytes(b'OTHER_PRIVATE_FLAG_CONTENT\n')
                row = entry.training_hold_observation()
                self.assertNotIn('request', row)
                self.assertNotIn('OTHER_PRIVATE_FLAG_CONTENT', str(row))
                flag.unlink()
                flag.symlink_to(state/'missing')
                self.assertEqual(entry.training_hold_observation()['classification'], 'UNVERIFIED_TYPE_OR_SIZE')

    def test_supervisor_running_and_stopped_timestamp_readback(self):
        for output, expected in (
                ('nox-dispatcher-t855u RUNNING pid 123, uptime 1:02:03', ('RUNNING', 123)),
                ('nox-dispatcher-t855u STOPPED Nov 16 04:05 AM', ('STOPPED', None))):
            with patch.object(entry, 'command', return_value=(0, output)):
                row = entry.service()
                self.assertEqual((row['state'], row['pid']), expected)

    def test_global_stop_prevents_any_service_command(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(entry, 'STATE', Path(directory)), \
                 patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '123', 'NOX_OWNER_SOURCE_SHA': 'a'*40}), \
                 patch.object(entry, 'reviewed_modules', return_value=({}, binding)), \
                 patch.object(entry, 'sources'), patch.object(entry, 'global_stop', return_value=True), \
                 patch.object(entry, 'command') as command:
                with self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER_STOP'):
                    entry.main()
                command.assert_not_called()

    def test_existing_request_is_readback_only_no_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state/'owner_native_subagents_install_123.json').write_text('{}')
            with patch.object(entry, 'STATE', state), \
                 patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '123', 'NOX_OWNER_SOURCE_SHA': 'a'*40}), \
                 patch.object(entry, 'reviewed_modules') as assets:
                with self.assertRaisesRegex(RuntimeError, 'ALREADY_STARTED'):
                    entry.main()
                assets.assert_not_called()

    def test_native_pin_drift_fails_before_controller_action(self):
        with patch.object(entry, 'read', return_value=b'changed native source'), \
             patch.object(entry, 'command') as command:
            with self.assertRaisesRegex(RuntimeError, 'SOURCE_CHANGED'):
                entry.sources()
            command.assert_not_called()

    def test_catalog_contains_only_three_actual_review_operations(self):
        catalog = entry.catalog(binding, 'a'*64)
        rows = binding.autonomy.validate_submission(catalog, allowed_handlers={binding.HANDLER})['ordered']
        self.assertEqual(len(rows), 3)
        self.assertEqual({row['params']['role'] for row in rows}, set(binding.ROLES))
        self.assertTrue(all(row['resource'] == 'CPU_LIGHT' for row in rows))
        self.assertTrue(all(row['handler'] == binding.HANDLER for row in rows))


if __name__ == '__main__':
    unittest.main(verbosity=2)
