"""Read-only API safety regressions; synthetic fixtures, no host/model access."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('inspector_compat_privacy', Path(__file__).with_name('owner_native_inspect.py'))
INSPECT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSPECT)


class CompatPrivacyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'nox'
        self.root.mkdir()
        scope = patch.object(INSPECT, 'ROOT', self.root)
        scope.start()
        self.addCleanup(scope.stop)
        self.private = 'ghp_' + 'SYNTHETICSECRET' * 2

    def test_qwen_codes_are_recognized_values_not_lexical_secrets(self):
        result = INSPECT.safe_qwen_receipt_fields({'schema': self.private, 'state': 'PASS',
            'error': self.private, 'reason': 'OwnerPrivatePhrase', 'status': 'HOLD_BACKUP'})
        self.assertEqual(result, {'state': 'PASS', 'status': 'HOLD_BACKUP'})

    def test_queue_result_code_cannot_publish_token_or_private_text(self):
        for value in (self.private, 'OwnerPrivatePhrase'):
            result = INSPECT.safe_owner_task({'id': 'owner.review.fixture',
                'status': 'done', 'result_state': value})
            self.assertNotIn('result_state', result)
            self.assertEqual(result['status'], 'done')

    def test_receipt_codes_cannot_publish_token_or_private_text(self):
        path = self.root / 'receipt.json'
        path.write_text(json.dumps({'schema': 'NOX_SAFE', 'state': 'PASS',
            'status': self.private, 'kind': 'OwnerPrivatePhrase', 'result_state': self.private}))
        result = INSPECT.bounded_receipt_meta(path)
        self.assertEqual(result['fields'], {'schema': 'NOX_SAFE', 'state': 'PASS'})

    def test_huge_and_nonfinite_numeric_metrics_are_omitted_without_crash(self):
        for value in (10**400, -10**400, float('nan'), float('inf'), True):
            with self.subTest(kind=type(value).__name__):
                self.assertEqual(INSPECT.safe_qwen_receipt_fields(
                    {'loss': value, 'finished_at': value, 'updated_at': value}), {})

    def test_receipt_counter_boolean_is_not_an_optimizer_step(self):
        path = self.root / 'receipt.json'
        path.write_text(json.dumps({'successful_optimizer_steps': True, 'training_started': True}))
        self.assertEqual(INSPECT.bounded_receipt_meta(path)['fields'], {'training_started': True})

    def test_receipt_exponent_overflow_fails_closed(self):
        path = self.root / 'receipt.json'
        path.write_text('{"state":"PASS","metric":1e999}')
        self.assertEqual(INSPECT.bounded_receipt_meta(path)['state'], 'HOLD_INVALID_JSON')

    def test_receipt_parent_symlink_never_reads_public_looking_private_data(self):
        outside = self.root.parent / 'outside'
        outside.mkdir()
        (outside / 'receipt.json').write_text('{"state":"PASS"}')
        (self.root / 'linked').symlink_to(outside, target_is_directory=True)
        result = INSPECT.bounded_receipt_meta(self.root / 'linked/receipt.json')
        self.assertNotIn('fields', result)
        self.assertNotEqual(result['state'], 'READ_ONLY_METADATA')

    def test_qwen_lora_symlink_is_not_an_approved_run_directory(self):
        outside = self.root.parent / 'private_lora'
        run = outside / 'qwen35_9b/20261118_01'
        run.mkdir(parents=True)
        (run / 'owner_progress.json').write_text('{"state":"RUNNING","successful_updates":9}')
        (self.root / 'lora').symlink_to(outside, target_is_directory=True)
        result = INSPECT.qwen_training_readback()
        self.assertFalse(any('fields' in row for row in result))
        self.assertNotIn('successful_updates', str(result))

    def test_queue_parent_symlink_cannot_publish_task_status(self):
        outside = self.root.parent / 'private_state'
        (outside / 'dispatcher').mkdir(parents=True)
        (outside / 'dispatcher/state.json').write_text(json.dumps({'tasks': {
            'owner.private': {'id': 'owner.private', 'status': 'done'}}}))
        (self.root / 'state').symlink_to(outside, target_is_directory=True)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            INSPECT.owner_component_readback()
        result = json.loads(output.getvalue().split('=', 1)[1])
        self.assertEqual(result['tasks'], [])
        self.assertNotEqual(result['queue_scope'], 'OWNER_TASK_STATUS_ONLY_NO_RESULTS')

    def slots(self, payload):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, count): return json.dumps(payload).encode()[:count]
        with patch.object(INSPECT.urllib.request, 'urlopen', return_value=Response()), \
             patch.object(INSPECT.shutil, 'which', return_value=None):
            return INSPECT.chat_storage()

    def test_slot_projection_rejects_nested_private_state_and_context(self):
        result = self.slots([{'id': 1, 'state': {'private_result': 'PRIVATE_SLOT_PAYLOAD'},
                              'n_ctx': ['PRIVATE_SLOT_CONTEXT'], 'is_processing': False}])
        self.assertEqual(result['model_slots'], [{'id': 1, 'is_processing': False}])
        self.assertNotIn('PRIVATE_SLOT', json.dumps(result))

    def test_slot_projection_checks_numeric_bounds_and_exact_boolean_type(self):
        result = self.slots([{'id': True, 'n_ctx': 10**20, 'state': self.private, 'is_processing': 1},
                            {'id': 2, 'n_ctx': 4096, 'state': 'idle', 'is_processing': False}])
        self.assertEqual(result['model_slots'], [{}, {'id': 2, 'n_ctx': 4096, 'state': 'idle', 'is_processing': False}])

    def test_controls_withholds_innocuously_named_private_configuration(self):
        pool = self.root / 'config/dispatcher_agents_t868u.json'
        pool.parent.mkdir()
        pool.write_text(json.dumps({'workers': [{'name': 'nox_worker',
            'system_prompt': 'PRIVATE_S03_CONVERSATION', 'credentials': 'PRIVATE_OPAQUE_VALUE'}]}))
        with patch.object(INSPECT, 'supervisor_config', return_value=[]), \
             patch.object(INSPECT, 'installed_package_versions_readback', return_value={}), \
             patch.object(INSPECT, 'pinned_sftconfig_signature_probe', return_value={}):
            result = INSPECT.controls()
        self.assertNotIn('PRIVATE_', json.dumps(result))
        row = next(row for row in result if row.get('record') == 'dispatcher_workers')
        self.assertTrue(row['configuration_withheld'])
        self.assertEqual(row['bytes'], pool.stat().st_size)
        self.assertEqual(len(row['sha256']), 64)

    def test_controls_does_not_export_source_literals_or_follow_parent_symlinks(self):
        scripts = self.root.parent / 'private_scripts'
        scripts.mkdir()
        (scripts / 'chat_proxy.py').write_text("prompt = 'PRIVATE_SOURCE_LITERAL'\n")
        (self.root / 'scripts').symlink_to(scripts, target_is_directory=True)
        with patch.object(INSPECT, 'supervisor_config', return_value=[]), \
             patch.object(INSPECT, 'installed_package_versions_readback', return_value={}), \
             patch.object(INSPECT, 'pinned_sftconfig_signature_probe', return_value={}):
            result = INSPECT.controls()
        self.assertNotIn('PRIVATE_SOURCE_LITERAL', json.dumps(result))
        row = next(row for row in result if row.get('path') == str(self.root / 'scripts/chat_proxy.py'))
        self.assertNotIn('sha256', row)

    def test_hf_metadata_never_follows_a_symlinked_model_directory(self):
        target = self.root.parent / 'private_model'
        target.mkdir()
        for name in ('tokenizer.json','tokenizer_config.json'):
            (target / name).write_text('{}')
        header = json.dumps({'a': {'dtype':'F16','shape':[1],'data_offsets':[0,2]}}).encode()
        name = 'model-00001-of-00001.safetensors'
        (target / name).write_bytes(len(header).to_bytes(8,'little') + header + b'\0\0')
        (target / 'model.safetensors.index.json').write_text(json.dumps({'weight_map': {'a':name}}))
        model = self.root / 'model'
        model.symlink_to(target, target_is_directory=True)
        result = INSPECT.hf_metadata_probe(model)
        self.assertTrue(result['status'].startswith('HOLD_'))
        self.assertFalse(result['weight_payload_sha256_verified'])
        self.assertNotIn('tensor_count', result)

    def test_pinned_metadata_children_disable_bytecode_before_third_party_imports(self):
        for method in (INSPECT.installed_package_versions_readback, INSPECT.pinned_sftconfig_signature_probe):
            with self.subTest(method=method.__name__), \
                 patch.object(INSPECT, 'pinned_python_path_status', return_value='PINNED_NATIVE_PYTHON_TRUSTED'), \
                 patch.object(INSPECT, 'run', return_value=(1, '')) as run:
                method(Path('/root/venv_volta/bin/python'))
            argv = run.call_args.args[0]
            self.assertEqual(argv[:3], ['/root/venv_volta/bin/python','-I','-c'])
            self.assertIn('sys.dont_write_bytecode = True', argv[3])
            self.assertLess(argv[3].index('sys.dont_write_bytecode = True'), argv[3].index('importlib.metadata'))


class ProcessIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'nox'
        self.root.mkdir()
        self.proc = Path(temporary.name) / 'proc'
        (self.proc / 'net').mkdir(parents=True)
        for name in ('tcp', 'tcp6'):
            (self.proc / 'net' / name).write_text('sl local_address rem_address st tx rx tr tm retrnsmt inode\n')
        for name, value in (('ROOT', self.root), ('PROC', self.proc)):
            scope = patch.object(INSPECT, name, value)
            scope.start(); self.addCleanup(scope.stop)
        self.process = self.proc / '432'
        (self.process / 'fd').mkdir(parents=True)
        self.set_ticks(777)
        (self.process / 'cmdline').write_bytes(b'llama-server\0--port\08081\0')
        (self.process / 'environ').write_bytes(b'CUDA_VISIBLE_DEVICES=0\0')
        (self.process / 'status').write_text('NSpid:\t432\nVmRSS:\t100 kB\nThreads:\t2\n')

    def set_ticks(self, ticks):
        (self.process / 'stat').write_text('432 (llama server) S ' + ' '.join(['0'] * 18 + [str(ticks)]) + '\n')

    def fake_run(self, args, timeout=12):
        if args[0] == 'nvidia-smi': return 0, '432, GPU-01234567, 100\n'
        if len(args) == 3: return 3, args[2] + ' STOPPED\n'
        return 0, 'nox-chat-8081 RUNNING pid 432, uptime 0:00:03\n'

    def assert_not_mapped(self, result):
        self.assertFalse(any(row.get('gpu_compute_apps') for row in result))
        self.assertTrue(result[-1]['unresolved'])

    def test_pid_recycled_during_gpu_query_cannot_be_attributed(self):
        def run(args, timeout=12):
            if args[0] == 'nvidia-smi': self.set_ticks(888)
            return self.fake_run(args, timeout)
        with patch.object(INSPECT, 'run', side_effect=run):
            self.assert_not_mapped(INSPECT.processes())

    def test_pid_recycled_while_reading_argv_cannot_be_attributed(self):
        original = Path.read_bytes
        def read(path):
            if path == self.process / 'cmdline': self.set_ticks(888)
            return original(path)
        with patch.object(INSPECT, 'run', side_effect=self.fake_run), patch.object(Path, 'read_bytes', read):
            self.assert_not_mapped(INSPECT.processes())

    def listener(self, inodes):
        (self.proc / 'net/tcp').write_text('sl local_address rem_address st tx rx tr tm retrnsmt inode\n' +
            ''.join(f'{index}: 0100007F:1F91 00000000:0000 0A 0 0 0 0 0 {inode}\n' for index, inode in enumerate(inodes)))
        with patch.object(INSPECT, 'run', side_effect=self.fake_run):
            return INSPECT.owner_safety_snapshot()['listener_8081']

    def test_partial_inode_ownership_is_not_a_complete_listener_map(self):
        (self.process / 'fd/3').symlink_to('socket:[42]')
        result = self.listener((42, 43))
        self.assertEqual(result['socket_inodes_observed'], 2)
        self.assertFalse(result['complete_pid_map'])
        self.assertEqual(result['status'], 'UNRESOLVED_LISTENER_OWNER')

    def test_one_pid_owning_all_inodes_is_deduplicated_and_complete(self):
        (self.process / 'fd/3').symlink_to('socket:[42]')
        (self.process / 'fd/4').symlink_to('socket:[43]')
        result = self.listener((42, 43))
        self.assertTrue(result['complete_pid_map'])
        self.assertEqual(result['matched_pids'], [{'pid': 432, 'start_ticks': 777}])

    def test_recycled_pid_during_socket_scan_is_not_complete(self):
        (self.process / 'fd/3').symlink_to('socket:[42]')
        original = INSPECT.os.readlink
        def readlink(path, **kwargs):
            target = original(path, **kwargs)
            if path == self.process / 'fd/3': self.set_ticks(888)
            return target
        with patch.object(INSPECT.os, 'readlink', side_effect=readlink):
            result = self.listener((42,))
        self.assertFalse(result['complete_pid_map'])
        self.assertEqual(result['matched_pids'], [])


if __name__ == '__main__':
    unittest.main()
