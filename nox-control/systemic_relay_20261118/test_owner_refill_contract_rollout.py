import contextlib
import base64
import fcntl
import io
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import owner_refill_contract_rollout as rollout


HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
MANIFEST = next((HERE / 'next_pack_44368502183/package/relay').glob('*.json'))
RUNTIME = HERE / 'runtime/owner_systemic_refill.py'


class RolloutContractTests(unittest.TestCase):
    def test_owner_repair_transport_builds_the_exact_two_asset_payload(self):
        spec = importlib.util.spec_from_file_location(
            '_refill_operator', REPOSITORY / 'nox-control/owner_native_operator.py')
        operator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(operator)
        entry = 'nox-control/systemic_relay_20261118/owner_refill_contract_rollout.py'
        self.assertEqual(operator.FILES['repair'], entry)
        paths = operator.repair_bundle_paths('repair', entry, ('nox-control/owner_native_repair.py',))
        assets = {Path(path).name: base64.b64encode(Path(path).read_bytes()).decode('ascii')
                  for path in paths}
        self.assertEqual(set(assets), {'owner_systemic_refill.py', 'continuous_transaction_helpers.py'})
        template = operator._load_action_payload('repair')
        self.assertEqual(template.count('__NOX_BUNDLE_JSON__'), 1)
        compiled = template.replace('__NOX_BUNDLE_JSON__', json.dumps(assets, sort_keys=True))
        self.assertEqual(compiled, rollout.build_payload(REPOSITORY))
        compile(compiled, '<fixed-owner-repair-payload>', 'exec')
        operator._validate_forward_marker('repair', 'NOX_MAINT_REFLEX_RESTORE={"state":"PREFLIGHT"}')
        operator._validate_forward_marker('repair', 'NOX_MAINT_REPAIR_COMPLETE=true')
        with self.assertRaisesRegex(RuntimeError, 'HOLD_REMOTE_MARKER_NOT_ALLOWLISTED'):
            operator._validate_forward_marker('repair', 'NOX_MAINT_FREEFORM=true')

    def test_embedded_payload_and_both_assets_compile(self):
        import ast
        payload = rollout.build_payload(REPOSITORY)
        assets = None
        for node in ast.walk(ast.parse(payload)):
            if (isinstance(node, ast.Assign) and node.targets
                    and getattr(node.targets[0], 'id', None) == 'BUNDLE'
                    and isinstance(node.value, ast.Dict) and node.value.keys):
                assets = ast.literal_eval(node.value)
        self.assertIsNotNone(assets)
        helper, candidate = rollout.decode_bundle(assets)
        self.assertEqual(candidate, RUNTIME.read_bytes())
        self.assertEqual(helper.STATE, 'state/dispatcher/state.json')
        damaged = {**assets, 'owner_systemic_refill.py': 'YQ=='}
        with self.assertRaisesRegex(RuntimeError, 'BUNDLE_PIN'):
            rollout.decode_bundle(damaged)

    def test_global_active_claim_or_unsettled_native_claim_is_never_idle(self):
        def inspect(rows):
            helper = SimpleNamespace(STATE='queue.json', read_regular=lambda *_:
                                     rollout.encode({'tasks': rows}))
            return rollout.read_queue(helper, Path('/root/nox'))

        with self.assertRaisesRegex(RuntimeError, 'ACTIVE_QUEUE_CLAIM'):
            inspect({'legacy': {'status': 'running'}})
        with self.assertRaisesRegex(RuntimeError, 'ACTIVE_QUEUE_CLAIM'):
            inspect({'native': {'status': 'retry', 'native_worker_lease': {'pid': 123}}})
        with self.assertRaisesRegex(RuntimeError, 'ACTIVE_QUEUE_CLAIM'):
            inspect({'native': {'status': 'blocked', 'native_worker_lease': {'phase': 'ACTIVE'}}})
        self.assertIn('native', inspect({'native': {'status': 'blocked',
                         'native_worker_lease': {'phase': 'SETTLED'}}})[0]['tasks'])
        self.assertEqual(inspect({'legacy': {'status': 'pending'}})[0]['tasks'],
                         {'legacy': {'status': 'pending'}})

    def test_only_actual_headroom_clears_floor(self):
        helper = SimpleNamespace(read_budget_snapshot=lambda _:
            {'max_bytes': 4 << 30, 'current_bytes': 3 << 30,
             'minimum_headroom_bytes': 2 << 30, 'inactive_file_bytes': 2 << 30})
        with self.assertRaisesRegex(RuntimeError, 'RAW_CGROUP_HEADROOM'):
            rollout.headroom(helper, {})
        helper.read_budget_snapshot = lambda _: {
            'max_bytes': 4 << 30, 'current_bytes': 2 << 30, 'minimum_headroom_bytes': 2 << 30}
        self.assertEqual(rollout.headroom(helper, {}), 2 << 30)

    def test_binds_native_request_to_every_current_original_state(self):
        raw = MANIFEST.read_bytes()
        manifest = json.loads(raw)
        manifest_sha = rollout.sha(raw)
        module = rollout.load_module('_runtime_in_fixture', RUNTIME.read_bytes())
        first, second = sorted(manifest['registry']['parents'])[:2]
        tasks = {first: {'status': 'done'}, second + '.retry': {'status': 'pending'},
                 'outside': {'status': 'blocked'}}
        selection = module.select_next(manifest, tasks, {}, {
            'slots_available': 3, 'now': 1795108298, 'callback_sha256': 'a' * 64,
            'manifest_sha256': manifest_sha})
        request = selection['refill_request']
        status = {'manifest_sha256': manifest_sha, 'eligible_proposals': 0,
                  'fingerprint': request['request_id'], 'refill_request': request}
        self.assertEqual(rollout.verify_refill_request(module, status, manifest, manifest_sha,
                         {'tasks': tasks}), request['request_id'])
        request['original_task_states'].pop()
        with self.assertRaisesRegex(RuntimeError, 'REFILL_REQUEST_ORIGINAL_TASK_IDS'):
            rollout.verify_refill_request(module, status, manifest, manifest_sha, {'tasks': tasks})


