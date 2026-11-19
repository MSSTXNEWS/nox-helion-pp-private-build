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
        return f"{pid} ({comm}) S " + " ".join(['0']*18+[str(ticks)]) + "\n"

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
            (p/'cmdline').write_bytes(b'/usr/bin/python3\0/root/nox/worker.py\0')
            (p/'comm').write_text('nox-worker\n')
            rows=audit.process_rows(proc_root=Path(temp))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['pid'],123)
            self.assertEqual(rows[0]['start_ticks'],123456)
            self.assertNotIn('stat',rows[0])
            self.assertNotIn('raw_stat',rows[0])

class V13WheelhouseAdmissionTests(unittest.TestCase):
    def test_live_python312_cu124_never_accepts_cp311_wheels(self):
        got = audit.v13_wheelhouse_admission({
            '_runtime': {'python_abi': 'cpython-312', 'platform': 'linux-x86_64'},
            'torch': '2.6.0+cu124'})
        self.assertEqual(got, 'HOLD_WHEELHOUSE_CP311_PYTHON_ABI_MISMATCH')

    def test_python311_but_cuda124_still_blocks(self):
        got = audit.v13_wheelhouse_admission({
            '_runtime': {'python_abi': 'cpython-311', 'platform': 'linux-x86_64', 'python_version': '3.11.10'},
            'torch': '2.6.0+cu124'})
        self.assertEqual(got, 'HOLD_WHEELHOUSE_CU126_TORCH_BUILD_MISMATCH')

    def test_unknown_runtime_or_torch_cannot_be_reported_installed(self):
        self.assertEqual(audit.v13_wheelhouse_admission({}),
                         'HOLD_WHEELHOUSE_RUNTIME_ABI_UNKNOWN')
        self.assertEqual(audit.v13_wheelhouse_admission({
            '_runtime': {'python_abi': 'cpython-311', 'platform': 'linux-x86_64', 'python_version': '3.11.10'},
            'torch': None}), 'HOLD_WHEELHOUSE_TORCH_BUILD_UNKNOWN')

    def test_matching_metadata_still_requires_native_sm70_smoke(self):
        got = audit.v13_wheelhouse_admission({
            '_runtime': {'python_abi': 'cpython-311', 'platform': 'linux-x86_64', 'python_version': '3.11.10'},
            'torch': '2.9.0+cu126'})
        self.assertEqual(got, 'SOURCE_ONLY_WHEELHOUSE_ABI_CANDIDATE_NATIVE_SM70_HOLD')
        self.assertNotIn('INSTALLED', got)

    def test_cp311_cache_tag_cannot_hide_different_or_missing_interpreter_version(self):
        for observed in ('3.12.4', '3.11', '3.11.9+unexpected', None, 311):
            with self.subTest(observed=observed):
                got = audit.v13_wheelhouse_admission({
                    '_runtime': {'python_abi': 'cpython-311',
                                 'python_version': observed, 'platform': 'linux-x86_64'},
                    'torch': '2.9.0+cu126'})
                self.assertEqual(got, 'HOLD_WHEELHOUSE_CP311_VERSION_MISMATCH')

    def test_cu126_suffix_without_valid_torch_release_is_not_admitted(self):
        for label in ('unknown+cu126', '2.9+cu126', '2.9.0+cu126+fake',
                      '2.9.0+cu126\\n', '2.9.0+cu124'):
            with self.subTest(label=label):
                got = audit.v13_wheelhouse_admission({
                    '_runtime': {'python_abi': 'cpython-311',
                                 'python_version': '3.11.10',
                                 'platform': 'linux-x86_64'},
                    'torch': label})
                self.assertEqual(got, 'HOLD_WHEELHOUSE_CU126_TORCH_BUILD_MISMATCH')

    def test_native_inventory_includes_original_volta_python(self):
        import inspect
        source = inspect.getsource(audit.packages)
        self.assertIn('/root/venv_volta/bin/python', source)
        self.assertIn('sys.implementation.cache_tag', source)
        self.assertIn('_wheelhouse_candidate', source)


from test_owner_native_audit_pinned_v10 import PinnedModelInventoryAdmissionTest

if __name__=='__main__':
    unittest.main()
