"""TempFS continuation regression. No native application or network is used."""
import contextlib
from datetime import datetime, timezone, timedelta
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

import model_reference_changed_path_qa as qa
from p0_witness_protocol import Hold

HERE = Path(__file__).resolve().parent
PRIOR = (HERE / 'inputs/ACTUAL_PRIOR_OUTCOME_CANONICAL.json').read_bytes()


class ContinuationTests(unittest.TestCase):
    def seed_prior(self, state):
        path = state / qa.JOURNAL
        path.mkdir(mode=0o700)
        reservation = {'request': qa.PRIOR_REQUEST, 'source_sha': qa.PRIOR_SOURCE,
            'nonce': '7' * 32, 'install_request': qa.RELEASE['install_request'],
            'dialog_id': qa.DIALOG, 'automatic_retry_allowed': False}
        for name, raw in [('outcome.json', PRIOR), ('reservation.json', qa.canonical(reservation))]:
            file = path / name
            file.write_bytes(raw); file.chmod(0o600)
        return path, {name: (qa.ZeroSendContinuation.file_identity((path / name).stat()),
                            (path / name).read_bytes()) for name in ('outcome.json', 'reservation.json')}

    def assert_old_unchanged(self, path, original):
        for name, expected in original.items():
            self.assertEqual((qa.ZeroSendContinuation.file_identity((path / name).stat()),
                              (path / name).read_bytes()), expected)

    def test_actual_zero_send_receipt_then_exclusive_child_lost_ack_or_unknown_never_replays(self):
        # This oracle is the canonical actual native result, not a result built
        # from the implementation's own expected outcome fields.
        self.assertEqual(len(PRIOR), 3534)
        self.assertEqual(qa.digest(PRIOR),
            'f0224c15acf37aaad4b45380ce174a27ae2acbafbdf361f036f07eca846e4fd9')
        self.assertEqual(json.loads(PRIOR)['http_counts']['model_post'], 0)
        for mode in ('normal', 'intent_ack_lost', 'socket_unknown', 'prior_intent', 'prior_replaced'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                state = Path(directory) / 'state'; state.mkdir(mode=0o700)
                path, original = self.seed_prior(state)
                with patch.object(qa.native, 'STATE', state):
                    journal = qa.ZeroSendContinuation('1001', 'b' * 40)
                    self.addCleanup(journal.close_prior)
                    if mode == 'prior_intent':
                        (path / 'model_post_intent.json').write_text('{}')
                        with self.assertRaisesRegex(Hold, 'HOLD_CONTINUATION_PRIOR_SEND_INTENT'):
                            journal.preflight()
                        self.assertFalse((path / qa.CONTINUATION).exists())
                        self.assert_old_unchanged(path, original)
                        continue
                    journal.preflight()
                    self.assertEqual(journal.context['nonce'], '7' * 32)
                    if mode == 'prior_replaced':
                        replacement = path / 'replacement'
                        replacement.write_bytes(PRIOR); replacement.chmod(0o600)
                        os.replace(replacement, path / 'outcome.json')
                        with self.assertRaisesRegex(Hold, 'HOLD_CONTINUATION_PRIOR_FILE_REPLACED'):
                            journal.__enter__()
                        self.assertFalse((path / qa.CONTINUATION).exists())
                        continue
                    client = qa.Client()
                    class LocalOnlyOpener:
                        calls = 0
                        def open(self, request, **kwargs):
                            self.calls += 1
                            self.request = request
                            if mode == 'socket_unknown':
                                raise TimeoutError('LOCAL_SYNTHETIC_UNCERTAINTY')
                            return io.BytesIO(b'')
                    opener = LocalOnlyOpener(); client.opener = opener
                    with journal:
                        original_write = journal.write
                        def ack_lost(name, value):
                            original_write(name, value)
                            if name == 'model_post_intent.json':
                                raise OSError('LOCAL_DURABLE_WRITE_ACK_LOST')
                        with patch.object(journal, 'write', side_effect=ack_lost if mode == 'intent_ack_lost' else original_write):
                            if mode == 'intent_ack_lost':
                                with self.assertRaises(OSError): journal.send(client)
                            elif mode == 'socket_unknown':
                                with self.assertRaises(TimeoutError): journal.send(client)
                            else:
                                journal.send(client).close()
                                with self.assertRaisesRegex(Hold, 'HOLD_QA_POST_REPLAY'):
                                    journal.send(client)
                        self.assertTrue((path / qa.CONTINUATION / 'model_post_intent.json').exists())
                    expected_posts = 0 if mode == 'intent_ack_lost' else 1
                    self.assertEqual(opener.calls, expected_posts)
                    self.assertEqual(client.counts['model_post'], expected_posts)
                    again = qa.ZeroSendContinuation('1002', 'c' * 40)
                    with self.assertRaisesRegex(Hold, 'HOLD_CONTINUATION_ALREADY_RESERVED_NO_RETRY'):
                        again.preflight()
                    self.assertEqual(opener.calls, expected_posts)
                    self.assert_old_unchanged(path, original)

    def test_real_wait_adapter_sse_sql_and_raw_counter_in_one_attempt(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            root = Path(directory)
            state = root / 'state'; state.mkdir(mode=0o700)
            scripts = root / 'scripts'; scripts.mkdir(mode=0o700)
            status = root / 'status'; status.mkdir(mode=0o700)
            logs = root / 'logs'; logs.mkdir(mode=0o700)
            priority = state / 'priority'; priority.mkdir(mode=0o700)
            arbiter = scripts / 'nox_priority_arbiter.py'
            arbiter.write_bytes((HERE / 'inputs/actual_arbiter_source.py').read_bytes())
            arbiter.chmod(0o775)  # Actual evidence reader permits this observed mode.
            log = logs / 'proxy.log'; log.write_bytes(b''); log.chmod(0o664)
            lease = state / 'owner_maintenance.lock'; lease.write_bytes(b''); lease.chmod(0o600)
            lease_pin = {'dev': lease.stat().st_dev, 'ino': lease.stat().st_ino}
            credential = root / 'auth-fixture'; credential.write_bytes(b'synthetic-only'); credential.chmod(0o600)
            counter = status / 'chat_state.json'
            # A nonhistorical value proves no implicit assumption of four.
            before_counter = b'{"inflight":9,"last_start":1,"last_end":2,"last_ts":2,"path":"chat","stream_finished":true,"legacy_extra":{"private":"fixture-private-old-state"}}\n'
            after_counter = b'{"inflight":9,"last_start":3,"last_end":4,"last_ts":4,"path":"chat","stream_finished":true,"legacy_extra":{"private":"fixture-private-old-state"}}\n'
            counter.write_bytes(before_counter); counter.chmod(0o600)
            path, old_journal = self.seed_prior(state)
            db_path = root / 'knowledge.sqlite'
            old_q, old_a = 'Fixture previous question', 'Fixture previous answer'
            old_frame = qa.native.full_turn_episode(old_q, old_a)
            old_sha = qa.digest(('M1|' + old_frame).encode())
            answer = 'Процесс использует ' + qa.MODEL_REFERENCE
            frame = qa.native.full_turn_episode(qa.QUESTION, answer)
            new_sha = qa.digest(('M1|' + frame).encode()); exchange = 'S03-fixture-complete'
            with sqlite3.connect(db_path) as db:
                db.executescript('''CREATE TABLE nox_v29_dialogs(dialog_id TEXT, owner TEXT, title TEXT,
                    archived INTEGER, revision INTEGER, created_at TEXT, updated_at TEXT);
                    CREATE TABLE nox_v29_dialog_messages(row_id INTEGER PRIMARY KEY, dialog_id TEXT,
                    exchange_id TEXT, role TEXT, content TEXT, ts TEXT);
                    CREATE TABLE s03_items(id TEXT, segment TEXT, provenance TEXT, sha256 TEXT, text TEXT);''')
                db.execute('INSERT INTO nox_v29_dialogs VALUES(?,?,?,?,?,?,?)',
                    (qa.DIALOG, 'nox-single-owner', 'Synthetic QA', 0, 2, 'old', 'old'))
                db.executemany('INSERT INTO nox_v29_dialog_messages VALUES(?,?,?,?,?,?)',
                    [(10, qa.DIALOG, qa.OLD_EXCHANGE, 'user', old_q, 'old'),
                     (11, qa.DIALOG, qa.OLD_EXCHANGE, 'assistant', old_a, 'old')])
                db.execute('INSERT INTO s03_items VALUES(?,?,?,?,?)',
                    (qa.OLD_EXCHANGE, 'M1', 'chat_turn', old_sha, old_frame))
            binding = {'dev': db_path.stat().st_dev, 'ino': db_path.stat().st_ino}
            for name, value in [('ROOT', root), ('SCRIPTS', scripts), ('STATE', state)]:
                stack.enter_context(patch.object(qa.native, name, value))
            stack.enter_context(patch.object(qa, 'DB', db_path))
            stack.enter_context(patch.object(qa, 'COUNTER', counter))
            stack.enter_context(patch.object(qa, 'OLD_RECORD_SHA', old_sha))
            before_sql = qa.own_database_snapshot(binding)
            stack.enter_context(patch.object(qa, 'PRIOR_PREFIX_SHA', qa.digest(qa.canonical(before_sql['rows']))))
            clock = {'now': time.time(), 'elapsed': 0.0, 'login': None, 'initial_last': None}
            def stamp(epoch):
                return datetime.fromtimestamp(epoch, timezone(timedelta(hours=1))).strftime('%Y-%m-%d %H:%M:%S %Z')
            def update_priority():
                active = clock['login'] is not None and clock['now'] - clock['login'] < 180
                values = {'CHAT_ACTIVE': b'1' if active else b'0',
                    'MODE': b'ACTIVE' if active else b'IDLE',
                    'status.json': qa.canonical({'mode': 'ACTIVE' if active else 'IDLE',
                        'train_pause': active, 'idle_threshold_min': 3,
                        'last_owner_chat': stamp(clock['login']) if clock['login'] is not None else None})}
                for name, raw in values.items():
                    file = priority / name
                    file.write_bytes(raw); file.chmod(0o600)
                    os.utime(file, (clock['now'], clock['now']))
            update_priority()
            original_waiter = qa.LoginIdleWait
            def fake_sleep(seconds):
                clock['now'] += seconds; clock['elapsed'] += seconds; update_priority()
            def waiter_factory(*args, **kwargs):
                return original_waiter(*args, **kwargs, clock=lambda: clock['now'],
                    monotonic=lambda: clock['elapsed'], sleep=fake_sleep)
            stack.enter_context(patch.object(qa, 'LoginIdleWait', side_effect=waiter_factory))
            native_idle_calls = []
            def owner_idle_fixture():
                qa.native.global_stop_guard()
                self.assertEqual((priority / 'MODE').read_bytes(), b'IDLE')
                self.assertEqual((priority / 'CHAT_ACTIVE').read_bytes(), b'0')
                self.assertFalse(json.loads((priority / 'status.json').read_bytes())['train_pause'])
                native_idle_calls.append(clock['elapsed'])
                return {'fixture_authoritative_idle': True}
            stack.enter_context(patch.object(qa.native, 'owner_idle', side_effect=owner_idle_fixture))
            stack.enter_context(patch.object(qa.native, 'maintenance_lease', return_value=contextlib.nullcontext(lease_pin)))
            # Only native deployment context/pin is replaced by local TempFS.
            original_require = qa.require
            def local_context(condition, code):
                if code in ('HOLD_OWNER_CONTEXT', 'HOLD_MAINTENANCE_LOCK_PIN'): return
                return original_require(condition, code)
            stack.enter_context(patch.object(qa, 'require', side_effect=local_context))
            stack.enter_context(patch.object(qa.native, 'checked_directory', return_value=None))
            stack.enter_context(patch.object(qa.native, 'WORKSPACE_STOP', root / 'NOX_STOP'))
            identity = {'process': {'pid': 123, 'start_ticks': 456, 'state': 'S'}}
            stack.enter_context(patch.object(qa.native, 'service_identity', return_value=identity))
            stack.enter_context(patch.object(qa.native, 'process', return_value=identity['process']))
            stack.enter_context(patch.object(qa.native, 'require_same_service', return_value=None))
            stack.enter_context(patch.object(qa.native, 'resolve_password_path', return_value=credential))
            stack.enter_context(patch.object(qa, 'source_readback', return_value=({}, {'chat_proxy.py': b'', 'common.py': b''})))
            stack.enter_context(patch.object(qa, 'installed_release', return_value={'fixture': True}))
            stack.enter_context(patch.object(qa, 'database_binding', return_value=binding))
            menu = b'FIXTURE_MENU'.ljust(43021, b' ')
            stack.enter_context(patch.object(qa, 'MENU_SHA', qa.digest(menu)))
            fixture = self
            class Response(io.BytesIO):
                status = 200
                headers = {'Content-Type': 'text/event-stream'}
            class FakeClient:
                def __init__(self):
                    self.jar = [object()]
                    self.counts = {'login_post': 0, 'model_post': 0, 'dialog_create_post': 0, 'get': 0}
                def raw(self, route, data=None, limit=32768):
                    if route == '/chat/login':
                        self.counts['login_post'] += 1
                        fixture.assertEqual(self.counts['login_post'], 1)
                        clock['login'] = int(clock['now'])
                        line = datetime.fromtimestamp(clock['login'], timezone.utc).strftime('%Y-%m-%d %H:%M:%S %z')
                        with log.open('ab') as output: output.write((line + ' chat_login_ok ip=127.0.0.1\n').encode())
                        update_priority(); return b'{}'
                    fixture.assertEqual(route, qa.MENU_PATH); self.counts['get'] += 1
                    return menu
                def json(self, route):
                    fixture.assertEqual(route, qa.HISTORY_PATH); self.counts['get'] += 1
                    snap = qa.own_database_snapshot(binding)
                    return {'status': 'READY', 'dialog_id': qa.DIALOG, 'revision': snap['dialog'][4],
                        'messages': [{'role': r[1], 'content': r[2], 'ts': r[3], 'exchange_id': r[4]} for r in snap['rows']]}
                def request(self, route, data):
                    fixture.assertEqual(route, '/api/nox/chat')
                    fixture.assertEqual(data['request_id'], 'model-reference-' + '7' * 32)
                    fixture.assertTrue((path / qa.CONTINUATION / 'model_post_intent.json').is_file())
                    fixture.assertGreaterEqual(clock['elapsed'], 182)
                    self.counts['model_post'] += 1; fixture.assertEqual(self.counts['model_post'], 1)
                    with sqlite3.connect(db_path) as db:
                        db.executemany('INSERT INTO nox_v29_dialog_messages VALUES(?,?,?,?,?,?)',
                            [(12, qa.DIALOG, exchange, 'user', qa.QUESTION, 'new'),
                             (13, qa.DIALOG, exchange, 'assistant', answer, 'new')])
                        db.execute('UPDATE nox_v29_dialogs SET revision=3')
                        db.execute('INSERT INTO s03_items VALUES(?,?,?,?,?)', (exchange, 'M1', 'chat_turn', new_sha, frame))
                    counter.write_bytes(after_counter)
                    frames = [{'type': 'context'}, {'type': 'meta', 'dialog_id': qa.DIALOG},
                        {'type': 'token', 't': answer}, {'type': 'done', 'status': 'done', 'saved': True,
                         's03_integrated': True, 'exchange_id': exchange,
                         's03_readback': 'FULL_QUESTION_AND_ANSWER_SUBSTRINGS',
                         's03_proof': 'M1_LENGTH_FRAMED_V2_SHA256', 's03_record_sha256': new_sha}]
                    return Response(b''.join(b'data: ' + qa.canonical(f) + b'\n\n' for f in frames))
            stack.enter_context(patch.object(qa, 'Client', FakeClient))
            stack.enter_context(patch.dict(os.environ, NOX_OWNER_REQUEST_ID='1003', NOX_OWNER_SOURCE_SHA='e' * 40))
            result = qa.run()
            self.assertTrue(result['completed'], result)
            self.assertEqual(result['http_counts'], {'login_post': 1, 'model_post': 1, 'dialog_create_post': 0, 'get': 3})
            self.assertEqual(result['owner_chat_posts_across_known_attempts'], 1)
            self.assertEqual(native_idle_calls, [0.0, 182.0, 182.0])
            for field, expected_raw, filename in (
                    ('counter_before_send', before_counter, 'counter_before.json'),
                    ('counter_after_persistence', after_counter, 'counter_after.json')):
                projection = result[field]
                self.assertEqual(projection['sha256'], qa.digest(expected_raw))
                self.assertEqual(projection['bytes'], len(expected_raw))
                self.assertEqual(projection['extra_key_count'], 3)
                self.assertFalse(projection['writer_key_present'])
                self.assertFalse(projection['activity_schema_key_present'])
                self.assertFalse(projection['raw_contents_exported'])
                self.assertNotIn('legacy_counter_has_writer_identity', projection)
                evidence = path / qa.CONTINUATION / filename
                evidence_bytes = evidence.read_bytes()
                self.assertEqual(json.loads(evidence_bytes)['raw_utf8'].encode(), expected_raw)
                self.assertEqual(evidence.stat().st_mode & 0o777, 0o600)
                self.assertEqual(projection['private_evidence']['sha256'], qa.digest(evidence_bytes))
                self.assertEqual(projection['private_evidence']['metadata']['ino'], evidence.stat().st_ino)
                self.assertTrue(projection['private_evidence']['readback_exact'])
            self.assertEqual(result['counter_before_send']['inflight'], 9)
            self.assertEqual(result['counter_observation']['numeric_delta'], 0)
            self.assertFalse(result['counter_observation']['expected_value_assigned'])
            self.assertEqual(result['idle_wait']['login_markers'], 1)
            self.assertEqual(result['idle_wait']['elapsed_seconds'], 182)
            self.assertTrue(result['history_and_s03']['full_frame_verified'])
            self.assert_old_unchanged(path, old_journal)
            self.assertEqual(json.loads((path / qa.CONTINUATION / 'outcome.json').read_bytes()), result)
            self.assertNotIn(old_a, json.dumps(result)); self.assertNotIn('synthetic-only', json.dumps(result))
            self.assertNotIn('fixture-private-old-state', json.dumps(result))
            self.assertNotIn('legacy_extra', json.dumps(result))
            self.assertFalse(result['unknown_delivery_possible'])
            # Presence is observed, not equated with a trustworthy identity.
            extra = json.loads(after_counter); extra.update(writer=None, activity_schema='fixture')
            counter.write_bytes(qa.canonical(extra))
            _, observed = qa.counter_snapshot()
            self.assertTrue(observed['writer_key_present'])
            self.assertTrue(observed['activity_schema_key_present'])


if __name__ == '__main__':
    unittest.main()
