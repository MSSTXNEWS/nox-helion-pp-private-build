"""NOX V94: 60-task existing OneHost optimized for answer quality and AI speed."""
import json
from pathlib import Path
import unittest
from nox_runpod.teacher_mesh.v47.control.dispatcher import (
    load_matrix,plan,_priority
)
from nox_runpod.teacher_mesh.v47.control.worm_supervisor import audit_native_queue,release_evidence

ROOT=Path(__file__).resolve().parents[4]
M=ROOT/'nox_runpod/teacher_mesh/v47/control/TASKS_60_V46.json'
R=ROOT/'coordination/NOX_R60_MASTER.json'
def state(**kw):
    x={'native_verified':True,'s03_native_verified':True,'stop_active':False,
       'student_serving':True,'chat_state':'idle','chat_recent':False,
       'completed':{},'existing_tasks':[],'progress':{},
       'native_writes_available':False,
       'gpu1_peak_verified':False,'gpu1_owner_lease':False,
       'gpu1_teacher_active':True,'gpu1_trainer_active':False,
       'resources':{'available_cpu_slots':8,'available_gpu1_slots':1,
                    'disk_free_bytes':17_440_000_000,
                    'checkpoint_disk_reserve_bytes':10_000_000_000}}
    x.update(kw)
    return x
