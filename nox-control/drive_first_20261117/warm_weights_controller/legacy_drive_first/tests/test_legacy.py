import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from legacy_drive_first import install

ROOT=Path(__file__).resolve().parents[1]


class LegacyDriveOnlyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.bin=self.base/'bin';self.bin.mkdir();self.shm=self.base/'shm';self.shm.mkdir()
        self.models=self.base/'models';self.models.mkdir();self.trace=self.base/'calls.jsonl'
        self.body=b'tiny-local-drive-fixture';self.source=self.base/'object';self.source.write_bytes(self.body)
        self.row={'dir':'teachers','name':'fixture.gguf','size':len(self.body),
                  'sha256':hashlib.sha256(self.body).hexdigest(),
                  'hf_url':'https://huggingface.co/NEVER_CALL/resolve/main/fixture.gguf',
                  'drive_id':'upload_blocked_uploadfile_100mb_limit'}
        text=(ROOT/'nox_teachers_warm.drive_first.sh').read_text()
        # Test-only path/cap instrumentation: never execute against native paths.
        text=text.replace('LOG=/var/log/nox/teachers_warm.log','LOG='+str(self.base/'warm.log'))
        text=text.replace('SHM_ROOT=/dev/shm/nox_t802u','SHM_ROOT='+str(self.shm))
        text=text.replace('MODELS=/root/nox/models','MODELS='+str(self.models))
        text=text.replace('RESERVE_BYTES=$((512 * 1024 * 1024))','RESERVE_BYTES=0')
        text=text.replace("shm_avail() { df -B1 --output=avail /dev/shm | tail -1 | tr -d ' '; }","shm_avail() { printf '1073741824\\n'; }")
        self.script=self.base/'warm.sh';self.script.write_text(text)
        self.env=dict(os.environ,PATH=str(self.bin)+os.pathsep+os.environ['PATH'],
            TEACHERS_MANIFEST=str(self.base/'manifest.json'),NOX_FIX_TRACE=str(self.trace),
            NOX_FIX_SOURCE=str(self.source),NOX_FIX_CONFIG='1',NOX_FIX_DOWNLOAD_FAIL='0')
        self.stub('rclone','''import json,os,sys,shutil
with open(os.environ['NOX_FIX_TRACE'],'a') as f:f.write(json.dumps(['rclone']+sys.argv[1:])+'\\n')
if sys.argv[1:]==['listremotes']:
    print('noxdrive:' if os.environ['NOX_FIX_CONFIG']=='1' else '');sys.exit(0)
assert sys.argv[1:4]==['backend','copyid','noxdrive:']
if os.environ['NOX_FIX_DOWNLOAD_FAIL']=='1':sys.exit(17)
shutil.copyfile(os.environ['NOX_FIX_SOURCE'],sys.argv[-1])
''')
        self.stub('curl',"import os,sys\nopen(os.environ['NOX_FIX_TRACE'],'a').write('[\"curl\"]\\n')\nsys.exit(91)\n")
        real_sha=shutil.which('sha256sum')
        self.stub('sha256sum',"import os,sys\nopen(os.environ['NOX_FIX_TRACE'],'a').write('[\"sha256sum\"]\\n')\nos.execv("+repr(real_sha)+",["+repr(real_sha)+"]+sys.argv[1:])\n")

    def tearDown(self):self.temp.cleanup()

    def stub(self,name,body):
        p=self.bin/name;p.write_text('#!/usr/bin/env python3\n'+body);p.chmod(0o755)

    def run_script(self):
        (self.base/'manifest.json').write_text(json.dumps({'files':[self.row]}))
        return subprocess.run(['bash',str(self.script)],env=self.env,text=True,capture_output=True,timeout=10)

    def calls(self):return [json.loads(x) for x in self.trace.read_text().splitlines()] if self.trace.exists() else []

    def verified(self):
        self.row['drive_id']='1FixtureDriveObjectVerified000001'
        self.row['drive_verification']={'verified':True,'drive_id':self.row['drive_id'],
            'size':self.row['size'],'sha256':self.row['sha256'],'receipt_id':'fixture-only','verified_at':'fixture-only'}

    def test_missing_drive_binding_or_config_blocks_new_download_preserves_existing_weights(self):
        result=self.run_script();self.assertNotEqual(result.returncode,0)
        self.assertIn('verified whole-object Drive binding required',result.stdout);self.assertEqual(self.calls(),[])
        self.verified();self.env['NOX_FIX_CONFIG']='0'
        result=self.run_script();self.assertNotEqual(result.returncode,0)
        self.assertIn('DRIVE_RCLONE_NOT_CONFIGURED',result.stdout)
        self.assertEqual(self.calls(),[['rclone','listremotes']]);self.trace.unlink()
        dest=self.shm/'teachers/fixture.gguf';dest.parent.mkdir(exist_ok=True);dest.write_bytes(self.body)
        (self.models/'teachers').symlink_to(dest.parent);before=dest.stat()
        self.row.pop('drive_verification');result=self.run_script()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(dest.stat().st_ino,before.st_ino);self.assertEqual(dest.stat().st_mtime_ns,before.st_mtime_ns)
        self.assertEqual(self.calls(),[]) # no SHA loop or provider command for existing size match.
        dest.write_bytes(b'existing mismatched file must remain')
        original=dest.read_bytes();result=self.run_script()
        self.assertNotEqual(result.returncode,0);self.assertEqual(dest.read_bytes(),original)
        self.assertEqual(self.calls(),[]);self.assertTrue((self.models/'teachers').is_symlink())

    def test_hf_url_never_called_even_after_drive_failure_and_installer_cas(self):
        self.verified();self.env['NOX_FIX_DOWNLOAD_FAIL']='1'
        result=self.run_script();self.assertNotEqual(result.returncode,0)
        self.assertTrue(any(x[:3]==['rclone','backend','copyid'] for x in self.calls()))
        self.assertFalse(any(x[0]=='curl' or any('huggingface' in a for a in x) for x in self.calls()))
        self.env['NOX_FIX_DOWNLOAD_FAIL']='0';self.trace.unlink()
        result=self.run_script();self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual((self.shm/'teachers/fixture.gguf').read_bytes(),self.body)
        self.assertFalse(any(x[0]=='curl' for x in self.calls()))
        target=self.base/'native-fixture-warm.sh';target.write_bytes((ROOT/'source/nox_teachers_warm.sh').read_bytes());target.chmod(0o750)
        lock=self.base/'owner_maintenance.lock';lock.touch()
        with self.assertRaisesRegex(ValueError,'compare-and-swap'):
            install.install(apply=True,expected_source_sha='0'*64,target=target,lock_path=lock)
        self.assertEqual(install.sha(target.read_bytes()),install.BEFORE_SHA)
        with lock.open('r+') as held:
            fcntl.flock(held.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'lock busy'):
                install.install(apply=True,expected_source_sha=install.BEFORE_SHA,target=target,lock_path=lock)
        receipt=install.install(apply=True,expected_source_sha=install.BEFORE_SHA,target=target,lock_path=lock)
        self.assertEqual(receipt['status'],'PATCH_APPLIED_NOT_EXECUTED')
        self.assertEqual(install.sha(target.read_bytes()),install.AFTER_SHA)
        self.assertEqual(install.sha(Path(receipt['backup']).read_bytes()),install.BEFORE_SHA)
        self.assertEqual(target.stat().st_mode&0o777,0o750)
        self.assertEqual(install.install(apply=True,expected_source_sha=install.BEFORE_SHA,target=target,lock_path=lock)['status'],'ALREADY_APPLIED')


if __name__=='__main__':unittest.main()
