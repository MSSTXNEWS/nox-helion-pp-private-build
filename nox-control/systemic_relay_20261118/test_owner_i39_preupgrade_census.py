import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import owner_i39_preupgrade_census as census


class I39CensusTests(unittest.TestCase):
    def setUp(self):
        fixture = tempfile.TemporaryDirectory()
        self.addCleanup(fixture.cleanup)
        self.root = Path(fixture.name)
        self.workspace = self.root / census.WORKSPACE
        self.workspace.mkdir(parents=True)
        self.config = self.root / census.CONFIG
        self.config.parent.mkdir()
        self.bootstrap = self.workspace / census.BOOTSTRAP
        self.verifier = self.workspace / census.VERIFIER
        self.forge = self.workspace / census.FORGE
        self.known_postimage = Path(__file__).parent / 'reviewed_recovery/assets/reviewed_forge_budget_payload.source'
        self.forge.write_bytes(self.known_postimage.read_bytes())
        self.set_bindings()

    def set_bindings(self, verifier_sha=None):
        pins = {census.FORGE: hashlib.sha256(b'old baseline bytes').hexdigest()}
        if verifier_sha is not None:
            pins[census.VERIFIER] = verifier_sha
        self.config.write_bytes(census.canonical({
            'schema': 'NOX_NATIVE_SUBAGENT_BINDING_V1', 'instance_id': 60509551,
            'owner_authorized': True,
            'project_executor': {'roots': {'NOX_PROJECT_SOURCE': {
                'path': str(self.workspace), 'integration_kind': 'SOURCE_WORKSPACE',
                'allowed_paths': list(pins),
            }}},
        }))
        self.bootstrap.write_bytes(census.canonical({
            'schema': 'NOX_PROJECT_SOURCE_BOOTSTRAP_RECEIPT_V1', 'root': str(self.workspace),
            'file_pins': pins, 'source_refs': [], 'source_file_count': len(pins),
            'manifest_sha256': census.sha(census.canonical({
                'schema': 'NOX_PROJECT_SOURCE_BASELINE_V1', 'files': pins, 'source_refs': [],
            })),
        }))

    def test_newer_forge_postimage_and_absent_verifier(self):
        result = census.observe(self.root)
        self.assertEqual(result['forge_known_preimage'], 'REVIEWED_FORGE_BUDGET_POSTIMAGE')
        self.assertIsNone(result['verifier_sha256'])
        self.assertFalse(result['exact_i39_verifier_registered'])
        self.assertFalse(result['full_workspace_census'])

    def test_present_test_requires_both_allowlisting_and_matching_pin(self):
        raw = b'reviewed verifier bytes\n'
        pin = census.sha(raw)
        self.verifier.write_bytes(raw)
        with patch.object(census, 'VERIFIER_SHA', pin):
            self.assertFalse(census.observe(self.root)['exact_i39_verifier_registered'])
            self.set_bindings(pin)
            self.assertTrue(census.observe(self.root)['exact_i39_verifier_registered'])
            self.verifier.write_bytes(b'drift')
            self.assertFalse(census.observe(self.root)['exact_i39_verifier_registered'])

    def test_symlink_is_neither_followed_nor_reported_absent(self):
        self.verifier.symlink_to(self.forge)
        with self.assertRaises(OSError):
            census.observe(self.root)

    def test_changed_second_read_holds(self):
        first = census.read_snapshot(self.root)
        self.forge.write_bytes(b'changed between passes')
        second = census.read_snapshot(self.root)
        with patch.object(census, 'read_snapshot', side_effect=[first, second]):
            with self.assertRaisesRegex(census.Hold, 'OBSERVED_DRIFT'):
                census.observe(self.root)

    def test_exact_scope_does_not_scan_other_workspace_paths(self):
        unknown = self.workspace / 'not-in-scope.py'
        unknown.symlink_to('/root/should-not-be-opened')
        with patch.object(census, 'stable_read', wraps=census.stable_read) as read:
            self.assertEqual(census.observe(self.root)['state'], 'OBSERVED_TWO_STABLE_READS')
        self.assertEqual({call.args[0] for call in read.call_args_list}, {
            self.config, self.bootstrap, self.forge, self.verifier,
        })

    def test_fixed_repair_transport_only_compiles_the_read_only_census(self):
        root = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location('_operator', root / 'nox-control/owner_native_operator.py')
        operator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(operator)
        entry = 'nox-control/systemic_relay_20261118/owner_i39_preupgrade_census.py'
        self.assertEqual(operator.FILES['repair'], entry)
        self.assertEqual(operator.repair_bundle_paths('repair', entry, ('nox-control/owner_native_repair.py',)), ())
        payload = operator._load_action_payload('repair')
        self.assertEqual(payload, (root / entry).read_text())
        compile(payload, '<fixed-owner-i39-census>', 'exec')
        operator._validate_forward_marker('repair', census.MARKER + '{"read_only":true}')
        operator._validate_forward_marker('repair', 'NOX_MAINT_REPAIR_COMPLETE=true')


if __name__ == '__main__':
    unittest.main()
