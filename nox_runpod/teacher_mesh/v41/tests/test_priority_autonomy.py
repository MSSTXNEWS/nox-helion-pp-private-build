import unittest,hashlib
from training.priority_autonomy import plan_priorities,submit_verified_plan,SchedulerPorts
from training.no_loss_acceptance import accept_checkpoint
from training.native_receipt_export import verified_dashboard

S='a'*64
R='b'*64

def row(i, progress, verified=True, lane='CORE'):
 return {'task_id':f'nox.task{i:04d}','lane':lane,'state':'IN_PROGRESS',
         'progress_percent':progress,'native_verified':verified,
         'source_sha256':S,'receipt_sha256':R,'owner_scope_confirmed':True}

class TestQueue(unittest.TestCase):
 def test_strict_above_50(self):
  d=plan_priorities([row(1,20),row(2,70),row(3,55),row(4,98)],existing_job_ids=[])
  self.assertEqual([q['progress_percent'] for q in d['planned']],[98,70,55])
  self.assertEqual(d['jobs_enqueued'],0)
 def test_fallback_when_no_above_50(self):
  d=plan_priorities([row(1,40),row(2,25)],existing_job_ids=[])
  self.assertEqual([q['progress_percent'] for q in d['planned']],[40,25])
 def test_no_faked_progress(self):
  bad=row(1,88,False)
  self.assertEqual(plan_priorities([bad],existing_job_ids=[])['planned'],[])
 def test_no_textual_progress(self):
  bad=row(1,'завершено 90%')
  self.assertEqual(plan_priorities([bad],existing_job_ids=[])['planned'],[])
 def test_duplicate_ignored(self):
  d=plan_priorities([row(1,70),row(1,70),row(2,60)],existing_job_ids=['nox.task0002'])
  self.assertEqual(len(d['planned']),1)
 def test_no_callbacks_is_hold(self):
  p=plan_priorities([row(1,90)],existing_job_ids=[])
  from types import SimpleNamespace
  self.assertEqual(submit_verified_plan(p,SimpleNamespace(),owner_scope='nox.owner')['state'],'HOLD_NATIVE_CALLBACKS')
 def test_native_queue_real_receipt(self):
  p=plan_priorities([row(1,85)],existing_job_ids=[])
  h=SchedulerPorts(authorize=lambda s:True,stop=lambda:False,
         queue_enqueue=lambda q:{'accepted':True,'job_id':'nox.job1'},
         queue_readback=lambda t:{'job_id':t,'state':'pending'},
         s03_audit=lambda e:True,native_duplicate_check=lambda n:False)
  result=submit_verified_plan(p,h,owner_scope='nox.owner')
  self.assertEqual(result['jobs_enqueued'],1)
  self.assertEqual(result['receipts'][0]['job_id'],'nox.job1')
 def test_native_stop_hold(self):
  p=plan_priorities([row(1,85)],existing_job_ids=[])
  h=SchedulerPorts(authorize=lambda s:True,stop=lambda:True,
         queue_enqueue=lambda q:{'accepted':True,'job_id':'nox.job1'},
         queue_readback=lambda t:{'job_id':t,'state':'pending'},
         s03_audit=lambda e:True,native_duplicate_check=lambda n:False)
  self.assertEqual(submit_verified_plan(p,h,owner_scope='nox.owner')['jobs_enqueued'],0)

class TestCheckpoint(unittest.TestCase):
 def test_no_real_checkpoint_hold(self):
  self.assertIn('NO_CHECKPOINT_RESTORE_PROOF',accept_checkpoint({})['reasons'])
 def test_owner_claim_5min_not_evidence(self):
  result=accept_checkpoint({'checkpoint_age_seconds':300})
  self.assertEqual(result['state'],'HOLD')
 def test_proper_native_gate(self):
  state={k:S for k in ('active_model_sha256','checkpoint_sha256','s03_snapshot_sha256','external_backup_manifest_sha256')}
  state.update(external_checkpoint_restore_tested=True,s03_external_restore_tested=True,
               reloaded_weights_match_checkpoint=True,optimizer_state_present=True,
               checkpoint_age_seconds=299,native_stop_active=False)
  self.assertEqual(accept_checkpoint(state)['state'],'READY_FOR_NATIVE_OWNER_APPROVAL')

class TestDashboard(unittest.TestCase):
 def test_cannot_bypass_native_verifier(self):
  d=verified_dashboard(lambda:{'schema':'nox-learning-3axes-evidence-v1','axes':{}},lambda r:False)
  self.assertEqual(d['state'],'HOLD_UNTRUSTED_NATIVE_EVIDENCE')
 def test_approved_empty_evidence_shows_hold(self):
  d=verified_dashboard(lambda:{'schema':'nox-learning-3axes-evidence-v1','axes':{}},lambda r:True)
  self.assertEqual(d['state'],'NATIVE_SOURCE_VERIFIED')
  self.assertIsNone(d['dashboard']['overall']['percent'])
if __name__=='__main__':unittest.main()

class TestNativePublish(unittest.TestCase):
 def test_denied_does_not_overwrite(self):
  import tempfile,pathlib
  from training.dashboard_publish import publish_from_native
  with tempfile.TemporaryDirectory() as d:
   dest=pathlib.Path(d)/'nox-learning-3axes-dashboard.json'
   dest.write_text('original')
   x=publish_from_native(lambda:{},lambda d:True,lambda:False,lambda:False,existing_web_root=d)
   self.assertFalse(x['written']);self.assertEqual(dest.read_text(),'original')
 def test_native_verified_unknown_is_not_fake_percent(self):
  import tempfile,pathlib,json
  from training.dashboard_publish import publish_from_native
  with tempfile.TemporaryDirectory() as d:
   dest=pathlib.Path(d)/'nox-learning-3axes-dashboard.json'
   dest.write_text('{}')
   x=publish_from_native(lambda:{'schema':'nox-learning-3axes-evidence-v1','axes':{}},
       lambda d:True,lambda:True,lambda:False,existing_web_root=d)
   self.assertTrue(x['written']);self.assertEqual(json.loads(dest.read_text())['overall']['percent'],None)
