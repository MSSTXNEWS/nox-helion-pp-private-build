"""Budget arithmetic, real guard wiring, and historical-source non-replay.

Scheduler callback fixtures are source tests, not proof of native deployment.
The receipt migration test executes a real isolated source change locally;
its S03 transport remains the exact-record unit fixture.
"""
import copy
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import owner_autonomy_pool as pool
import owner_subagent_dispatcher as binding
from owner_subagent_processes import GateError
from test_owner_four_queue import ClaimingNative, task
import test_owner_project_native as project_fixture


def budget(**changes):
    return {'schema':pool.BOUNDED_CPU_SCHEMA, 'source':'cgroup_v2', 'instance_id':60509551,
            'observed_at':time.time(), 'worker_slots':3, 'current_bytes':193828540416,
            'max_bytes':194065203200, 'inactive_file_bytes':9657630720,
            'file_bytes':190000000000, 'shmem_bytes':75403436032,
            'sandbox_limit_bytes':256*pool.MIB, 'planner_reserve_bytes':128*pool.MIB,
            'minimum_headroom_bytes':pool.BOUNDED_CPU_HEADROOM,
            'memory_psi_some_avg10':0.0, 'memory_psi_full_avg10':0.0,
            'cpu_pressure':0.0, **changes}


def args(value):
    decision = pool.bounded_cpu_decision(value)
    return {'memory_ratio':decision['projected_memory_ratio'],
            'cpu_pressure':value['cpu_pressure'], 'bounded_cpu_budget':value}


def rows():
    return [task(q, n, handler=binding.PROJECT_HANDLER) for q in range(4) for n in range(2)]


