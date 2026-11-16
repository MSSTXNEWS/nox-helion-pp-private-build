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
            'state':'RUNNING','instance_id':60509551,'origin':'existing_onehost',
            'native_heartbeat_verified':True,'heartbeat_age_seconds':1} for i in range(2)]
        n.native_queue_claim.side_effect=lambda task,owner_pids:{'job_id':'native-'+task['id']}
        n.s03_readback.side_effect=lambda tid,jid:{'task_id':tid,'job_id':jid,'native_verified':True,
            'receipt_sha256':'b'*64}
        r=pool.tick_existing_dispatcher({'_nox_owner_autonomy_native':n},{},mode='NORMAL')
        self.assertEqual(r['jobs_started'],2)
        self.assertEqual(r['active_subexecutor_processes'],2)

    def test_30_jobs_one_command(self):
        rows=self.make_rows(30)
        validated=pool.validate_page({'schema':pool.SCHEMA,'tasks':rows},allowed_handlers={'owner_component'})
        self.assertEqual(len(validated),30)
        self.assertEqual(len(pool.choose_ready(validated,status={},mode='NORMAL',memory_ratio=.4)),2)
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
        self.assertEqual(len(pool.choose_ready(rows,status={'job.00000':'running','job.00001':'running'},mode='NORMAL',memory_ratio=.4)),0)
        self.assertEqual(len(pool.choose_ready(rows,status={'job.00000':'done'},mode='NORMAL',memory_ratio=.4)),2)

    def test_no_thread_alias_as_os_process(self):
        bad=[{'pid':777,'process_starttime':1,'native_pid_verified':True,'state':'RUNNING','instance_id':60509551,'origin':'existing_onehost',
            'native_heartbeat_verified':True,'heartbeat_age_seconds':1}]*3
        with self.assertRaisesRegex(pool.AutoHold,'DUPLICATE_NATIVE_PROCESS'):
            pool.verify_distinct_native_processes(bad,requested=3)

    def test_real_independent_processes_normal_and_forsazh(self):
        for count in (2,6):
            q=mp.Queue();go=mp.Event(); processes=[];ready_events=[]
            for _ in range(count):
                ready=mp.Event();ready_events.append(ready)
                p=mp.Process(target=process_echo,args=(q,ready,go))
                p.start();processes.append(p)
            observed=[q.get(timeout=4)[0] for _ in range(count)]
            go.set()
            for p in processes:p.join(timeout=5)
            self.assertEqual(len(set(observed)),count)
            self.assertTrue(all(p.exitcode==0 for p in processes))

    def test_idle_still_opens_two_or_six_os_processes(self):
        n=Mock();n.owner_allowed.return_value=True;n.stop_active.return_value=False;n.writer_lease.return_value=True
        n.ensure_processes.return_value=True
        for mode,count in [('NORMAL',2),('FORSAZH',6)]:
            n.process_readback.return_value=[{'pid':20+i,'process_starttime':100+i,'native_pid_verified':True,'state':'RUNNING','instance_id':60509551,'origin':'existing_onehost',
            'native_heartbeat_verified':True,'heartbeat_age_seconds':1} for i in range(count)]
            result=pool.admit_native_tick(n,tasks=[],status={},mode=mode,memory_ratio=.5)
            self.assertEqual(result['state'],'NATIVE_POOL_READY_IDLE')
            self.assertEqual(result['active_subexecutor_processes'],count)
            n.ensure_processes.assert_called_with(count)

    def test_empty_queue_still_keeps_default_pool(self):
        n=Mock();n.read_reviewed_catalog.return_value={'schema':pool.SCHEMA,'tasks':[]}
        n.read_resource_snapshot.return_value={'native_verified':True,'instance_id':60509551,
            'stop_active':False,'source_sha_verified':True,'owner_scope_verified':True,
            'task_status':{},'cgroup_memory_ratio':.5,'cpu_pressure':0,'gpu_available':False}
        n.allowed_handlers.return_value={'owner_component'}
        n.owner_allowed.return_value=True;n.stop_active.return_value=False;n.writer_lease.return_value=True
        n.ensure_processes.return_value=True
        n.process_readback.return_value=[{'pid':60+i,'process_starttime':100+i,'native_pid_verified':True,
            'state':'RUNNING','instance_id':60509551,'origin':'existing_onehost',
            'native_heartbeat_verified':True,'heartbeat_age_seconds':1} for i in range(2)]
        r=pool.tick_existing_dispatcher({'_nox_owner_autonomy_native':n},{},mode='NORMAL')
        self.assertEqual(r['state'],'NATIVE_POOL_READY_IDLE')
        self.assertEqual(r['active_subexecutor_processes'],2)

    def test_native_gates_hold_or_verified(self):
        task=pool.validate_page({'schema':pool.SCHEMA,'tasks':self.make_rows(3)},allowed_handlers={'owner_component'})
        n=Mock();n.owner_allowed.return_value=True;n.stop_active.return_value=False;n.writer_lease.return_value=True
        n.ensure_processes.return_value=True
        n.process_readback.return_value=[{'pid':10+i,'process_starttime':100+i,'native_pid_verified':True,'state':'RUNNING','instance_id':60509551,'origin':'existing_onehost',
            'native_heartbeat_verified':True,'heartbeat_age_seconds':1} for i in range(2)]
        n.native_duplicate_check.return_value=False
        n.native_queue_claim.side_effect=lambda task,owner_pids:{'job_id':'native-'+task['id']}
        n.s03_readback.side_effect=lambda tid,jid:{'task_id':tid,'job_id':jid,'native_verified':True,'receipt_sha256':'b'*64}
        receipt=pool.admit_native_tick(n,tasks=task,status={},mode='NORMAL',memory_ratio=.5)
        self.assertEqual(receipt['jobs_started'],2)
        self.assertEqual(receipt['active_subexecutor_processes'],2)
        n.stop_active.return_value=True
        self.assertEqual(pool.admit_native_tick(n,tasks=task,status={},mode='NORMAL',memory_ratio=.5)['jobs_started'],0)


    def _native_claim_mock(self):
        n=Mock()
        n.owner_allowed.return_value=True
        n.stop_active.return_value=False
        n.writer_lease.return_value=True
        n.ensure_processes.return_value=True
        n.native_duplicate_check.return_value=False
        n.process_readback.return_value=[
            {'pid':500+i,'process_starttime':1000+i,'native_pid_verified':True,
             'state':'RUNNING','instance_id':60509551,'origin':'existing_onehost',
            'native_heartbeat_verified':True,'heartbeat_age_seconds':1}
            for i in range(2)]
        n.native_queue_claim.side_effect=lambda task,owner_pids:{'job_id':'native-'+task['id']}
        n.s03_readback.side_effect=lambda tid,jid:{
            'native_verified':True,'task_id':tid,'job_id':jid,'receipt_sha256':'b'*64}
        return n

    def test_post_s03_readback_stop_revocation_preserves_claim_and_holds(self):
        n=self._native_claim_mock()
        def s03_then_stop(tid, jid):
            n.stop_active.return_value=True
            return {'task_id':tid,'job_id':jid,'native_verified':True,
                    'receipt_sha256':'b'*64}
        n.s03_readback.side_effect=s03_then_stop
        tasks=pool.validate_page({'schema':pool.SCHEMA,'tasks':self.make_rows(3)},
                                 allowed_handlers={'owner_component'})
        out=pool.admit_native_tick(n,tasks=tasks,status={},mode='NORMAL',memory_ratio=.5)
        self.assertEqual(out['state'],'HOLD_STOP_OR_LEASE_CHANGED')
        self.assertEqual(out['jobs_started'],1)
        self.assertEqual(out['receipts'][0]['task_id'],'job.00000')
        self.assertEqual(n.native_queue_claim.call_count,1)

    def test_post_s03_readback_lease_revocation_preserves_claim(self):
        n=self._native_claim_mock()
        def s03_then_revoke(tid, jid):
            n.writer_lease.return_value=False
            return {'task_id':tid,'job_id':jid,'native_verified':True,
                    'receipt_sha256':'b'*64}
        n.s03_readback.side_effect=s03_then_revoke
        tasks=pool.validate_page({'schema':pool.SCHEMA,'tasks':self.make_rows(3)},
                                 allowed_handlers={'owner_component'})
        out=pool.admit_native_tick(n,tasks=tasks,status={},mode='NORMAL',memory_ratio=.5)
        self.assertEqual(out['state'],'HOLD_STOP_OR_LEASE_CHANGED')
        self.assertEqual(out['jobs_started'],1)
        self.assertEqual(n.native_queue_claim.call_count,1)

    def test_post_s03_readback_owner_probe_failure_fails_closed(self):
        n=self._native_claim_mock()
        def s03_then_fault(tid, jid):
            n.owner_allowed.side_effect=OSError('owner auth readback unavailable')
            return {'task_id':tid,'job_id':jid,'native_verified':True,
                    'receipt_sha256':'b'*64}
        n.s03_readback.side_effect=s03_then_fault
        tasks=pool.validate_page({'schema':pool.SCHEMA,'tasks':self.make_rows(3)},
                                 allowed_handlers={'owner_component'})
        out=pool.admit_native_tick(n,tasks=tasks,status={},mode='NORMAL',memory_ratio=.5)
        self.assertEqual(out['state'],'HOLD_OWNER_GATE_READBACK')
        self.assertEqual(out['jobs_started'],1)
        self.assertEqual(n.native_queue_claim.call_count,1)

    def test_ambiguous_s03_exception_retains_claim_id(self):
        n=self._native_claim_mock()
        n.s03_readback.side_effect=RuntimeError('native S03 unavailable')
        tasks=pool.validate_page({'schema':pool.SCHEMA,'tasks':self.make_rows(3)},
                                 allowed_handlers={'owner_component'})
        out=pool.admit_native_tick(n,tasks=tasks,status={},mode='NORMAL',memory_ratio=.5)
        self.assertEqual(out['state'],'HOLD_S03_NATIVE_READBACK')
        self.assertEqual(out['possible_unverified_claim'],'job.00000')
        self.assertEqual(out['jobs_started'],0)
        self.assertEqual(n.native_queue_claim.call_count,1)

    def test_native_claim_exception_preserves_ambiguous_task_for_readback(self):
        n=self._native_claim_mock()
        n.native_queue_claim.side_effect=TimeoutError('ACK lost after possible enqueue')
        tasks=pool.validate_page({'schema':pool.SCHEMA,'tasks':self.make_rows(3)},
                                 allowed_handlers={'owner_component'})
        result=pool.admit_native_tick(n,tasks=tasks,status={},mode='NORMAL',memory_ratio=.5)
        self.assertEqual(result['state'],'UNKNOWN_NATIVE_CLAIM')
        self.assertEqual(result['possible_unverified_claim'],'job.00000')
        self.assertEqual(result['jobs_started'],0)
        self.assertEqual(result['receipts'],[])
        n.native_queue_claim.assert_called_once()
        n.s03_readback.assert_not_called()

    def test_duplicate_lookup_exception_must_not_claim_any_task(self):
        n=self._native_claim_mock()
        n.native_duplicate_check.side_effect=OSError('native duplicate lookup timeout')
        tasks=pool.validate_page({'schema':pool.SCHEMA,'tasks':self.make_rows(1)},
                                 allowed_handlers={'owner_component'})
        result=pool.admit_native_tick(n,tasks=tasks,status={},mode='NORMAL',memory_ratio=.5)
        self.assertEqual(result['state'],'HOLD_NATIVE_DUPLICATE_READBACK')
        self.assertEqual(result['possible_unverified_claim'],'job.00000')
        self.assertEqual(result['jobs_started'],0)
        n.native_queue_claim.assert_not_called()

    def test_ambiguous_later_claim_preserves_prior_verified_s03_receipt(self):
        n=self._native_claim_mock()
        def claim(task, owner_pids):
            if task['id']=='job.00001':
                raise ConnectionError('ACK lost')
            return {'job_id':'native-'+task['id']}
        n.native_queue_claim.side_effect=claim
        tasks=pool.validate_page({'schema':pool.SCHEMA,'tasks':self.make_rows(3)},
                                 allowed_handlers={'owner_component'})
        result=pool.admit_native_tick(n,tasks=tasks,status={},mode='NORMAL',memory_ratio=.5)
        self.assertEqual(result['state'],'UNKNOWN_NATIVE_CLAIM')
        self.assertEqual(result['possible_unverified_claim'],'job.00001')
        self.assertEqual(result['jobs_started'],1)
        self.assertEqual(result['receipts'][0]['task_id'],'job.00000')
        self.assertEqual(n.native_queue_claim.call_count,2)

    def test_duplicate_native_job_id_fails_closed(self):
        n=self._native_claim_mock()
        n.native_queue_claim.side_effect=lambda task,owner_pids:{'job_id':'SAME-JOB'}
        tasks=pool.validate_page({'schema':pool.SCHEMA,'tasks':self.make_rows(3)},
                                 allowed_handlers={'owner_component'})
        out=pool.admit_native_tick(n,tasks=tasks,status={},mode='NORMAL',memory_ratio=.5)
        self.assertEqual(out['state'],'HOLD_NATIVE_JOB_ID_COLLISION')
        self.assertEqual(out['jobs_started'],1)
        self.assertEqual(out['possible_unverified_claim'],'job.00001')
        self.assertEqual(n.native_queue_claim.call_count,2)

    def test_owner_scope_revoked_during_duplicate_lookup(self):
        n=self._native_claim_mock()
        n.owner_allowed.side_effect=[True,True,False]
        tasks=pool.validate_page({'schema':pool.SCHEMA,'tasks':self.make_rows(1)},
                                 allowed_handlers={'owner_component'})
        out=pool.admit_native_tick(n,tasks=tasks,status={},mode='NORMAL',memory_ratio=.5)
        self.assertEqual(out['state'],'HOLD_STOP_OR_LEASE_CHANGED')
        n.native_queue_claim.assert_not_called()

    def test_reused_pid_with_different_starttime_not_extra_worker(self):
        rows=[{'pid':777,'process_starttime':100+i,'native_pid_verified':True,
               'state':'RUNNING','instance_id':60509551,'origin':'existing_onehost',
            'native_heartbeat_verified':True,'heartbeat_age_seconds':1}
              for i in range(3)]
        with self.assertRaisesRegex(pool.AutoHold,'DUPLICATE_NATIVE_PROCESS'):
            pool.verify_distinct_native_processes(rows,requested=3)

    def test_claim_is_not_execution(self):
        n=self._native_claim_mock()
        n.s03_readback.side_effect=lambda tid,jid:{
            'native_verified':True,'task_id':tid,'job_id':jid,
            'receipt_sha256':'b'*64,'task_note':'ADMITTED_NOT_EXECUTED'}
        tasks=pool.validate_page({'schema':pool.SCHEMA,'tasks':self.make_rows(1)},
                                 allowed_handlers={'owner_component'})
        out=pool.admit_native_tick(n,tasks=tasks,status={},mode='NORMAL',memory_ratio=.5)
        self.assertEqual(out['jobs_started'],1)
        self.assertEqual(out['jobs_completed_verified'],0)
        self.assertEqual(out['receipts'][0]['execution_evidence'],'ADMITTED_NOT_EXECUTED')

    def test_execution_requires_verified_terminal_result(self):
        self.assertEqual(pool.classify_native_job_proof({}),'EXECUTION_UNVERIFIED')
        self.assertEqual(pool.classify_native_job_proof({'terminal_state':'COMPLETED',
            'result_sha256':'c'*64}),'EXECUTION_UNVERIFIED')
        self.assertEqual(pool.classify_native_job_proof({'terminal_state':'COMPLETED',
            'execution_verified':True,'result_sha256':'BAD'}),'EXECUTION_UNVERIFIED')
        self.assertEqual(pool.classify_native_job_proof({'terminal_state':'COMPLETED',
            'execution_verified':True,'result_sha256':'c'*64}),'DONE_NATIVE')
        self.assertEqual(pool.classify_native_job_proof({'terminal_state':'COMPLETED',
            'execution_verified':True,'result_sha256':'c'*64,
            'task_note':'ADMITTED_NOT_EXECUTED'}),'ADMITTED_NOT_EXECUTED')

    def test_native_process_requires_recent_independent_heartbeat(self):
        valid=[{'pid':701+i,'process_starttime':2000+i,'native_pid_verified':True,
                'native_heartbeat_verified':True,'heartbeat_age_seconds':1,
                'state':'RUNNING','instance_id':60509551,'origin':'existing_onehost'}
               for i in range(3)]
        self.assertEqual(len(pool.verify_distinct_native_processes(valid,requested=3)),3)
        for delta in ({'native_heartbeat_verified':False},
                      {'native_heartbeat_verified':None},
                      {'heartbeat_age_seconds':601},
                      {'heartbeat_age_seconds':-1},
                      {'heartbeat_age_seconds':float('nan')},
                      {'heartbeat_age_seconds':True}):
            rows=[dict(x) for x in valid]
            rows[1].update(delta)
            with self.subTest(delta=str(delta)), self.assertRaisesRegex(pool.AutoHold,'UNVERIFIED_OS_PROCESS_COUNT'):
                pool.verify_distinct_native_processes(rows,requested=3)
        rows=[dict(x) for x in valid]
        del rows[1]['heartbeat_age_seconds']
        with self.assertRaisesRegex(pool.AutoHold,'UNVERIFIED_OS_PROCESS_COUNT'):
            pool.verify_distinct_native_processes(rows,requested=3)

    def test_stop_revoked_while_ensuring_idle_processes(self):
        n=self._native_claim_mock()
        n.stop_active.side_effect=[False,True]
        out=pool.admit_native_tick(n,tasks=[],status={},mode='NORMAL',memory_ratio=.5)
        self.assertEqual(out['state'],'HOLD_STOP_OR_LEASE_CHANGED')
        self.assertEqual(out['jobs_started'],0)
        n.native_queue_claim.assert_not_called()

    def test_writer_lease_revoked_before_idle_readback_acceptance(self):
        n=self._native_claim_mock()
        n.writer_lease.side_effect=[True,False]
        out=pool.admit_native_tick(n,tasks=[],status={},mode='NORMAL',memory_ratio=.5)
        self.assertEqual(out['state'],'HOLD_STOP_OR_LEASE_CHANGED')
        n.native_queue_claim.assert_not_called()


    def test_unknown_none_status_is_present_and_never_requeued(self):
        tasks=pool.validate_page({'schema':pool.SCHEMA,'tasks':self.make_rows(1)},
                                 allowed_handlers={'owner_component'})
        task_id=tasks[0]['id']
        self.assertEqual(len(pool.choose_ready(tasks,status={},mode='NORMAL',
                                              memory_ratio=.5)),1)
        self.assertEqual(pool.choose_ready(tasks,status={task_id:None},mode='NORMAL',
                                            memory_ratio=.5),[])

    def test_null_status_does_not_issue_second_native_claim(self):
        n=self._native_claim_mock()
        tasks=pool.validate_page({'schema':pool.SCHEMA,'tasks':self.make_rows(1)},
                                 allowed_handlers={'owner_component'})
        result=pool.admit_native_tick(n,tasks=tasks,status={tasks[0]['id']:None},
                                      mode='NORMAL',memory_ratio=.5)
        self.assertEqual(result['state'],'NATIVE_POOL_READY_IDLE')
        self.assertEqual(result['jobs_started'],0)
        n.native_queue_claim.assert_not_called()
        n.native_duplicate_check.assert_not_called()


    def test_claimed_queued_and_unknown_reserve_all_normal_native_slots(self):
        tasks=pool.validate_page({'schema':pool.SCHEMA,'tasks':self.make_rows(4)},
                                 allowed_handlers={'owner_component'})
        status={'old-1':'CLAIMED','old-2':'queued','old-3':None}
        # Existing leases remain capacity claims even when not yet RUNNING.
        self.assertEqual(pool.choose_ready(tasks,status=status,mode='NORMAL',
                                           memory_ratio=.5),[])
        n=self._native_claim_mock()
        out=pool.admit_native_tick(n,tasks=tasks,status=status,
                                   mode='NORMAL',memory_ratio=.5)
        self.assertEqual(out['jobs_started'],0)
        n.native_queue_claim.assert_not_called()

    def test_explicit_terminal_states_release_slots_but_unknown_do_not(self):
        tasks=pool.validate_page({'schema':pool.SCHEMA,'tasks':self.make_rows(4)},
                                 allowed_handlers={'owner_component'})
        status={'old-complete':'completed','old-failed':'FAILED','old-cancel':'CANCELED',
                'old-unverified':{'state':'done'}}
        ready=pool.choose_ready(tasks,status=status,mode='NORMAL',memory_ratio=.5)
        self.assertEqual(len(ready),1)
        # The string "running" is not the only inflight status.
        status={'old-running':'RUNNING','old-admitted':'ADMITTED_NOT_EXECUTED'}
        ready=pool.choose_ready(tasks,status=status,mode='NORMAL',memory_ratio=.5)
        self.assertEqual(len(ready),0)

    def test_native_queue_capacity_does_not_overclaim_with_admitted_jobs(self):
        tasks=pool.validate_page({'schema':pool.SCHEMA,'tasks':self.make_rows(6)},
                                 allowed_handlers={'owner_component'})
        n=self._native_claim_mock()
        status={'prior-1':'ADMITTED_NOT_EXECUTED','prior-2':'running'}
        out=pool.admit_native_tick(n,tasks=tasks,status=status,
                                   mode='NORMAL',memory_ratio=.5)
        self.assertEqual(out['state'],'NATIVE_POOL_READY_IDLE')
        self.assertEqual(out['jobs_started'],0)
        self.assertEqual(n.native_queue_claim.call_count,0)
        self.assertEqual(len(out['receipts']),0)

if __name__=='__main__':unittest.main()
