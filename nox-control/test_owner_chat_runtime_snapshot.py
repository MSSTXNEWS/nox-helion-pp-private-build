import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('runtime_snapshot_tested', Path(__file__).with_name('owner_chat_runtime_snapshot.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class SnapshotTests(unittest.TestCase):
    def test_argv_and_environment_do_not_export_other_content(self):
        argv = b'\0'.join([b'/root/nox/bin/llama-server', b'--api-key', b'PRIVATE_VALUE', b'-t', b'12', b'--threads-batch=8', b'--threads-http', b'secret-value'])
        with mock.patch.object(m, 'read', return_value=argv):
            value = m.arguments()
        self.assertEqual(value, {'executable_verified': True, 'numeric_flags': {'threads': 12, 'threads_batch': 8, 'threads_http': 'UNKNOWN'}})
        with mock.patch.object(m, 'read', return_value=b'API_KEY=PRIVATE_VALUE\0OMP_NUM_THREADS=4\0LLAMA_ARG_THREADS=not-a-number\0'):
            env = m.environment()
        self.assertEqual(env, {'OMP_NUM_THREADS': 4, 'LLAMA_ARG_THREADS': 'UNKNOWN'})
        self.assertNotIn('PRIVATE_VALUE', json.dumps([value, env]))

    def props(self, value):
        opener = mock.Mock()
        opener.open.return_value = io.BytesIO(json.dumps(value).encode())
        with mock.patch.object(m.urllib.request, 'build_opener', return_value=opener):
            return m.properties()

    def test_props_projection_rejects_raw_or_malformed_fields(self):
        result = self.props({'build_info': 'b12345-abcdef0123', 'total_slots': 6, 'prompt': 'PRIVATE_VALUE', 'chat_template': 'PRIVATE_VALUE', 'default_generation_settings': {'n_ctx': 32768, 'n_threads': 12}})
        self.assertEqual(result, {'state': 'OBSERVED', 'build_info': 'b12345-abcdef0123', 'total_slots': 6, 'context_per_slot': 32768, 'n_threads': 12})
        bad = self.props({'build_info': 'PRIVATE_VALUE\n', 'total_slots': True, 'n_threads': 'PRIVATE_VALUE'})
        self.assertEqual(bad, {'state': 'OBSERVED', 'build_info': 'UNKNOWN'})
        self.assertIsNone(m.NoRedirect().redirect_request(None, None, None, None, None))

    def test_properties_response_limit(self):
        opener = mock.Mock()
        opener.open.return_value = io.BytesIO(b' ' * 131073)
        with mock.patch.object(m.urllib.request, 'build_opener', return_value=opener):
            self.assertEqual(m.properties()['state'], 'UNKNOWN_RESPONSE_LIMIT')

    def test_startup_log_requires_exact_launcher_and_is_not_pid_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launch, log = root / 'launch', root / 'log'
            raw = b'LOG=/root/nox/logs/llama-chat-8081.log\n'
            launch.write_bytes(raw)
            log.write_bytes(b'PRIVATE_VALUE\nsystem_info: n_threads = 12 (n_threads_batch = 8) / 80\n')
            with mock.patch.multiple(m, LAUNCH=launch, LOG=log, LAUNCH_SHA=hashlib.sha256(raw).hexdigest()):
                result = m.startup_log()
                self.assertEqual(result['state'], 'LOG_ONLY_NOT_PID_PROVEN')
                self.assertEqual(result['thread_values']['n_threads'], [12])
                self.assertEqual(result['thread_values']['n_threads_batch'], [8])
                self.assertNotIn('PRIVATE_VALUE', json.dumps(result))
                launch.write_bytes(raw + b'changed')
                self.assertEqual(m.startup_log()['state'], 'UNKNOWN_LAUNCH_SOURCE')

    def test_wrong_pid_start_never_reads_metadata(self):
        with mock.patch.object(m, 'cpu', return_value={}), mock.patch.object(m, 'process', return_value={'start_ticks': m.START_TICKS + 1}), mock.patch.object(m, 'arguments') as args:
            result = m.snapshot()
        self.assertEqual(result['state'], 'PROCESS_IDENTITY_CHANGED')
        args.assert_not_called()

    def test_process_disappearing_drops_process_specific_snapshot(self):
        before = {'pid': m.PID, 'start_ticks': m.START_TICKS}
        with mock.patch.object(m, 'cpu', return_value={}), mock.patch.object(m, 'process', side_effect=[before, None]), mock.patch.object(m, 'arguments', return_value={'executable_verified': True}), mock.patch.object(m, 'environment', return_value={}), mock.patch.object(m, 'properties', return_value={}), mock.patch.object(m, 'startup_log', return_value={}), mock.patch.object(m, 'executable', return_value={}):
            result = m.snapshot()
        self.assertEqual(result['state'], 'PROCESS_IDENTITY_CHANGED')
        self.assertFalse(result['process_identity_verified'])
        self.assertNotIn('props', result)

    def test_executable_full_hash_and_size_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary, proc = root / 'llama-server', root / 'proc'
            proc.mkdir()
            binary.write_bytes(b'synthetic executable')
            (proc / 'exe').symlink_to(binary)
            with mock.patch.multiple(m, PROC=proc, BINARY=binary):
                result = m.executable()
                self.assertEqual(result['sha256'], hashlib.sha256(binary.read_bytes()).hexdigest())
                self.assertTrue(result['configured_inode_matches'])
                with binary.open('wb') as stream:
                    stream.truncate(64 * 1024 * 1024 + 1)
                self.assertEqual(m.executable()['state'], 'HASH_NOT_READ_SIZE_LIMIT')

    def test_read_rejects_fifo_and_symlink_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            os.mkfifo(root / 'pipe')
            self.assertIsNone(m.read(root / 'pipe', 100))
            (root / 'file').write_bytes(b'private')
            (root / 'link').symlink_to(root / 'file')
            self.assertIsNone(m.read(root / 'link', 100))


if __name__ == '__main__':
    unittest.main()
