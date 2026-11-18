"""Focused source regressions; these tests do not attest native worker PIDs."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch


MODULE_PATH = Path(os.environ.get('NOX_TASK_PLANS_UNDER_TEST',
    str(Path(__file__).with_name('owner_task_plans.py'))))
SPEC = importlib.util.spec_from_file_location('plans_cap3_under_test', MODULE_PATH)
plans = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plans)


class CapThreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(plans, 'ROOT', self.root)
        self.root_patch.start()
        self.components_patch = patch.dict(sys.modules, {
            'owner_component_tasks': types.SimpleNamespace(HANDLERS={})})
        self.components_patch.start()
        self.pressure_patch = patch.object(plans, 'pressure_snapshot', return_value={
            'state': 'LOAD_OBSERVED', 'memory_ratio': 0.2, 'cpu_some_avg10': 0.0})
        self.pressure_patch.start()
        self.old_bound = plans._BOUND
        plans._BOUND = None
        self.policy()

    def tearDown(self):
        plans._BOUND = self.old_bound
        self.pressure_patch.stop()
        self.components_patch.stop()
        self.root_patch.stop()
        self.temp.cleanup()

    def write(self, relative, obj):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj) + '\n')

    def policy(self, cap=3):
        self.write('config/owner_task_lifecycle.json', {
            'schema': 'NOX_OWNER_TASK_LIFECYCLE_V1',
            'parallelism': {'global_cap': cap, 'normal_target': 6, 'task_boost_target': 6}})

    def namespace(self, workers=6):
        mentor = types.SimpleNamespace(stop_active=lambda: False)
        return {'WORKERS': workers, 'HANDLERS': {}, '_qlock': threading.RLock(),
                'STATE': self.root / 'state/dispatcher/state.json', 'owner_mentor': mentor,
                'run_one': lambda state, task: None, 'ingest_owner_orders': lambda state: None,
                'deps_ok': lambda state, task: True, 'save_state': lambda state: None,
                '_nox_owner_task_admitted': lambda task: True}

    def test_explicit_owner_cap_clamps_normal_and_boost(self):
        self.assertEqual(plans.parallel_policy(), ('NORMAL', 3))
        self.write('state/task_boost_mode.json', {'enabled': True})
        self.assertEqual(plans.parallel_policy(), ('TASK_BOOST', 3))
        self.assertEqual(plans.admission_capacity()[1], 3)
        request = {'schema': plans.REQUEST, 'intent': 'optimize_workers', 'worker_target': 3}
        self.assertEqual(plans.requested_plan({'params': {'plan': request}}), request)
        with self.assertRaises(plans.PlanHold):
            plans.requested_plan({'params': {'plan': {**request, 'worker_target': 6}}})

    def test_absent_explicit_cap_preserves_legacy_policy_only(self):
        self.write('config/owner_task_lifecycle.json', {
            'schema': 'NOX_OWNER_TASK_LIFECYCLE_V1', 'parallelism': {'normal_target': 3}})
        self.assertEqual(plans.global_worker_cap(), 6)
        self.assertEqual(plans.parallel_policy(), ('NORMAL', 3))
        self.write('state/task_boost_mode.json', {'enabled': True})
        self.assertEqual(plans.parallel_policy(), ('TASK_BOOST', 6))
        # This is a policy read; no process or service is ever started.

    def test_invalid_explicit_cap_cannot_fall_back_to_six(self):
        for value in (True, None, 2, 7, '3'):
            with self.subTest(cap=value):
                self.policy(value)
                with self.assertRaises(plans.PlanHold):
                    plans.parallel_policy()

    def test_config_normalizes_three_without_changing_existing_work(self):
        ns = self.namespace(workers=6)  # Compatibility with legacy declared capacity.
        ns['owner_mentor'].atomic_json = lambda path, data: path.write_text(json.dumps(data))
        ns['owner_mentor'].worker_config = lambda _: self.fail('Legacy six-slot normalizer called')
        planner = plans.Planner(ns)
        planner.manifest = lambda _: {'parameters': {'worker_target': 3}}
        old = {'workers': 6, 'min_workers': 6, 'max_workers': 6,
               'tuner_may_adjust': True, 'unrelated': {'keep': 'unchanged'}}
        self.write('config/dispatcher_agents_t868u.json', old)
        planner.state = {'tasks': {'running': {'id': 'running', 'status': 'running',
                            'owner_claim': {'nonce': 'a' * 24}},
                          'done': {'id': 'done', 'status': 'done', 'result': {'proof': 'keep'}}}}
        before = copy.deepcopy(planner.state)
        result = planner._worker_configuration_locked(True, {'id': 'configuration'})
        saved = json.loads((self.root / 'config/dispatcher_agents_t868u.json').read_text())
        self.assertEqual([saved[k] for k in ('workers', 'min_workers', 'max_workers')], [3, 3, 3])
        self.assertFalse(saved['tuner_may_adjust'])
        self.assertEqual(saved['unrelated'], old['unrelated'])
        self.assertEqual(planner.state, before)
        self.assertEqual(result['configured_workers'], 3)
        self.assertIsNone(result['native_process_count'])
        self.assertFalse(result['native_process_count_verified'])
        self.assertEqual(result['scope'], 'CONFIGURED_DISPATCHER_TASK_SLOTS_ONLY')

    def test_fourth_claim_blocked_across_plans_and_current_claims_keep_running(self):
        ns = self.namespace()
        plans.bind_dispatcher(ns)
        planner = ns['_owner_planner']
        tasks = {str(i): {'id': str(i), 'status': 'running', 'owner_plan_id': 'plan-' + str(i),
                         'owner_claim': {'nonce': str(i) * 24}} for i in (1, 2, 3)}
        planner.state = {'tasks': tasks}
        pending = {'id': 'fourth', 'status': 'pending'}
        before = copy.deepcopy(planner.state)
        self.assertFalse(ns['_nox_owner_task_admitted'](pending))
        self.assertTrue(ns['_nox_owner_task_admitted'](tasks['1']))
        self.assertEqual(planner.state, before)
        tasks['3']['status'] = 'done'
        self.assertTrue(ns['_nox_owner_task_admitted'](pending))
        planner.state = None
        self.assertFalse(ns['_nox_owner_task_admitted'](pending))

    def test_plan_manifest_status_and_legacy_namespace_do_not_claim_six_processes(self):
        ns = self.namespace(workers=3)
        plans.bind_dispatcher(ns)
        planner = ns['_owner_planner']
        state = {'tasks': {'retained': {'id': 'retained', 'status': 'done', 'result': 'keep'}}}
        request = {'schema': plans.REQUEST, 'intent': 'optimize_workers', 'worker_target': 3}
        parent = {'id': 'owner.cap3', 'status': 'pending'}
        result = planner.install(state, parent, request)
        self.assertEqual(result['global_worker_cap'], 3)
        manifest = planner.manifest(parent)
        self.assertEqual(manifest['global_worker_cap'], 3)
        self.assertEqual(manifest['parameters']['worker_target'], 3)
        self.assertEqual(state['tasks']['retained']['result'], 'keep')
        metadata = plans.plan_metadata(parent, state)
        self.assertEqual(metadata['global_cap'], 3)
        self.assertFalse(metadata['native_process_count_verified'])
        self.assertIsNone(metadata['native_process_count'])


if __name__ == '__main__':
    unittest.main()
