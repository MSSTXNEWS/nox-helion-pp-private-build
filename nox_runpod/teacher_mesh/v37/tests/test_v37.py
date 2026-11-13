import unittest,json,sys,tempfile,os,hashlib,pathlib
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from nox_v37.live_inventory import parse_gpu,parse_apps
from nox_v37.admission import admission,tune_next_microbatch
from nox_v37.native_admin import dispatch,canonical_request
from nox_v37.self_builder import review
from nox_v37.self_model import build_self_report
from nox_v37.anti_dup import check_job
from nox_v37.continuous import propose,LogWriter

SAMPLE='0, GPU-abc, Tesla V100-SXM2-32GB, 32768, 11000, 6, 49\n1, GPU-def, Tesla V100-SXM2-32GB, 32768, 19000, 93, 59\n'
def host():return {'gpus':parse_gpu(SAMPLE),'ram':{'available_mib':40000},
 'disk':{'free_bytes':40_000_000_000},
 'runtime_abi':{'capabilities':[[7,0],[7,0]],'torch_cuda':'12.4','bf16':False}}
def request(action='server.status'):
 return dict(action=action,target_id='nox.gpu',tenant_id='nox',principal_id='owner',chat_id='resonance',request_id='run123')
class InventoryTests(unittest.TestCase):
 def test_2_gpus(self):self.assertEqual(parse_gpu(SAMPLE)[0]['vram_free_mib'],21768)
 def test_reject_one_card(self):
  with self.assertRaises(ValueError):parse_gpu(SAMPLE.splitlines()[0])
 def test_no_sensor(self):
  with self.assertRaises(ValueError):parse_gpu(SAMPLE.replace('93, 59','N/A, 59'))
 def test_processes(self):self.assertEqual(parse_apps('GPU-abc, 44, python, 1600 MiB\n')[0]['pid'],44)
 def test_bad_pid_is_not_process(self):self.assertFalse(parse_apps('GPU-abc, INVALID, python, 1600 MiB'))
class AdmissionTests(unittest.TestCase):
 def test_ok(self):self.assertEqual(admission(host(),gpu_idx=0,new_job_peak_mib=12000,checkpoint_bytes=2_000_000_000,external_checkpoint_verified=True)['state'],'READY_TO_REQUEST_NATIVE_APPROVAL')
 def test_vram_hold(self):self.assertEqual(admission(host(),gpu_idx=1,new_job_peak_mib=20000,checkpoint_bytes=2_000_000_000,external_checkpoint_verified=True)['state'],'HOLD')
 def test_no_backup(self):self.assertIn('NO_DURABLE_BACKUP_RECEIPT',admission(host(),gpu_idx=0,new_job_peak_mib=3000,checkpoint_bytes=0,external_checkpoint_verified=False)['reason'])
 def test_no_cuda_version(self):
  h=host();h['runtime_abi']['torch_cuda']='13.0'
  self.assertIn('CUDA_TORCH_SM70_NOT_PROVEN',admission(h,gpu_idx=0,new_job_peak_mib=1000,checkpoint_bytes=0,external_checkpoint_verified=True)['reason'])
 def test_temperature(self):
  h=host();h['gpus'][0]['temp_core_c']=89
  self.assertIn('TEMPERATURE_HOLD',admission(h,gpu_idx=0,new_job_peak_mib=1000,checkpoint_bytes=0,external_checkpoint_verified=True)['reason'])
 def test_disk(self):
  h=host();h['disk']['free_bytes']=13_000_000_000
  self.assertIn('DISK_CHECKPOINT_SPACE',admission(h,gpu_idx=0,new_job_peak_mib=1000,checkpoint_bytes=0,external_checkpoint_verified=True)['reason'])
 def test_no_fictitious_85_pct(self):
  self.assertFalse(admission(host(),gpu_idx=0,new_job_peak_mib=1000,checkpoint_bytes=0,external_checkpoint_verified=True)['launch'])
 def test_tune_after_checkpoint(self):
  t=tune_next_microbatch(microbatch=4,accumulation=2,target_effective=8,peak_vram_mib=28000,hard_cap_mib=29000,oom=True)
  self.assertEqual(t['microbatch_next'],2);self.assertEqual(t['gradient_accumulation_next'],4)