class BoundedCpuTests(unittest.TestCase):
    def test_actual_native_bytes_admit_without_changing_ratio(self):
        value = budget()
        result = pool.bounded_cpu_decision(value)
        self.assertTrue(result['eligible'])
        self.assertEqual(result['headroom_bytes'], 8686333952)
        self.assertEqual(result['reserved_bytes'], 3*384*pool.MIB)
        self.assertGreater(result['projected_memory_ratio'], .95)
        self.assertAlmostEqual(result['raw_memory_ratio'], 193828540416/194065203200)
        self.assertEqual(len(pool.choose_ready(rows(), status={}, mode='NORMAL', **args(value))), 3)
        self.assertEqual(pool.choose_ready(rows(), status={}, mode='NORMAL',
                                          memory_ratio=result['projected_memory_ratio']), [])

    def test_exact_two_gib_headroom_boundary(self):
        value = budget(current_bytes=100*pool.MIB, inactive_file_bytes=0)
        value['max_bytes'] = value['current_bytes'] + 3*384*pool.MIB + pool.BOUNDED_CPU_HEADROOM
        self.assertTrue(pool.bounded_cpu_decision(value)['eligible'])
        value['max_bytes'] -= 1
        self.assertEqual(pool.bounded_cpu_decision(value)['reason'], 'HOLD_BOUNDED_CPU_HEADROOM')

    def test_shmem_is_never_reclaimable(self):
        value = budget(file_bytes=75403436032)
        result = pool.bounded_cpu_decision(value)
        self.assertEqual(result['reclaimable_bytes'], 0)
        self.assertFalse(result['eligible'])

    def test_schema_numbers_reserve_ratio_and_pressure_fail_closed(self):
        base = budget()
        for changes in ({'max_bytes':True}, {'worker_slots':1}, {'planner_reserve_bytes':0},
                        {'minimum_headroom_bytes':0}, {'memory_psi_full_avg10':float('nan')},
                        {'shmem_bytes':base['file_bytes']+1}, {'sandbox_limit_bytes':0}):
            with self.subTest(changes=changes), self.assertRaises(pool.AutoHold):
                pool.bounded_cpu_decision({**base, **changes})
        missing = dict(base);missing.pop('memory_psi_some_avg10')
        with self.assertRaises(pool.AutoHold):pool.bounded_cpu_decision(missing)
        with self.assertRaisesRegex(pool.AutoHold, 'RATIO_MISMATCH'):
            pool.bounded_cpu_decision(base, memory_ratio=.1)
        with self.assertRaisesRegex(pool.AutoHold, 'PRESSURE_MISMATCH'):
            pool.bounded_cpu_decision(base, cpu_pressure=1)
        for changes, reason in (({'observed_at':time.time()-6}, 'STALE_SNAPSHOT'),
                                ({'observed_at':time.time()+1}, 'STALE_SNAPSHOT'),
                                ({'memory_psi_some_avg10':1}, 'MEMORY_PRESSURE'),
                                ({'memory_psi_full_avg10':1}, 'MEMORY_PRESSURE'),
                                ({'cpu_pressure':50}, 'CPU_PRESSURE')):
            self.assertEqual(pool.bounded_cpu_decision({**base, **changes})['reason'], 'HOLD_BOUNDED_CPU_'+reason)

    def test_only_typed_cpu_light_tasks_use_budget(self):
        value = budget();candidates=rows()[:4]
        candidates[0]['handler'] = binding.HANDLER
        candidates[1]['resource'] = 'GPU_EXCLUSIVE'
        candidates[2]['resource'] = 'CPU_IO'
        candidates[3]['resource_demand'] = None
        self.assertEqual(pool.choose_ready(candidates, status={}, mode='NORMAL', **args(value)), [])

    def test_three_slots_pending_unknown_and_fourth_queue_fairness(self):
        value = budget();candidates=rows()
        ready = pool.choose_ready(candidates, status={}, mode='FORSAZH', worker_cap=6, **args(value))
        self.assertEqual([row['queue_id'] for row in ready], list(pool.QUEUE_IDS[:3]))
        status={ready[0]['id']:'pending', ready[1]['id']:None}
        self.assertEqual(len(pool.choose_ready(candidates, status=status, mode='NORMAL', **args(value))), 1)
        status[ready[2]['id']]='running'
        self.assertEqual(pool.choose_ready(candidates, status=status, mode='NORMAL', **args(value)), [])
        status.update({row['id']:'done' for row in ready})
        next_rows=pool.choose_ready(candidates, status=status, mode='NORMAL', queue_cursor=3, **args(value))
        self.assertEqual(next_rows[0]['queue_id'], pool.QUEUE_IDS[3])

    def test_existing_admit_and_final_submit_guards_use_same_budget(self):
        value=budget();native=ClaimingNative(rows());native.count=0
        result=pool.admit_native_tick(native,tasks=native.tasks,status={},mode='NORMAL',**args(value))
        self.assertEqual(result['jobs_started'],3)
        self.assertEqual(native.ensure_calls,1)
        snapshot={'native_verified':True,'instance_id':60509551,'stop_active':False,
                  'owner_scope_verified':True,'source_sha_verified':True,
                  'cgroup_memory_ratio':args(value)['memory_ratio'],'cpu_pressure':0,
                  'admission_class':'BOUNDED_CPU_PROJECT_SOURCE','bounded_cpu_budget':value}
        self.assertIsNone(binding.resource_wait_reason(snapshot))
        for key in ('stop_active','owner_scope_verified','source_sha_verified'):
            bad=copy.deepcopy(snapshot);bad[key]=not bad[key]
            self.assertIsNotNone(binding.resource_wait_reason(bad))
        bad=copy.deepcopy(snapshot);bad['bounded_cpu_budget']['observed_at']-=6
        self.assertEqual(binding.resource_wait_reason(bad),'HOLD_BOUNDED_CPU_STALE_SNAPSHOT')
        for stop,lease in ((True,True),(False,False)):
            blocked=ClaimingNative(rows());blocked.stop=stop;blocked.lease=lease
            result=pool.admit_native_tick(blocked,tasks=blocked.tasks,status={},mode='NORMAL',**args(value))
            self.assertEqual(result['state'],'HOLD_OWNER_STOP_OR_WRITER_LEASE')
            self.assertEqual(blocked.claimed,[])


