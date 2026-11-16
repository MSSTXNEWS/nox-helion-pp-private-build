import importlib.util, hashlib, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('backup',Path(__file__).with_name('owner_native_deploy.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class BackupGateTests(unittest.TestCase):
 def test_absent_profile_no_mutation_no_snapshot_no_remote(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp); flags={str(p/'STOP'):'a'*64}
   with patch.dict(os.environ,{'NOX_OWNER_REQUEST_ID':'123','NOX_OWNER_SOURCE_SHA':'a'*40}), patch.object(m,'flag_snapshot',return_value=flags), patch.object(m,'stopped_services',return_value=28), patch.object(m,'profile_probe',return_value=(None,[{'present':False}]*3)), patch.object(m.os,'open',side_effect=AssertionError('mutation')), patch.object(m,'helper_module',side_effect=AssertionError('snapshot')):
    result=m.execute()
   self.assertEqual(result['state'],'HOLD_NO_EXISTING_PRIVATE_NOX_DRIVE_PROFILE')
   self.assertEqual(result['source_writes'],0);self.assertEqual(result['uploaded_bytes'],0)
   self.assertFalse(result['source_deleted']);self.assertFalse(result['resume_attempted'])
 def test_private_profile_no_credentials_printed(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'rclone.conf';p.write_text('SECRET_NOT_TO_READ');p.chmod(0o600)
   with patch.object(m,'PROFILES',(p,)), patch.object(m,'run',return_value=(0,b'nox_drive:\n')), patch.object(m,'executable',return_value='/usr/bin/rclone'), patch.object(Path,'read_text',side_effect=AssertionError('secret read')):
    selected,rows=m.profile_probe()
   self.assertEqual(selected,p);self.assertNotIn('SECRET',str(rows))
   p.chmod(0o644)
   with patch.object(m,'PROFILES',(p,)), patch.object(m,'run',side_effect=AssertionError('unsafe profile')):
    self.assertIsNone(m.profile_probe()[0])
 def test_exact_helper_reused_and_sqlite_restore(self):
  helper=m.helper_module()
  with tempfile.TemporaryDirectory() as tmp:
   a=Path(tmp)/'original.db'; b=Path(tmp)/'copy.db'
   import sqlite3
   with sqlite3.connect(a) as db:db.execute('create table t(x)');db.execute('insert into t values(17)')
   helper.snapshot_sqlite(a,b)
   with sqlite3.connect(b) as db:self.assertEqual(db.execute('select x from t').fetchone(),(17,))
 def test_checkpoint_hashes_pinned_and_no_pickles_loaded(self):
  self.assertEqual(len(m.PAYLOAD_SHA),10)
  self.assertEqual(m.PAYLOAD_SHA['optimizer.pt'],'94807af108a97210c97280bce06d86ac4ad4aa4e89a0273a796bb0de56707646')
  source=Path(m.__file__).read_text()
  self.assertNotIn('torch.load',source);self.assertNotIn('pickle.load',source)
 def test_symlink_profile_cannot_trigger_client(self):
  with tempfile.TemporaryDirectory() as tmp:
   real=Path(tmp)/'real';real.write_text('x');real.chmod(0o600)
   link=Path(tmp)/'link';link.symlink_to(real)
   with patch.object(m,'PROFILES',(link,)),patch.object(m,'run',side_effect=AssertionError('symlink used')):
    self.assertIsNone(m.profile_probe()[0])
 def test_remote_stream_restore_hash(self):
  import subprocess
  with tempfile.TemporaryDirectory() as tmp:
   data=b'private restore fixture';out=Path(tmp)/'restored'
   real_popen=subprocess.Popen
   def pipe(*a,**kw):return real_popen(['python','-c','import sys;sys.stdout.buffer.write('+repr(data)+')'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
   with patch.object(m.subprocess,'Popen',side_effect=pipe),patch.object(m,'executable',return_value='/usr/bin/rclone'):
    count=m.copy_stream_restore('config','nox_drive:private',out,len(data),hashlib.sha256(data).hexdigest())
   self.assertEqual(count,len(data));self.assertEqual(out.read_bytes(),data)
 def test_corrupt_remote_never_accepted(self):
  import subprocess
  with tempfile.TemporaryDirectory() as tmp:
   real_popen=subprocess.Popen
   def pipe(*a,**kw):return real_popen(['python','-c','print("bad",end="")'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
   with patch.object(m.subprocess,'Popen',side_effect=pipe),patch.object(m,'executable',return_value='/usr/bin/rclone'):
    with self.assertRaisesRegex(m.Hold,'REMOTE_RESTORE_SHA'):m.copy_stream_restore('config','nox_drive:private',Path(tmp)/'out',3,'0'*64)

if __name__=='__main__':unittest.main()
