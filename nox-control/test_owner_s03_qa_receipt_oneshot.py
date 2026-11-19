from datetime import datetime, timezone
import json
import sqlite3
import unittest
from unittest.mock import patch

import owner_s03_qa_receipt_oneshot as probe


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.executescript('''
            CREATE TABLE nox_v29_dialogs(dialog_id, owner, archived, title);
            CREATE TABLE nox_chat_received_goals(dialog_id, owner, request_id, received_at,
                s03_record_id, s03_sha256, resolved_by_request_id, state, question_sha256, question);
            CREATE TABLE s03_items(id, segment, provenance, text, meta, sha256);
            CREATE TABLE nox_v29_dialog_messages(dialog_id, exchange_id, role, content);
        ''')
        self.dialog, self.request = 'a' * 32, 'b' * 32
        self.answer = 'A synthetic answer.'
        self.event = datetime.fromtimestamp(1795113250, timezone.utc)
        self.db.execute('INSERT INTO nox_v29_dialogs VALUES(?,?,?,?)',
                        (self.dialog, probe.OWNER, 0, probe.TITLES[0]))
        self.db.executemany('INSERT INTO nox_v29_dialog_messages VALUES(?,?,?,?)', (
            (self.dialog, 'S03-test', 'user', probe.QUESTION),
            (self.dialog, 'S03-test', 'assistant', self.answer)))
        self.db.execute('INSERT INTO nox_chat_received_goals VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (self.dialog, probe.OWNER, self.request, self.event.isoformat(), 'S03-test',
                         'c' * 64, self.request, 'RESPONSE_COMMITTED',
                         probe.digest(probe.QUESTION.encode()), probe.QUESTION))

    def manifest(self, dialog, request, question, answer, event):
        self.assertEqual((dialog, request, question, answer, event),
                         (self.dialog, self.request, probe.QUESTION, self.answer, self.event))
        return 'S03-test', 'private-content', 'c' * 64, 'private-meta'

    def add_canonical_item(self):
        self.db.execute('INSERT INTO s03_items VALUES(?,?,?,?,?,?)',
                        ('S03-test', 'M1', 'chat_turn_scoped_v3', 'private-content', 'private-meta', 'c' * 64))

    def test_owner_history_without_s03_does_not_pass(self):
        with patch.object(probe, 'ANSWER_SHA', probe.digest(self.answer.encode())):
            with self.assertRaisesRegex(RuntimeError, 'OWNER_PAIR_UNPROVEN'):
                probe.verify(self.db, self.manifest)

    def test_exact_manifest_returns_only_hashes(self):
        self.add_canonical_item()
        with patch.object(probe, 'ANSWER_SHA', probe.digest(self.answer.encode())):
            proof = probe.verify(self.db, self.manifest)
        self.assertTrue(proof['canonical_s03_write_verified'])
        self.assertNotIn('private', json.dumps(proof))

    def test_wrong_answer_or_companion_record_does_not_pass(self):
        self.add_canonical_item()
        with self.assertRaisesRegex(RuntimeError, 'OWNER_PAIR_UNPROVEN'):
            probe.verify(self.db, self.manifest)
        self.db.execute("UPDATE s03_items SET text='changed'")
        with patch.object(probe, 'ANSWER_SHA', probe.digest(self.answer.encode())):
            with self.assertRaisesRegex(RuntimeError, 'MANIFEST'):
                probe.verify(self.db, self.manifest)


if __name__ == '__main__':
    unittest.main()
