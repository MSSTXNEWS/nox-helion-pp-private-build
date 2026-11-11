#!/usr/bin/env python3
"""Synthetic unit tests only. No model weights, GPU, RunPod, networks or REAL step evidence."""
import json, os, pathlib, shutil, subprocess, sys, tempfile, unittest
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from nox_local_preflight import assess,local_path,sha256_file
from nox_local_telemetry import inspect

HERE=pathlib.Path(__file__).parent
ARCHIVE_TRAINER=pathlib.Path('/mnt/data/nox_training_review/NOX_TRAINING_PROGRAM_20261112/train_n36/train_n36.py')

class TestNoLossLocalFirst(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='nox-local-first-');self.addCleanup(self.tmp.cleanup)
  root=self.root=pathlib.Path(self.tmp.name,'root');root.mkdir()
  self.base=pathlib.Path(self.tmp.name,'ram-base');self.base.mkdir()
  (self.base/'model.safetensors.index.json').write_text(json.dumps({'weight_map':{'a':'model-00001-of-00002.safetensors','b':'model-00002-of-00002.safetensors'}}))
  (self.base/'model-00001-of-00002.safetensors').write_bytes(b'FAKE UNIT TEST 1')
  (self.base/'model-00002-of-00002.safetensors').write_bytes(b'FAKE UNIT TEST 2')
  data=root/'data/tok';data.mkdir(parents=True)
  (data/'train.pt').write_bytes(b'train fixture - never a real dataset')
  (data/'hold.pt').write_bytes(b'hold fixture - never a real dataset')
  ck=root/'ckpt/sft/last';ck.mkdir(parents=True)
  (ck/'STEP').write_text('85')
  (ck/'adapter_model.safetensors').write_bytes(b'fake adapter bytes')
  (ck/'adapter_config.json').write_text('{}')
  (ck/'opt.pt').write_bytes(b'fake optimizer bytes')
  (root/'ckpt/sft/plan.json').write_text('[[0]]')
  seed=root/'seed';seed.mkdir();(seed/'common.py').write_text('student_system="synthetic fixture"\n')
  scripts=root/'scripts';scripts.mkdir()
  self.trainer=scripts/'train_n36_local.py'
  self.trainer.write_text('import os\nW=os.environ.get("NOX_WORKDIR","/root/nox_local")\nTD=os.environ.get("TD",f"{W}/data/tok")\n')
 def args(self,hash_checkpoint=False,expect=85):
  from argparse import Namespace
  return Namespace(root=str(self.root),base=str(self.base),data=None,ckpt=None,trainer=str(self.trainer),seed=None,
                   expected_step=expect,reserve_gb=0,hash_checkpoint=hash_checkpoint,hash_base=False,json_out=None,backup_digest_manifest=None)
 def test_without_hash_no_fake_full_model(self):
  r=assess(self.args());self.assertEqual(r['status'],'LOCAL_PATHS_READY_CHECKPOINT_HASH_PENDING')
  self.assertEqual(r['observedStep'],85)
  self.assertIsNone(r['percentDistilledKnowledge']);self.assertFalse(r['fullStudentWeightsVerified'])
 def test_adapter_checksum_not_equal_full_weights(self):
  r=assess(self.args(True));self.assertEqual(r['status'],'LOCAL_ADAPTER_SELF_HASHED_REFERENCE_NOT_VERIFIED')
  self.assertTrue(r['checks']['checkpoint_hashes']['complete']);self.assertFalse(r['fullStudentWeightsVerified'])
 def test_backed_up_digests_compare(self):
  from nox_local_preflight import sha256_file
  ck=self.root/'ckpt/sft/last'
  report={'step':85,'hashes':{n:sha256_file(str(ck/n)) for n in ['STEP','adapter_model.safetensors','opt.pt','adapter_config.json']}}
  p=self.root/'backup-sha.json';p.write_text(json.dumps(report))
  a=self.args(True);a.backup_digest_manifest=str(p)
  r=assess(a);self.assertEqual(r['status'],'ADAPTER_BACKUP_DIGEST_MATCHED_NOT_FULL_WEIGHTS')
  self.assertTrue(r['externalBackupDigestMatched'])
  report['hashes']['STEP']='deadbeef';p.write_text(json.dumps(report))
  self.assertEqual(assess(a)['status'],'HOLD')
 def test_step_mismatch_detected(self):
  r=assess(self.args(expect=86));self.assertEqual(r['status'],'HOLD');self.assertIn('STEP_BELOW_OWNER_REPORTED_85',r['problems'])
 def test_missing_optimizer_holds(self):
  (self.root/'ckpt/sft/last/opt.pt').unlink();self.assertEqual(assess(self.args(True))['status'],'HOLD')
 def test_trainer_network_dependency_holds(self):
  self.trainer.write_text('W="/workspace/nox36"\n')
  self.assertIn('TRAINER_STILL_DEPENDS_ON_NETWORK_PATH',assess(self.args())['problems'])
 def test_telemetry_never_implies_full_weights(self):
  proof=assess(self.args(True));data={'step':85,'total':100}
  x=inspect(proof,data,5)
  self.assertEqual(x['status'],'HOLD');self.assertFalse(x['fullStudentWeightsVerified'])
  report={'step':85,'hashes':{n:sha256_file(str(self.root/'ckpt/sft/last'/n)) for n in ['STEP','adapter_model.safetensors','opt.pt','adapter_config.json']}}
  p=self.root/'backup-sha.json';p.write_text(json.dumps(report))
  a=self.args(True);a.backup_digest_manifest=str(p)
  verified=assess(a)
  r=inspect(verified,data,5)
  self.assertEqual(r['status'],'LOCAL_TRAINER_STATUS_FILE_FRESH')
  self.assertEqual(r['stepCompletionPercent'],85)
  self.assertFalse(r['fullStudentWeightsVerified']);self.assertIsNone(r['intelligenceProgressPercent'])
  self.assertEqual(inspect(verified,data,121)['status'],'LOCAL_CHECKPOINT_HASH_MATCHED')
 def test_network_rejected_before_stat(self):
  with self.assertRaisesRegex(ValueError,'NETWORK_PATH_BLOCKED'):local_path('/workspace/nox36')
 def test_network_symlink_rejected(self):
  link=pathlib.Path(self.tmp.name,'network-link');link.symlink_to('/workspace/nox36')
  with self.assertRaisesRegex(ValueError,'NETWORK_SYMLINK_BLOCKED'):local_path(str(link/'ckpt/last'))
 def test_local_copy_default_dry_run_and_idempotent(self):
  source=self.root/'ckpt/sft/last';dst=pathlib.Path(self.tmp.name,'dest')
  for extra,expected in [([], 'DRY_RUN_NOT_COPIED'),(['--apply'],'VERIFIED_LOCAL_COPY'),(['--apply'],'VERIFIED_LOCAL_COPY')]:
   p=subprocess.run([sys.executable,str(HERE/'nox_copy_verified.py'),'--source',str(source),'--target',str(dst),
    '--expect-step','85','--reserve-gb','0',*extra],capture_output=True,text=True)
   self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(json.loads(p.stdout)['status'],expected)
 def test_local_copy_conflict_never_overwrites(self):
  source=self.root/'ckpt/sft/last';dst=pathlib.Path(self.tmp.name,'dest');dst.mkdir()
  (dst/'STEP').write_text('999')
  p=subprocess.run([sys.executable,str(HERE/'nox_copy_verified.py'),'--source',str(source),'--target',str(dst),
    '--expect-step','85','--reserve-gb','0','--apply'],capture_output=True,text=True)
  self.assertEqual(p.returncode,2);self.assertIn('DEST_EXISTS_DIFFERENT',p.stdout);self.assertEqual((dst/'STEP').read_text(),'999')
 def test_local_copy_never_touches_workspace(self):
  p=subprocess.run([sys.executable,str(HERE/'nox_copy_verified.py'),'--source','/workspace/nox36','--target',str(self.root),
    '--reserve-gb','0'],capture_output=True,text=True)
  self.assertEqual(p.returncode,2);self.assertIn('NETWORK_PATH_BLOCKED',p.stdout)
 def test_script_is_syntactically_valid(self):
  for name in ['nox_local_preflight.py','nox_patch_trainer.py','nox_copy_verified.py','nox_local_telemetry.py']:
   import ast
   ast.parse((HERE/name).read_text())

if __name__=='__main__':unittest.main(verbosity=2)