class RolloutTransactionTests(unittest.TestCase):
    def exercise(self, *, boot_issue=False, low_memory=False, backoff=False,
                 prestart_memory=False, foreign=False, legacy_workers_issue=False):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / 'package'
            config = {
                'schema': 'NOX_NATIVE_SUBAGENT_BINDING_V1', 'instance_id': 60509551,
                'owner_authorized': True, 'mode': 'NORMAL', 'target': 3,
                'execution_mode': 'NATIVE_PROJECT_V1', 'policy_id': 'NOX_WEB_WEIGHTS_V06',
                'module_pins': {'owner_systemic_refill.py': rollout.sha(b'preimage'),
                                'owner_subagent_dispatcher.py': rollout.sha(b'director')},
                'project_executor': {'package_root': str(package)},
                'systemic_relay': {'sha256': 'a' * 64, 'path': str(package / 'relay/current.json')}}
            original = {rollout.CONFIG: rollout.encode(config), rollout.REFILL: b'preimage'}
            helper, _ = self.helper(root)
            for path, raw in {**original, rollout.DIRECTOR: b'director',
                              helper.STATE: b'{"tasks":{}}',
                              'state/owner_maintenance.lock': b'',
                              'state/TRAIN_PAUSE_REQUEST.flag': b'pause'}.items():
                helper.atomic(root / path, raw)

            old = {'pid': 123, 'start_ticks': 500}
            new = {'pid': 124, 'start_ticks': 501}
            restored = {'pid': 125, 'start_ticks': 502}
            live = [old]
            attempted = []
            backoff_active = [False]
            helper.expected_processes = lambda _: {'director': old, 'workers': []}
            helper.descendant_snapshot = lambda _: []
            helper.wait_previous_descendants_stopped = lambda *args, **kwargs: None
            helper.process_identity = lambda pid: live[-1] if live and live[-1]['pid'] == pid else None
            helper.stop_clear = lambda _: True
            def stop():
                attempted.append('stop')
                live.clear()
                backoff_active[0] = False
            helper.stop_checked = stop
            def supervisor(action):
                if action == 'status':
                    return ({'state': 'RUNNING', 'pid': live[-1]['pid']} if live else
                            {'state': 'BACKOFF' if backoff_active[0] else 'STOPPED', 'pid': None})
                self.assertEqual(action, 'start')
                with (root / 'state/owner_maintenance.lock').open('rb') as lease_probe:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(lease_probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                attempted.append('start')
                if (backoff or foreign) and attempted.count('start') == 1:
                    backoff_active[0] = backoff
                    if foreign:
                        live.append(new)
                    raise RuntimeError('HOLD_FIXTURE_START')
                instance = restored if attempted.count('start') > 1 else new
                live.append(instance)
                return {'action': 'start', 'rc': 0}
            helper.supervisor = supervisor
            candidate = b'candidate'
            old_pins = {path: rollout.sha(raw) for path, raw in original.items()}
            config_before = rollout.encode(config)
            idle_rows = {'workers': [{'pid': row['pid'], 'process_starttime': row['start_ticks']}
                                     for row in rollout.EXPECTED_PROCESSES['expected_workers']]}
            def postboot(*args):
                with (root / 'state/owner_maintenance.lock').open('rb') as lease_probe:
                    fcntl.flock(lease_probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if boot_issue:
                    raise RuntimeError('HOLD_FIXTURE_BOOT')
                return 'a' * 64
            with (patch.multiple(rollout, OLD=old_pins, DIRECTOR_SHA=rollout.sha(b'director'),
                                 REFILL_SHA=rollout.sha(candidate)),
                  patch.object(rollout, 'load_module'),
                  patch.object(rollout, 'service_guard', return_value={}),
                  patch.object(rollout, 'verify_legacy_contracts', return_value=(6, {})),
                  patch.object(rollout, 'read_idle_workers', return_value=idle_rows),
                  patch.object(rollout, 'headroom', side_effect=(
                      RuntimeError('HOLD_FIXTURE_MEMORY') if low_memory else
                      [2 ** 31] * 3 + [RuntimeError('HOLD_FIXTURE_MEMORY')] if prestart_memory else
                      None), return_value=2 ** 31),
                  patch.object(rollout, 'wait_for_legacy_workers',
                               side_effect=RuntimeError('HOLD_FIXTURE_LEGACY_WORKERS')
                               if legacy_workers_issue else None),
                  patch.object(rollout, 'wait_for_request', side_effect=postboot),
                  contextlib.redirect_stdout(io.StringIO()) as log):
                if low_memory or boot_issue or backoff or prestart_memory or foreign:
                    with self.assertRaisesRegex(RuntimeError, 'HOLD_FIXTURE_'):
                        rollout.rollout(helper, root, candidate, '1', 'b' * 40)
                else:
                    receipt = rollout.rollout(helper, root, candidate, '1', 'b' * 40)
                    self.assertEqual(receipt['state'], 'REFILL_CONTRACT_RUNTIME_INSTALLED')
                    self.assertEqual(receipt['legacy_contracts_checked'], 6)
            self.assertEqual((root / 'state/TRAIN_PAUSE_REQUEST.flag').read_bytes(), b'pause')
            self.assertEqual((root / helper.STATE).read_bytes(), b'{"tasks":{}}')
            if low_memory:
                self.assertEqual(attempted, [])
                self.assertFalse((root / 'state/dispatcher/refill_contract_rollouts/1').exists())
            else:
                backup = root / 'state/dispatcher/refill_contract_rollouts/1'
                self.assertEqual((backup / Path(rollout.CONFIG).name).read_bytes(), config_before)
                self.assertEqual((backup / Path(rollout.REFILL).name).read_bytes(), b'preimage')
                self.assertEqual((root / rollout.REFILL).read_bytes(),
                                 b'preimage' if boot_issue or backoff or prestart_memory else candidate)
            if boot_issue or backoff:
                self.assertEqual(attempted, ['stop', 'start', 'stop', 'start'])
                self.assertEqual((root / rollout.CONFIG).read_bytes(), config_before)
                self.assertIn('"rollback_preimages_verified":true', log.getvalue())
                if legacy_workers_issue:
                    self.assertNotIn('"rollback_verified":true', log.getvalue())
                    self.assertIn('HOLD_FIXTURE_LEGACY_WORKERS', log.getvalue())
                else:
                    self.assertIn('"rollback_verified":true', log.getvalue())
                self.assertEqual(live, [restored])
            if prestart_memory:
                self.assertEqual(attempted, ['stop', 'start'])
                self.assertEqual((root / rollout.CONFIG).read_bytes(), config_before)
                self.assertIn('"rollback_verified":true', log.getvalue())
            if foreign:
                self.assertEqual(attempted, ['stop', 'start'])
                self.assertEqual(live, [new])
                self.assertIn('RECOVERY_FOREIGN_DIRECTOR', log.getvalue())

    @staticmethod
    def helper(root):
        helper_path = REPOSITORY / 'nox-control/continuous_executor_20261118/assets/continuous_transaction_helpers.py'
        return rollout.load_module('_fixture_transaction_helper', helper_path.read_bytes()), root

    def test_success_uses_only_scoped_preimages_and_durable_backup(self):
        self.exercise()

    def test_failed_postboot_receipt_rolls_back_only_our_runtime(self):
        self.exercise(boot_issue=True)

    def test_low_memory_leaves_services_and_files_untouched(self):
        self.exercise(low_memory=True)

    def test_backoff_under_held_lease_stops_candidate_and_restores_old_runtime(self):
        self.exercise(backoff=True)

    def test_prestart_memory_drift_restores_old_runtime_without_starting_candidate(self):
        self.exercise(prestart_memory=True)

    def test_failed_start_never_adopts_or_stops_a_foreign_running_pid(self):
        self.exercise(foreign=True)

    def test_restored_source_and_pid_do_not_imply_verified_worker_rollback(self):
        self.exercise(boot_issue=True, legacy_workers_issue=True)


if __name__ == '__main__':
    unittest.main()
