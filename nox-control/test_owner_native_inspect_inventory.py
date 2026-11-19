#!/usr/bin/env python3
"""Regression: original OneHost knowledge.sqlite is not an empty S03.

Only local temporary files and stubbed HTTP are used. No native inference,
S03 text, credentials or training resources are accessed.
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

MODULE_PATH = Path(__file__).with_name('owner_native_inspect.py')
spec = importlib.util.spec_from_file_location('nox_owner_inspect', MODULE_PATH)
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)


class FakeResponse:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, limit=None): return b'[]'


class MemoryInventoryTests(unittest.TestCase):
    def test_canonical_knowledge_sqlite_is_visible_without_reading_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            db=root/'kb'/'knowledge.sqlite'
            db.parent.mkdir()
            db.write_bytes(b'not-real-s03-content')
            rows=inspector.memory_metadata_inventory((root/'memory',root/'kb'))
            self.assertEqual([x['path'] for x in rows],[str(db)])
            self.assertEqual(rows[0]['bytes'],len(b'not-real-s03-content'))
            self.assertNotIn('text',rows[0])
            self.assertNotIn('S03',str(rows))

    def test_all_three_extensions_and_hardlink_are_deduplicated(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('a.db','b.sqlite','c.sqlite3'):
                (root/name).write_bytes(name.encode())
            (root/'c_alias.sqlite').hardlink_to(root/'c.sqlite3')
            rows=inspector.memory_metadata_inventory((root,))
            self.assertEqual(len(rows),3)
            self.assertEqual(set(Path(r['path']).suffix for r in rows),{'.db','.sqlite','.sqlite3'})

    def test_symlinks_not_followed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); target=root/'knowledge.sqlite';target.write_bytes(b'x')
            symlink=root/'symlink.db';symlink.symlink_to(target)
            rows=inspector.memory_metadata_inventory((root,))
            self.assertEqual([r['path'] for r in rows],[str(target)])
            outside=root/'outside';outside.mkdir()
            (outside/'private.sqlite').write_bytes(b'y')
            linked=root/'linked';linked.symlink_to(outside,target_is_directory=True)
            self.assertEqual(inspector.memory_metadata_inventory((linked,)),[])

    def test_output_explicitly_reports_recall_unknown_and_slots_not_models(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'kb').mkdir()
            (root/'kb'/'knowledge.sqlite').write_bytes(b'S03 metadata only')
            with mock.patch.object(inspector,'ROOT',root), \
                 mock.patch.object(inspector.shutil,'which',return_value=None), \
                 mock.patch.object(inspector.urllib.request,'urlopen',return_value=FakeResponse()):
                result=inspector.chat_storage()
            self.assertEqual(result['s03_recall_status'],'UNKNOWN_NOT_PROBED')
            self.assertEqual(result['memory_files_scope'],'LOCAL_METADATA_ONLY')
            self.assertEqual(result['model_slots_scope'],'INFERENCE_CONTEXT_SLOTS_NOT_MODEL_INSTANCES')
            self.assertEqual(result['model_slots'],[])
            self.assertEqual(len(result['memory_files']),1)
            self.assertEqual(result['health']['8080']['status'],200)

    def test_process_stat_uses_final_comm_delimiter_for_pid_identity(self):
        # Linux /proc/PID/stat encloses comm in parentheses; comm itself may
        # contain ") ". The first delimiter corrupts start_ticks and ppid.
        with tempfile.TemporaryDirectory() as temp:
            proc = Path(temp)
            worker = proc / '432'
            worker.mkdir()
            (worker / 'cmdline').write_bytes(b'/usr/bin/python3\0nox-worker.py\0')
            (worker / 'stat').write_text(
                '432 (nox) worker) S 1 ' + ' '.join(['0'] * 17 + ['987654']) + '\n')
            (worker / 'environ').write_bytes(b'PROC_NAME=nox-worker\0')
            (worker / 'status').write_text('NSpid:\t432\nVmRSS:\t10 kB\nThreads:\t1\n')
            with mock.patch.object(inspector, 'PROC', proc):
                with mock.patch.object(inspector, 'run', return_value=(0, '')):
                    rows = inspector.processes()
            result = next(x for x in rows if x.get('pid') == 432)
            self.assertEqual(result['state'], 'S')
            self.assertEqual(result['ppid'], 1)
            self.assertEqual(result['starttime'], '987654')
            self.assertEqual(result['namespace_pids'], [432])

    def test_recycled_pid_during_probe_cannot_claim_gpu_vram(self):
        # The nvidia-smi PID predates the slower /proc status/environ sample.
        # A reused PID must remain UNMAPPED rather than crediting a new process.
        with tempfile.TemporaryDirectory() as temp:
            proc = Path(temp)
            worker = proc / '432'
            worker.mkdir()
            (worker / 'cmdline').write_bytes(b'/usr/bin/python3\0nox-worker.py\0')
            (worker / 'stat').write_text(
                '432 (nox-worker) S 1 ' + ' '.join(['0'] * 17 + ['987654']) + '\n')
            (worker / 'environ').write_bytes(b'PROC_NAME=nox-worker\0')
            (worker / 'status').write_text('NSpid:\t432\nVmRSS:\t10 kB\nThreads:\t1\n')
            real_read_text = Path.read_text
            count = [0]

            def raced_read_text(path, *args, **kwargs):
                original = real_read_text(path, *args, **kwargs)
                if path == worker / 'stat':
                    count[0] += 1
                    if count[0] > 1:
                        return original.replace('987654', '987655')
                return original

            def fake_run(args, timeout=12):
                if args[0] == 'nvidia-smi':
                    return (0, '432, GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee, 2048')
                return (0, '')

            with mock.patch.object(inspector, 'PROC', proc), \
                 mock.patch.object(inspector, 'run', side_effect=fake_run), \
                 mock.patch.object(Path, 'read_text', raced_read_text):
                rows = inspector.processes()
            self.assertEqual(count[0], 2)
            self.assertFalse(any(row.get('pid') == 432 for row in rows))
            mapping = next(row for row in rows if row.get('record') == 'gpu_pid_mapping')
            self.assertEqual(mapping['unresolved'][0]['mapping'], 'UNMAPPED')
            self.assertEqual(mapping['unresolved'][0]['reported_pid'], 432)

    def test_qwen_receipt_is_bounded_metadata_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            run=root/'lora'/'qwen35_9b'/'6907283384'
            run.mkdir(parents=True)
            (run/'owner_progress.json').write_text(
                '{"state":"LOADING","global_step":0,"optimizer_steps_verified":false,'
                '"training_private_corpus":"DO_NOT_EXPORT_THIS_TEXT"}')
            with mock.patch.object(inspector,'ROOT',root):
                rows=inspector.qwen_training_readback()
            self.assertEqual(len(rows),3)
            progress=next(x for x in rows if x.get('receipt')=='owner_progress.json')
            self.assertEqual(progress['fields']['global_step'],0)
            self.assertIs(progress['fields']['optimizer_steps_verified'],False)
            self.assertNotIn('training_private_corpus',str(rows))
            self.assertEqual(len([x for x in rows if x['state']=='NOT_OBSERVED']),2)

    def test_qwen_missing_run_does_not_claim_zero_optimizer_steps(self):
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(inspector,'ROOT',Path(temp)):
                rows=inspector.qwen_training_readback()
            self.assertEqual(rows[0]['state'],'RUN_DIRECTORY_NOT_OBSERVED')
            self.assertNotIn('global_step',str(rows))


if __name__=='__main__':
    unittest.main()