class NativeBudgetAndHistoryTests(unittest.TestCase):
    def setUp(self):
        project_fixture.NativeProjectTests.setUp(self)

    def test_native_snapshot_preserves_actual_budget_and_fresh_claim_gate(self):
        native=self.native;native.projects.config['sandbox']['memory_mb']=256
        value=budget()
        files={'memory.current':str(value['current_bytes']),'memory.max':str(value['max_bytes']),
               'memory.stat':'\n'.join(key+' '+str(value[field]) for key,field in
                    (('inactive_file','inactive_file_bytes'),('file','file_bytes'),('shmem','shmem_bytes'))),
               'cpu.pressure':'some avg10=0.00 avg60=0 total=0\n',
               'memory.pressure':'some avg10=0.00 avg60=0 total=0\nfull avg10=0.00 avg60=0 total=0\n'}
        with patch.object(Path,'read_text',lambda path,*a,**kw:files[path.name]):
            snapshot=native.read_resource_snapshot()
        self.assertGreater(snapshot['cgroup_memory_ratio'],.95)
        self.assertEqual(snapshot['bounded_cpu_decision']['headroom_bytes'],8686333952)
        self.assertEqual(snapshot['bounded_cpu_budget']['current_bytes'],value['current_bytes'])
        self.assertEqual(native.last_resource_admission['bounded_cpu_budget'],snapshot['bounded_cpu_budget'])
        native._fresh_admission_reason=lambda **kw:'HOLD_BOUNDED_CPU_HEADROOM'
        with self.assertRaisesRegex(GateError,'BOUNDED_CPU_HEADROOM'):
            native.native_queue_claim(self.tasks[0],[101,102,103])
        self.assertEqual(native.state['tasks'],{})

    def test_historical_project_receipt_verifies_but_cannot_replay(self):
        native=self.native;native.process_readback=binding.Native.process_readback.__get__(native)
        self.addCleanup(native.close_pool)
        self.assertTrue(native.ensure_processes(3))
        native.projects.claim(self.tasks[0],[r['pid'] for r in native.process_readback()])
        row=native.state['tasks'][self.tasks[0]['id']]
        row.update(status='running',owner_claim={'nonce':'e'*24,'pid':os.getpid()})
        ok,info=native._handle(row);self.assertTrue(ok,info)
        row.update(status='done',result=info);native.ns['save_state'](native.state)
        prior=copy.deepcopy(row);old_source=native.source
        native.source='f'*64;native.config['historical_project_source_sha256']=[old_source]
        self.assertEqual(native.projects.validate_row(self.tasks[0])['task_id'],row['id'])
        self.assertEqual(native.verify(row,info)['source_sha256'],old_source)
        with self.assertRaisesRegex(GateError,'HISTORICAL_PROJECT_VERIFY_ONLY'):
            native.projects.claim(self.tasks[1],[r['pid'] for r in native.process_readback()])
        self.assertFalse(native.projects.admitted(row))
        self.assertEqual(native.projects.handle(row),(False,'HOLD_PROJECT_NATIVE_CLAIM'))
        native.projects.reconcile()
        self.assertEqual(row,prior)
        native.config['historical_project_source_sha256']=[]
        self.assertIsNone(native.verify(row,info))

    def test_exact_historical_blocked_receipt_releases_capacity_without_rewrite(self):
        native=self.native;native.projects.claim(self.tasks[0],[101,102,103])
        row=native.state['tasks'][self.tasks[0]['id']]
        row.update(status='running',owner_claim={'nonce':'d'*24,'pid':os.getpid()})
        evidence={'schema':binding.project_executor.EVIDENCE_SCHEMA,'task_id':row['id'],
                  'parent_task_id':row['parent_task_id'],'queue_id':row['queue_id'],
                  'plan_sha256':row['params']['plan_sha256'],'original_task_accepted':False,
                  'acceptance_scope':'SOURCE_PATCH_TESTED','state':'FAILED_TESTS',
                  'project_source_changed':False}
        event={'project_evidence':evidence,'project_evidence_sha256':binding.digest(binding.encoded(evidence))}
        ok,info=native.projects._finish(row,event,'d'*24);self.assertFalse(ok)
        row.update(status='blocked',result=info);native.ns['save_state'](native.state)
        prior=copy.deepcopy(row);old_source=native.source
        native.source='f'*64;native.config['historical_project_source_sha256']=[old_source]
        self.assertTrue(native.projects.terminal_for_capacity(row))
        self.assertTrue(native._settled_project_failure(row))
        native.projects.reconcile();self.assertEqual(row,prior)
        native.config['historical_project_source_sha256']=[]
        self.assertFalse(native.projects.terminal_for_capacity(row))
        self.assertFalse(native._settled_project_failure(row))


if __name__=='__main__':
    unittest.main()
