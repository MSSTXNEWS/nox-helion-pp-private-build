import unittest
from training.proof_metrics import assess,SCHEMA

SHA='a'*64
B='b'*64
C='c'*64
D='d'*64

def k(p=20,t=25):return dict(native_verified=True,receipt_sha256=SHA,source_uri='s03://qa/knowledge',total_tests=t,passed_tests=p,suite_sha256=B,independent_evaluator=True,source_disjoint=True,s03_recall_verified=True)
def s(p=12,t=20):return dict(native_verified=True,receipt_sha256=B,source_uri='s03://qa/skills',total_tests=t,passed_tests=p,suite_sha256=SHA,independent_evaluator=True,source_disjoint=True,regression_suite_passed=True)
def w(p=40,t=100):return dict(native_verified=True,receipt_sha256=C,source_uri='nox-checkpoint://qa/model',checkpointed_optimizer_steps=p,target_optimizer_steps=t,baseline_model_sha256=SHA,student_weights_sha256=B,checkpoint_sha256=C,optimizer_receipt_sha256=D,real_optimizer_verified=True,checkpoint_reload_verified=True,independent_holdout_passed=True)
def data(knowledge=None,skills=None,weights=None):return {'schema':SCHEMA,'axes':{'knowledge':knowledge if knowledge is not None else k(),'skills':skills if skills is not None else s(),'weights':weights if weights is not None else w()}}

class EvidenceTests(unittest.TestCase):
 def test_unknown_not_false_zero(self):
  a=assess({'schema':SCHEMA,'axes':{}})
  self.assertIsNone(a['overall']['percent']);self.assertIsNone(a['axes']['weights']['percent'])
 def test_verified_30_35_35(self):
  a=assess(data());self.assertEqual(a['axes']['knowledge']['percent'],80);self.assertEqual(a['axes']['skills']['percent'],60);self.assertEqual(a['axes']['weights']['percent'],40);self.assertEqual(a['overall']['percent'],59.0)
 def test_gpu_utilization_not_weights(self):
  v=data();v['axes']['weights']={'gpu_utilization':100,'total_tests':100,'passed_tests':100}
  self.assertIsNone(assess(v)['axes']['weights']['percent'])
 def test_no_full_pass_without_holdout(self):
  d=data(k(25,25),s(20,20),w(100,100));d['axes']['weights']['independent_holdout_passed']=False
  self.assertEqual(assess(d)['overall']['state'],'HOLD_RELEASE_GATE')
 def test_full_acceptance_requires_e2e_stop_restore(self):
  d=data(k(25,25),s(20,20),w(100,100));d.update(native_onehost_stop_test_passed=True,s03_restart_restore_test_passed=True,production_e2e_passed=True)
  self.assertTrue(assess(d)['overall_release_accepted'])
 def test_bad_sha_rejected(self):
  d=data();d['axes']['knowledge']['receipt_sha256']='BAD'
  self.assertEqual(assess(d)['axes']['knowledge']['state'],'HOLD')
 def test_same_base_and_student_rejected(self):
  d=data();d['axes']['weights']['student_weights_sha256']=SHA
  self.assertIsNone(assess(d)['axes']['weights']['percent'])
 def test_overshoot_step_rejected(self):
  self.assertIsNone(assess(data(weights=w(101,100)))['axes']['weights']['percent'])
 def test_benchmark_not_independent(self):
  d=data();d['axes']['skills']['independent_evaluator']=False
  self.assertIsNone(assess(d)['axes']['skills']['percent'])
 def test_skill_regression(self):
  d=data();d['axes']['skills']['regression_suite_passed']=False
  self.assertIsNone(assess(d)['axes']['skills']['percent'])
 def test_knowledge_missing_s03(self):
  d=data();d['axes']['knowledge']['s03_recall_verified']=False
  self.assertIsNone(assess(d)['axes']['knowledge']['percent'])
