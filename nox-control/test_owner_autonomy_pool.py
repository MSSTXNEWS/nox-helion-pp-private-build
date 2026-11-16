import json
import multiprocessing as mp
import os
import time
import unittest
from unittest.mock import Mock
import owner_autonomy_pool as pool


def process_echo(q, ready, go):
    q.put((os.getpid(), os.getppid()))
    ready.set()
    go.wait(6)

class PoolTests(unittest.TestCase):
    def make_rows(self,n):
        return [{'id':f'job.{i:05d}','handler':'owner_component','deps':[f'job.{i-1:05d}'] if i%5==4 else [],
                 'priority':'P0' if i%3==0 else 'P2','resource':'CPU_LIGHT',
                 'source_sha256':'a'*64,'estimated_cost':1+i%9} for i in range(n)]

    def test_any_count_in_one_command(self):
        rows=self.make_rows(1500)
        result=pool.validate_submission({'schema':pool.SCHEMA,'tasks':rows},allowed_handlers={'owner_component'})
        self.assertEqual(result['task_count'],1500)
        self.assertGreater(result['page_count'],1)
        self.assertTrue(all(len(p['tasks'])<=256 for p in result['pages']))
        self.assertEqual(len({t['id'] for p in result['pages'] for t in p['tasks']}),1500)

    def test_cross_page_cycle_fails(self):
        rows=self.make_rows(550)
        rows[0]['deps']=['job.00549']
        rows[549]['deps']=['job.00000']
        with self.assertRaisesRegex(pool.AutoHold,'CYCLE'):
            pool.validate_submission({'schema':pool.SCHEMA,'tasks':rows},allowed_handlers={'owner_component'})

    def test_dispatcher_tick_requires_real_native_callbacks(self):
        self.assertEqual(pool.tick_existing_dispatcher({}, {}, mode='NORMAL')['state'],'HOLD_NATIVE_POOL_CALLBACKS')
        n=Mock()
        n.read_reviewed_catalog.return_value={'schema':pool.SCHEMA,'tasks':self.make_rows(4)}
        n.read_resource_snapshot.return_value={'native_verified':True,'instance_id':60509551,
            'stop_active':False,'source_sha_verified':True,'owner_scope_verified':True,
            'task_status':{},'cgroup_memory_ratio':.4,'cpu_pressure':0,'gpu_available':False}
        n.allowed_handlers.return_value={'owner_component'}
        n.owner_allowed.return_value=True;n.stop_active.return_value=False;n.writer_lease.return_value=True
        n.ensure_processes.return_value=True;n.native_duplicate_check.return_value=False
        n.process_readback.return_value=[{'pid':30+i,'process_starttime':100+i,'native_pid_verified':True,
            'state':'RUNNING','instance_id':60509551,'origin':'existing_onehost'} for i in range(3)]
        n.native_queue_claim.side_effect=lambda task,owner_pids:{'job_id':'native-'+task['id']}
        n.s03_readback.side_effect=lambda tid,jid:{'task_id':tid,'job_id':jid,'native_verified':True,
            'receipt_sha256':'b'*64}
        r=pool.tick_existing_dispatcher({'_nox_owner_autonomy_native':n},{},mode='NORMAL')
        self.assertEqual(r['jobs_started'],3)
        self.assertEqual(r['active_subexecutor_processes'],3)

    def test_30_jobs_one_command(self):
        rows=self.make_rows(30)
        validated=pool.validate_page({'schema':pool.SCHEMA,'tasks':rows},allowed_handlers={'owner_component'})
        self.assertEqual(len(validated),30)
        self.assertEqual(len(pool.choose_ready(validated,status={},mode='NORMAL',memory_ratio=.4)),3)
        self.assertEqual(len(pool.choose_ready(validated,status={},mode='FORSAZH',memory_ratio=.4)),6)

    def test_many_jobs_as_bounded_pages_no_global_count(self):
        n=4000;all_seen=set()
        for start in range(0,n,200):
            rows=self.make_rows(n)[start:start+200]
            # self-contained dependency not needed beyond already-accepted IDs
            page=pool.validate_page({'schema':pool.SCHEMA,'tasks':rows},
                allowed_handlers={'owner_component'},known_ids=all_seen)
            all_seen.update(x['id'] for x in page)
        self.assertEqual(len(all_seen),n)

    def test_cycle_rejected(self):
        rows=[{'id':'a','deps':['b'],'handler':'owner_component','source_sha256':'a'*64},
              {'id':'b','deps':['a'],'handler':'owner_component','source_sha256':'a'*64}]
        with self.assertRaisesRegex(pool.AutoHold,'CYCLE'):
            pool.validate_page({'schema':pool.SCHEMA,'tasks':rows},allowed_handlers={'owner_component'})

    def test_reject_unreviewed_handler(self):
        with self.assertRaisesRegex(pool.AutoHold,'UNREVIEWED'):
            pool.validate_page({'schema':pool.SCHEMA,'tasks':[{'id':'x','handler':'arbitrary_shell','source_sha256':'a'*64}]},allowed_handlers={'owner_component'})

    def test_mode_pressure_and_dependency(self):
        rows=pool.validate_page({'schema':pool.SCHEMA,'tasks':self.make_rows(30)},allowed_handlers={'owner_component'})
        self.assertEqual(pool.choose_ready(rows,status={},mode='FORSAZH',memory_ratio=.96),[])
        self.assertEqual(len(pool.choose_ready(rows,status={},mode='FORSAZH',memory_ratio=.86)),3)
        self.assertEqual(len(pool.choose_ready(rows,status={},mode='FORSAZH',memory_ratio=.4,cpu_pressure=51)),1)
        self.assertEqual(len(pool.choose_ready(rows,status={'job.00000':'running','job.00001':'running'},mode='NORMAL',memory_ratio=.4)),1)
        self.assertEqual(len(pool.choose_ready(rows,status={'job.00000':'done'},mode='NORMAL',memory_ratio=.4)),3)

    def test_no_thread_alias_as_os_process(self):
        bad=[{'pid':777,'process_starttime':1,'native_pid_verified':True,'state':'RUNNING','instance_id':60509551,'origin':'existing_onehost'}]*3
        with self.assertRaisesRegex(pool.AutoHold,'DUPLICATE_NATIVE_PROCESS'):
            pool.verify_distinct_native_processes(bad,requested=3)

    def test_real_independent_processes_normal_and_forsazh(self):
        for count in (3,6):
            q=mp.Queue();go=mp.Event(); processes=[]
            for _ in range(count):
                p=mp.Process(target=process_echo,args=(q,mp.Event(),go))
                p.start();processes.append(p)
            observed=[q.get(timeout=4)[0] for _ in range(count)]
            go.set()
            for p in processes:p.join(timeout=5)
            self.assertEqual(len(set(observed)),count)
            self.assertTrue(all(p.exitcode==0 for p in processes))

    def test_idle_does_not_start_processes_for_pid_count(self):
        n=Mock();n.owner_allowed.return_value=True;n.stop_active.return_value=False;n.writer_lease.return_value=True
        n.ensure_processes.return_value=True
        for mode,count in [('NORMAL',3),('FORSAZH',6)]:
            n.process_readback.return_value=[{'pid':20+i,'process_starttime':100+i,'native_pid_verified':True,'state':'RUNNING','instance_id':60509551,'origin':'existing_onehost'} for i in range(count)]
            result=pool.admit_native_tick(n,tasks=[],status={},mode=mode,memory_ratio=.5)
            self.assertEqual(result['state'],'NATIVE_QUEUE_IDLE')
            self.assertEqual(result['active_subexecutor_processes'],count)
            n.ensure_processes.assert_not_called()

    def test_empty_queue_still_keeps_default_pool(self):
        n=Mock();n.read_reviewed_catalog.return_value={'schema':pool.SCHEMA,'tasks':[]}
        n.read_resource_snapshot.return_value={'native_verified':True,'instance_id':60509551,
            'stop_active':False,'source_sha_verified':True,'owner_scope_verified':True,
            'task_status':{},'cgroup_memory_ratio':.5,'cpu_pressure':0,'gpu_available':False}
        n.allowed_handlers.return_value={'owner_component'}
        n.owner_allowed.return_value=True;n.stop_active.return_value=False;n.writer_lease.return_value=True
        n.ensure_processes.return_value=True
        n.process_readback.return_value=[{'pid':60+i,'process_starttime':100+i,'native_pid_verified':True,
            'state':'RUNNING','instance_id':60509551,'origin':'existing_onehost'} for i in range(3)]
        r=pool.tick_existing_dispatcher({'_nox_owner_autonomy_native':n},{},mode='NORMAL')
        self.assertEqual(r['state'],'NATIVE_QUEUE_IDLE')
        self.assertEqual(r['active_subexecutor_processes'],3)
        n.ensure_processes.assert_not_called()

    def test_native_gates_hold_or_verified(self):
        task=pool.validate_page({'schema':pool.SCHEMA,'tasks':self.make_rows(3)},allowed_handlers={'owner_component'})
        n=Mock();n.owner_allowed.return_value=True;n.stop_active.return_value=False;n.writer_lease.return_value=True
        n.ensure_processes.return_value=True
        n.process_readback.return_value=[{'pid':10+i,'process_starttime':100+i,'native_pid_verified':True,'state':'RUNNING','instance_id':60509551,'origin':'existing_onehost'} for i in range(3)]
        n.native_duplicate_check.return_value=False
        n.native_queue_claim.side_effect=lambda task,owner_pids:{'job_id':'native-'+task['id']}
        n.s03_readback.side_effect=lambda tid,jid:{'task_id':tid,'job_id':jid,'native_verified':True,'receipt_sha256':'b'*64}
        receipt=pool.admit_native_tick(n,tasks=task,status={},mode='NORMAL',memory_ratio=.5)
        self.assertEqual(receipt['jobs_started'],3)
        self.assertEqual(receipt['active_subexecutor_processes'],3)
        n.stop_active.return_value=True
        self.assertEqual(pool.admit_native_tick(n,tasks=task,status={},mode='NORMAL',memory_ratio=.5)['jobs_started'],0)

if __name__=='__main__':unittest.main()
