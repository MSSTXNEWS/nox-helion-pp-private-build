import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('handback_diagnostic_test_module', HERE / 'owner_qwen_handback_diagnostic.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class HandbackDiagnosticTests(unittest.TestCase):
    def test_exact_dependency_definitions_and_symlink_reader(self):
        with patch.object(m, 'BUNDLE', {m.OBSERVER: base64.b64encode((HERE / m.OBSERVER).read_bytes()).decode()}):
            reader = m.observer()
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'plain'; p.write_bytes(b'fixed')
            self.assertEqual(reader.read(p)[0], b'fixed')
            link = Path(temp) / 'link'; link.symlink_to(p)
            with self.assertRaisesRegex(RuntimeError, 'PATH'):
                reader.read(link)
        with patch.object(m, 'BUNDLE', {m.OBSERVER: base64.b64encode(b'raise Exception("bad")').decode()}):
            with self.assertRaisesRegex(RuntimeError, 'BUNDLE_PIN'):
                m.observer()

    def test_only_exact_resume_task_and_safe_reason_are_projected(self):
        secret = 'PRIVATE PROMPT /home/private/file TOKEN'
        value = {'tasks': {'unrelated': {'prompt': secret}, m.RESUME_ID: {
            'id': m.RESUME_ID, 'handler': 'owner_media_resume', 'status': 'pending', 'retries': 0,
            'note': "{'state': 'WAIT_MEDIA_QUEUE_DRAIN', 'private': '" + secret + "'}",
            'result': {'state': 'WAIT_MEDIA_QUEUE_DRAIN', 'prompt': secret},
            'owner_claim': {'nonce': 'a' * 24, 'pid': 724331}}}}
        result = m.task_projection(value)
        self.assertEqual(result['note_code'], 'WAIT_MEDIA_QUEUE_DRAIN')
        self.assertEqual(result['state'], 'pending')
        self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(m.task_projection({'tasks': {}})['resume_task_present'], False)

    def test_exact_pause_binding_and_terminal_no_training_text(self):
        secret = 'PRIVATE CONTENT'
        yielded = {'job_id': m.JOB, 'active': True, 'resume': True,
                   'pause_token': 'NOX_MEDIA_CHECKPOINT_YIELD ' + m.JOB + '\n',
                   'checkpoint': {'step': 8, 'checkpoint': str(m.OUTPUT / m.CHECKPOINT8)}, 'prompt': secret}
        result = m.yield_projection(yielded)
        self.assertTrue(result['pause_token_matches'])
        self.assertTrue(result['checkpoint']['names_observed_checkpoint8'])
        terminal = m.terminal_projection({'state': 'EXISTING_TRAINER_HOLD_OR_PAUSE', 'successful_optimizer_steps': 8,
            'new_successful_optimizer_steps': 2, 'update_evidence': [{'private': secret}] * 8,
            'exception': secret, 'reload_verified': True, 'checkpoint': str(m.OUTPUT / m.CHECKPOINT8)})
        self.assertEqual(terminal['update_evidence_count'], 8)
        self.assertEqual(terminal['new_successful_optimizer_steps'], 2)
        self.assertNotIn(secret, json.dumps([result, terminal]))

    def test_missing_files_and_exceptions_do_not_leak_paths(self):
        def missing():
            raise FileNotFoundError('/private/credential')
        def bad():
            raise ValueError('PRIVATE PASSWORD')
        self.assertEqual(m.attempt(missing), {'present': False})
        self.assertEqual(m.attempt(bad)['reason'], 'HOLD_DIAGNOSTIC_READ_UNVERIFIED')
        self.assertIsNone(m.safe_code('HOLD_PASS secret'))

    def test_snapshot_is_read_only_and_missing_resume_is_explicit(self):
        secret = 'PRIVATE PROMPT NEVER EMIT'
        visited = []
        def read(path, maximum=262144):
            visited.append(str(path))
            if '/released-' in str(path):
                raise FileNotFoundError()
            raw = b'fixed'
            return raw, {'sha256': m.digest(raw), 'bytes': len(raw), 'mtime_ns': 1}
        def document(path, maximum=262144):
            raw, meta = read(path, maximum)
            name = Path(path).name
            if name == 'state.json':
                return {'tasks': {'unrelated': {'prompt': secret}}}, meta
            if name == 'request.json':
                raise FileNotFoundError()
            if name == 'owner_last_result.json':
                return {'state': 'EXISTING_TRAINER_HOLD_OR_PAUSE', 'successful_optimizer_steps': 8,
                        'new_successful_optimizer_steps': 2, 'private': secret}, meta
            return {'private': secret}, meta
        reader = types.SimpleNamespace(read=read, document=document,
            services=lambda: {'nox-train-volta-t866u': {'state': 'FATAL', 'pid': None}})
        result = m.snapshot(reader)
        self.assertEqual(result['files_written'], 0)
        self.assertFalse(result['resume_admitted'])
        self.assertFalse(result['resume_task']['resume_task_present'])
        self.assertFalse(result['handback_request']['present'])
        self.assertEqual(result['terminal']['successful_optimizer_steps'], 8)
        self.assertNotIn(secret, json.dumps(result))
        self.assertFalse(any(path.endswith(('.safetensors', '.pt', '.pth')) for path in visited))
        self.assertLess(len(json.dumps(result)), 48000)

    def test_nonfinite_values_and_unrelated_process_fields_are_suppressed(self):
        value = m.terminal_projection({'successful_optimizer_steps': float('nan'),
            'process_identity': {'pid': 709581, 'start_ticks': '149189867', 'argv': 'SECRET'},
            'holdout_loss': float('inf')})
        self.assertIsNone(value['successful_optimizer_steps'])
        self.assertIsNone(value['holdout_loss'])
        self.assertNotIn('SECRET', json.dumps(value, allow_nan=False))


if __name__ == '__main__':
    unittest.main()
