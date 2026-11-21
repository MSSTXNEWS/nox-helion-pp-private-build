"""Exercise the refill snapshot with a copied repository manifest and original registry."""

import fcntl
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import owner_systemic_refill_snapshot as snapshot
import owner_systemic_taskpack as taskpack
from runtime import owner_systemic_refill as relay


HERE = Path(__file__).resolve().parent
CONTROL = HERE.parent
NATIVE_HELPER = CONTROL / 'continuous_executor_20261118/assets/continuous_transaction_helpers.py'
DISPOSITION = CONTROL / 'complete_executor_20261118/evidence/all295_execution_disposition.json'
REGISTRY = CONTROL / 'four_queue_20261118'
MANIFEST = next((HERE / 'next_pack_44368502183/package/relay').glob('*.json'))
NOW = 1_800_000_000
PUBLISHER_SHA = '1' * 64
OWNER_SOURCE_SHA = '2' * 40


class RefillSnapshotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.helper = snapshot.load_module('_test_transaction', NATIVE_HELPER.read_bytes())
        self.disposition = DISPOSITION.read_bytes()
        self.manifest = json.loads(MANIFEST.read_bytes())
        manifest_sha = MANIFEST.stem
        self.assertEqual(snapshot.sha(MANIFEST.read_bytes()), manifest_sha)
        runtime = (HERE / 'runtime/owner_systemic_refill.py').read_bytes()
        callback = b'reviewed callback'
        self.write('scripts/owner_systemic_refill.py', runtime)
        self.write('scripts/owner_subagent_dispatcher.py', callback)
        self.write('state/owner_maintenance.lock', b'')
        relative = Path('state/dispatcher/project_executor/package/relay') / MANIFEST.name
        self.write(relative, MANIFEST.read_bytes())
        self.config = {
            'schema': 'NOX_NATIVE_SUBAGENT_BINDING_V1', 'owner_authorized': True,
            'instance_id': snapshot.INSTANCE, 'mode': 'NORMAL', 'target': 3,
            'global_worker_cap': 3, 'execution_mode': 'NATIVE_PROJECT_V1',
            'module_pins': {'owner_systemic_refill.py': snapshot.sha(runtime),
                            'owner_subagent_dispatcher.py': snapshot.sha(callback)},
            'systemic_relay': {'sha256': manifest_sha, 'path': str(self.root / relative)},
        }
        self.write(self.helper.CONFIG, self.config)
        originals = {'tasks': 'work_tasks.json', 'ideas': 'work_ideas.json',
                     'receipts': 'work_receipts.json', 'routing': 'NOX_FOUR_QUEUE_ROUTING_20261118.json'}
        for key, name in originals.items():
            self.write(Path('state/dispatcher') / snapshot.REGISTRY_NAMES[key],
                       (REGISTRY / name).read_bytes())

        self.tasks = {}
        self.pins = {}
        for mission in self.manifest['missions']:
            input_sha = relay._input(mission)
            task_id = mission['parent_task_id'] + '.relay.' + mission['mission_id'] + '.' + input_sha[:16]
            self.tasks[task_id] = {'status': 'done', 'systemic_relay': {'binding': {
                'mission_id': mission['mission_id'], 'mission_revision': mission['revision'],
                'input_sha256': input_sha,
            }}}
            self.pins.update({row['path']: row['sha256'] for row in mission['context']})
        self.write(self.helper.STATE, {'tasks': self.tasks})
        self.request = relay.select_next(self.manifest, self.tasks, {'NOX_PROJECT_SOURCE': self.pins},
            {'slots_available': 3, 'callback_sha256': snapshot.sha(callback), 'now': NOW,
             'manifest_sha256': manifest_sha})['refill_request']
        self.assertIsNotNone(self.request)
        self.native = {
            'observed_at': NOW, 'director': {'pid': 10, 'process_starttime': 100},
            'project_queues': {'state': 'HANDOFF_RECEIVED_PROJECT_EXECUTION_BOUND',
                               'dispatch_cap': 3, 'received_unique_tasks': 295},
            'workers': [{'pid': pid, 'process_starttime': pid * 10, 'role': role,
                         'state': 'RUNNING', 'instance_id': snapshot.INSTANCE,
                         'native_pid_verified': True, 'current_task': None}
                        for pid, role in enumerate(sorted(snapshot.ROLES), 11)],
            'systemic_relay': {'state': 'REFILL_REQUIRED', 'manifest_sha256': manifest_sha,
                               'eligible_proposals': 0, 'shared_queue': True,
                               'refill_request': self.request},
        }
        self.write(self.helper.STATUS, {'native_subexecutors': self.native})
        self.source = {
            'files': {name: {'sha256': pin, 'size': 42, 'mode': 0o600}
                      for name, pin in self.pins.items()},
        }
        self.source['files_sha256'] = snapshot.sha(snapshot.encode(self.source['files']))
        self.helper.source_snapshot = lambda *_: self.source
        valid_pids = set(range(10, 17))
        self.helper.process_identity = lambda pid: (
            {'pid': pid, 'start_ticks': pid * 10, 'ppid': 10 if pid in (11, 12, 13) else 1}
            if pid in valid_pids else None)
        self.helper.read_budget_snapshot = lambda *_: {
            'max_bytes': 10 << 30, 'current_bytes': 6 << 30, 'minimum_headroom_bytes': 2 << 30,
            'memory_psi_full_avg10': 0.0, 'memory_psi_some_avg10': 0.0,
        }
        self.services = {snapshot.DIRECTOR: 10, **{service: pid for pid, service in
                                                   enumerate(snapshot.PROTECTED.values(), 14)}}

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else snapshot.encode(value))

    def capture(self, get_services=None):
        return snapshot.capture(self.root, self.helper, self.disposition, PUBLISHER_SHA,
                                '1234', OWNER_SOURCE_SHA, now=lambda: NOW,
                                get_services=get_services or (lambda: self.services))

    def test_producer_output_matches_existing_taskpack_validators(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        owner, checkpoint, request, census, readback = self.capture()
        taskpack._validate_refill_request(request, self.manifest, MANIFEST.stem)
        taskpack.validate_owner_snapshot(owner, now=NOW,
            expected_previous_sha=MANIFEST.stem, expected_refill_request=request['request_id'],
            expected_registry_sha=snapshot.sha(self.disposition),
            expected_source_sha=self.source['files_sha256'],
            expected_native_readback_sha=snapshot.sha(snapshot.encode(readback)))
        self.assertEqual(checkpoint['owner_snapshot_sha256'], snapshot.sha(snapshot.encode(owner)))
        self.assertEqual(owner['process_identity_sha256'], snapshot.sha(snapshot.encode({
            'director': checkpoint['expected_director'], 'workers': checkpoint['expected_workers'],
            'protected_processes': checkpoint['protected_processes'],
        })))
        self.assertEqual(checkpoint['publisher_template_sha256'], PUBLISHER_SHA)
        self.assertEqual(census['roots']['NOX_PROJECT_SOURCE'], self.pins)
        self.assertFalse(readback['publication_authorized'])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_active_claim_and_stop_hold_before_capture(self):
        self.write(self.helper.STATE, {'tasks': {'active': {'status': 'running'}}})
        with self.assertRaisesRegex(snapshot.SnapshotHold, 'ACTIVE_CLAIMS'):
            self.capture()
        self.write('state/STOP', b'')
        with self.assertRaisesRegex(snapshot.SnapshotHold, 'STOP_OR_MAINTENANCE'):
            self.capture()

    def test_changed_original_registry_does_not_mint_snapshot(self):
        self.write('state/dispatcher/project_work_receipts_source.json', b'{}')
        with self.assertRaisesRegex(snapshot.SnapshotHold, 'ORIGINAL_REGISTRY_DRIFT'):
            self.capture()

    def test_previous_manifest_parent_pin_must_match_original_spec(self):
        registry = self.manifest['registry']
        next(iter(registry['parents'].values()))['spec_sha256'] = '0' * 64
        with self.assertRaisesRegex(snapshot.SnapshotHold, 'MANIFEST_ORIGINAL_PARENT_BINDING'):
            snapshot.read_registry(self.root, self.helper, json.loads(self.disposition), registry)

    def test_dispatcher_shared_maintenance_lease_allows_readonly_snapshot(self):
        lock = self.root / 'state/owner_maintenance.lock'
        with lock.open('rb') as handle:
            fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
            owner, checkpoint, request, census, readback = self.capture()
            self.assertFalse(readback['publication_authorized'])
            self.assertFalse(readback['native_write_performed'])
            self.assertEqual(checkpoint['owner_snapshot_sha256'],
                             snapshot.sha(snapshot.encode(owner)))
            self.assertEqual(census['atomic_snapshot'], True)

    def test_exclusive_maintenance_writer_still_blocks_snapshot(self):
        lock = self.root / 'state/owner_maintenance.lock'
        with lock.open('rb') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(snapshot.SnapshotHold, 'MAINTENANCE_BUSY'):
                self.capture()

    def test_low_ram_readonly_snapshot_cannot_authorize_publishing(self):
        self.helper.read_budget_snapshot = lambda *_: {
            'max_bytes': 10 << 30, 'current_bytes': (10 << 30) - (96 << 20),
            'minimum_headroom_bytes': 2 << 30,
            'memory_psi_full_avg10': 0.0, 'memory_psi_some_avg10': 0.0,
        }
        _, _, _, _, readback = self.capture()
        self.assertEqual(readback['minimum_observed_raw_headroom_bytes'], 96 << 20)
        self.assertFalse(readback['publication_authorized'])
        self.assertFalse(readback['native_write_performed'])

    def test_worker_current_task_holds_even_if_durable_queue_looks_idle(self):
        self.native['workers'][0]['current_task'] = 'active'
        self.write(self.helper.STATUS, {'native_subexecutors': self.native})
        with self.assertRaisesRegex(snapshot.SnapshotHold, 'WORKERS_NOT_IDLE'):
            self.capture()

    def test_missing_legacy_cap_requires_live_project_cap(self):
        del self.config['global_worker_cap']
        self.write(self.helper.CONFIG, self.config)
        self.assertEqual(self.capture()[-1]['native_dispatch_cap'], 3)
        self.native['project_queues']['dispatch_cap'] = 4
        self.write(self.helper.STATUS, {'native_subexecutors': self.native})
        with self.assertRaisesRegex(snapshot.SnapshotHold, 'NATIVE_PROJECT_DISPATCH_SCOPE'):
            self.capture()

    def test_project_mode_is_required_despite_healthy_workers(self):
        del self.config['execution_mode']
        self.write(self.helper.CONFIG, self.config)
        with self.assertRaisesRegex(snapshot.SnapshotHold, 'OWNER_RUNTIME_SCOPE'):
            self.capture()

    def test_queue_drift_between_reads_does_not_mint_snapshot(self):
        calls = 0

        def drift():
            nonlocal calls
            calls += 1
            if calls == 1:
                self.write(self.helper.STATE, {'tasks': {**self.tasks, 'legacy': {'status': 'done'}}})
            return self.services

        with self.assertRaisesRegex(snapshot.SnapshotHold, 'INPUTS_CHANGED'):
            self.capture(get_services=drift)

    def test_no_current_refill_or_stale_worker_status_held(self):
        self.native['systemic_relay']['state'] = 'WAIT_EXISTING_WORK'
        self.write(self.helper.STATUS, {'native_subexecutors': self.native})
        with self.assertRaisesRegex(snapshot.SnapshotHold, 'NO_CURRENT_REFILL_REQUIRED'):
            self.capture()
        self.native['observed_at'] = NOW - 61
        self.write(self.helper.STATUS, {'native_subexecutors': self.native})
        with self.assertRaisesRegex(snapshot.SnapshotHold, 'NATIVE_STATUS_STALE'):
            self.capture()

    def test_refill_currently_reported_with_wrong_request_fingerprint_held(self):
        self.request['request_id'] = '0' * 64
        self.write(self.helper.STATUS, {'native_subexecutors': self.native})
        with self.assertRaisesRegex(snapshot.SnapshotHold, 'REQUEST_CAS_MISMATCH'):
            self.capture()

    def test_legacy_refill_request_without_original_state_cannot_be_reused(self):
        del self.request['original_task_states']
        self.write(self.helper.STATUS, {'native_subexecutors': self.native})
        with self.assertRaisesRegex(snapshot.SnapshotHold, 'REFILL_REQUEST_CONTRACT_INCOMPATIBLE'):
            self.capture()

    def test_legacy_pinned_module_cannot_mint_successor_snapshot(self):
        old_runtime = b'def validate_manifest(manifest):\n    return manifest\n'
        self.write('scripts/owner_systemic_refill.py', old_runtime)
        self.config['module_pins']['owner_systemic_refill.py'] = snapshot.sha(old_runtime)
        self.write(self.helper.CONFIG, self.config)
        with self.assertRaisesRegex(snapshot.SnapshotHold, 'REFILL_RUNTIME_CONTRACT_INCOMPATIBLE'):
            self.capture()

    def test_failed_transport_does_not_emit_snapshot(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaisesRegex(snapshot.SnapshotHold, 'EXACT_OWNER_TRANSPORT'):
                snapshot.main()


if __name__ == '__main__':
    unittest.main()
