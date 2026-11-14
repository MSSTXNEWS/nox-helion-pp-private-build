import unittest
from training.recovery_plan import build_plan

SHA='a'*64

def healthy():
 return dict(instance_id='60509551',gpus=[dict(index=i,name='Tesla V100-SXM2-32GB',vram_free_mib=12000,compute_util_pct=50) for i in (0,1)],
             driver_cuda_toolkit_major=12,sm=70,bf16=False,free_disk_bytes=40_000_000_000,ram_available_mib=18000,
             external_checkpoint_restore_verified=True,checkpoint_sha256=SHA,s03_offsite_restore_verified=True,
             student_weights_active_sha256=SHA,training_error_diagnosed=True,no_live_optimizer_process=True,native_stop_active=False)
class RestartTests(unittest.TestCase):
 def test_ready_proposal_does_not_execute(self):
  s=build_plan(healthy());self.assertEqual(s['state'],'READY_FOR_EXISTING_NATIVE_APPROVAL');self.assertFalse(s['performed']);self.assertEqual(s['target_compute_util_pct'],85)
 def test_disk_full_holds(self):
  x=healthy();x['free_disk_bytes']=16_000_000_000
  self.assertIn('DISK_LT_20GB',build_plan(x)['reasons'])
 def test_must_have_backup(self):
  x=healthy();x['external_checkpoint_restore_verified']=False
  self.assertEqual(build_plan(x)['state'],'HOLD')
 def test_no_blind_restarts(self):
  x=healthy();x['no_live_optimizer_process']=False
  self.assertIn('MAY_INTERRUPT_ACTIVE_OPTIMIZER',build_plan(x)['reasons'])
 def test_volta_no_cuda13(self):
  x=healthy();x['driver_cuda_toolkit_major']=13
  self.assertEqual(build_plan(x)['state'],'HOLD')
 def test_distinct_gpu_vram(self):
  x=healthy();x['gpus'][1]['vram_free_mib']=1000
  self.assertIn('GPU_1_LOW_VRAM_HEADROOM',build_plan(x)['reasons'])
 def test_no_stop_approval(self):
  x=healthy();x['native_stop_active']=True
  self.assertIn('STOP_OR_STOP_SENSOR_NOT_VERIFIED',build_plan(x)['reasons'])
 def test_missing_s03_backup(self):
  x=healthy();x['s03_offsite_restore_verified']=False
  self.assertIn('S03_OFFSITE_RESTORE_NOT_VERIFIED',build_plan(x)['reasons'])
