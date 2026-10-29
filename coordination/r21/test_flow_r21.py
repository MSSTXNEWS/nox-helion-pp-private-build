import unittest
from flow_r21 import queue_preview
H='a'*40;B='b'*40;D='d'*40;T='2026-10-29T20:00:00+03:00'
def saved():
    return {'schema':'NOX_V16_R20_FIXED_DISPATCH_SNAPSHOT_V1','head_at_snapshot':H,
            'register_blob':B,'tasks':[
              {'id':'ERR-SRC-003','owner':'T06','state':'OPEN','depends_on':[]},
              {'id':'ERR-SRC-005','owner':'T06','state':'PATCHED','depends_on':[],
               'source_error_status':'FIX_APPLIED_UNVERIFIED'},
              {'id':'T06','owner':'T06','state':'OPEN','depends_on':[]},
              {'id':'T08','owner':'T08','state':'OPEN','depends_on':['T06']},
              {'id':'T09','owner':'T09','state':'OPEN','depends_on':['T08']},
              {'id':'T10','owner':'T10','state':'OPEN','depends_on':['T09']},
              {'id':'T11-GITLAB-AUTH','owner':'T11','state':'OPEN','depends_on':[]},
              {'id':'T11','owner':'T11','state':'OPEN','depends_on':['T10','T11-GITLAB-AUTH']} ]}
class TestR21(unittest.TestCase):
 def call(self,s=None,h=H,b=B,t=T):return queue_preview(s or saved(),h,b,t)
 def test_real_git_schema(self):self.assertEqual(self.call()['status'],'READ_ONLY_PLAN_NOT_AUTHORIZED')
 def test_stale_head(self):self.assertEqual(self.call(h=D)['ready'],[])
 def test_stale_register(self):self.assertTrue(self.call(b=D)['register_drift'])
 def test_bad_sha(self):
  with self.assertRaisesRegex(ValueError,'OBSERVED_HEAD_SHA_REQUIRED'):self.call(h='short')
 def test_missing_provenance(self):
  s=saved();del s['register_blob']
  with self.assertRaisesRegex(ValueError,'SNAPSHOT_PROVENANCE_MISSING'):self.call(s)
 def test_unverified_not_verified(self):
  s=saved();s['tasks'][1]['state']='VERIFIED'
  with self.assertRaisesRegex(ValueError,'UNVERIFIED_ERROR_PROMOTED'):self.call(s)
 def test_self_deadlock(self):
  s=saved();s['tasks'][2]['depends_on']=['ERR-SRC-003']
  with self.assertRaisesRegex(ValueError,'T06_SELF_DEADLOCK_REINTRODUCED'):self.call(s)
 def test_t06_ready_qa_waiting(self):
  o=self.call();self.assertIn('T06',[x['id'] for x in o['ready']]);self.assertNotIn('T08',[x['id'] for x in o['ready']])
 def test_gitlab_auth_independent(self):self.assertIn('T11-GITLAB-AUTH',[x['id'] for x in self.call()['ready']])
 def test_no_remote_authorization(self):
  o=self.call();self.assertFalse(o['qa_accepted']);self.assertTrue(o['zero_mutations'])
 def test_duplicate_tasks(self):
  s=saved();s['tasks'].append(s['tasks'][0].copy())
  with self.assertRaisesRegex(ValueError,'DUPLICATE_OR_INVALID_TASK_ID'):self.call(s)
 def test_dependency_cycle(self):
  s=saved();s['tasks'][3]['depends_on']=['T09']
  with self.assertRaisesRegex(ValueError,'DEPENDENCY_CYCLE'):self.call(s)
 def test_lease_no_takeover(self):
  s=saved();s['tasks'][0]['lease']={'owner':'T06','expires_at':'2026-10-29T18:00:00Z'}
  self.assertEqual(next(x for x in self.call(s)['ready'] if x['id']=='ERR-SRC-003')['state'],'LEASE_REQUIRES_OWNER_CAS')
 def test_bad_timestamp(self):
  with self.assertRaisesRegex(ValueError,'INVALID_TIME'):self.call(t='tomorrow')
 def test_explicit_hold_not_ready(self):
  s=saved();s['tasks'][0]['state']='HOLD'
  self.assertNotIn('ERR-SRC-003',[x['id'] for x in self.call(s)['ready']])
 def test_original_core_schema(self):
  s=saved();s['schema']='NOX_V16_R20_DISPATCH_SNAPSHOT_V1';s['head_snapshot']=s.pop('head_at_snapshot');s['error_register_blob']=s.pop('register_blob')
  self.assertEqual(self.call(s)['status'],'READ_ONLY_PLAN_NOT_AUTHORIZED')
if __name__=='__main__':unittest.main()