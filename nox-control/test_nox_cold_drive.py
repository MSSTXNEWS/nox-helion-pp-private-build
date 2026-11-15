"""Source-only tests. The rclone fixture is local transport, NOT cloud evidence."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nox_cold_drive as cold

FAKE = r'''
import os,sys,json,time,shutil
from pathlib import Path
args=sys.argv[1:]
def loc(v):
    return Path(os.environ['TEST_REMOTE'])/v.split(':',1)[1] if v.startswith('fixture:') else Path(v)
cmd=args[0]
if cmd=='copyto':
    src,dst=loc(args[1]),loc(args[2])
    if src.name==os.environ.get('FAIL_NAME'):sys.exit(9)
    time.sleep(0.06)
    dst.parent.mkdir(parents=True,exist_ok=True)
    if '--immutable' in args and dst.exists() and dst.read_bytes()!=src.read_bytes():sys.exit(10)
    shutil.copyfile(src,dst)
elif cmd=='cat':
    if os.environ.get('TEST_STALL'):time.sleep(5)
    b=loc(args[1]).read_bytes()
    if os.environ.get('TEST_CORRUPT'):b=b'X'+b[1:]
    if os.environ.get('TEST_TRUNCATE'):b=b[:-1]
    if os.environ.get('TEST_OVERSIZE'):b+=b'X'
    if os.environ.get('TEST_STDERR'):sys.stderr.write('e'*200000)
    sys.stdout.buffer.write(b)
    if os.environ.get('TEST_CAT_FAILURE'):sys.exit(5)
elif cmd=='size':
    p=loc(args[1]);print(json.dumps({'bytes':p.stat().st_size,'count':1}))
else:sys.exit(12)
'''

class ColdTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='nox-cold-tests-')
        self.root=Path(self.tmp.name);self.bin=self.root/'bin';self.bin.mkdir()
        fake=self.bin/'rclone';fake.write_text('#!'+sys.executable+'\n'+FAKE);fake.chmod(0o700)
        self.env=patch.dict(os.environ,{'PATH':str(self.bin)+os.pathsep+os.environ.get('PATH',''),
                                       'TEST_REMOTE':str(self.root/'remote')})
        self.env.start()
        self.src=self.root/'model.gguf';self.src.write_bytes(b'verified model bytes'*1000)
        self.receipts=self.root/'receipts'
        self.job={'source':str(self.src),'remote':'fixture:cold','receipt_dir':str(self.receipts),
                  'timeout':10,'sha256':cold.sha256(self.src)}
    def tearDown(self):
        self.env.stop();self.tmp.cleanup()
    def manifest(self,**kw):
        data={'generated_at':time.time(),'active_paths':[],'protected_paths':[],
              'evict_paths':[str(self.src)]};data.update(kw)
        p=self.root/'active.json';p.write_text(json.dumps(data));return str(p)
    def test_upload_cli_has_no_ram_reserve_gate(self):
        with patch.object(cold,'upload') as op:
            self.assertEqual(cold.main(['upload','--file',str(self.src),'--remote','fixture:cold']),0)
            op.assert_called_once()
    def test_batch_defaults_six_processes(self):
        self.assertEqual(cold.parser().parse_args(['batch','--manifest','m.json','--remote','fixture:cold']).workers,6)
    def test_more_than_six_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            cold.parser().parse_args(['batch','--manifest','m.json','--remote','fixture:cold','--workers','7'])
    def test_nonpositive_ram_reserve_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            cold.main(['load','--remote','fixture:cold/a.gguf','--sha256','a'*64,'--reserve-gib','0'])
    def test_missing_sha_before_io(self):
        args=cold.parser().parse_args(['load','--remote','fixture:cold/a.gguf','--sha256','bad'])
        with patch.object(cold,'command') as op,self.assertRaises(ValueError):cold.load(args)
        op.assert_not_called()
    def test_symlink_source_rejected(self):
        p=self.root/'link.gguf';p.symlink_to(self.src)
        with self.assertRaises(ValueError):cold.assert_model(p)
    def test_symlink_parent_rejected(self):
        p=self.root/'linked';p.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):cold.assert_model(p/'model.gguf')
    def test_hardlink_rejected(self):
        p=self.root/'hard.gguf';os.link(self.src,p)
        with self.assertRaises(ValueError):cold.assert_model(p)
    def test_checkpoint_folder_rejected(self):
        p=self.root/'checkpoint-12'/'m.safetensors';p.parent.mkdir();p.write_bytes(b'1')
        with self.assertRaises(ValueError):cold.assert_model(p)
    def test_optimizer_filename_rejected(self):
        p=self.root/'optimizer.pt';p.write_bytes(b'1')
        with self.assertRaises(ValueError):cold.assert_model(p)
    def test_s03_folder_rejected(self):
        p=self.root/'S03'/'m.bin';p.parent.mkdir();p.write_bytes(b'1')
        with self.assertRaises(ValueError):cold.assert_model(p)
    def test_remote_connection_string_rejected(self):
        with self.assertRaises(ValueError):cold.assert_remote(':s3:bucket')
    def test_remote_traversal_rejected(self):
        with self.assertRaises(ValueError):cold.assert_remote('fixture:../bucket')
    def test_remote_newline_rejected(self):
        with self.assertRaises(ValueError):cold.assert_remote('fixture:abc\nsecret')
    def test_streaming_copy_and_receipt(self):
        with patch.object(cold.shutil,'disk_usage',side_effect=AssertionError('no extra disk needed')):
            row=cold.copy_verified(self.job)
        self.assertTrue(row['readback_verified']);self.assertTrue(self.src.exists())
        self.assertEqual(json.loads(Path(row['receipt']).read_text())['sha256'],self.job['sha256'])
    def test_corrupt_readback_keeps_original(self):
        with patch.dict(os.environ,{'TEST_CORRUPT':'1'}),self.assertRaises(RuntimeError):cold.copy_verified(self.job)
        self.assertTrue(self.src.exists());self.assertFalse(list(self.receipts.glob('*.json')))
    def test_truncated_readback_keeps_original(self):
        with patch.dict(os.environ,{'TEST_TRUNCATE':'1'}),self.assertRaises(RuntimeError):cold.copy_verified(self.job)
        self.assertTrue(self.src.exists())
    def test_oversize_readback_fails(self):
        with patch.dict(os.environ,{'TEST_OVERSIZE':'1'}),self.assertRaises(RuntimeError):cold.copy_verified(self.job)
    def test_full_bytes_with_failed_command_not_pass(self):
        with patch.dict(os.environ,{'TEST_CAT_FAILURE':'1'}),self.assertRaises(RuntimeError):cold.copy_verified(self.job)
    def test_stderr_does_not_deadlock(self):
        with patch.dict(os.environ,{'TEST_STDERR':'1'}):self.assertTrue(cold.copy_verified(self.job)['readback_verified'])
    def test_stream_timeout(self):
        row=cold.copy_verified(self.job)
        with patch.dict(os.environ,{'TEST_STALL':'1'}),self.assertRaises(RuntimeError):
            cold.stream_sha256(row['destination'],row['size'],0.15)
    def test_wrong_source_hash_before_copy(self):
        with patch.object(cold,'command') as op,self.assertRaises(ValueError):
            cold.copy_verified({**self.job,'sha256':'0'*64})
        op.assert_not_called()
    def test_mutating_source_during_readback(self):
        digest=self.job['sha256']
        def changed(*args):self.src.write_bytes(b'mutated');return digest
        with patch.object(cold,'stream_sha256',side_effect=changed),self.assertRaises(RuntimeError):cold.copy_verified(self.job)
        self.assertTrue(self.src.exists())
    def test_same_basename_no_overwrite(self):
        row1=cold.copy_verified(self.job)
        p=self.root/'other'/'model.gguf';p.parent.mkdir();p.write_bytes(b'other model')
        row2=cold.copy_verified({**self.job,'source':str(p),'sha256':cold.sha256(p)})
        self.assertNotEqual(row1['destination'],row2['destination'])
    def test_active_model_no_eviction(self):
        row=cold.copy_verified(self.job)
        with self.assertRaises(ValueError):cold.evict_verified(row,self.manifest(active_paths=[str(self.src)]))
        self.assertTrue(self.src.exists())
    def test_protected_directory_no_eviction(self):
        with self.assertRaises(ValueError):cold.fresh_manifest(self.manifest(protected_paths=[str(self.root)]),self.src)
    def test_stale_manifest_rejected(self):
        with self.assertRaises(ValueError):cold.fresh_manifest(self.manifest(generated_at=time.time()-301),self.src)
    def test_nonfinite_manifest_rejected(self):
        with self.assertRaises(ValueError):cold.fresh_manifest(self.manifest(generated_at=float('nan')),self.src)
    def test_explicit_eviction_required(self):
        with self.assertRaises(ValueError):cold.fresh_manifest(self.manifest(evict_paths=[]),self.src)
    def test_source_changes_before_eviction(self):
        row=cold.copy_verified(self.job);self.src.write_bytes(b'new model')
        with self.assertRaises(RuntimeError):cold.evict_verified(row,self.manifest())
        self.assertTrue(self.src.exists())
    def test_open_file_blocks_eviction(self):
        with self.src.open('rb'),self.assertRaises(RuntimeError):cold.assert_not_open(self.src)
    def test_verified_fixture_eviction_record(self):
        row=cold.copy_verified(self.job)
        with patch.object(cold,'assert_not_open'):
            result=cold.evict_verified(row,self.manifest())
        self.assertFalse(self.src.exists());self.assertTrue(result['source_deleted'])
        self.assertEqual(result['source_logical_bytes_removed'],row['size'])
    def test_storage_lock_excludes_second_writer(self):
        with cold.maintenance_lock(self.receipts),self.assertRaises(RuntimeError):
            with cold.maintenance_lock(self.receipts):pass
    def test_atomic_receipt_rejects_symlink(self):
        p=self.root/'r.json';p.symlink_to(self.src)
        with self.assertRaises(ValueError):cold.atomic_json(p,{'x':1})
    def test_cgroup_budget_not_host_total(self):
        def text(p,*args,**kw):
            return {'/proc/meminfo':'MemAvailable: 104857600 kB\n',
                    '/sys/fs/cgroup/memory.max':str(20*cold.GIB),
                    '/sys/fs/cgroup/memory.current':str(10*cold.GIB)}[str(p)]
        with patch.object(Path,'read_text',autospec=True,side_effect=text),\
             patch.object(Path,'is_file',autospec=True,side_effect=lambda p:str(p).endswith('memory.max')),\
             patch.object(cold.shutil,'disk_usage',return_value=type('D',(),{'free':100*cold.GIB})()):
            self.assertEqual(cold.memory_budget('/dev/shm',2),8*cold.GIB)
    def test_six_process_batch_transfer(self):
        files=[]
        for i in range(6):
            p=self.root/('m%d.gguf'%i);p.write_bytes(bytes([i+1])*1048576)
            files.append({'path':str(p),'sha256':cold.sha256(p)})
        m=self.root/'batch.json';m.write_text(json.dumps({'files':files}))
        args=cold.parser().parse_args(['batch','--manifest',str(m),'--remote','fixture:cold',
                                      '--receipt-dir',str(self.receipts),'--workers','6'])
        with contextlib.redirect_stdout(io.StringIO()):cold.batch(args)
        summary=json.loads((self.receipts/'last-batch.json').read_text())
        rows=[json.loads(Path(p).read_text()) for p in summary['receipts']]
        pids=sorted({r['worker_pid'] for r in rows})
        self.assertEqual(summary['copies_verified'],6);self.assertEqual(len(pids),6)
        self.assertTrue(all(Path(r['source']).exists() for r in rows))
        proof={'kind':'LOCAL_FIXTURE_ONLY_NOT_VAST_OR_DRIVE','worker_pids':pids,'copies_verified':6,
               'bytes_verified':sum(r['size'] for r in rows),'source_deleted':False}
        if os.environ.get('NOX_TEST_PROOF'):
            Path(os.environ['NOX_TEST_PROOF']).write_text(json.dumps(proof,indent=2))
    def test_incomplete_batch_never_evicts_any_source(self):
        files=[]
        for name in ['ok.gguf','fail.gguf']:
            p=self.root/name;p.write_bytes(b'bytes');files.append({'path':str(p),'sha256':cold.sha256(p)})
        m=self.root/'batch.json';m.write_text(json.dumps({'files':files}))
        args=cold.parser().parse_args(['batch','--manifest',str(m),'--remote','fixture:cold',
                                      '--receipt-dir',str(self.receipts),'--evict','--active-manifest',self.manifest()])
        with patch.dict(os.environ,{'FAIL_NAME':'fail.gguf'}),self.assertRaises(RuntimeError):cold.batch(args)
        self.assertTrue(all(Path(x['path']).exists() for x in files))
        self.assertEqual(json.loads((self.receipts/'last-batch.json').read_text())['sources_deleted'],0)

if __name__=='__main__':unittest.main(verbosity=2)
