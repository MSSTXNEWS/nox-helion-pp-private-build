"""NOX V93: source-only acceptance for the ONE existing 60-job OneHost.

Functional self-model is evidence-backed; no artificial consciousness claim.
No fake job IDs or native completion data are written to the repository.
"""
import json
from pathlib import Path
import unittest

from nox_runpod.teacher_mesh.v47.control.dispatcher import (
    load_matrix,plan,_priority,enqueue_approved,NativePorts,
)

ROOT=Path(__file__).resolve().parents[4]
MATRIX=ROOT/"nox_runpod/teacher_mesh/v47/control/TASKS_60_V46.json"
MASTER=ROOT/"coordination/NOX_R60_MASTER.json"


def native_status(**changes):
    state={'native_verified':True,'s03_native_verified':True,
        'stop_active':False,'student_serving':True,
        'chat_state':'idle','chat_recent':False,
        'completed':{},'existing_tasks':[],'progress':{},
        'native_writes_available':False,
        'gpu1_peak_verified':False,'gpu1_owner_lease':False,
        'gpu1_teacher_active':True,'gpu1_trainer_active':False,
        'resources':{'available_cpu_slots':8,'available_gpu1_slots':1,
                     'disk_free_bytes':17_400_000_000,
                     'checkpoint_disk_reserve_bytes':10_000_000_000}}
    state.update(changes)
    return state

