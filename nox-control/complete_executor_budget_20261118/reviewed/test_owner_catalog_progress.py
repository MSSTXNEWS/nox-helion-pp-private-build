"""Regressions for the exhausted-catalog stall; local status/queue fixtures.

No native process, model, service, or original-task acceptance is simulated as
deployed. Run this file directly from the repository with Python 3.
"""
import copy
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

CONTROL = Path(__file__).resolve().parents[2]
for directory in (CONTROL, CONTROL/'four_queue_20261118',
                  CONTROL/'complete_executor_20261118/runtime',
                  CONTROL/'complete_executor_retries_20261118/runtime',
                  CONTROL/'complete_executor_budget_20261118/runtime'):
    sys.path.insert(0, str(directory))

import owner_subagent_dispatcher as binding


def task(task_id, parent='1A01', deps=()):
    return {'id':task_id, 'handler':binding.PROJECT_HANDLER,
            'params':{'parent_task_id':parent}, 'deps':list(deps)}


def native(rows, states):
    value = binding.Native.__new__(binding.Native)
    value.ns = {'_qlock':threading.RLock()}
    value.catalog = {'schema':binding.autonomy.SCHEMA, 'tasks':rows}
    value.config = {'execution_mode':binding.PROJECT_MODE}
    value.state = {'tasks':states}
    value.projects = SimpleNamespace(reconcile=lambda:None)
    return value