class AdminTests(unittest.TestCase):
 def test_unknown_command_refused(self):
  with self.assertRaises(ValueError):canonical_request(request('shell.run'))
 def test_freeform_command_refused(self):
  x=request();x['command']='rm -rf /';
  with self.assertRaises(ValueError):canonical_request(x)
 def test_denied_scope(self):
  ret=dispatch(request(),host_authorize=lambda _:False,host_stop=lambda:False,host_inspect=lambda _:{});
  self.assertEqual(ret['state'],'HOLD_STOP_OR_OWNER_SCOPE')
 def test_read_only(self):
  ret=dispatch(request(),host_authorize=lambda _:True,host_stop=lambda:False,host_inspect=lambda _:dict(ok=True));
  self.assertEqual(ret['state'],'READ_ONLY_OBSERVED');self.assertFalse(ret['performed'])
 def test_write_preview_no_execution(self):
  seen=[];ret=dispatch(request('host.reboot'),host_authorize=lambda _:True,host_stop=lambda:False,
    host_inspect=lambda _:dict(boot_id='x'),host_execute=lambda *args:seen.append(True));
  self.assertEqual(ret['state'],'OWNER_CONFIRMATION_REQUIRED');self.assertFalse(seen)
 def test_sha_wrong_no_execution(self):
  seen=[];ret=dispatch(request('training.pause'),approved_request_sha='wrong',host_authorize=lambda _:True,host_stop=lambda:False,
    host_inspect=lambda _:dict(ok=True),host_execute=lambda *args:seen.append(True));
  self.assertEqual(ret['state'],'OWNER_CONFIRMATION_REQUIRED');self.assertFalse(seen)
 def test_owner_denies(self):
  q=request('checkpoint.backup');h=canonical_request(q)[1]
  ret=dispatch(q,approved_request_sha=h,host_authorize=lambda _:True,host_stop=lambda:False,host_inspect=lambda _:dict(ok=True),
    host_approve=lambda *args:False,host_execute=lambda *args:1,host_receipt_verify=lambda *args:True,host_readback=lambda *args:True)
  self.assertEqual(ret['state'],'HOLD_SIGNED_APPROVAL_NOT_VALID')
 def test_authorised_execution(self):
  q=request('checkpoint.backup');h=canonical_request(q)[1];seen=[]
  ret=dispatch(q,approved_request_sha=h,host_authorize=lambda _:True,host_stop=lambda:False,
    host_inspect=lambda _:dict(sha='a'),host_approve=lambda *args:True,
    host_execute=lambda *args:seen.append('ran') or dict(sha='b'),host_receipt_verify=lambda *args:True,
    host_readback=lambda *args:dict(sha='b'))
  self.assertTrue(ret['performed']);self.assertEqual(seen,['ran']);self.assertFalse(ret['release_accepted'])
 def test_stop_gate(self):
  self.assertEqual(dispatch(request('teacher.start'),host_authorize=lambda _:True,host_stop=lambda:True,host_inspect=lambda _:dict(ok=True))['state'],'HOLD_STOP_OR_OWNER_SCOPE')
class SelfTests(unittest.TestCase):
 def test_birth_no_fabrication(self):
  r=build_self_report(receipts=[dict(native_verified=False,kind='verified_birth',occurred_at='2026',verified_sha256='a')],goal_register=[],current_training={})
  self.assertIsNone(r['birth_at'])
 def test_birth_requires_real_optimizer_reload(self):
  receipts=[dict(native_verified=True,kind='verified_birth',occurred_at='2026-11-10',verified_sha256='a',optimizer_step_verified=False,weights_reloaded=True)]
  self.assertIsNone(build_self_report(receipts=receipts,goal_register=[],current_training={})['birth_at'])
 def test_birth_valid(self):
  receipts=[dict(native_verified=True,kind='verified_birth',occurred_at='2026-11-10',verified_sha256='a',optimizer_step_verified=True,weights_reloaded=True)]
  self.assertEqual(build_self_report(receipts=receipts,goal_register=[],current_training={})['birth_at'],'2026-11-10')
 def test_selfbuilder_unreviewed(self):
  a=dict(expected_head='a'*40,changed_paths=['nox_runpod/teacher_mesh/x.py'],diff_sha256='b'*64,owner_review_required=False)
  self.assertEqual(review(a,current_head='a'*40,independent_test_receipt=dict(source_head='a'*40,all_pass=True))['state'],'HOLD')
 def test_selfbuilder_path_traversal(self):
  a=dict(expected_head='a'*40,changed_paths=['nox_runpod/teacher_mesh/../../sensitive'],diff_sha256='b'*64,owner_review_required=True)
  self.assertIn('UNSAFE_PATH',review(a,current_head='a'*40,independent_test_receipt=dict(source_head='a'*40,all_pass=True))['reasons'])
 def test_selfbuilder_reviewable_no_auto_merge(self):
  a=dict(expected_head='a'*40,changed_paths=['nox_runpod/teacher_mesh/new.py'],diff_sha256='b'*64,owner_review_required=True)
  v=review(a,current_head='a'*40,independent_test_receipt=dict(source_head='a'*40,all_pass=True))
  self.assertEqual(v['state'],'REVIEWABLE_PR_CANDIDATE_NOT_MERGED');self.assertFalse(v['auto_merged'])
