import hashlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location('owner_media_acceptance_entry', HERE / 'owner_media_acceptance_entry.py')
a = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(a)


def hold_lock(path, ready, stop):
    import fcntl
    with open(path, 'w') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        ready.send(os.getpid())
        stop.recv()


class MediaAcceptanceTests(unittest.TestCase):
    def test_runtime_pin_and_missing_context_prevent_remote_work(self):
        self.assertEqual(a.digest((HERE / 'owner_media_runtime.py').read_bytes()), a.RUNTIME_SHA)
        with patch.dict(os.environ, {}, clear=True), patch.object(a.OwnerClient, 'authenticate') as auth:
            with self.assertRaisesRegex(RuntimeError, 'OWNER_CONTEXT'):
                a.main()
            auth.assert_not_called()

    def test_mixed_controller_group_cannot_be_admitted(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(a, 'SCRIPTS', Path(tmp)):
            files = {'nox_dispatcher_t855u.py': b'old dispatcher', 'owner_task_lifecycle.py': b'old lifecycle', 'owner_event_outbox.py': b'old outbox'}
            old = {name: a.digest(raw) for name, raw in files.items()}
            new = {name: a.digest(b'new ' + raw) for name, raw in files.items()}
            for name, raw in files.items():
                (Path(tmp) / name).write_bytes(raw)
            (Path(tmp) / 'owner_media_runtime.py').write_bytes(b'runtime')
            with patch.object(a, 'SOURCE_GROUPS', {'old': old, 'new': new}), patch.object(a, 'RUNTIME_SHA', a.digest(b'runtime')):
                self.assertEqual(a.sources()[0]['group'], 'old')
                (Path(tmp) / 'owner_event_outbox.py').write_bytes(b'new old outbox')
                with self.assertRaisesRegex(RuntimeError, 'SOURCE_PINS'):
                    a.sources()

    def test_forged_or_unfinished_queue_claim_is_not_completion(self):
        job_id = 'a' * 32
        task = {'id': 'owner.media.' + job_id, 'handler': 'owner_media', 'params': {'job_id': job_id},
                'locks': ['gpu1'], 'class': 'owner_order', 'status': 'running',
                'owner_claim': {'pid': 101, 'worker': 'nox-agent-03', 'nonce': 'd' * 24}}
        self.assertIsNone(a.claim_projection(task, job_id, 101, require_done=True))
        task.update(status='done', result={'id': job_id, 'state': 'COMPLETED', 'generation_verified': True})
        self.assertEqual(a.claim_projection(task, job_id, 101, True)['nonce'], 'd' * 24)
        with self.assertRaisesRegex(RuntimeError, 'NATIVE_CLAIM'):
            a.claim_projection(task, job_id, 102, True)
        task['owner_claim']['worker'] = 'nox-agent-32'
        with self.assertRaisesRegex(RuntimeError, 'NATIVE_CLAIM'):
            a.claim_projection(task, job_id, 101, True)

    def test_actual_forge_lock_holder_pid_is_observed_and_release_is_distinct(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(a, 'STATE', Path(tmp)):
            path = Path(tmp) / 'forge_training.lock'
            receiving, sending = multiprocessing.Pipe(False)
            stop_receiver, stop_sender = multiprocessing.Pipe(False)
            process = multiprocessing.Process(target=hold_lock, args=(str(path), sending, stop_receiver))
            process.start()
            try:
                self.assertTrue(receiving.poll(3))
                pid = receiving.recv()
                self.assertTrue(a.forge_holder(pid))
                self.assertFalse(a.forge_holder(pid + 10000))
            finally:
                stop_sender.send(True)
                process.join(3)
                if process.is_alive():
                    process.terminate(); process.join()
            self.assertFalse(a.forge_holder(pid))

    def test_decoding_rejects_still_frames_wrong_codec_and_missing_timestamps(self):
        request = dict(a.CASES[1])
        proof = {'width': 256, 'height': 256, 'frames': 9, 'codec': 'vp9', 'metadata_fps': None, 'decoded_fps': 8,
                 'distinct_decoded_frames': 9, 'max_channel_range': 240,
                 'timestamps_strictly_increasing': True, 'timestamp_span_seconds': 1, 'max_frame_interval_error_seconds': 0}
        self.assertEqual(a.validate_decode(proof, request), proof)
        for key, value in [('frames', 1), ('codec', 'h264'), ('decoded_fps', 25), ('distinct_decoded_frames', 1),
                           ('timestamps_strictly_increasing', False), ('timestamp_span_seconds', 9),
                           ('max_frame_interval_error_seconds', 0.01), ('decoded_fps', float('nan'))]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                a.validate_decode(dict(proof, **{key: value}), request)

    def test_independent_real_png_decoder_accepts_pixels_and_rejects_blank(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'image.png'
            image = Image.new('RGB', (512, 512))
            image.putdata([(x % 256, y % 256, (x + y) % 256) for y in range(512) for x in range(512)])
            image.save(path)
            expected = {key: a.CASES[0][key] for key in ('kind', 'width', 'height', 'frames', 'fps')}
            result = subprocess.run([sys.executable, '-c', a.DECODE, str(path), json.dumps(expected)], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(a.validate_decode(json.loads(result.stdout), a.CASES[0])['frames'], 1)
            Image.new('RGB', (512, 512), 'black').save(path)
            result = subprocess.run([sys.executable, '-c', a.DECODE, str(path), json.dumps(expected)], capture_output=True, timeout=10)
            with self.assertRaisesRegex(RuntimeError, 'BLANK_OUTPUT'):
                a.validate_decode(json.loads(result.stdout), a.CASES[0])

    def test_file_scope_rejects_symlink_fifo_and_path_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'data'; path.write_bytes(b'original')
            link = Path(tmp) / 'link'; link.symlink_to(path)
            with self.assertRaisesRegex(RuntimeError, 'PATH'):
                a.read(link)
            fifo = Path(tmp) / 'fifo'; os.mkfifo(fifo)
            with self.assertRaisesRegex(RuntimeError, 'FILE_SCOPE'):
                a.read(fifo)
            with self.assertRaisesRegex(RuntimeError, 'FILE_CHANGED'):
                with a.regular_fd(path, 100):
                    replacement = Path(tmp) / 'replacement'; replacement.write_bytes(b'replaced')
                    os.replace(replacement, path)

    def test_private_receipts_are_immutable_and_repeated_request_cannot_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'accepted.json'
            value = {'state': 'VERIFIED', 'pixels_exported': False}
            sha = a.write_record(path, value, immutable=True)
            self.assertEqual(sha, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                a.write_record(path, {'state': 'REPLACED'}, immutable=True)
            self.assertEqual(a.document(path), value)

    def test_foreign_active_jobs_block_unload_without_exposing_prompt(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(a, 'STATE', Path(tmp)):
            directory = Path(tmp) / 'media/jobs'; directory.mkdir(parents=True)
            job = {'id': 'b' * 32, 'state': 'RUNNING', 'request': {'prompt': 'PRIVATE_OWNER_PROMPT'}}
            (directory / (job['id'] + '.json')).write_text(json.dumps(job))
            runtime = Mock(ACTIVE={'RUNNING'})
            with self.assertRaisesRegex(RuntimeError, '^WAIT_MEDIA_ACCEPTANCE_OWNER_WORK$'):
                a.no_other_jobs(runtime)
            a.no_other_jobs(runtime, [job['id']])

    def test_final_unload_holds_real_leases_and_does_not_start_training(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(a, 'STATE', Path(tmp)):
            root = Path(tmp); runtime = Mock(); runtime.engine_identity.return_value = {'pid': 42}
            runtime.queue_ids.return_value = {'queue_running': [], 'queue_pending': []}
            runtime.gpu1.return_value = {'free_mib': 32491, 'used_mib': 4, 'total_mib': 32495}
            flags = {'hold_sha256': 'f' * 64, 'pause_sha256': None}
            observed = []
            def command(path, data):
                self.assertEqual(path, '/free')
                self.assertEqual(data, {'unload_models': True, 'free_memory': True})
                for rel in ('media/controller.lock', 'forge_training.lock'):
                    with self.assertRaisesRegex(RuntimeError, 'WAIT_MEDIA_ACCEPTANCE_LEASE'):
                        with a.lease(root / rel):
                            pass
                observed.append(True)
            runtime.engine.side_effect = command
            with patch.object(a, 'training_guard', return_value=(flags, {'state': 'STOPPED', 'pid': None})), patch.object(a, 'no_other_jobs'):
                result = a.final_unload(runtime, {}, flags, {'pid': 42})
            self.assertEqual(observed, [True]); self.assertFalse(result['training_started'])
            self.assertTrue(result['forge_lease_reacquired']); self.assertTrue(result['forge_lease_released'])
            with a.lease(root / 'forge_training.lock'):
                pass
            runtime.service_state.assert_not_called()

    def test_sanitized_errors_and_api_scope_never_emit_secrets(self):
        self.assertEqual(a.safe_error(RuntimeError('PRIVATE_PASSWORD')), 'HOLD_MEDIA_ACCEPTANCE_RUNTIMEERROR')
        client = a.OwnerClient('PRIVATE_COOKIE')
        for path in ('https://example.com', '/api/ui/media/../../secret', '/api/ui/media/jobs/' + 'a' * 32 + '/cancel'):
            with patch.object(a.http.client, 'HTTPConnection') as remote:
                with self.assertRaisesRegex(RuntimeError, 'API_SCOPE'):
                    client.connection(path)
                remote.assert_not_called()


if __name__ == '__main__':
    unittest.main()
