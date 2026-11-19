"""A0 1A02: exact durable S03 request-id context fence regression.

Run: python -m unittest -v test_owner_chat_request_scope.py
Source-only SQLite in tempfile. No OneHost, no GPU, no external database.
"""
import contextlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import owner_chat_request_ledger as target


class TestOwnerChatRequestScope(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'original-s03-fixture.sqlite3'
        with self.open_db(True) as conn:
            conn.executescript(target.SCHEMA)
        self.ledger=target.RequestLedger(self.open_db,'nox-single-owner')
        self.identity_patch=patch.object(target,'identity',
                                         lambda pid=None:(501,123,'fixture-boot'))
        self.identity_patch.start()
        self.addCleanup(self.identity_patch.stop)
        self.rid='owner-request-123456'
        self.question='Проверка памяти'
        self.payload={'message':self.question,'dialog_id':None,'history':[]}
        self.scope='session-original'

    @contextlib.contextmanager
    def open_db(self,write=False):
        conn=sqlite3.connect(self.path,timeout=2)
        conn.row_factory=sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def admitted(self,**changes):
        arguments=dict(rid=self.rid,question=self.question,dialog_id=None,
                       payload=self.payload,session_scope=self.scope)
        arguments.update(changes)
        return self.ledger.accept(**arguments)

    def assert_context_fence(self,**changes):
        with self.assertRaises(target.LedgerError) as result:
            self.admitted(**changes)
        self.assertEqual(result.exception.code,'REQUEST_ID_CONTEXT_CONFLICT')
        # A rejected collision cannot modify, complete, or stop original work.
        snapshot=self.ledger.snapshot(self.rid)
        self.assertEqual(snapshot['state'],'accepted')
        self.assertEqual(snapshot['last_event_id'],1)
        self.assertFalse(snapshot['stop_requested'])

    def test_same_session_exact_retry_is_idempotent(self):
        accepted,token=self.admitted()
        self.assertIsInstance(token,str)
        replay,second=self.admitted()
        self.assertIsNone(second)
        self.assertEqual(replay['exchange_id'],accepted['exchange_id'])
        self.assertEqual(replay['last_event_id'],accepted['last_event_id'])

    def test_foreign_session_cannot_replay_exact_same_payload(self):
        self.admitted()
        self.assert_context_fence(session_scope='session-foreign')

    def test_foreign_dialog_cannot_alias_existing_id(self):
        self.admitted()
        self.assert_context_fence(dialog_id='a'*32)

    def test_foreign_question_cannot_alias_existing_id(self):
        self.admitted()
        self.assert_context_fence(question='Другое сообщение')

    def test_changed_payload_preserves_original_request(self):
        self.admitted()
        with self.assertRaises(target.LedgerError) as result:
            self.admitted(payload={'message':'different','dialog_id':None,'history':[]})
        self.assertEqual(result.exception.code,'REQUEST_ID_PAYLOAD_CONFLICT')
        self.assertEqual(self.ledger.snapshot(self.rid)['last_event_id'],1)


if __name__=='__main__':
    unittest.main()
