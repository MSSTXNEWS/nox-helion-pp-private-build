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
    if '--offset' in args and not os.environ.get('TEST_IGNORE_RANGE'):
        off=int(args[args.index('--offset')+1]);cnt=int(args[args.index('--count')+1])
        b=b[off:off+cnt]
    if os.environ.get('TEST_STDERR'):sys.stderr.write('e'*200000)
    sys.stdout.buffer.write(b)
    if os.environ.get('TEST_CAT_FAILURE'):sys.exit(5)
elif cmd=='size':
    if os.environ.get('TEST_STALL_SIZE'):time.sleep(5)
    if os.environ.get('TEST_SIZE_FLOOD'):sys.stdout.write('X'*70000);sys.exit(0)
    if os.environ.get('TEST_SIZE_FAILURE'):sys.exit(9)
    item=next((v for v in args[1:] if not v.startswith('--')),None)
    p=loc(item);print(json.dumps({'bytes':p.stat().st_size,'count':1}))
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
    def test_qwen_lora_run_is_not_an_evictable_model(self):
        p=self.root/'LoRA'/'qlora_t866u'/'runs_owner_hybrid'/'adapter_model.safetensors'
        p.parent.mkdir(parents=True);p.write_bytes(b'checkpoint adapter')
        with self.assertRaisesRegex(ValueError,'HOLD_PROTECTED_PATH'):
            cold.assert_model(p)
        with patch.object(cold,'command') as transfer,self.assertRaises(ValueError):
            cold.copy_verified({**self.job,'source':str(p)})
        transfer.assert_not_called()

    def test_adapter_file_outside_lora_folder_is_protected(self):
        for name in ('adapter.safetensors','adapter_model.safetensors',
                     'LoRA-merged.gguf','QLoRA.bin'):
            p=self.root/name;p.write_bytes(b'unique adapter or training state')
            with self.subTest(name=name),self.assertRaisesRegex(
                    ValueError,'HOLD_PROTECTED_TRAINING_STATE'):
                cold.assert_model(p)

    def test_adapter_directory_not_evictable(self):
        p=self.root/'adapters'/'unique.safetensors'
        p.parent.mkdir(parents=True);p.write_bytes(b'not a cold-eviction candidate')
        with self.assertRaisesRegex(ValueError,'HOLD_PROTECTED_PATH'):
            cold.assert_model(p)

    def test_ordinary_inactive_gguf_stays_eligible_for_copy(self):
        self.assertEqual(cold.assert_model(self.src),self.src)

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
        with patch.object(cold,'assert_not_open'), patch.object(cold,'independent_restore',return_value=True):
            result=cold.evict_verified(row,self.manifest(),str(self.root/'separate-mount'))
        self.assertFalse(self.src.exists());self.assertTrue(result['source_deleted'])
        self.assertEqual(result['source_logical_bytes_removed'],row['size'])
    def test_evict_without_independent_restore_never_unlinks(self):
        row=cold.copy_verified(self.job)
        with patch.object(cold,'assert_not_open'), self.assertRaisesRegex(RuntimeError,'HOLD_INDEPENDENT_RESTORE_REQUIRED'):
            cold.evict_verified(row,self.manifest())
        self.assertTrue(self.src.exists())

    def test_same_filesystem_is_not_independent_restore(self):
        row=cold.copy_verified(self.job)
        with self.assertRaisesRegex(ValueError,'HOLD_RESTORE_NOT_INDEPENDENT_FILESYSTEM'):
            cold.independent_restore(row,self.root,10)
        self.assertTrue(self.src.exists())

    def test_full_independent_tmpfs_restore_sha_and_cleanup(self):
        if not Path('/dev/shm').is_dir():
            self.skipTest('no tmpfs available')
        with tempfile.TemporaryDirectory(prefix='nox-restore-test-',dir='/dev/shm') as restored:
            if Path(restored).stat().st_dev == self.src.stat().st_dev:
                self.skipTest('test host has no separate mount')
            row=cold.copy_verified(self.job)
            with patch.object(cold,'memory_budget',return_value=10**7):
                self.assertTrue(cold.independent_restore(row,restored,10))
            self.assertEqual(list(Path(restored).iterdir()),[])
        self.assertTrue(self.src.exists())

    def test_corrupt_offsite_restoration_never_passes(self):
        if not Path('/dev/shm').is_dir():
            self.skipTest('no tmpfs available')
        with tempfile.TemporaryDirectory(prefix='nox-restore-test-',dir='/dev/shm') as restored:
            if Path(restored).stat().st_dev == self.src.stat().st_dev:
                self.skipTest('test host has no separate mount')
            row=cold.copy_verified(self.job)
            remote_file=Path(os.environ['TEST_REMOTE'])/row['destination'].split(':',1)[1]
            remote_file.write_bytes(b'Z'+remote_file.read_bytes()[1:])
            with patch.object(cold,'memory_budget',return_value=10**7), self.assertRaisesRegex(RuntimeError,'HOLD_INDEPENDENT_RESTORE_SHA_MISMATCH'):
                cold.independent_restore(row,restored,10)
            self.assertEqual(list(Path(restored).iterdir()),[])
        self.assertTrue(self.src.exists())

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
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                cold.batch(args)
        except RuntimeError:
            summary_path = self.receipts/'last-batch.json'
            summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
            self.fail('Six-process fixture transfer incomplete: ' + json.dumps({
                'requested': summary.get('requested'), 'copies_verified': summary.get('copies_verified'),
                'error_types': [e.get('error') for e in summary.get('errors', [])]
            }))
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
                                      '--receipt-dir',str(self.receipts),'--evict','--active-manifest',self.manifest(),
                                      '--restore-test-dir',str(self.root)])
        with patch.dict(os.environ,{'FAIL_NAME':'fail.gguf'}),self.assertRaises(RuntimeError):cold.batch(args)
        self.assertTrue(all(Path(x['path']).exists() for x in files))
        self.assertEqual(json.loads((self.receipts/'last-batch.json').read_text())['sources_deleted'],0)


    def stage_range(self):
        remote=Path(os.environ['TEST_REMOTE'])/'cold'/'model.gguf'
        remote.parent.mkdir(parents=True,exist_ok=True)
        remote.write_bytes(self.src.read_bytes())

    def test_verified_range_uses_exact_block_not_entire_model(self):
        self.stage_range()
        body=self.src.read_bytes()
        selected=body[111:111+512]
        got=cold.read_verified_range(
            'fixture:cold/model.gguf',111,512,len(body),hashlib.sha256(selected).hexdigest(),
            timeout=5,stop_probe=lambda:False)
        self.assertEqual(got,selected)
        self.assertEqual(len(got),512)
        self.assertTrue(self.src.exists())

    def test_verified_range_block_hash_rejects_corruption(self):
        self.stage_range()
        body=self.src.read_bytes()
        with patch.dict(os.environ,{'TEST_CORRUPT':'1'}),self.assertRaisesRegex(
                RuntimeError,'HOLD_RANGE_SHA_MISMATCH'):
            cold.read_verified_range('fixture:cold/model.gguf',0,100,len(body),
                                     hashlib.sha256(body[:100]).hexdigest(),stop_probe=lambda:False)

    def test_verified_range_overfetch_never_publishes(self):
        self.stage_range()
        body=self.src.read_bytes()
        with patch.dict(os.environ,{'TEST_IGNORE_RANGE':'1'}),self.assertRaisesRegex(
                RuntimeError,'HOLD_RANGE_OVERSIZE'):
            cold.read_verified_range('fixture:cold/model.gguf',100,100,len(body),
                                     hashlib.sha256(body[100:200]).hexdigest(),stop_probe=lambda:False)

    def test_verified_range_network_failure_and_timeout(self):
        self.stage_range()
        body=self.src.read_bytes()
        hashpart=hashlib.sha256(body[:100]).hexdigest()
        with patch.dict(os.environ,{'TEST_CAT_FAILURE':'1'}),self.assertRaisesRegex(
                RuntimeError,'HOLD_RANGE_INCOMPLETE'):
            cold.read_verified_range('fixture:cold/model.gguf',0,100,len(body),hashpart,
                                     timeout=5,stop_probe=lambda:False)
        with patch.dict(os.environ,{'TEST_STALL':'1'}),self.assertRaisesRegex(
                RuntimeError,'HOLD_RANGE_TIMEOUT'):
            cold.read_verified_range('fixture:cold/model.gguf',0,100,len(body),hashpart,
                                     timeout=.25,stop_probe=lambda:False)

    def test_verified_range_stop_and_bounds_before_network(self):
        self.stage_range()
        body=self.src.read_bytes()
        hashpart=hashlib.sha256(body[:100]).hexdigest()
        with patch.object(cold,'command') as cmd,self.assertRaisesRegex(
                RuntimeError,'HOLD_OWNER_STOP'):
            cold.read_verified_range('fixture:cold/model.gguf',0,100,len(body),hashpart,
                                     stop_probe=lambda:True)
        cmd.assert_not_called()
        for offset,length in [(-1,100),(0,0),(0,2**20+1),(len(body),1),
                              (len(body)-10,100)]:
            with patch.object(cold,'command') as cmd,self.assertRaisesRegex(
                    ValueError,'HOLD_RANGE_BOUNDS'):
                cold.read_verified_range('fixture:cold/model.gguf',offset,length,len(body),
                                         hashpart,stop_probe=lambda:False)
            cmd.assert_not_called()

    def test_verified_range_metadata_obeys_owner_stop_during_stall(self):
        self.stage_range()
        body=self.src.read_bytes()
        checks=[0]
        def probe():
            checks[0] += 1
            return checks[0] >= 4
        start=time.monotonic()
        with patch.dict(os.environ,{'TEST_STALL_SIZE':'1'}), self.assertRaisesRegex(
                RuntimeError,'HOLD_OWNER_STOP'):
            cold.read_verified_range('fixture:cold/model.gguf',0,100,len(body),
                hashlib.sha256(body[:100]).hexdigest(),timeout=5,stop_probe=probe)
        self.assertLess(time.monotonic()-start,2.5)

    def test_verified_range_metadata_is_capped_without_disk_spool(self):
        self.stage_range()
        body=self.src.read_bytes()
        with patch.dict(os.environ,{'TEST_SIZE_FLOOD':'1'}), self.assertRaisesRegex(
                RuntimeError,'HOLD_RANGE_METADATA_OVERSIZE'):
            cold.read_verified_range('fixture:cold/model.gguf',0,100,len(body),
                hashlib.sha256(body[:100]).hexdigest(),timeout=5,stop_probe=lambda:False)
        self.assertTrue(self.src.exists())

    def test_verified_range_metadata_failure_no_false_pass(self):
        self.stage_range()
        body=self.src.read_bytes()
        with patch.dict(os.environ,{'TEST_SIZE_FAILURE':'1'}), self.assertRaisesRegex(
                RuntimeError,'HOLD_RANGE_METADATA_INCOMPLETE'):
            cold.read_verified_range('fixture:cold/model.gguf',0,100,len(body),
                hashlib.sha256(body[:100]).hexdigest(),timeout=5,stop_probe=lambda:False)

    def test_verified_range_metadata_respects_total_deadline(self):
        self.stage_range()
        body=self.src.read_bytes()
        start=time.monotonic()
        with patch.dict(os.environ,{'TEST_STALL_SIZE':'1'}), self.assertRaisesRegex(
                RuntimeError,'HOLD_RANGE_TIMEOUT'):
            cold.read_verified_range('fixture:cold/model.gguf',0,100,len(body),
                hashlib.sha256(body[:100]).hexdigest(),timeout=.25,stop_probe=lambda:False)
        self.assertLess(time.monotonic()-start,2.5)

    def test_verified_range_object_size_changed(self):
        self.stage_range()
        body=self.src.read_bytes()
        with self.assertRaisesRegex(RuntimeError,'HOLD_RANGE_OBJECT_SIZE_CHANGED'):
            cold.read_verified_range('fixture:cold/model.gguf',0,100,len(body)+1,
                hashlib.sha256(body[:100]).hexdigest(),stop_probe=lambda:False)

if __name__=='__main__':unittest.main(verbosity=2)