class DedupTests(unittest.TestCase):
 def test_verify_sha(self):self.assertEqual(check_job({'sha256':'unverified'},{},[])['state'],'HOLD_SHA_REQUIRED')
 def test_skip_completed(self):
  mdl=dict(sha256='a'*64);j=dict(dataset_sha256='b'*64,kind='distillation',objective='quality');r=check_job(mdl,j,[])
  d=dict(job_fingerprint=r['fingerprint'],native_verified=True,status='COMPLETED_WITH_SHA_AND_EVAL',checkpoint_sha256='c'*64)
  self.assertEqual(check_job(mdl,j,[d])['state'],'SKIP_ALREADY_VERIFIED')
 def test_protect_running(self):
  mdl=dict(sha256='a'*64);j=dict(dataset_sha256='b'*64,kind='distillation',objective='quality');r=check_job(mdl,j,[])
  d=dict(job_fingerprint=r['fingerprint'],native_verified=True,status='RUNNING')
  self.assertEqual(check_job(mdl,j,[d])['state'],'PROTECT_RUNNING_NO_DUPLICATE')
class ContinuityTests(unittest.TestCase):
 def test_gpu0_idle_is_candidate(self):
  p=propose(host());self.assertEqual(p['per_gpu'][0]['state'],'CANDIDATE_FOR_NEXT_APPROVED_JOB')
  self.assertFalse(p['actual_gpu_job_launched'])
 def test_log_cap_no_deletion(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'telemetry.jsonl';p.write_text('a'*10)
   with self.assertRaises(RuntimeError):LogWriter(p,max_bytes=5).write(dict(state='X'))
   self.assertEqual(p.read_text(),'a'*10)
 def test_schedule_336(self):
  a=json.loads((ROOT/'manifests/CONTINUOUS_14_DAY_336_HOUR_SLOTS.json').read_text())['slots']
  self.assertEqual(len(a),336);self.assertEqual({x['day'] for x in a},set(range(1,15)))
  self.assertTrue(all(x['not_auto_executed'] for x in a))
 def test_no_download_existing(self):
  a=json.loads((ROOT/'manifests/FIRST_HOUR_NO_DUP_STATUS.json').read_text())['items']
  self.assertTrue(any(x['id']=='comfyui' and x['action']=='REUSE_IMAGE_GRAPH' for x in a))
if __name__=='__main__':unittest.main()

# Extra integration regression: file integrity gate for 35B sharded source.
class PartsTests(unittest.TestCase):
 def test_sha_valid(self):
  from nox_v37.verify_parts import verify
  with tempfile.TemporaryDirectory() as d:
   pathlib.Path(d,'p00').write_bytes(b'ABC')
   m={'schema':'NOX_V37_EXPECTED_PARTS_SHA256','parts':[{'relative_path':'p00','bytes':3,'sha256':hashlib.sha256(b'ABC').hexdigest()}]}
   self.assertEqual(verify(d,m)['state'],'ALL_PARTS_SHA_PASS')
 def test_mismatch_fail_closed(self):
  from nox_v37.verify_parts import verify
  with tempfile.TemporaryDirectory() as d:
   pathlib.Path(d,'p00').write_bytes(b'ABC')
   m={'schema':'NOX_V37_EXPECTED_PARTS_SHA256','parts':[{'relative_path':'p00','bytes':3,'sha256':'0'*64}]}
   self.assertEqual(verify(d,m)['state'],'HOLD')
 def test_path_traversal(self):
  from nox_v37.verify_parts import verify
  with tempfile.TemporaryDirectory() as d:
   m={'schema':'NOX_V37_EXPECTED_PARTS_SHA256','parts':[{'relative_path':'../secret','bytes':3,'sha256':'0'*64}]}
   with self.assertRaises(ValueError):verify(d,m)
