"""3A02: observed revocation before the SQL read must prevent that read."""
from contextlib import contextmanager
import sqlite3
import unittest

from s03_existing_readback import read_existing_exchange


class RevokedReadbackTests(unittest.TestCase):
    def setUp(self):
        self.allowed = True
        self.queries = 0
        self.opened = 0
        self.dialog = 'a' * 32
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.executescript('''
            CREATE TABLE nox_v29_dialogs(dialog_id TEXT,owner TEXT,archived INTEGER);
            CREATE TABLE nox_v29_dialog_messages(row_id INTEGER PRIMARY KEY,
                dialog_id TEXT,role TEXT,content TEXT,exchange_id TEXT);
        ''')
        self.db.execute('INSERT INTO nox_v29_dialogs VALUES(?,?,0)',
                        (self.dialog,'nox-single-owner'))
        for role, content in [('user','Question'),('assistant','Answer')]:
            self.db.execute('INSERT INTO nox_v29_dialog_messages(dialog_id,role,content,exchange_id) VALUES(?,?,?,?)',
                            (self.dialog,role,content,'exchange-1'))

    def run_read(self, revoke_at=None):
        owner = self
        class ReadConnection:
            def execute(self, *args):
                owner.queries += 1
                return owner.db.execute(*args)
        @contextmanager
        def connect():
            self.opened += 1
            if revoke_at == 'connect': self.allowed = False
            yield ReadConnection()
            if revoke_at == 'close': self.allowed = False
        def locate(dialog, turn, receipt, lease):
            if revoke_at == 'receipt': self.allowed = False
            return dict(dialog_id=dialog,turn_id=turn,receipt_id=receipt,
                        lease_epoch=lease,durable=True,verified=True,exchange_id='exchange-1')
        return read_existing_exchange(connect, locate, lambda:self.allowed,
                                      dialog_id=self.dialog,turn_id='turn-1',
                                      receipt_id='receipt-1',lease_epoch='epoch-1')

    def test_revoked_during_connection_entry_never_issues_sql(self):
        self.assertIsNone(self.run_read('connect'))
        self.assertEqual(self.opened, 1)
        self.assertEqual(self.queries, 0)

    def test_revoked_during_receipt_lookup_never_opens_database(self):
        self.assertIsNone(self.run_read('receipt'))
        self.assertEqual((self.opened, self.queries), (0, 0))

    def test_revoked_on_close_never_returns_rows(self):
        self.assertIsNone(self.run_read('close'))
        self.assertEqual(self.queries, 1)

    def test_authorized_exact_exchange_still_reads_pair(self):
        result = self.run_read()
        self.assertEqual(result['status'], 'READY')
        self.assertEqual([x['role'] for x in result['messages']], ['user', 'assistant'])
        self.assertEqual(self.queries, 1)


if __name__ == '__main__': unittest.main()
