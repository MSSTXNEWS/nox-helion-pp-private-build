import ast
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

        tree = ast.parse(Path(inspect.__file__).read_text(encoding='utf-8'))
        functions = {node.name: node for node in tree.body
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        reachable = set()
        pending = ['main']
        while pending:
            name = pending.pop()
            if name in reachable or name not in functions:
                continue
            reachable.add(name)
            for node in ast.walk(functions[name]):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in functions and node.func.id not in reachable:
                        pending.append(node.func.id)
        self.assertNotIn('s03_receipt_check', reachable)
        for name in reachable:
            for node in ast.walk(functions[name]):
                if isinstance(node, ast.Import):
                    self.assertFalse(any(alias.name == 'sqlite3' for alias in node.names))
                if isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(node.module, 'sqlite3')
        self.assertEqual(inspect.bounded_training_checkpoint()['state'],
                         'UNKNOWN_NO_FIXED_ALLOWLISTED_V135_RECEIPT_PATH')


    def test_s03_source_preimages_are_allowlisted_but_loaded_state_stays_unknown(self):
        expected = (
            's03_memory.py', 'owner_s03_gateway.py',
            'owner_s03_activate_entry.py', 'owner_s03_recover_activate.py',
            'owner_s03_content_reindex_entry.py',
        )
        self.assertEqual(inspect.S03_SOURCE_NAMES, expected)
        self.assertTrue(set(expected).issubset(inspect.PINNED_PREIMAGE_NAMES))
        with mock.patch.object(inspect, 'bounded_s03_json',
                               side_effect=lambda path, kind: {'path': str(path), 'kind': kind}), \
             mock.patch.object(inspect, 'bounded_lstat',
                               side_effect=lambda path: {'path': str(path), 'exists': True, 'size': 4096}):
            projected = inspect.bounded_s03_projection()
        self.assertEqual(projected['source_names'], list(expected))
        self.assertEqual(projected['source_paths'],
                         [str(inspect.SCRIPTS / name) for name in expected])
        self.assertEqual(projected['loaded_state'], 'UNKNOWN')
        self.assertIsNone(projected['loaded_evidence'])
        self.assertNotIn('sha256', projected['canonical_snapshot'])


if __name__ == '__main__':
    unittest.main()
