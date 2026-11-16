import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

import owner_task_plans as plans
import owner_component_tasks as components


class NativeFixture:
    def __init__(self, root):
        self.root = root
        self.state = {'tasks': {}}
        self.state_path = root / 'state/dispatcher/state.json'
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.stopped = False
        self.native_allowed = True
        self.calls = []
        self.ns = {'WORKERS': 6, 'STATE': self.state_path, '_qlock': threading.RLock(),
                   'HANDLERS': {'owner_order': lambda task: (True, {'accepted': True})}}
        self.mentor = types.SimpleNamespace(
            stop_active=lambda: self.stopped,
            worker_config=lambda value: dict(value, workers=6, min_workers=6, max_workers=6, tuner_may_adjust=False),
            atomic_json=self.write,
            component_validation=lambda task: {'verification': {'kind': 'native_cgroup_budget',
                'cpu_quota_cores': 19.2, 'memory_max': 194065203200, 'memory_current': 80000000000}},
            verify_success=self.verify)
        self.ns.update(owner_mentor=self.mentor, save_state=self.save, run_one=self.run,
                       ingest_owner_orders=lambda state: None,
                       _nox_owner_task_admitted=lambda task: self.native_allowed,
                       deps_ok=lambda state, task: all((state['tasks'].get(k) or {}).get('status') == 'done' for k in task.get('deps', [])))

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        path.chmod(0o600)

    def save(self, state):
        with self.ns['_qlock']:
            clean = {'tasks': {key: {k: v for k, v in value.items() if not k.startswith('_')}
                               for key, value in state['tasks'].items()}}
            self.write(self.state_path, clean)

    def verify(self, task, evidence=None):
        if task.get('handler') == 'owner_media':
            if isinstance(evidence, dict) and evidence.get('generation_verified') is True:
                return {'kind': 'native_media_output', 'job_sha256': 'a' * 64,
                        'outputs': [{'sha256': 'b' * 64, 'bytes': 100}], 'media_kind': 'image'}
            return None
        return plans.verify_success(task, evidence)

    def run(self, state, task):
        ok, evidence = self.ns['HANDLERS'][task['handler']](task)
        with self.ns['_qlock']:
            task['status'] = 'done' if ok is True else 'pending' if ok == 'wait' else 'blocked'
            task['result'] = evidence
            self.save(state)
        return ok, evidence

    def execute(self, task):
        with self.ns['_qlock']:
            task['status'] = 'running'
            task['owner_claim_epoch'] = time.time()
            task['owner_claim'] = {'nonce': secrets.token_hex(12), 'pid': os.getpid(), 'worker': 'fixture-native'}
            self.save(self.state)
        return self.ns['run_one'](self.state, task)

    def order(self, intent='audit', **extra):
        task = {'id': 'owner.' + secrets.token_hex(6), 'handler': 'owner_order', 'class': 'owner_order',
                'status': 'pending', 'deps': [], 'locks': [],
                'params': {'plan': {'schema': plans.REQUEST, 'intent': intent, **extra}}}
        self.state['tasks'][task['id']] = task
        return task

    def complete_steps(self, parent):
        while True:
            ready = [row for row in self.state['tasks'].values() if row.get('owner_parent_id') == parent['id']
                     and row.get('status') == 'pending' and self.ns['deps_ok'](self.state, row)]
            if not ready:
                break
            waiting = False
            for child in ready:
                outcome, _ = self.execute(child)
                waiting |= outcome == 'wait'
            if waiting:
                break


class PlansTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.root_patch = patch.object(plans, 'ROOT', self.root)
        self.root_patch.start(); self.addCleanup(self.root_patch.stop)
        self.pressure_patch = patch.object(plans, 'pressure_snapshot', return_value={
            'state': 'LOAD_OBSERVED', 'memory_ratio': 0.4, 'cpu_some_avg10': 0.1})
        self.pressure_patch.start(); self.addCleanup(self.pressure_patch.stop)
        self.fx = NativeFixture(self.root)
        handlers = {'owner.' + name: (lambda component=name: {'verified': True,
                    'scope': 'BOUNDED_' + component.upper(), 'blockers': []}) for name in plans.COMPONENTS}
        self.component_patch = patch.dict(components.HANDLERS, handlers)
        self.component_patch.start(); self.addCleanup(self.component_patch.stop)
        plans.bind_dispatcher(self.fx.ns)
        self.addCleanup(setattr, plans, '_BOUND', None)

    def test_acceptance_is_pending_six_branches_and_no_recursive_expansion(self):
        parent = self.fx.order()
        ok, info = self.fx.execute(parent)
        self.assertEqual(ok, 'wait')
        self.assertFalse(info['verified'])
        self.assertEqual(parent['handler'], 'owner_plan_join')
        children = [t for t in self.fx.state['tasks'].values() if t.get('owner_parent_id') == parent['id']]
        self.assertEqual(len(children), 6)
        self.assertEqual(len({t['id'] for t in children}), 6)
        self.assertTrue(all(t['handler'] == 'owner_plan_step' and not t['deps'] for t in children))
        with self.assertRaisesRegex(plans.PlanHold, 'RECURSIVE'):
            plans.requested_plan(dict(children[0], params=parent['params']))
        # Rebinding never replaces the dispatcher pool or grows the queue.
        run = self.fx.ns['run_one']
        plans.bind_dispatcher(self.fx.ns)
        self.assertIs(self.fx.ns['run_one'], run)

    def test_join_proves_all_children_and_rejects_tampered_native_state(self):
        parent = self.fx.order()
        self.fx.execute(parent)
        self.fx.complete_steps(parent)
        unrelated = {'id': 'unrelated', 'status': 'running', '_held_locks': [threading.Lock()]}
        self.fx.state['tasks']['unrelated'] = unrelated
        ok, info = self.fx.execute(parent)
        self.assertIs(ok, True)
        proof = plans.verify_success(parent, info)
        self.assertEqual(proof['kind'], 'bounded_native_plan_join')
        self.assertEqual(proof['verified_children'], 6)
        self.assertEqual(proof['scope'], 'BOUNDED_COMPONENT_AUDIT')
        child = self.fx.state['tasks'][parent['owner_plan_children'][0]]
        child['result']['scope'] = 'FALSE_UPGRADED_INTELLIGENCE'
        self.fx.save(self.fx.state)
        self.assertIsNone(plans.verify_success(parent, info))

    def test_claim_nonce_and_receipt_source_cannot_be_reused(self):
        parent = self.fx.order()
        self.fx.execute(parent)
        child = self.fx.state['tasks'][parent['owner_plan_children'][0]]
        ok, evidence = self.fx.execute(child)
        self.assertIs(ok, True)
        self.assertIsNotNone(plans.verify_success(child, evidence))
        self.assertEqual(Path(evidence['receipt_path']).stat().st_mode & 0o777, 0o600)
        forged = copy.deepcopy(child)
        forged['owner_claim']['nonce'] = '0' * 24
        self.assertIsNone(plans.verify_success(forged, evidence))
        receipt = json.loads(Path(evidence['receipt_path']).read_text())
        receipt['source_sha256'] = 'f' * 64
        self.fx.write(Path(evidence['receipt_path']), receipt)
        changed = dict(evidence, receipt_sha256=plans.file_sha(evidence['receipt_path']))
        self.assertIsNone(plans.verify_success(child, changed))

    def test_failed_child_releases_parent_for_honest_failure(self):
        parent = self.fx.order()
        self.fx.execute(parent)
        child = self.fx.state['tasks'][parent['owner_plan_children'][0]]
        child['status'] = 'blocked'
        self.assertTrue(self.fx.ns['deps_ok'](self.fx.state, parent))
        ok, evidence = self.fx.execute(parent)
        self.assertIs(ok, False)
        self.assertEqual(evidence['state'], 'HOLD_PLAN_CHILD_FAILED')
        self.assertFalse(evidence['verified'])

    def test_unknown_or_dummy_order_never_fake_done(self):
        parent = self.fx.order('run_generated_shell')
        ok, evidence = self.fx.execute(parent)
        self.assertIs(ok, False)
        self.assertEqual(evidence['state'], 'NEEDS_PLAN_UNREVIEWED_INTENT')
        self.assertEqual(len(self.fx.state['tasks']), 1)
        with self.assertRaises(plans.PlanHold):
            plans.requested_plan({'params': {'orders': [{'name': 'DUMMY execute anything'}]}})
        self.assertEqual(plans.requested_plan({'params': {'orders': [{'name': 'Статус'}]}})['intent'], 'audit')

    def test_legacy_ingestion_does_not_reset_owned_dag_or_previous_claim(self):
        # Rebind a fresh native fixture whose old ingest reconstructs parents.
        fixture = NativeFixture(self.root)
        def legacy_ingest(state):
            for row in state['tasks'].values():
                if row.get('owner_plan_id') and not row.get('owner_parent_id'):
                    row.update(handler='owner_order', deps=[])
        fixture.ns['ingest_owner_orders'] = legacy_ingest
        plans.bind_dispatcher(fixture.ns)
        parent = fixture.order()
        fixture.execute(parent)
        child = fixture.state['tasks'][parent['owner_plan_children'][0]]
        fixture.execute(child)
        claim = copy.deepcopy(child['owner_claim'])
        expected_deps = list(parent['deps'])
        fixture.ns['ingest_owner_orders'](fixture.state)
        self.assertEqual(parent['handler'], 'owner_plan_join')
        self.assertEqual(parent['deps'], expected_deps)
        self.assertEqual(child['owner_claim'], claim)
        self.assertEqual(child['status'], 'done')
        self.assertEqual(len(fixture.state['tasks']), 7)

    def test_three_branch_config_change_preserves_other_fields_and_verified_scope(self):
        config = self.root / 'config/dispatcher_agents_t868u.json'
        self.fx.write(config, {'workers': 32, 'min_workers': 24, 'max_workers': 32,
                               'tuner_may_adjust': True, 'existing_owner_option': 'preserved'})
        parent = self.fx.order('optimize_workers')
        self.fx.execute(parent)
        self.assertEqual(len(parent['owner_plan_children']), 3)
        self.fx.complete_steps(parent)
        after = plans.read_json(config)
        self.assertEqual(after['existing_owner_option'], 'preserved')
        self.assertEqual(after['workers'], 6)
        self.assertFalse(after['tuner_may_adjust'])
        ok, evidence = self.fx.execute(parent)
        self.assertIs(ok, True)
        self.assertEqual(evidence['scope'], 'SIX_EXECUTOR_CONFIGURATION_ONLY')
        self.assertIn('MEASURED_MODEL_CAPACITY_NOT_ESTABLISHED', evidence['blockers'])

    def test_stop_and_exclusive_maintenance_block_configuration_write(self):
        config = self.root / 'config/dispatcher_agents_t868u.json'
        self.fx.write(config, {'workers': 8})
        before = config.read_bytes()
        parent = self.fx.order('optimize_workers')
        self.fx.execute(parent)
        steps = [self.fx.state['tasks'][key] for key in parent['owner_plan_children']]
        self.fx.execute(steps[0])
        self.fx.stopped = True
        ok, info = self.fx.execute(steps[1])
        self.assertEqual((ok, info['state']), ('wait', 'WAIT_NATIVE_ADMISSION'))
        self.assertEqual(config.read_bytes(), before)
        self.fx.stopped = False
        lock_path = self.root / 'state/owner_maintenance.lock'
        with lock_path.open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            ok, info = self.fx.execute(steps[1])
            self.assertEqual((ok, info['state']), ('wait', 'WAIT_NATIVE_MAINTENANCE'))
        self.assertEqual(config.read_bytes(), before)

    def test_training_and_downloads_wait_for_real_mutation_admission(self):
        hold = self.root / 'state/TRAIN_HOLD.flag'
        hold.write_text('OWNER_HOLD')
        for intent, extra, code in [('training_resume', {}, 'WAIT_TRAINING_ADMISSION'),
                ('downloads', {'component_ids': ['approved.component']}, 'WAIT_DOWNLOAD_ADMISSION')]:
            parent = self.fx.order(intent, **extra)
            self.fx.execute(parent)
            self.fx.complete_steps(parent)
            children = [self.fx.state['tasks'][key] for key in parent['owner_plan_children']]
            self.assertTrue(any(t.get('result', {}).get('state') == code for t in children))
            self.assertEqual(parent['status'], 'pending')
        self.assertEqual(hold.read_text(), 'OWNER_HOLD')

    def test_media_attaches_exact_single_native_task_and_preserves_gpu_lock(self):
        job_id = 'c' * 32
        task = {'id': 'owner.media.' + job_id, 'handler': 'owner_media', 'class': 'owner_order',
                'status': 'pending', 'locks': ['gpu1'], 'deps': [], 'params': {'job_id': job_id}}
        self.fx.state['tasks'][task['id']] = task
        self.fx.ns['owner_media_runtime'] = types.SimpleNamespace(load_job=lambda value: {'request': {'kind': 'image', 'prompt': 'private prompt'}},
                                                                   capabilities=lambda: {'image': True})
        self.fx.ns['HANDLERS']['owner_media'] = lambda value: (True, {'generation_verified': True})
        self.fx.ns['ingest_owner_orders'](self.fx.state)
        self.fx.ns['ingest_owner_orders'](self.fx.state)
        self.assertEqual(sum(t.get('handler') == 'owner_media' for t in self.fx.state['tasks'].values()), 1)
        self.assertEqual(task['locks'], ['gpu1'])
        self.assertEqual(len(task['deps']), 2)
        self.assertFalse(self.fx.ns['deps_ok'](self.fx.state, task))
        parent = self.fx.state['tasks'][task['owner_parent_id']]
        self.assertEqual(len(parent['owner_plan_children']), 3)
        raw = (plans.plan_directory(task['owner_plan_id']) / 'manifest.json').read_text()
        self.assertNotIn('private prompt', raw)
        self.fx.complete_steps(parent)
        ok, evidence = self.fx.execute(parent)
        self.assertIs(ok, True)
        self.assertEqual(evidence['scope'], 'VERIFIED_MEDIA_OUTPUT')

    def test_normal_three_and_boost_six_are_admission_targets_not_capacity_claims(self):
        parent = self.fx.order()
        self.fx.execute(parent)
        children = [self.fx.state['tasks'][key] for key in parent['owner_plan_children']]
        for child in children[:3]:
            child['status'] = 'running'
        self.assertFalse(self.fx.ns['_nox_owner_task_admitted'](children[3]))
        self.assertTrue(self.fx.ns['_nox_owner_task_admitted'](children[0]))
        self.fx.write(self.root / 'state/task_boost_mode.json', {'enabled': True})
        self.assertTrue(self.fx.ns['_nox_owner_task_admitted'](children[3]))
        meta = plans.plan_metadata(parent, self.fx.state)
        self.assertEqual(meta['planned_branches'], 6)
        self.assertEqual(meta['admitted_width'], 6)
        self.assertEqual(meta['global_cap'], 6)
        self.assertFalse(meta['recursive_expansion'])
        self.fx.native_allowed = False
        self.assertFalse(self.fx.ns['_nox_owner_task_admitted'](children[3]))

    def test_fifo_and_symlink_receipts_fail_without_blocking(self):
        fifo = self.root / 'state/fifo'
        os.mkfifo(fifo)
        with self.assertRaises(plans.PlanHold):
            plans.read_bytes(fifo)
        directory = self.root / 'state/owner_plans' / ('d' * 24)
        directory.parent.mkdir(parents=True)
        directory.symlink_to(self.root / 'state', target_is_directory=True)
        with self.assertRaises(plans.PlanHold):
            plans.atomic_json(directory / 'receipt.json', {})

    def test_pressure_reduces_new_claims_and_never_interrupts_existing_claim(self):
        parent = self.fx.order()
        self.fx.execute(parent)
        children = [self.fx.state['tasks'][key] for key in parent['owner_plan_children']]
        self.fx.write(self.root / 'state/task_boost_mode.json', {'enabled': True})
        active = children[0]
        active.update(status='running', owner_claim={'nonce': 'a' * 24})
        with patch.object(plans, 'pressure_snapshot', return_value={'state': 'LOAD_OBSERVED', 'memory_ratio': .97, 'cpu_some_avg10': 1}):
            self.assertFalse(self.fx.ns['_nox_owner_task_admitted'](children[1]))
            self.assertTrue(self.fx.ns['_nox_owner_task_admitted'](active))
            meta = plans.plan_metadata(parent, self.fx.state)
            self.assertEqual(meta['planned_branches'], 6)
            self.assertEqual(meta['new_admission_cap'], 0)
            self.assertEqual(meta['admitted_width'], 1)
            self.assertEqual(active['status'], 'running')
        with patch.object(plans, 'pressure_snapshot', return_value={'state': 'LOAD_OBSERVED', 'memory_ratio': .4, 'cpu_some_avg10': 60}):
            self.assertFalse(self.fx.ns['_nox_owner_task_admitted'](children[1]))
            self.assertEqual(plans.admission_capacity()[1], 1)
        self.assertTrue(self.fx.ns['_nox_owner_task_admitted'](children[1]))

    def test_source_pin_and_binding_order_enforced(self):
        source = '\n'.join('def ' + name + '(*args): pass' for name in
                           ('run_one', 'owner_claim_ready', 'ingest_owner_orders', 'deps_ok')) + '\nif __name__ == "__main__":\n    pass\n'
        sha = hashlib.sha256(source.encode()).hexdigest()
        changed = plans.patch_dispatcher(source, sha)
        self.assertIn('owner_task_plans.bind_dispatcher(globals())', changed)
        with self.assertRaises(plans.PlanHold):
            plans.patch_dispatcher(source, 'f' * 64)
        with self.assertRaises(plans.PlanHold):
            extra = source + '\n# NOX_OWNER_TASK_LIFECYCLE_BIND_V1\n'
            plans.patch_dispatcher(extra, hashlib.sha256(extra.encode()).hexdigest())


class PressureReadTests(unittest.TestCase):
    def test_actual_cgroup_files_are_bounded_and_cached_without_sampling_sleep(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(plans, 'CGROUP', Path(temporary)):
            root = Path(temporary)
            (root / 'memory.current').write_text('40\n')
            (root / 'memory.max').write_text('100\n')
            (root / 'cpu.pressure').write_text('some avg10=2.50 avg60=1.00 avg300=0.00 total=120\n')
            with patch.object(plans.time, 'monotonic', return_value=1000):
                first = plans.pressure_snapshot()
            self.assertEqual(first['memory_ratio'], .4)
            self.assertEqual(first['cpu_some_avg10'], 2.5)
            (root / 'memory.current').write_text('97\n')
            with patch.object(plans.time, 'monotonic', return_value=1001):
                self.assertEqual(plans.pressure_snapshot()['memory_ratio'], .4)
            with patch.object(plans.time, 'monotonic', return_value=1004):
                self.assertEqual(plans.pressure_snapshot()['memory_ratio'], .97)


if __name__ == '__main__':
    unittest.main()