class CatalogProgressTests(unittest.TestCase):
    def test_exhausted_catalog_requests_real_plans_without_replaying_work(self):
        obj = native([task('old.failed'), task('replacement.done')],
                     {'old.failed':{'status':'failed', 'owner_claim':{'nonce':'old'}},
                      'replacement.done':{'status':'done', 'owner_claim':{'nonce':'new'}}})
        before = copy.deepcopy(obj.state)
        result = obj._explain_idle({'state':'NATIVE_QUEUE_IDLE', 'jobs_started':0,
                                   'active_subexecutor_processes':3})
        self.assertEqual(result['state'], 'NATIVE_QUEUE_REVIEWED_CATALOG_EXHAUSTED')
        self.assertEqual(result['next_action'], 'REFILL_REVIEWED_CATALOG')
        self.assertFalse(result['original_completion_proven'])
        self.assertFalse(result['catalog_progress']['automatic_replay_allowed'])
        self.assertEqual(result['catalog_progress']['counts'][binding.PROJECT_HANDLER]['failed'], 1)
        self.assertEqual(obj.state, before)

    def test_unadmitted_dependency_is_a_wait_not_completed_project(self):
        obj = native([task('first'), task('next', deps=('first',))],
                     {'first':{'status':'failed'}})
        result = obj._explain_idle({'state':'NATIVE_QUEUE_IDLE', 'jobs_started':0})
        self.assertEqual(result['state'], 'NATIVE_QUEUE_DEPENDENCY_WAIT')
        self.assertEqual(result['next_action'], 'RESOLVE_REVIEWED_DEPENDENCIES')
        self.assertEqual(result['catalog_progress']['dependency_waiting'], 1)
        self.assertEqual(result['catalog_progress']['dependency_ready'], 0)

    def test_missing_null_and_terminal_rows_remain_distinct(self):
        obj = native([task('absent'), task('null'), task('cancelled'), task('blocked')],
                     {'null':None, 'cancelled':{'status':'cancelled'},
                      'blocked':{'status':'blocked'}})
        counts = obj.catalog_progress()['counts'][binding.PROJECT_HANDLER]
        self.assertEqual({key:counts[key] for key in
                          ('not_admitted','unknown','cancelled','blocked')},
                         {'not_admitted':1,'unknown':1,'cancelled':1,'blocked':1})

    def test_admission_holds_and_active_work_are_never_relabelled(self):
        obj = native([task('work')], {})
        for state in ('HOLD_OWNER_STOP_OR_WRITER_LEASE', 'HOLD_BOUNDED_CPU_HEADROOM',
                      'HOLD_OWNER_WORKER_RECONCILIATION_REQUIRED',
                      'NATIVE_QUEUE_POLICY_WAIT', 'NATIVE_POOL_CONTINUING',
                      'NATIVE_QUEUE_READBACK_VERIFIED'):
            with self.subTest(state=state):
                admission = {'state':state, 'jobs_started':0}
                self.assertIs(obj._explain_idle(admission), admission)

    def test_295_registry_coverage_never_means_295_executable_or_accepted(self):
        obj = native([task('first'), task('first.retry'), task('second', '1A02')],
                     {'first':{'status':'failed'}, 'first.retry':{'status':'done'}})
        ids = ['1A01','1A02'] + ['original.'+str(n) for n in range(293)]
        docs = {
            'work_tasks_sha256':{'tasks':[{} for _ in range(230)]},
            'work_ideas_sha256':{'ideas':[{} for _ in range(65)]},
            'routing_sha256':{'dispatch_cap':3, 'tasks':[
                {'task_id':task_id, 'queue_id':binding.autonomy.QUEUE_IDS[n%4]}
                for n,task_id in enumerate(ids)]}}
        raw = {binding.PROJECT_FILES[key]:binding.encoded(value) for key,value in docs.items()}
        obj.config = {'project_handoff':{key:binding.digest(raw[path])
                      for key,path in binding.PROJECT_FILES.items()}}
        with patch.object(binding, 'read', side_effect=lambda path,limit:raw[path]):
            result = obj.project_status()
        self.assertEqual(result['received_unique_tasks'], 295)
        self.assertEqual(result['bound_project_subtasks'], 3)
        self.assertEqual(result['project_status']['not_admitted'], 1)
        self.assertEqual(result['project_status']['failed'], 1)
        self.assertEqual(result['original_task_acceptance_added'], 0)
        progress = result['catalog_progress']
        self.assertEqual(progress['original_ids_with_current_project_plan'], 2)
        self.assertEqual(progress['original_ids_without_current_project_plan'], 293)
        self.assertFalse(progress['original_acceptance_known'])

    def test_tick_leaves_reviewed_refill_to_existing_admission(self):
        obj = native([task('done')], {'done':{'status':'done'}})
        obj.tick_lock, obj.lock = threading.Lock(), threading.RLock()
        obj.pool, obj._pool_recovery, obj._pool_recovery_uncertain = None, None, False
        obj.stop_active, obj.last_tick = lambda:False, 0
        admitted = {'state':'NATIVE_QUEUE_READBACK_VERIFIED', 'jobs_started':1}
        def admission(_namespace, state, **kwargs):
            if len(obj.catalog['tasks']) == 1:
                return {'state':'NATIVE_QUEUE_IDLE', 'jobs_started':0}
            return admitted
        with patch.object(binding.autonomy, 'tick_existing_dispatcher', side_effect=admission) as tick, \
             patch.object(binding.time, 'monotonic', side_effect=[100,100,200,200]):
            obj.tick(obj.state)
            self.assertEqual(obj.last_status['next_action'], 'REFILL_REVIEWED_CATALOG')
            old_pin = obj.last_status['catalog_progress']['catalog_sha256']
            obj.catalog['tasks'].append(task('new.reviewed', deps=('done',)))
            self.assertNotEqual(obj.catalog_progress()['catalog_sha256'], old_pin)
            obj.tick(obj.state)
        self.assertIs(obj.last_status, admitted)
        self.assertEqual(tick.call_count, 2)
        self.assertNotIn('new.reviewed', obj.state['tasks'])  # Status owns no queue writes.

    def test_agent_status_has_no_base_only_publish_window(self):
        obj = native([], {})
        obj.handle = obj.verify = obj.close = lambda *args:None
        obj.last_status = {'state':'NATIVE_QUEUE_REVIEWED_CATALOG_EXHAUSTED'}
        obj.last_resource_admission = None
        obj.last_pool_started_at = obj.last_pool_closed_at = obj.last_pool_close_reason = None
        writer_lock = threading.Lock()
        def observe_before_writer_lock():
            self.assertTrue(writer_lock.acquire(blocking=False))
            writer_lock.release()
            return [{'pid':123,'role':'runtime'}]
        obj.process_readback = observe_before_writer_lock
        obj.review_status = lambda:{'catalog_tasks':0}
        obj.project_status = lambda:{'received_unique_tasks':295}
        path = Path('/root/nox/status/agents_t856u.json')
        writes = []
        namespace = {'HANDLERS':{}, 'LOCKS':{}, '_qlock':threading.RLock(),
                     '_owner_lifecycle_bound':True, 'WORKERS':3, 'AGENT_STATUS':path,
                     'save_state':lambda state:None, 'write_status':lambda state:None,
                     '_nox_owner_task_admitted':lambda task:True,
                     'owner_mentor':SimpleNamespace(verify_success=lambda *args:False),
                     'atomic_write':lambda name,row:writes.append((name,copy.deepcopy(row)))}
        source_row = {'workers':[], 'at':100}
        def old_agents():
            with writer_lock:
                namespace['atomic_write'](path, source_row)
            return 'original-writer-return'
        namespace['write_agents_status'] = old_agents
        with patch.object(binding, 'Native', return_value=obj), \
             patch.object(binding.atexit, 'register'), \
             patch.object(binding, 'process_identity', return_value={'pid':99}):
            binding.bind_dispatcher(namespace)
            self.assertEqual(namespace['write_agents_status'](), 'original-writer-return')
            self.assertEqual(len(writes), 1)
            self.assertEqual(writes[0][1]['native_subexecutors']['workers'], [{'pid':123,'role':'runtime'}])
            self.assertNotIn('native_subexecutors', source_row)
            namespace['atomic_write'](Path('/root/nox/state/other.json'), {'other':1})
            self.assertEqual(writes[-1][1], {'other':1})
            obj.project_status = lambda:(_ for _ in ()).throw(binding.GateError('HOLD_PROJECT_HANDOFF_SHA'))
            namespace['write_agents_status']()
            self.assertEqual(len(writes), 3)
            failure = writes[-1][1]['native_subexecutors']
            self.assertEqual(failure['state'], 'HOLD_NATIVE_STATUS_PROJECTION')
            self.assertFalse(failure['worker_observation_valid'])
            obj.project_status = lambda:{'received_unique_tasks':295}
            obj.last_status = {'invalid':float('nan')}
            namespace['write_agents_status']()
            self.assertEqual(len(writes), 4)
            self.assertEqual(writes[-1][1]['native_subexecutors']['state'], 'HOLD_NATIVE_STATUS_PROJECTION')
            namespace['atomic_write'](path, source_row)
            self.assertEqual(len(writes), 5)
            self.assertEqual(writes[-1][1]['native_subexecutors']['state'], 'HOLD_NATIVE_STATUS_PUBLICATION_CONTEXT')


if __name__ == '__main__':
    unittest.main()
