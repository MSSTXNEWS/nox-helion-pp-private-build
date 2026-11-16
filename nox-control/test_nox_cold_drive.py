"""Source-only tests. The rclone fixture is local transport, NOT cloud evidence."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import threading
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
    if os.environ.get('TEST_STALL_COPY'):
        Path(os.environ['TEST_COPY_STARTED']).write_text(str(os.getpid()))
        time.sleep(5)
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
    if os.environ.get('TEST_CLOSE_STDOUT_THEN_STALL'):
        sys.stdout.flush()
        sys.stdout.close()
        if os.environ.get('TEST_EOF_MARKER'):
            Path(os.environ['TEST_EOF_MARKER']).write_text('eof')
        time.sleep(5)
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
    def test_ram_load_holds_when_cgroup_reserve_drops_during_copy(self):
        if not Path('/dev/shm').is_dir():
            self.skipTest('tmpfs unavailable')
        with tempfile.TemporaryDirectory(prefix='nox-ram-budget-', dir='/dev/shm') as ram_dir:
            remote=Path(os.environ['TEST_REMOTE'])/'cold'/'model.gguf'
            remote.parent.mkdir(parents=True, exist_ok=True)
            remote.write_bytes(self.src.read_bytes())
            args=cold.parser().parse_args([
                'load','--remote','fixture:cold/model.gguf','--ram-dir',ram_dir,
                '--sha256',cold.sha256(self.src),'--reserve-gib','1','--timeout','5'])
            size=self.src.stat().st_size
            with patch.object(cold,'memory_budget',side_effect=[size+1,-1]), \
                 self.assertRaisesRegex(RuntimeError,'HOLD_RAM_RESERVE_AFTER_COPY'):
                with contextlib.redirect_stdout(io.StringIO()):
                    cold.load(args)
            self.assertFalse((Path(ram_dir)/'model.gguf').exists())
            self.assertEqual(list(Path(ram_dir).glob('.nox-load-*')),[])

    def test_ram_load_publishes_only_when_postcopy_reserve_remains(self):
        if not Path('/dev/shm').is_dir():
            self.skipTest('tmpfs unavailable')
        with tempfile.TemporaryDirectory(prefix='nox-ram-budget-', dir='/dev/shm') as ram_dir:
            remote=Path(os.environ['TEST_REMOTE'])/'cold'/'model.gguf'
            remote.parent.mkdir(parents=True, exist_ok=True)
            remote.write_bytes(self.src.read_bytes())
            args=cold.parser().parse_args([
                'load','--remote','fixture:cold/model.gguf','--ram-dir',ram_dir,
                '--sha256',cold.sha256(self.src),'--reserve-gib','1','--timeout','5'])
            size=self.src.stat().st_size
            with patch.object(cold,'memory_budget',side_effect=[size+1,1]):
                with contextlib.redirect_stdout(io.StringIO()):
                    cold.load(args)
            self.assertEqual((Path(ram_dir)/'model.gguf').read_bytes(),self.src.read_bytes())
            self.assertEqual(list(Path(ram_dir).glob('.nox-load-*')),[])

    def test_owner_stop_paths_cover_existing_onehost_variants(self):
        names={str(p) for p in cold.OWNER_STOP_PATHS}
        self.assertTrue({'/root/nox/STOP','/root/nox/STOP.flag',
                         '/root/nox/stop.flag','/root/nox/.stop',
                         '/root/nox/program/STOP','/root/nox/state/STOP',
                         '/root/nox/state/STOP.flag','/workspace/NOX_STOP'} <= names)

    def test_ram_load_owner_stop_blocks_metadata_request(self):
        if not Path('/dev/shm').is_dir():
            self.skipTest('tmpfs unavailable')
        with tempfile.TemporaryDirectory(prefix='nox-ram-owner-stop-',dir='/dev/shm') as ram_dir:
            args=cold.parser().parse_args([
                'load','--remote','fixture:cold/model.gguf','--ram-dir',ram_dir,
                '--sha256',cold.sha256(self.src),'--reserve-gib','1','--timeout','5'])
            stop=self.root/'STOP.flag';stop.touch()
            with patch.object(cold,'OWNER_STOP_PATHS',(stop,)), patch.object(
                    cold,'command') as cmd, self.assertRaisesRegex(RuntimeError,'HOLD_OWNER_STOP'):
                cold.load(args)
            cmd.assert_not_called()
            self.assertEqual(list(Path(ram_dir).iterdir()),[])

    def test_ram_load_stop_during_copy_never_publishes(self):
        if not Path('/dev/shm').is_dir():
            self.skipTest('tmpfs unavailable')
        with tempfile.TemporaryDirectory(prefix='nox-ram-owner-stop-',dir='/dev/shm') as ram_dir:
            remote=Path(os.environ['TEST_REMOTE'])/'cold'/'model.gguf'
            remote.parent.mkdir(parents=True,exist_ok=True)
            remote.write_bytes(self.src.read_bytes())
            args=cold.parser().parse_args([
                'load','--remote','fixture:cold/model.gguf','--ram-dir',ram_dir,
                '--sha256',cold.sha256(self.src),'--reserve-gib','1','--timeout','5'])
            stop=self.root/'STOP.flag'
            original=cold.command
            def stop_after_copy(argv,timeout=3600):
                result=original(argv,timeout)
                if argv[1]=='copyto':stop.touch()
                return result
            with patch.object(cold,'OWNER_STOP_PATHS',(stop,)), patch.object(
                    cold,'command',side_effect=stop_after_copy), patch.object(
                    cold,'memory_budget',return_value=self.src.stat().st_size+1), self.assertRaisesRegex(
                    RuntimeError,'HOLD_OWNER_STOP'):
                cold.load(args)
            self.assertFalse((Path(ram_dir)/'model.gguf').exists())
            self.assertEqual(list(Path(ram_dir).glob('.nox-load-*')),[])

    def test_ram_load_stop_after_fsync_never_publishes(self):
        if not Path('/dev/shm').is_dir():
            self.skipTest('tmpfs unavailable')
        with tempfile.TemporaryDirectory(prefix='nox-ram-owner-stop-',dir='/dev/shm') as ram_dir:
            remote=Path(os.environ['TEST_REMOTE'])/'cold'/'model.gguf'
            remote.parent.mkdir(parents=True,exist_ok=True)
            remote.write_bytes(self.src.read_bytes())
            args=cold.parser().parse_args([
                'load','--remote','fixture:cold/model.gguf','--ram-dir',ram_dir,
                '--sha256',cold.sha256(self.src),'--reserve-gib','1','--timeout','5'])
            stop=self.root/'STOP.flag'
            original=os.fsync
            def stop_after_fsync(fd):
                result=original(fd);stop.touch();return result
            with patch.object(cold,'OWNER_STOP_PATHS',(stop,)), patch.object(
                    cold.os,'fsync',side_effect=stop_after_fsync), patch.object(
                    cold,'memory_budget',side_effect=[self.src.stat().st_size+1,1]), self.assertRaisesRegex(
                    RuntimeError,'HOLD_OWNER_STOP'):
                cold.load(args)
            self.assertFalse((Path(ram_dir)/'model.gguf').exists())
            self.assertEqual(list(Path(ram_dir).glob('.nox-load-*')),[])

    def test_owner_stop_cancels_inflight_ram_copy_without_publish(self):
        if not Path('/dev/shm').is_dir():
            self.skipTest('tmpfs unavailable')
        with tempfile.TemporaryDirectory(prefix='nox-ram-cancel-',dir='/dev/shm') as ram_dir:
            remote=Path(os.environ['TEST_REMOTE'])/'cold'/'model.gguf'
            remote.parent.mkdir(parents=True,exist_ok=True)
            remote.write_bytes(self.src.read_bytes())
            marker=self.root/'copy-started'
            stop=self.root/'STOP.flag'
            def trigger_stop():
                for _ in range(100):
                    if marker.exists():
                        stop.touch()
                        return
                    time.sleep(.02)
            args=cold.parser().parse_args([
                'load','--remote','fixture:cold/model.gguf','--ram-dir',ram_dir,
                '--sha256',cold.sha256(self.src),'--reserve-gib','1','--timeout','4'])
            watcher=threading.Thread(target=trigger_stop,daemon=True)
            started=time.monotonic()
            with patch.dict(os.environ,{'TEST_STALL_COPY':'1','TEST_COPY_STARTED':str(marker)}), \
                 patch.object(cold,'OWNER_STOP_PATHS',(stop,)), \
                 patch.object(cold,'memory_budget',return_value=self.src.stat().st_size+1), \
                 self.assertRaisesRegex(RuntimeError,'HOLD_OWNER_STOP'):
                watcher.start()
                cold.load(args)
            watcher.join(timeout=2)
            self.assertTrue(marker.exists())
            self.assertTrue(stop.exists())
            self.assertLess(time.monotonic()-started,2.8)
            self.assertFalse((Path(ram_dir)/'model.gguf').exists())
            self.assertEqual(list(Path(ram_dir).glob('.nox-load-*')),[])

    def test_owner_stop_interrupts_stalled_rclone_metadata(self):
        remote=Path(os.environ['TEST_REMOTE'])/'cold'/'model.gguf'
        remote.parent.mkdir(parents=True,exist_ok=True)
        remote.write_bytes(self.src.read_bytes())
        checks=[0]
        def gate():
            checks[0]+=1
            if checks[0]>=4:
                raise RuntimeError('HOLD_OWNER_STOP')
        started=time.monotonic()
        with patch.dict(os.environ,{'TEST_STALL_SIZE':'1'}), \
             patch.object(cold,'assert_owner_stop_clear',side_effect=gate), \
             self.assertRaisesRegex(RuntimeError,'HOLD_OWNER_STOP'):
            cold.command(['rclone','size','--json','fixture:cold/model.gguf'],timeout=4)
        self.assertLess(time.monotonic()-started,2.8)

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
    def test_stream_readback_stop_before_io(self):
        stop=self.root/'STOP.flag';stop.touch()
        with patch.object(cold,'OWNER_STOP_PATHS',(stop,)), \
             patch.object(cold.subprocess,'Popen') as launched, \
             self.assertRaisesRegex(RuntimeError,'HOLD_OWNER_STOP'):
            cold.stream_sha256('fixture:cold/model.gguf', 123, 5)
        launched.assert_not_called()

    def test_stream_readback_stop_during_stall(self):
        remote=Path(os.environ['TEST_REMOTE'])/'cold'/'model.gguf'
        remote.parent.mkdir(parents=True,exist_ok=True)
        remote.write_bytes(self.src.read_bytes())
        stop=self.root/'STOP.flag'
        timer=threading.Timer(.20,stop.touch)
        started=time.monotonic()
        with patch.dict(os.environ,{'TEST_STALL':'1'}), \
             patch.object(cold,'OWNER_STOP_PATHS',(stop,)), \
             self.assertRaisesRegex(RuntimeError,'HOLD_OWNER_STOP'):
            timer.start()
            cold.stream_sha256('fixture:cold/model.gguf',remote.stat().st_size,4)
        timer.join(timeout=2)
        self.assertLess(time.monotonic()-started,2.8)

    def test_stream_readback_stop_after_eof(self):
        remote=Path(os.environ['TEST_REMOTE'])/'cold'/'model.gguf'
        remote.parent.mkdir(parents=True,exist_ok=True)
        remote.write_bytes(self.src.read_bytes())
        marker=self.root/'EOF';stop=self.root/'STOP.flag'
        def trigger():
            for _ in range(150):
                if marker.exists():
                    stop.touch();return
                time.sleep(.02)
        watcher=threading.Thread(target=trigger,daemon=True)
        started=time.monotonic()
        with patch.dict(os.environ,{'TEST_CLOSE_STDOUT_THEN_STALL':'1',
                                    'TEST_EOF_MARKER':str(marker)}), \
             patch.object(cold,'OWNER_STOP_PATHS',(stop,)), \
             self.assertRaisesRegex(RuntimeError,'HOLD_OWNER_STOP'):
            watcher.start()
            cold.stream_sha256('fixture:cold/model.gguf',remote.stat().st_size,4)
        watcher.join(timeout=2)
        self.assertTrue(marker.exists())
        self.assertLess(time.monotonic()-started,2.8)

    def test_stream_readback_timeout_after_eof(self):
        remote=Path(os.environ['TEST_REMOTE'])/'cold'/'model.gguf'
        remote.parent.mkdir(parents=True,exist_ok=True)
        remote.write_bytes(self.src.read_bytes())
        started=time.monotonic()
        with patch.dict(os.environ,{'TEST_CLOSE_STDOUT_THEN_STALL':'1'}), \
             self.assertRaisesRegex(RuntimeError,'HOLD_READBACK_TIMEOUT'):
            cold.stream_sha256('fixture:cold/model.gguf',remote.stat().st_size,.35)
        self.assertLess(time.monotonic()-started,2.8)

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
    def test_open_hardlink_alias_blocks_eviction_by_inode(self):
        alias = self.root/'other-name.gguf'
        os.link(self.src, alias)
        proc = self.root/'proc'/'123'
        (proc/'fd').mkdir(parents=True)
        (proc/'fd'/'5').symlink_to(alias)
        (proc/'maps').write_text('')
        with self.assertRaisesRegex(RuntimeError, 'HOLD_MODEL_OPEN_BY_PROCESS'):
            cold.assert_not_open(self.src, self.root/'proc')

    def test_mapped_hardlink_alias_blocks_eviction_by_inode(self):
        alias = self.root/'mapped-alias.gguf'
        os.link(self.src, alias)
        info = self.src.stat()
        proc = self.root/'proc'/'123'
        (proc/'fd').mkdir(parents=True)
        (proc/'maps').write_text('0000-1000 r--p 00000000 %02x:%02x %d %s\\n' %
             (os.major(info.st_dev), os.minor(info.st_dev), info.st_ino, alias))
        with self.assertRaisesRegex(RuntimeError, 'HOLD_MODEL_MEMORY_MAPPED'):
            cold.assert_not_open(self.src, self.root/'proc')

    def test_late_process_open_blocks_eviction_on_second_scan(self):
        row=cold.copy_verified(self.job)
        with patch.object(cold,'independent_restore',return_value=True), patch.object(
                cold,'assert_not_open',side_effect=[
                    None, RuntimeError('HOLD_MODEL_OPEN_BY_PROCESS')]) as scan:
            with self.assertRaisesRegex(RuntimeError,'HOLD_MODEL_OPEN_BY_PROCESS'):
                cold.evict_verified(row,self.manifest(),str(self.root/'separate-mount'))
        self.assertEqual(scan.call_count,2)
        self.assertTrue(self.src.exists())
        self.assertFalse(row['source_deleted'])

    def test_successful_fixture_eviction_requires_two_open_scans(self):
        row=cold.copy_verified(self.job)
        with patch.object(cold,'independent_restore',return_value=True), patch.object(
                cold,'assert_not_open') as scan:
            result=cold.evict_verified(row,self.manifest(),str(self.root/'separate-mount'))
        self.assertEqual(scan.call_count,2)
        self.assertTrue(result['source_deleted'])
        self.assertFalse(self.src.exists())

    def test_verified_fixture_eviction_record(self):
        row=cold.copy_verified(self.job)
        with patch.object(cold,'assert_not_open'), patch.object(cold,'independent_restore',return_value=True):
            result=cold.evict_verified(row,self.manifest(),str(self.root/'separate-mount'))
        self.assertFalse(self.src.exists());self.assertTrue(result['source_deleted'])
        self.assertEqual(result['source_logical_bytes_removed'],row['size'])

    def test_owner_stop_blocks_eviction_before_restore(self):
        row=cold.copy_verified(self.job)
        stop=self.root/'STOP.flag';stop.touch()
        with patch.object(cold,'OWNER_STOP_PATHS',(stop,)),patch.object(
                cold,'independent_restore') as restore,self.assertRaisesRegex(
                RuntimeError,'HOLD_OWNER_STOP'):
            cold.evict_verified(row,self.manifest(),str(self.root/'separate-mount'))
        restore.assert_not_called()
        self.assertTrue(self.src.exists())

    def test_owner_stop_during_restore_blocks_unlink(self):
        row=cold.copy_verified(self.job)
        stop=self.root/'STOP.flag'
        def restore_then_stop(*args,**kwargs):
            stop.touch()
            return True
        with patch.object(cold,'OWNER_STOP_PATHS',(stop,)),patch.object(
                cold,'independent_restore',side_effect=restore_then_stop),patch.object(
                cold,'assert_not_open'),self.assertRaisesRegex(RuntimeError,'HOLD_OWNER_STOP'):
            cold.evict_verified(row,self.manifest(),str(self.root/'separate-mount'))
        self.assertTrue(self.src.exists())

    def test_owner_stop_before_unlink_blocks_eviction(self):
        row=cold.copy_verified(self.job)
        stop=self.root/'STOP.flag'
        original=cold.fresh_manifest
        visits=[0]
        def checked_manifest(*args,**kwargs):
            visits[0]+=1
            result=original(*args,**kwargs)
            if visits[0]==2:
                stop.touch()
            return result
        with patch.object(cold,'OWNER_STOP_PATHS',(stop,)),patch.object(
                cold,'independent_restore',return_value=True),patch.object(
                cold,'assert_not_open'),patch.object(
                cold,'fresh_manifest',side_effect=checked_manifest),self.assertRaisesRegex(
                RuntimeError,'HOLD_OWNER_STOP'):
            cold.evict_verified(row,self.manifest(),str(self.root/'separate-mount'))
        self.assertTrue(self.src.exists())

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

    def test_verified_range_stop_after_eof_before_child_exit(self):
        self.stage_range()
        body=self.src.read_bytes()
        marker=self.root/'cat-stdout-closed'
        started=time.monotonic()
        with patch.dict(os.environ, {
            'TEST_CLOSE_STDOUT_THEN_STALL':'1',
            'TEST_EOF_MARKER':str(marker),
        }), self.assertRaisesRegex(RuntimeError,'HOLD_OWNER_STOP'):
            cold.read_verified_range('fixture:cold/model.gguf',0,100,len(body),
                hashlib.sha256(body[:100]).hexdigest(),timeout=4,
                stop_probe=lambda:marker.exists())
        self.assertTrue(marker.exists())
        self.assertLess(time.monotonic()-started,2.5)
        self.assertTrue(self.src.exists())

    def test_verified_range_timeout_after_eof_before_child_exit(self):
        self.stage_range()
        body=self.src.read_bytes()
        started=time.monotonic()
        with patch.dict(os.environ, {'TEST_CLOSE_STDOUT_THEN_STALL':'1'}), \
             self.assertRaisesRegex(RuntimeError,'HOLD_RANGE_TIMEOUT'):
            cold.read_verified_range('fixture:cold/model.gguf',0,100,len(body),
                hashlib.sha256(body[:100]).hexdigest(),timeout=.35,
                stop_probe=lambda:False)
        self.assertLess(time.monotonic()-started,2.5)
        self.assertTrue(self.src.exists())

    def test_verified_range_default_stop_checks_all_native_aliases_before_network(self):
        self.stage_range()
        body = self.src.read_bytes()
        aliases = tuple(self.root / ('owner-stop-' + str(i)) for i in range(8))
        self.assertEqual(len(cold.OWNER_STOP_PATHS), 8)
        with patch.object(cold, 'OWNER_STOP_PATHS', aliases):
            for alias in aliases:
                with self.subTest(alias=alias.name):
                    alias.touch()
                    try:
                        with patch.object(cold, '_range_size_with_stop') as size_call, \
                             self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER_STOP'):
                            cold.read_verified_range(
                                'fixture:cold/model.gguf', 0, 100, len(body),
                                hashlib.sha256(body[:100]).hexdigest(), timeout=3)
                        size_call.assert_not_called()
                    finally:
                        alias.unlink()

    def test_verified_range_default_stop_detects_dangling_symlink(self):
        self.stage_range()
        body = self.src.read_bytes()
        stop = self.root / 'dangling-owner-stop'
        stop.symlink_to(self.root / 'nonexistent-target')
        self.assertFalse(stop.exists())
        self.assertTrue(stop.is_symlink())
        with patch.object(cold, 'OWNER_STOP_PATHS', (stop,)), \
             patch.object(cold, '_range_size_with_stop') as size_call, \
             self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER_STOP'):
            cold.read_verified_range(
                'fixture:cold/model.gguf', 0, 100, len(body),
                hashlib.sha256(body[:100]).hexdigest(), timeout=3)
        size_call.assert_not_called()

    def test_verified_range_default_stop_rechecked_after_metadata(self):
        self.stage_range()
        body = self.src.read_bytes()
        stop = self.root / 'late-owner-stop'
        def metadata(remote, deadline, probe):
            stop.touch()
            return {'count': 1, 'bytes': len(body)}
        with patch.object(cold, 'OWNER_STOP_PATHS', (stop,)), \
             patch.object(cold, '_range_size_with_stop', side_effect=metadata), \
             patch.object(cold.subprocess, 'Popen') as popen, \
             self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER_STOP'):
            cold.read_verified_range(
                'fixture:cold/model.gguf', 0, 100, len(body),
                hashlib.sha256(body[:100]).hexdigest(), timeout=3)
        popen.assert_not_called()

    def test_verified_range_object_size_changed(self):
        self.stage_range()
        body=self.src.read_bytes()
        with self.assertRaisesRegex(RuntimeError,'HOLD_RANGE_OBJECT_SIZE_CHANGED'):
            cold.read_verified_range('fixture:cold/model.gguf',0,100,len(body)+1,
                hashlib.sha256(body[:100]).hexdigest(),stop_probe=lambda:False)



class ColdOwnerMaintenanceGateRegressions(unittest.TestCase):
    def test_unreadable_owner_control_holds_before_rclone(self):
        with patch.object(cold, 'OWNER_STOP_PATHS', (Path('/invalid/STOP'),)), \
             patch.object(cold.os, 'lstat', side_effect=PermissionError(13, 'denied')), \
             patch.object(cold.subprocess, 'Popen') as spawn, \
             self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER_STOP_UNREADABLE'):
            cold.command(['rclone', 'size', 'fixture:models'], timeout=2)
        spawn.assert_not_called()

    def test_custom_range_probe_cannot_bypass_owner_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            stop = Path(tmp) / 'STOP'
            stop.touch()
            with patch.object(cold, 'OWNER_STOP_PATHS', (stop,)), \
                 patch.object(cold, '_range_size_with_stop') as metadata, \
                 self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER_STOP'):
                cold.read_verified_range('fixture:cold/model.gguf', 0, 1, 1,
                                         '0'*64, stop_probe=lambda: False)
            metadata.assert_not_called()

    def test_range_owner_model_update_blocks_before_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            flag = Path(tmp) / 'OWNER_MAINTENANCE.flag'
            flag.touch()
            with patch.object(cold, 'OWNER_STOP_PATHS', ()), \
                 patch.object(cold, 'OWNER_MODEL_UPDATE_FLAG', flag), \
                 patch.object(cold, '_range_size_with_stop') as metadata, \
                 self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER_STOP'):
                cold.read_verified_range('fixture:cold/model.gguf', 0, 1, 1,
                                         '0'*64, stop_probe=lambda: False)
            metadata.assert_not_called()

    def test_readonly_storage_audit_refuses_unreadable_owner_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(cold, 'OWNER_STOP_PATHS', (Path('/invalid/STOP'),)), \
                 patch.object(cold.os, 'lstat', side_effect=OSError(40, 'too many links')), \
                 self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER_STOP_UNREADABLE'):
                cold.deepseek_storage_admission({}, tmp)

    def test_owner_model_update_regular_flag_blocks_rclone_before_spawn(self):
        with tempfile.TemporaryDirectory() as tmp:
            flag = Path(tmp) / 'OWNER_MAINTENANCE.flag'
            flag.touch()
            with patch.object(cold, 'OWNER_STOP_PATHS', ()), \
                 patch.object(cold, 'OWNER_MODEL_UPDATE_FLAG', flag), \
                 patch.object(cold.subprocess, 'Popen') as spawn, \
                 self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER_MODEL_UPDATE'):
                cold.command(['rclone', 'lsf', 'fixture:models'], timeout=2)
            spawn.assert_not_called()

    def test_owner_model_update_dangling_symlink_blocks_eviction_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            flag = Path(tmp) / 'OWNER_MAINTENANCE.flag'
            flag.symlink_to(Path(tmp) / 'not-yet-created')
            with patch.object(cold, 'OWNER_STOP_PATHS', ()), \
                 patch.object(cold, 'OWNER_MODEL_UPDATE_FLAG', flag), \
                 self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER_MODEL_UPDATE'):
                cold.assert_owner_stop_clear()

    def test_no_model_update_flag_does_not_fake_owner_writer_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            flag = Path(tmp) / 'OWNER_MAINTENANCE.flag'
            with patch.object(cold, 'OWNER_STOP_PATHS', ()), \
                 patch.object(cold, 'OWNER_MODEL_UPDATE_FLAG', flag):
                cold.assert_owner_stop_clear()
            # Source gate clearance is never evidence of native owner lease.
            self.assertFalse(flag.exists())


class DeepSeekStorageAdmissionRegressions(unittest.TestCase):
    def manifest(self):
        return {'repository':"ISTA-DASLab/DeepSeek-V4.1-Flash-1017-GSQ-RCO-GGUF",
                'revision':cold.DEEPSEEK_REVISION,'quantization':'GSQ-RCO-IQ2_XXS',
                'total_unique_gguf_bytes':cold.DEEPSEEK_TOTAL_BYTES,
                'files':[{'path':k,'bytes':v[0],'sha256':v[1]} for k,v in cold.DEEPSEEK_PINS.items()],
                'alias':{'path':cold.DEEPSEEK_ALIAS,'target':cold.DEEPSEEK_ENGRAM,'duplicate_bytes':False}}

    def test_immutable_unique_six_file_capacity_and_zero_native_claim(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(cold,'OWNER_STOP_PATHS',()):
            result=cold.deepseek_storage_admission(self.manifest(),tmp)
        self.assertEqual(result['unique_bytes'],248834257920)
        self.assertEqual(result['unverified_bytes'],248834257920)
        self.assertEqual(result['sha256_verified_bytes'],0)
        self.assertEqual(result['downloads_started'],0)
        self.assertFalse(result['owner_native_lease_verified'])

    def test_metadata_presence_only_is_not_verified_weights(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(cold,'OWNER_STOP_PATHS',()):
            name=next(iter(cold.DEEPSEEK_PINS))
            (Path(tmp)/name).write_bytes(b'x'*5780704)
            result=cold.deepseek_storage_admission(self.manifest(),tmp)
        self.assertEqual(result['files'][name],'SIZE_ONLY_SHA_UNVERIFIED')
        self.assertEqual(result['unverified_bytes'],248834257920)

    def test_bad_hash_duplicate_and_alias_are_rejected(self):
        m=self.manifest();m['files'][0]['sha256']='0'*64
        with tempfile.TemporaryDirectory() as tmp,patch.object(cold,'OWNER_STOP_PATHS',()),self.assertRaisesRegex(ValueError,'HOLD_DEEPSEEK_FILE_PIN'):
            cold.deepseek_storage_admission(m,tmp)
        m=self.manifest();m['files'][1]=dict(m['files'][0])
        with tempfile.TemporaryDirectory() as tmp,patch.object(cold,'OWNER_STOP_PATHS',()),self.assertRaisesRegex(ValueError,'HOLD_DEEPSEEK_FILE_PIN'):
            cold.deepseek_storage_admission(m,tmp)
        m=self.manifest();m['alias']['duplicate_bytes']=True
        with tempfile.TemporaryDirectory() as tmp,patch.object(cold,'OWNER_STOP_PATHS',()),self.assertRaisesRegex(ValueError,'HOLD_DEEPSEEK_ENGRAM_ALIAS'):
            cold.deepseek_storage_admission(m,tmp)

    def test_owner_stop_readonly_metadata_not_full_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            stop=Path(tmp)/'STOP';stop.touch()
            with patch.object(cold,'OWNER_STOP_PATHS',(stop,)), patch.object(cold,'sha256') as digest:
                result=cold.deepseek_storage_admission(self.manifest(),tmp)
                self.assertTrue(result['owner_stop_observed'])
                self.assertTrue(result['inspection_only_under_stop'])
                self.assertEqual(result['sha256_verified_bytes'],0)
                self.assertEqual(result['downloads_started'],0)
                self.assertFalse(result['owner_native_lease_verified'])
                digest.assert_not_called()
                with self.assertRaisesRegex(RuntimeError,'HOLD_OWNER_STOP_FULL_SCAN'):
                    cold.deepseek_storage_admission(self.manifest(),tmp,verify_full=True)
                digest.assert_not_called()
            with patch.object(cold,'OWNER_STOP_PATHS',()),self.assertRaisesRegex(ValueError,'HOLD_DEEPSEEK_MANIFEST_OR_RESERVE'):
                cold.deepseek_storage_admission(self.manifest(),tmp,reserve_bytes=1)

    def test_owner_model_update_maintenance_does_not_authorize_full_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            maintenance=Path(tmp)/'OWNER_MAINTENANCE.flag';maintenance.touch()
            with patch.object(cold,'OWNER_STOP_PATHS',()), patch.object(cold,'OWNER_MODEL_UPDATE_FLAG',maintenance), patch.object(cold,'sha256') as digest:
                result=cold.deepseek_storage_admission(self.manifest(),tmp)
                self.assertTrue(result['owner_maintenance_flag_observed'])
                self.assertTrue(result['inspection_only_under_stop'])
                self.assertFalse(result['native_model_installed'])
                with self.assertRaisesRegex(RuntimeError,'HOLD_OWNER_STOP_FULL_SCAN'):
                    cold.deepseek_storage_admission(self.manifest(),tmp,verify_full=True)
                digest.assert_not_called()



    def test_disk_free_cannot_authorize_unverified_owner_quota(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(cold, 'OWNER_STOP_PATHS', ()), \
             patch.object(cold.shutil, 'disk_usage',
                          return_value=SimpleNamespace(free=500*cold.GIB)):
            result = cold.deepseek_storage_admission(self.manifest(), tmp)
        self.assertTrue(result['filesystem_capacity_candidate'])
        self.assertFalse(result['capacity_admitted'])
        self.assertEqual(result['owner_quota_free_bytes'], None)
        self.assertEqual(result['quota_status'],
                         'UNKNOWN_OWNER_NATIVE_QUOTA_READBACK_REQUIRED')
        self.assertEqual(result['state'], 'HOLD_STORAGE_AUTH_OR_SEEKABLE_PLACEMENT')
        self.assertEqual(result['downloads_started'], 0)

    def test_readonly_mount_rejects_capacity_even_if_disk_usage_reports_free(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(cold, 'OWNER_STOP_PATHS', ()), \
             patch.object(cold.os, 'statvfs',
                          return_value=SimpleNamespace(f_flag=getattr(os, 'ST_RDONLY', 1))), \
             patch.object(cold.shutil, 'disk_usage',
                          return_value=SimpleNamespace(free=500*cold.GIB)):
            result = cold.deepseek_storage_admission(self.manifest(), tmp)
        self.assertTrue(result['filesystem_readonly'])
        self.assertFalse(result['filesystem_capacity_candidate'])
        self.assertFalse(result['capacity_admitted'])
        self.assertEqual(result['state'], 'HOLD_STORAGE_AUTH_OR_SEEKABLE_PLACEMENT')


if __name__=='__main__':unittest.main(verbosity=2)
