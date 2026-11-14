"""NOX V94: 60-task existing OneHost optimized for answer quality and AI speed."""
import json
from pathlib import Path
import unittest
from nox_runpod.teacher_mesh.v47.control.dispatcher import (
    load_matrix,plan,_priority
)
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
    def test_no_pending_fake_consciousness_or_gpu_trainer(self):
        self.assertEqual(self.master['registered_count'],0)
        self.assertTrue(self.m['dispatch_policy']['one_student_only'])
        self.assertEqual(self.m['dispatch_policy']['chat_priority'],'P0')
        self.assertEqual(self.m['dispatch_policy']['max_gpu1_training_jobs'],1)
        self.assertEqual(self.master['training_compute_target_pct'],85)
        self.assertEqual(self.master['cpu_worker_fraction_max'],0.85)
if __name__=='__main__':unittest.main()
