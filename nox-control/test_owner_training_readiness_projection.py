import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import owner_complete_executor_observe as inspect


class BoundedProjectionRegression(unittest.TestCase):
    def test_projection_redacts_sensitive_values_and_keeps_unknowns_closed(self):
        abi = inspect.callback_abi_projection(
            b"def s03_readback(record, /, *, strict=False):\n    return record\n"
        )
        self.assertEqual(abi['state'], 'PARSED')
        self.assertEqual(abi['s03_readback']['posonly'], ['record'])
        self.assertEqual(abi['s03_readback']['kwonly_defaults'], ['strict'])

        raw = json.dumps({
            'enabled': True,
            'providers': ['local', 'sk-abcdefgh12345678', 'remote-safe'],
            'minimum_verified_providers': 2,
            'credential': 'must-not-leak',
        }).encode()
        record = {'path': '/root/nox/config/owner_senior_gateway.json',
                  'exists': True, 'size': len(raw), 'sha256': 'a' * 64}
        with mock.patch.object(inspect, 'bounded_file', return_value=(record, raw)):
            projected = inspect.bounded_config_projection(
                Path('/root/nox/config/owner_senior_gateway.json'), 'senior'
            )
        encoded = json.dumps(projected)
        self.assertEqual(projected['providers'], ['local', 'remote-safe'])
        self.assertNotIn('credential', encoded)
        self.assertNotIn('must-not-leak', encoded)
        self.assertNotIn('sk-abcdefgh12345678', encoded)

        self.assertIsNone(inspect.bounded_training_inputs()['manifest_path'])
        self.assertEqual(inspect.bounded_training_inputs()['state'],
                         'UNKNOWN_NO_FIXED_ALLOWLISTED_V135_PATH')
        self.assertIsNone(inspect.bounded_training_lease()['owner'])
        fake = SimpleNamespace(st_size=4096, st_mode=0o100600, st_uid=1000, st_gid=1000)
        with mock.patch.object(inspect.os, 'lstat', return_value=fake), \
             mock.patch.object(inspect, 'safe_read', side_effect=AssertionError('payload read')):
            snapshot = inspect.bounded_lstat('/root/nox/state/owner_s03/backups/6904379098/canonical.sqlite')
        self.assertEqual(snapshot['size'], 4096)
        self.assertNotIn('sha256', snapshot)


if __name__ == '__main__':
    unittest.main()
