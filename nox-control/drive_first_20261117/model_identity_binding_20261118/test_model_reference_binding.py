"""Focused TempFS/AST regressions; no native app imports or network calls."""
import ast
import asyncio
from contextlib import aclosing
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

import owner_model_reference_binding as binding
import build_model_reference_snapshot as producer
import source_transform

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'resonance_native_20261118' / 'source_inputs_private'


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.proc = self.root / 'proc'
        self.snapshot = self.root / 'state' / 'verified_model_reference.json'
        self.snapshot.parent.mkdir()
        self.doc = json.loads((HERE / 'verified_model_reference.json').read_bytes())
        self.doc['process'].update(pid=1234, start_ticks=500, ppid=17, uid=os.getuid())
        self.doc['model_reference']['basename'] = 'SYNTHETIC_MODEL_Q4.gguf'
        self.doc['listener'].update(fd=67, socket_inode=4567)
        self.argv = b'/fixture/llama-server\0-m\0/root/nox/models/SYNTHETIC_MODEL_Q4.gguf\0'
        self.doc['process']['argv_sha256'] = binding.sha(self.argv)
        self.doc['process']['exe_path_sha256'] = binding.sha(b'/fixture/llama-server')
        self.doc['process']['cwd_sha256'] = binding.sha(b'/root/nox')
        self.doc['listener']['network_namespace_sha256'] = binding.sha(b'net:[900]')
        self.process = self.proc / '1234'
        for part in ('fd', 'ns', 'net'):
            (self.process / part).mkdir(parents=True, exist_ok=True)
        (self.proc / 'self' / 'ns').mkdir(parents=True)
        (self.proc / 'self' / 'ns' / 'net').symlink_to('net:[900]')
        (self.process / 'ns' / 'net').symlink_to('net:[900]')
        (self.process / 'fd' / '67').symlink_to('socket:[4567]')
        (self.process / 'exe').symlink_to('/fixture/llama-server')
        (self.process / 'cwd').symlink_to('/root/nox')
        fields = ['S', '17'] + ['0'] * 17 + ['500'] + ['0'] * 6
        (self.process / 'stat').write_text('1234 (fixture model) ' + ' '.join(fields))
        (self.process / 'cmdline').write_bytes(self.argv)
        (self.process / 'status').write_text('Name:\tfixture\nUid:\t' + '\t'.join([str(os.getuid())] * 4) + '\n')
        self.header = b'  sl  local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n'
        self.row = (f'0: 00000000:{8098:04X} 00000000:0000 0A 00000000:00000000 '
                    f'00:00000000 00000000 {os.getuid()} 0 4567 1\n').encode()
        (self.process / 'net' / 'tcp').write_bytes(self.header + self.row)
        self.save_snapshot()
        for key, value in [('PROC', self.proc), ('SNAPSHOT', self.snapshot), ('OWNER_UID', os.getuid())]:
            patcher = mock.patch.object(binding, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def save_snapshot(self):
        self.snapshot.write_text(json.dumps(self.doc))
        self.snapshot.chmod(0o600)

    def test_current_process_reference_and_honest_scope(self):
        # Old audit time is provenance; fresh fingerprints are what make it current.
        self.doc['evidence']['observed_at'] = 1600000000
        self.save_snapshot()
        result = binding.current_reference(binding.PRIMARY_URL)
        self.assertEqual(result['state'], 'verified_reference', result)
        self.assertEqual(result['model_file_reference'], 'SYNTHETIC_MODEL_Q4.gguf')
        self.assertEqual(result['audit_observed_at'], 1600000000)
        for field in ('weight_contents_verified', 'architecture_or_training_verified',
                      'global_listener_uniqueness_verified', 'prior_chat_backend_verified', 'health_rechecked', 'atomic_snapshot'):
            self.assertIs(result[field], False)
        self.assertNotIn(self.argv.decode(errors='replace'), json.dumps(result))

    def test_route_mismatch_does_no_filesystem_read_and_exports_no_stale_name(self):
        with mock.patch.object(binding._Reader, 'directory', side_effect=AssertionError('unexpected read')):
            result = binding.current_reference(binding.FALLBACK_URL)
        self.assertEqual(result['state'], 'unverified')
        self.assertEqual(result['selected_route'], '127.0.0.1:8085')
        self.assertNotIn('model_file_reference', result)

    def test_process_or_metadata_drift_hides_reference(self):
        with self.subTest('argv changed'):
            (self.process / 'cmdline').write_bytes(self.argv + b'--different\0')
            result = binding.current_reference(binding.PRIMARY_URL)
            self.assertEqual(result['reason'], 'PROCESS_ARGV_CHANGED')
            self.assertNotIn('model_file_reference', result)
        (self.process / 'cmdline').write_bytes(self.argv)
        with self.subTest('snapshot writable by group'):
            self.snapshot.chmod(0o660)
            result = binding.current_reference(binding.PRIMARY_URL)
            self.assertEqual(result['reason'], 'SNAPSHOT_FILE_METADATA')
            self.assertNotIn('model_file_reference', result)
        self.snapshot.chmod(0o600)
        with self.subTest('snapshot symlink'):
            target = self.snapshot.with_suffix('.original')
            self.snapshot.rename(target)
            self.snapshot.symlink_to(target)
            result = binding.current_reference(binding.PRIMARY_URL)
            self.assertEqual(result['state'], 'unverified')
            self.assertNotIn('model_file_reference', result)

    def test_fd_replaced_after_table_match_invalidates_same_turn(self):
        read = os.read
        replaced = False
        def raced_read(fd, limit):
            nonlocal replaced
            value = read(fd, limit)
            if not replaced and value.startswith(self.header):
                replaced = True
                link = self.process / 'fd' / '67'
                link.unlink()
                link.symlink_to('socket:[99999]')
            return value
        with mock.patch.object(binding.os, 'read', side_effect=raced_read):
            result = binding.current_reference(binding.PRIMARY_URL)
        self.assertTrue(replaced)
        self.assertEqual(result['reason'], 'LISTENER_CHANGED_DURING_READ')
        self.assertNotIn('model_file_reference', result)

    def test_disappearing_namespace_releases_open_file_descriptors(self):
        (self.process / 'ns' / 'net').unlink()
        (self.process / 'ns').rmdir()
        before = len(os.listdir('/proc/self/fd'))
        result = binding.current_reference(binding.PRIMARY_URL)
        self.assertEqual(result['state'], 'unverified')
        self.assertEqual(len(os.listdir('/proc/self/fd')), before)
        self.assertTrue(binding.model_identity_query('какая ты модель?'))

    def test_owned_listener_early_stop_does_not_claim_global_uniqueness(self):
        (self.process / 'net' / 'tcp').write_bytes(self.header + self.row + b'X' * (binding.MAX_TCP + 50000))
        result = binding.current_reference(binding.PRIMARY_URL)
        self.assertEqual(result['state'], 'verified_reference', result)
        self.assertIs(result['global_listener_uniqueness_verified'], False)

    def test_narrow_query_and_no_io_on_ordinary_conversation(self):
        yes = ['какая модель в твоей основе?', 'Какая у тебя базовая модель?',
               'на какой модели ты работаешь?', 'какой gguf у тебя сейчас?',
               'Назови свою модель.', 'what model are you?', 'Which model are you running?']
        no = ['Привет', 'какая модель лучше?', 'скачай модель', 'какая модель у тебя и обнови сервер',
              'какая модель у тебя? запусти агента', 'пример: «какая модель у тебя?»',
              '```what model are you```', 'какая модель у тебя; удали старую',
              'What model are you using and train it?', 'Что такое модель?']
        with mock.patch.object(binding._Reader, '__init__', side_effect=AssertionError('classification I/O')):
            for text in yes:
                with self.subTest(text=text): self.assertTrue(binding.model_identity_query(text))
            for text in no:
                with self.subTest(text=text): self.assertFalse(binding.model_identity_query(text))

    def test_assigned_current_model_question_stays_standalone(self):
        self.assertTrue(binding.model_identity_query('Какая модель в твоей основе сейчас?'))
        self.assertFalse(binding.model_identity_query('Какая модель в твоей основе сейчас? И запусти обучение.'))
        self.assertFalse(binding.model_identity_query('Какая модель в твоей основе сейчас и скачай другую?'))

    def test_bounded_context_keeps_exact_prefix_question_and_verified_fact(self):
        prefix = 'FIXED CACHE PREFIX\n' + binding.CONTRACT + ' Keep facts honest.'
        payload = {'messages': [{'role': 'system', 'content': prefix + '\n\nOLD MODEL STATUS: ' + 'x' * 150000},
                                {'role': 'assistant', 'content': 'Old model name ' * 10000},
                                {'role': 'user', 'content': 'augmented old question'}],
                   'tools': [{'huge': 'x' * 50000}], 'max_tokens': 5000, 'model': 'config-alias',
                   '_agent_final': 'old answer'}
        before = copy.deepcopy(payload)
        question = 'какая модель в твоей основе?'
        result = binding.prepare_identity_request(binding.PRIMARY_URL, payload, question)
        self.assertEqual(payload, before)
        self.assertEqual(len(result['messages']), 2)
        self.assertEqual(result['messages'][1], {'role': 'user', 'content': question})
        self.assertTrue(result['messages'][0]['content'].startswith(prefix + '\n\nNOX_CURRENT_MODEL_REFERENCE_V1'))
        self.assertIn('SYNTHETIC_MODEL_Q4.gguf', result['messages'][0]['content'])
        self.assertNotIn('OLD MODEL STATUS', result['messages'][0]['content'])
        self.assertLessEqual(sum(len(m['content'].encode()) for m in result['messages']), binding.MAX_CONTEXT_BYTES)
        self.assertNotIn('tools', result)
        self.assertNotIn('_agent_final', result)
        self.assertEqual(result['tool_choice'], 'none')
        self.assertEqual(result['max_tokens'], 256)
        with self.assertRaises(binding.ReferenceUnavailable):
            binding.prepare_identity_request(binding.PRIMARY_URL, payload, 'какая модель у тебя и запусти обучение')

    def test_exact_source_inverse_and_existing_owner_loop_unchanged(self):
        for name in source_transform.PINS:
            raw = (SOURCE / name).read_bytes()
            result = source_transform.transform(name, raw)
            restored = source_transform._replace(result.decode(), [(new, old) for old, new in reversed(source_transform.EDITS[name])])
            self.assertEqual(restored.encode(), raw)
            with self.assertRaises(ValueError):
                source_transform.transform(name, raw + b'\n')

    def test_existing_sse_identity_branch_generates_once_without_tools(self):
        source = source_transform.transform('owner_chat_stream.py', (SOURCE / 'owner_chat_stream.py').read_bytes())
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.AsyncFunctionDef) and n.name == '_run')
        calls = []
        class Client:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
        async def events(client, url, request):
            calls.append((url, request))
            yield 'token', 'Ответ самой модели'
            yield 'message', {'content': 'Ответ самой модели', 'tool_calls': []}
        namespace = {'asyncio': asyncio, 'aclosing': aclosing, 'httpx': types.SimpleNamespace(AsyncClient=Client),
                     '_model_reference': binding, '_model_events': events, 'StreamFailure': RuntimeError}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<extracted owner identity seam>', 'exec'), namespace)
        payload = {'messages': [{'role': 'system', 'content': 'FIXED\n' + binding.CONTRACT + ' honest'}]}
        async def collect():
            return [row async for row in namespace['_run']({}, binding.PRIMARY_URL, payload, 'какая модель у тебя?')]
        self.assertEqual(asyncio.run(collect()), [('token', 'Ответ самой модели')])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], binding.PRIMARY_URL)
        self.assertNotIn('tools', calls[0][1])
        self.assertIn('SYNTHETIC_MODEL_Q4.gguf', calls[0][1]['messages'][0]['content'])

    def test_snapshot_builder_accepts_only_lossless_accepted_audit(self):
        raw = (HERE.parent / 'model_identity_native_20261118' / 'ROOT_NATIVE_AUDIT_44192038242.raw.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), producer.ACCEPTED_RAW_SHA)
        # The producer's accepted real audit is root-owned, unlike TempFS data.
        with mock.patch.object(binding, 'OWNER_UID', 0):
            self.assertEqual(producer.build(raw), (HERE / 'verified_model_reference.json').read_bytes())
            with self.assertRaises(ValueError): producer.build(raw + b' ')


if __name__ == '__main__':
    unittest.main()