class Priorities(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m=load_matrix(M)
        cls.master=json.loads(R.read_text())
        cls.n={t['number']:t for t in cls.m['tasks']}
    def test_all_60_single_onehost_no_fake_progress(self):
        self.assertEqual(len(self.n),60)
        self.assertEqual(len(self.master['tasks']),60)
        self.assertEqual(self.master['registered_count'],0)
        self.assertFalse(self.master['live_queue_verified'])
        self.assertTrue(self.master['onehost_only'])
        self.assertTrue(all(t['native_queue_id'] is None for t in self.master['tasks']))
        self.assertTrue(all(t['verified'] is False for t in self.master['tasks']))
        self.assertEqual(self.m['dispatch_policy']['training_priority_policy_version'],
                         'NOX_V99_DIRECT_BASE_TRAINING_85_FIRST')
        self.assertEqual(self.m['dispatch_policy']['gpu1_training_compute_target_pct'],85)
    def test_gpu_and_model_diagnosis_before_all_optional_wow(self):
        for n in (7,52,42,2,3,4,5,6,21,25):
            self.assertLess(_priority(self.n[n],{}),_priority(self.n[46],{}))
            self.assertLess(_priority(self.n[n],{}),_priority(self.n[49],{}))
    def test_acceleration_pretraining_then_real_weight_training_before_wow(self):
        for n in (7,42,21,25,26):
            self.assertLess(_priority(self.n[n],{}),_priority(self.n[27],{}))
            self.assertLess(_priority(self.n[n],{}),_priority(self.n[28],{}))
        # Owner's newest priority: full-weight training ahead of nonessential
        # self-repair/media, but mandatory P0 chat/STOP always wins.
        self.assertLess(_priority(self.n[27],{}),_priority(self.n[38],{}))
        self.assertLess(_priority(self.n[30],{}),_priority(self.n[49],{}))
    def test_verified_99percent_media_never_preempts_safety_or_accel(self):
        p={self.n[50]['task_id']:{
            'native_verified':True,'receipt_sha256':'f'*64,'percent':99}}
        self.assertLess(_priority(self.n[42],p),_priority(self.n[50],p))
        self.assertLess(_priority(self.n[51],p),_priority(self.n[50],p))
    def test_all_source_jobs_remain_p1_behind_real_p0_chat(self):
        out=plan(self.m,state(),max_new=8)
        self.assertEqual(out['state'],'SOURCE_PLAN_ONLY')
        self.assertGreater(len(out['planned']),0)
        for x in out['planned']:
            self.assertEqual(x['priority'],'P1')
            self.assertEqual(x['chat_priority'],'P0')
            self.assertIsInstance(x['performance_wave'],int)
            self.assertIsInstance(x['training_wave'],int)
            self.assertEqual(x['training_target_compute_pct'],85)
            self.assertTrue(x['requires_native_worker'])
            self.assertTrue(x['proposed_not_queued'])
        self.assertEqual(out['jobs_enqueued'],0)
    def test_no_gpu1_teacher_launch_without_lease(self):
        out=plan(self.m,state(),max_new=8)
        self.assertTrue(all(x['task_id'] not in {
            'NOX-V46-27','NOX-V46-28','NOX-V46-29','NOX-V46-30'}
            for x in out['planned']))
    def test_chat_generating_never_schedules_new_gpu1(self):
        x=state(chat_state='generating',chat_recent=True,
                gpu1_peak_verified=True,gpu1_owner_lease=True,
                gpu1_teacher_active=False,gpu1_trainer_active=False)
        result=plan(self.m,x,max_new=8)
        self.assertTrue(all(q['lane']!='TEACHERS' for q in result['planned']))
    def test_10gb_only_for_new_writes_cpu_still_valid(self):
        x=state(resources={'available_cpu_slots':4,'available_gpu1_slots':0,
                           'disk_free_bytes':8_000_000_000,
                           'checkpoint_disk_reserve_bytes':10_000_000_000})
        out=plan(self.m,x,max_new=4)
        self.assertEqual(out['state'],'SOURCE_PLAN_ONLY')
        self.assertTrue(len(out['planned'])>0)
        self.assertTrue(all(q['priority']=='P1' for q in out['planned']))
    def test_main_matrix_R60_exact_shared_priority(self):
        r={t['task_id']:t for t in self.master['tasks']}
        for t in self.m['tasks']:
            mapped=r['R60-'+str(t['number']).zfill(3)]
            self.assertEqual(mapped['performance_wave'],t['performance_wave'])
            self.assertEqual(mapped['performance_order'],t['performance_order'])
            self.assertEqual(mapped['training_wave'],t['training_wave'])
            self.assertEqual(mapped['training_order'],t['training_order'])
            self.assertEqual(mapped['priority'],t['priority'])
            self.assertEqual(set(mapped['depends_on']),
                         {'R60-'+x[-2:].rjust(3,'0') for x in t['depends_on']})
    def test_worm_register_zero_is_not_fake_sixty_processes(self):
        x=state(native_queue_verified=True,task_status={},now_unix=2000)
        result=audit_native_queue(self.m,x,now_unix=2000)
        self.assertEqual(result['tasks_expected'],60)
        self.assertEqual(result['native_registered_verified'],0)
        self.assertEqual(result['unregistered_count'],60)
        self.assertEqual(result['native_jobs_started'],0)

    def test_stale_gpu_heartbeat_never_triggers_kill_or_duplicate(self):
        row={'task_id':'NOX-V46-30','state':'RUNNING',
             'native_verified':True,'receipt_sha256':'a'*64,
             'heartbeat_unix':100}
        x=state(native_queue_verified=True,task_status={row['task_id']:row},now_unix=2000)
        audit=audit_native_queue(self.m,x,now_unix=2000)
        self.assertEqual(len(audit['stale_heartbeat_holds']),1)
        self.assertFalse(audit['stale_heartbeat_holds'][0]['restart_permitted'])
        self.assertNotIn('NOX-V46-30',{r['task_id'] for r in plan(self.m,x)['planned']})

    def test_failed_gpu_weights_requires_offsite_checkpoint_and_lease(self):
        row={'task_id':'NOX-V46-30','state':'FAILED','native_verified':True,
             'receipt_sha256':'a'*64,'attempt_count':1,
             'retry_after_unix':1000,'owner_lease_released':True,
             'terminal_verified':True,'checkpoint_restorable':False}
        x=state(native_queue_verified=True,task_status={row['task_id']:row},now_unix=2000)
        self.assertFalse(audit_native_queue(self.m,x,now_unix=2000)['retry_eligible_proposals'])
        row['checkpoint_restorable']=True
        audit=audit_native_queue(self.m,x,now_unix=2000)
        self.assertEqual(len(audit['retry_eligible_proposals']),1)
        self.assertTrue(audit['retry_eligible_proposals'][0]['owner_approval_required'])
        row['attempt_count']=3
        self.assertFalse(audit_native_queue(self.m,x,now_unix=2000)['retry_eligible_proposals'])

    def test_failed_gpu_retry_never_becomes_new_task_or_second_trainer(self):
        failed={'task_id':'NOX-V46-30','state':'FAILED','native_verified':True,
                'receipt_sha256':'a'*64,'attempt_count':1,
                'retry_after_unix':1000,'terminal_verified':True,
                'owner_lease_released':True,'checkpoint_restorable':True}
        inp=state(native_queue_verified=True,task_status={'NOX-V46-30':failed},
                  now_unix=2000,gpu1_peak_verified=True,gpu1_owner_lease=True,
                  gpu1_teacher_active=False,gpu1_trainer_active=False,
                  native_writes_available=True,
                  resources={'available_cpu_slots':8,'available_gpu1_slots':1,
                             'disk_free_bytes':40_000_000_000,
                             'checkpoint_disk_reserve_bytes':10_000_000_000})
        audit=audit_native_queue(self.m,inp,now_unix=2000)
        self.assertIn('NOX-V46-30',audit['protected_task_ids'])
        self.assertEqual(audit['retry_eligible_proposals'][0]['next_attempt'],2)
        self.assertFalse(audit['retry_eligible_proposals'][0]['may_enqueue_via_generic_plan'])
        planned=plan(self.m,inp,max_new=8)
        self.assertNotIn('NOX-V46-30',{r['task_id'] for r in planned['planned']})
        self.assertEqual(audit['native_jobs_restarted'],0)

    def test_failed_cpu_retry_also_not_fresh_task(self):
        failed={'task_id':'NOX-V46-01','state':'FAILED','native_verified':True,
                'receipt_sha256':'b'*64,'attempt_count':0,
                'retry_after_unix':0,'terminal_verified':True,
                'owner_lease_released':True}
        inp=state(native_queue_verified=True,task_status={failed['task_id']:failed},now_unix=2000)
        audit=audit_native_queue(self.m,inp,now_unix=2000)
        self.assertIn(failed['task_id'],audit['protected_task_ids'])
        self.assertNotIn(failed['task_id'],{r['task_id'] for r in plan(self.m,inp)['planned']})

    def test_unknown_lease_and_untrusted_complete_hold(self):
        row={'task_id':'NOX-V46-41','state':'COMPLETED','native_verified':True,
             'receipt_sha256':'bogus','independent_test_passed':True}
        x=state(native_queue_verified=True,task_status={row['task_id']:row},now_unix=2000)
        result=audit_native_queue(self.m,x,now_unix=2000)
        self.assertEqual(result['native_completed_verified'],0)
        self.assertIn(row['task_id'],result['protected_task_ids'])
        x['native_queue_verified']=False
        self.assertEqual(plan(self.m,x)['planned'],[])

    def test_three_hour_release_does_not_invent_quality_from_commit(self):
        r=release_evidence(old_source_sha='a'*64,new_source_sha='b'*64,
            native_web_e2e=False,quality_holdout_improved=False,backup_restorable=True)
        self.assertEqual(r['state'],'HOLD_NO_VERIFIED_IMPROVEMENT')
        self.assertFalse(r['subjective_consciousness_proven'])

    def test_no_pending_fake_consciousness_or_gpu_trainer(self):
        self.assertEqual(self.master['registered_count'],0)
        self.assertTrue(self.m['dispatch_policy']['one_student_only'])
        self.assertEqual(self.m['dispatch_policy']['chat_priority'],'P0')
        self.assertEqual(self.m['dispatch_policy']['max_gpu1_training_jobs'],1)
        self.assertEqual(self.master['training_compute_target_pct'],85)
        self.assertEqual(self.master['cpu_worker_fraction_max'],0.85)
if __name__=='__main__':unittest.main()