class Priority93(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m=load_matrix(MATRIX)
        cls.r=json.loads(MASTER.read_text(encoding='utf8'))
        cls.t={t['number']:t for t in cls.m['tasks']}

    def test_60_unique_tasks_no_cycle_in_single_matrix(self):
        self.assertEqual(len(self.t),60)
        self.assertEqual(len(self.r['tasks']),60)
        self.assertEqual(self.m['dispatch_policy']['strategic_policy_version'],
                         'NOX_V93_FUNCTIONAL_SELF_MODEL_SKILLS_FIRST')
        self.assertTrue(self.m['dispatch_policy']['s03_single_native'])
        self.assertEqual(self.r['registered_count'],0)
        self.assertEqual(sum(bool(t['native_queue_id']) for t in self.r['tasks']),0)

    def test_integrity_and_memory_outweigh_full_weight_teacher(self):
        self.assertLess(_priority(self.t[51],{}),_priority(self.t[27],{}))
        self.assertLess(_priority(self.t[11],{}),_priority(self.t[30],{}))
        self.assertLess(_priority(self.t[16],{}),_priority(self.t[30],{}))
        self.assertLess(_priority(self.t[17],{}),_priority(self.t[29],{}))

    def test_self_fixing_and_skill_memory_before_any_heavy_gpu(self):
        for n in (31,35,36,37,38,39,40,57,58,59):
            self.assertLess(_priority(self.t[n],{}),_priority(self.t[27],{}))
            self.assertLess(_priority(self.t[n],{}),_priority(self.t[46],{}))

    def test_95_percent_visual_cannot_preempt_live_memory_foundation(self):
        progress={self.t[50]['task_id']:
                    {'native_verified':True,'receipt_sha256':'b'*64,'percent':95}}
        self.assertLess(_priority(self.t[11],progress),
                        _priority(self.t[50],progress))

    def test_security_no_longer_depends_on_emotional_styling(self):
        self.assertEqual(self.t[19]['depends_on'],
                         ['NOX-V46-11','NOX-V46-53'])

    def test_functional_self_model_requires_s03_acl_and_genesis(self):
        self.assertEqual(set(self.t[17]['depends_on']),
            {'NOX-V46-13','NOX-V46-16','NOX-V46-19'})

    def test_autofix_no_wait_for_gpu_student_to_validate_code(self):
        self.assertEqual(set(self.t[57]['depends_on']),
            {'NOX-V46-38','NOX-V46-56'})
        self.assertNotIn('NOX-V46-30',self.t[60]['depends_on'])
        self.assertIn('NOX-V46-39',self.t[60]['depends_on'])

    def test_master_matches_runtime_source_priority_and_edges(self):
        names={t['task_id']:t for t in self.r['tasks']}
        for t in self.m['tasks']:
            row=names['R60-'+t['task_id'][-2:].rjust(3,'0')]
            self.assertEqual(t['strategic_wave'],row['strategic_wave'])
            self.assertEqual(t['strategic_order'],row['strategic_order'])
            self.assertEqual(t['priority'],row['priority'])
            self.assertEqual(
                {'R60-'+x[-2:].rjust(3,'0') for x in t['depends_on']},
                set(row['depends_on']))
        self.assertTrue(self.r['onehost_only'])
        self.assertFalse(self.r['live_queue_verified'])

    def test_17gb_allows_safe_cpu_planning_not_forge_or_download(self):
        d=plan(self.m,native_status(),max_new=8)
        self.assertEqual(d['state'],'SOURCE_PLAN_ONLY')
        self.assertGreater(len(d['planned']),0)
        self.assertEqual(d['jobs_enqueued'],0)
        for t in d['planned']:
            self.assertEqual(t['priority'],'P1')
            self.assertEqual(t['chat_priority'],'P0')
            self.assertEqual(t['strategic_wave'],0)
            self.assertNotIn(t['task_id'],{'NOX-V46-27','NOX-V46-28','NOX-V46-29'})
        self.assertTrue(any('GPU1_PEAK_PROFILE_UNVERIFIED' in x['reasons']
                    for x in d['sample_blocked']) or d['blocked_count']>0)

    def test_below_10gb_does_not_block_safe_readonly_cpu_work(self):
        d=plan(self.m,native_status(resources={'available_cpu_slots':4,
            'available_gpu1_slots':0,'disk_free_bytes':7_000_000_000,
            'checkpoint_disk_reserve_bytes':10_000_000_000}),max_new=4)
        self.assertEqual(d['state'],'SOURCE_PLAN_ONLY')
        self.assertGreater(len(d['planned']),0)
        self.assertTrue(all(x['priority']=='P1' for x in d['planned']))

    def test_active_chat_and_unleased_gpu_cannot_enqueue_teacher(self):
        d=plan(self.m,native_status(chat_state='generating',
              gpu1_peak_verified=True,gpu1_owner_lease=True,
              gpu1_teacher_active=False,gpu1_trainer_active=False))
        self.assertEqual(d['state'],'SOURCE_PLAN_ONLY')
        self.assertTrue(all(x['task_id']!='NOX-V46-27' for x in d['planned']))

    def test_simulated_native_ticket_never_becomes_real_completion(self):
        events=[]
        def enqueue(payload):
            self.assertEqual(payload['priority'],'P1')
            self.assertEqual(payload['chat_priority'],'P0')
            self.assertTrue(payload['must_recheck_chat_before_work'])
            return {'accepted':True,'job_id':'synthetic.v93.job1'}
        native=NativePorts(
            authorize=lambda s:True,stop=lambda:False,
            state=lambda:native_status(),
            native_task_status=lambda t:{},
            native_duplicate_check=lambda t:False,
            approve=lambda scope,h,obs:True,
            queue_enqueue=enqueue,
            queue_readback=lambda job_id:{'job_id':job_id,
                'task_id':'NOX-V46-51','state':'pending'},
            verify_queue_receipt=lambda ticket,payload:True,
            s03_audit=lambda event:events.append(event) or {'event_id':'synthetic'},
            s03_verify=lambda receipt,event:True,
        )
        out=enqueue_approved(native,self.m,'nox.owner',limit=1)
        self.assertEqual(out['state'],'NATIVE_QUEUE_READBACK_AND_S03_VERIFIED')
        self.assertEqual(len(events),1)
        self.assertFalse(out['training_completed'])
        self.assertFalse(out['weights_changed'])
        # Test-only synthetic port cannot mutate canonical master.
        self.assertEqual(self.r['registered_count'],0)

if __name__=="__main__":
    unittest.main()
