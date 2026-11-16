import importlib.util
import tempfile
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
AUDIT_PATH=HERE/'owner_native_audit.py'
spec=importlib.util.spec_from_file_location('owner_native_audit_model_paths',AUDIT_PATH)
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

PIN_PATH=HERE.parent/'nox_runpod'/'teacher_mesh'/'v51'/'hf_range_probe.py'
pinspec=importlib.util.spec_from_file_location('hf_range_probe_model_paths',PIN_PATH)
pinmod=importlib.util.module_from_spec(pinspec)
pinspec.loader.exec_module(pinmod)

class PinnedModelPathTests(unittest.TestCase):
    def test_exact_six_rows_match_immutable_hf_manifest(self):
        expected=tuple((x['path'].rsplit('/',1)[-1],x['bytes'],x['sha256']) for x in pinmod.PINNED_SOURCES)
        self.assertEqual(audit.PINNED_MODEL_FILES,expected)
        self.assertEqual(audit.MODEL_ROOT,'/root/nox/models')
        self.assertEqual(audit.pinned_model_paths()['manifest_revision'],'65d53bc8be65123e255ff02f3ded958b6dbf54fd')

    def test_reports_exact_targets_without_hashing(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            name,size,_=audit.PINNED_MODEL_FILES[0]
            (root/name).write_bytes(b'123')
            result=audit.pinned_model_paths(root=str(root))
            self.assertEqual(result['status'],'HOLD_MODEL_FILE_SIZE_MISMATCH')
            self.assertEqual(len(result['files']),6)
            first=result['files'][0]
            self.assertEqual(first['path'],str(root/name))
            self.assertTrue(first['exists'])
            self.assertEqual(first['type'],'regular')
            self.assertEqual(first['bytes'],3)
            self.assertEqual(first['expected_bytes'],size)
            self.assertEqual(first['size_status'],'MISMATCH')
            self.assertEqual(first['sha_status'],'NOT_CHECKED')
            self.assertEqual(result['files'][1]['type'],'missing')
            self.assertFalse(result['files'][1]['exists'])
            self.assertIsNone(result['files'][1]['bytes'])

    def test_final_symlink_is_never_followed(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as other:
            root=Path(temp)
            name,_,_=audit.PINNED_MODEL_FILES[0]
            target=Path(other)/'target.gguf'
            target.write_bytes(b'payload')
            (root/name).symlink_to(target)
            result=audit.pinned_model_paths(root=str(root))
            first=result['files'][0]
            self.assertEqual(result['status'],'HOLD_MODEL_PATH_SYMLINK')
            self.assertFalse(first['exists'])
            self.assertEqual(first['type'],'symlink')
            self.assertIsNone(first['bytes'])
            self.assertEqual(first['sha_status'],'NOT_CHECKED')

    def test_symlinked_root_ancestor_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as other:
            root=Path(temp)/'models'
            root.symlink_to(other,target_is_directory=True)
            result=audit.pinned_model_paths(root=str(root))
            self.assertEqual(result['status'],'HOLD_MODEL_PATH_SYMLINK')
            self.assertEqual(len(result['files']),6)
            self.assertTrue(all(x['type']=='blocked' and x['exists'] is None for x in result['files']))
            self.assertTrue(all(x['sha_status']=='NOT_CHECKED' for x in result['files']))

    def test_non_absolute_root_fails_closed(self):
        result=audit.pinned_model_paths(root='models')
        self.assertEqual(result['status'],'HOLD_MODEL_ROOT_NOT_ABSOLUTE')
        self.assertEqual(result['files'],[])

    def test_audit_model_section_only_runs_exact_stat_probe(self):
        result=audit.models()
        self.assertEqual(set(result),{'pinned_model_paths'})
        self.assertEqual(audit.models.__code__.co_names,('pinned_model_paths',))

class ProcessIdentityTests(unittest.TestCase):
    @staticmethod
    def stat_row(pid, ticks, comm='nox worker) main'):
        # stat field 22 is index 19 after the final ') ' separator.
        return f"{pid} ({comm}) S " + " ".join(['0']*18+[str(ticks)]) + "\\n"

    def test_start_ticks_parses_parentheses_and_spaces_in_comm(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            (p/'stat').write_text(self.stat_row(123,98765))
            self.assertEqual(audit.proc_start_ticks(p,123),98765)

    def test_process_identity_rejects_wrong_pid_and_bad_stat(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            (p/'stat').write_text(self.stat_row(234,98765))
            with self.assertRaises(ValueError):audit.proc_start_ticks(p,123)
            (p/'stat').write_text("123 (nox) S 1 2")
            with self.assertRaises(ValueError):audit.proc_start_ticks(p,123)

    def test_proc_inventory_emits_stable_start_ticks_without_raw_stat(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'123';p.mkdir()
            (p/'stat').write_text(self.stat_row(123,123456))
            (p/'cmdline').write_bytes(b'/usr/bin/python3\\0/root/nox/worker.py\\0')
            (p/'comm').write_text('nox-worker\\n')
            rows=audit.process_rows(proc_root=Path(temp))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['pid'],123)
            self.assertEqual(rows[0]['start_ticks'],123456)
            self.assertNotIn('stat',rows[0])
            self.assertNotIn('raw_stat',rows[0])

from test_owner_native_audit_pinned_v10 import PinnedModelInventoryAdmissionTest

if __name__=='__main__':
    unittest.main()
