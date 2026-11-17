"""Offline changed-path tests; no native app or network calls."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import model_reference_changed_path_qa as qa
from p0_witness_protocol import Turn, Hold, read_v24


class ChangedPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / 'state'; self.state.mkdir(mode=0o700)
        self.db = self.root / 'knowledge.sqlite'
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close); self.addCleanup(self.tmp.cleanup)
        self.stack.enter_context(patch.object(qa.native, 'STATE', self.state))
        self.stack.enter_context(patch.object(qa, 'DB', self.db))
        self.old_q, self.old_a = 'Синтетический предыдущий вопрос', 'Синтетический предыдущий ответ'
        frame = qa.native.full_turn_episode(self.old_q, self.old_a)
        self.old_sha = qa.digest(('M1|' + frame).encode())
        self.stack.enter_context(patch.object(qa, 'OLD_RECORD_SHA', self.old_sha))
        with sqlite3.connect(self.db) as db:
            db.executescript('''
                CREATE TABLE nox_v29_dialogs(dialog_id TEXT PRIMARY KEY, owner TEXT, title TEXT,
                    archived INTEGER, revision INTEGER, created_at TEXT, updated_at TEXT);
                CREATE TABLE nox_v29_dialog_messages(row_id INTEGER PRIMARY KEY, dialog_id TEXT,
                    exchange_id TEXT, role TEXT, content TEXT, ts TEXT);
                CREATE TABLE s03_items(id TEXT PRIMARY KEY, segment TEXT, provenance TEXT, sha256 TEXT, text TEXT);
            ''')
            db.execute('INSERT INTO nox_v29_dialogs VALUES(?,?,?,?,?,?,?)',
                       (qa.DIALOG, 'nox-single-owner', 'Own QA title', 0, 2, 'earlier', 'prior'))
            db.executemany('INSERT INTO nox_v29_dialog_messages VALUES(?,?,?,?,?,?)',
                [(10, qa.DIALOG, qa.OLD_EXCHANGE, 'user', self.old_q, 'prior'),
                 (11, qa.DIALOG, qa.OLD_EXCHANGE, 'assistant', self.old_a, 'prior')])
            db.execute('INSERT INTO s03_items VALUES(?,?,?,?,?)',
                       (qa.OLD_EXCHANGE, 'M1', 'chat_turn', self.old_sha, frame))
        info = self.db.stat(); self.binding = {'dev': info.st_dev, 'ino': info.st_ino}
        self.answer = 'Текущий процесс использует ' + qa.MODEL_REFERENCE + '.'
        self.frame = qa.native.full_turn_episode(qa.QUESTION, self.answer)
        self.new_sha = qa.digest(('M1|' + self.frame).encode())
        self.exchange = 'fixture-model-reference-0001'
        self.turn = Turn(self.answer, qa.DIALOG, self.exchange, self.new_sha, 900,
                         len(self.answer.encode()), 2, 0, 40, 40, 80)

    def append(self):
        with sqlite3.connect(self.db) as db:
            db.executemany('INSERT INTO nox_v29_dialog_messages VALUES(?,?,?,?,?,?)',
                [(12, qa.DIALOG, self.exchange, 'user', qa.QUESTION, 'new'),
                 (13, qa.DIALOG, self.exchange, 'assistant', self.answer, 'new')])
            db.execute('UPDATE nox_v29_dialogs SET revision=revision+1,updated_at=? WHERE dialog_id=?',
                       ('new', qa.DIALOG))
            db.execute('INSERT INTO s03_items VALUES(?,?,?,?,?)',
                       (self.exchange, 'M1', 'chat_turn', self.new_sha, self.frame))

    @staticmethod
    def http_history(snapshot):
        return {'status': 'READY', 'dialog_id': qa.DIALOG, 'revision': snapshot['dialog'][4],
                'messages': [{'role': r[1], 'content': r[2], 'ts': r[3], 'exchange_id': r[4]}
                             for r in snapshot['rows']]}

    def test_history_prefix_and_new_s03_are_verified_independently(self):
        before = qa.own_database_snapshot(self.binding)
        receipt = qa.verify_old_prefix(before, self.binding)
        self.assertNotIn(self.old_a, json.dumps(receipt))
        qa.verify_history_response(self.http_history(before), before)
        self.append()
        after = qa.own_database_snapshot(self.binding)
        receipt = qa.verify_appended_pair(before, after, self.turn, self.binding)
        self.assertTrue(receipt['prior_history_preserved'])
        self.assertEqual(receipt['new_record_sha256'], self.new_sha)
        qa.verify_history_response(self.http_history(after), after)
        with sqlite3.connect(self.db) as db:
            db.execute('UPDATE nox_v29_dialog_messages SET content=? WHERE row_id=11', ('changed',))
        with self.assertRaisesRegex(Hold, 'HOLD_PRIOR_HISTORY_CHANGED'):
            qa.verify_appended_pair(before, qa.own_database_snapshot(self.binding), self.turn, self.binding)

    def test_nonce_stays_outside_exact_match_question(self):
        target = Path(__file__).parents[1] / 'model_identity_binding_20261118/owner_model_reference_binding.py'
        spec = importlib.util.spec_from_file_location('qa_matcher_fixture', target)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        payload = qa.body('a' * 32)
        self.assertTrue(module.model_identity_query(payload['message']))
        self.assertEqual(payload['message'], qa.QUESTION)
        self.assertEqual(payload['history'], [])
        self.assertEqual(payload['dialog_id'], qa.DIALOG)
        self.assertEqual(payload['max_tokens'], 256)
        self.assertNotIn('a' * 32, payload['message'])
        self.assertIn('a' * 32, payload['request_id'])
        self.assertFalse(module.model_identity_query(payload['message'] + ' и проверь сервер'))

    def test_unknown_send_consumes_journal_and_http_allowlist_refuses_create(self):
        client = qa.Client()
        class SocketFailure:
            calls = 0
            def open(self, *args, **kwargs):
                self.calls += 1
                raise TimeoutError('SYNTHETIC_SOCKET_ONLY')
        opener = SocketFailure(); client.opener = opener
        with qa.Journal('123', 'a' * 40, 'b' * 32) as journal:
            with self.assertRaises(TimeoutError): journal.send(client)
            with self.assertRaisesRegex(Hold, 'HOLD_QA_POST_REPLAY'): journal.send(client)
            intent = json.loads((journal.path / 'model_post_intent.json').read_bytes())
            self.assertTrue(intent['uncertain_result_never_retried'])
            self.assertEqual(intent['body_sha256'], qa.digest(qa.canonical(qa.body('b' * 32))))
        self.assertEqual(client.counts['model_post'], 1)
        self.assertEqual(opener.calls, 1)
        with self.assertRaisesRegex(Hold, 'HOLD_QA_ALREADY_RESERVED_NO_RETRY'):
            with qa.Journal('124', 'c' * 40, 'd' * 32): pass
        with self.assertRaisesRegex(Hold, 'HOLD_POST_SCOPE_OR_REPLAY'):
            client.request('/api/ui/memory/dialogs/create', {'confirmed': True})
        self.assertEqual(client.counts['dialog_create_post'], 0)
        self.assertEqual(opener.calls, 1)

    def test_install_generation_projection_refuses_drift(self):
        raw_path = Path(__file__).parents[1] / 'acceleration_20261118/MODEL_BINDING_NATIVE_RESULT_44198936370.raw.json'
        value = json.loads(raw_path.read_bytes())['data']
        after = next(s['after'] for s in value['steps'] if s['phase'] == 'proxy_reloaded')
        command = 'synthetic-command-no-secret'
        after['config']['values'] = {'command': command}
        release = dict(qa.RELEASE, command_sha256=qa.digest(command.encode()))
        path = self.state / ('owner_v24_dialog_' + release['install_request'] + '.json')
        path.write_bytes(qa.canonical(value)); path.chmod(0o600)
        with patch.object(qa, 'RELEASE', release):
            receipt = qa.installed_release(after)
            self.assertEqual(receipt['proxy_generation']['pid'], 3648425)
            after['process']['start_ticks'] += 1
            with self.assertRaisesRegex(Hold, 'HOLD_ACTUAL_PROXY_GENERATION'):
                qa.installed_release(after)

    def test_full_orchestration_one_sse_request_and_private_result(self):
        fixture = self
        menu = b'SYNTHETIC_MENU_ASSET'
        class Response(io.BytesIO):
            status = 200
            headers = {'Content-Type': 'text/event-stream'}
        class FakeClient:
            def __init__(self):
                self.jar = [object()]
                self.counts = {'login_post': 0, 'model_post': 0, 'dialog_create_post': 0, 'get': 0}
            def raw(self, path, data=None, limit=32768):
                if path == '/chat/login': self.counts['login_post'] += 1; return b'{}'
                fixture.assertEqual(path, qa.MENU_PATH)
                self.counts['get'] += 1; return menu
            def json(self, path):
                fixture.assertEqual(path, qa.HISTORY_PATH)
                self.counts['get'] += 1
                return fixture.http_history(qa.own_database_snapshot(fixture.binding))
            def request(self, path, data=None):
                fixture.assertEqual(path, '/api/nox/chat')
                fixture.assertEqual(data['message'], qa.QUESTION)
                fixture.assertEqual(data['dialog_id'], qa.DIALOG)
                self.counts['model_post'] += 1
                fixture.append()
                frames = [{'type': 'context'}, {'type': 'meta', 'dialog_id': qa.DIALOG},
                    {'type': 'token', 't': fixture.answer}, {'type': 'done', 'status': 'done',
                     'saved': True, 's03_integrated': True, 'exchange_id': fixture.exchange,
                     's03_readback': 'FULL_QUESTION_AND_ANSWER_SUBSTRINGS',
                     's03_proof': 'M1_LENGTH_FRAMED_V2_SHA256', 's03_record_sha256': fixture.new_sha}]
                return Response(b''.join(b'data: ' + qa.canonical(f) + b'\n\n' for f in frames))
        credential = self.root / 'qa-auth'; credential.write_bytes(b'synthetic-fixture-only'); credential.chmod(0o600)
        # A fixed-length fixture keeps the production served-asset size gate in
        # the orchestration. Only its hash is a fixture value.
        menu = menu.ljust(43021, b' ')
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, NOX_OWNER_REQUEST_ID='999', NOX_OWNER_SOURCE_SHA='f' * 40))
            original_require = qa.require
            def fixture_require(condition, code):
                # The container fixture is not native root. Keep its real UID
                # for all file/DB ownership checks; waive only run()'s native
                # owner-context guard, which cannot be exercised in TempFS.
                if code == 'HOLD_OWNER_CONTEXT':
                    return
                return original_require(condition, code)
            stack.enter_context(patch.object(qa, 'require', side_effect=fixture_require))
            stack.enter_context(patch.object(qa.native, 'maintenance_lease', return_value=contextlib.nullcontext({'dev': 36, 'ino': 59886214})))
            for name in ('checked_directory', 'global_stop_guard', 'require_same_service'):
                stack.enter_context(patch.object(qa.native, name, return_value=None))
            stack.enter_context(patch.object(qa.native, 'service_identity', return_value={}))
            stack.enter_context(patch.object(qa.native, 'owner_idle', return_value={'fixture': True}))
            stack.enter_context(patch.object(qa.native, 'resolve_password_path', return_value=credential))
            stack.enter_context(patch.object(qa, 'source_readback', return_value=({}, {'chat_proxy.py': b'', 'common.py': b''})))
            stack.enter_context(patch.object(qa, 'installed_release', return_value={'fixture': True}))
            stack.enter_context(patch.object(qa, 'database_binding', return_value=self.binding))
            stack.enter_context(patch.object(qa, 'Client', FakeClient))
            stack.enter_context(patch.object(qa, 'MENU_SHA', qa.digest(menu)))
            result = qa.run()
        self.assertTrue(result['completed'], result)
        self.assertTrue(result['used'])
        self.assertFalse(result['accepted'])
        self.assertEqual(result['http_counts'], {'login_post': 1, 'model_post': 1, 'dialog_create_post': 0, 'get': 3})
        self.assertEqual(result['owner_chat_posts'], 1)
        self.assertEqual(result['backend_model_http_posts'], 'NOT_DIRECTLY_OBSERVED')
        self.assertTrue(result['system_prefix_bound_path_completion_inferred'])
        self.assertFalse(result['actual_model_input_trace_observed'])
        self.assertNotIn('system_prefix_bound_path_completed', result)
        self.assertEqual(result['own_synthetic_answer']['text'], self.answer)
        self.assertTrue(result['history_and_s03']['prior_history_preserved'])
        self.assertNotIn(self.old_a, json.dumps(result))
        self.assertNotIn('synthetic-fixture-only', json.dumps(result))
        self.assertEqual(json.loads((self.state / qa.JOURNAL / 'outcome.json').read_bytes()), result)


if __name__ == '__main__':
    unittest.main()
