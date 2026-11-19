"""CPU-only S03 receipt/readback tests; no native runtime or model access."""
from contextlib import nullcontext
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pass49" / "role3"))
from s03_existing_readback import read_existing_exchange

DIALOG = 'a' * 32
EXCHANGE = 'native-exchange'


class S03ReadbackContractTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.executescript('''
            CREATE TABLE nox_v29_dialogs(dialog_id TEXT PRIMARY KEY, owner TEXT, archived INTEGER);
            CREATE TABLE nox_v29_dialog_messages(row_id INTEGER PRIMARY KEY, dialog_id TEXT,
                role TEXT, content TEXT, exchange_id TEXT);
        ''')
        self.db.execute('INSERT INTO nox_v29_dialogs VALUES (?,?,0)', (DIALOG,'nox-single-owner'))
        self.rows = [('user','Привет'),('assistant','Hola')]
        self.allowed = True

    def run_readback(self, *, rows=None, owner=None, durable=True, verified=True):
        for role, content in (self.rows if rows is None else rows):
            self.db.execute('INSERT INTO nox_v29_dialog_messages(dialog_id,role,content,exchange_id)'
                            'VALUES (?,?,?,?)', (DIALOG,role,content,EXCHANGE))
        if owner is not None:
            self.db.execute('UPDATE nox_v29_dialogs SET owner=?',(owner,))
        def lookup(dialog, turn, receipt, lease):
            return dict(dialog_id=dialog,turn_id=turn,receipt_id=receipt,
                        lease_epoch=lease,exchange_id=EXCHANGE,durable=durable,verified=verified)
        return read_existing_exchange(lambda:nullcontext(self.db),lookup,lambda:self.allowed,
                 dialog_id=DIALOG,turn_id='turn',receipt_id='proof',lease_epoch='lease')

    def test_verified_owner_pair(self):
        result=self.run_readback()
        self.assertEqual(result['status'],'READY')
        self.assertEqual([row['role'] for row in result['messages']], ['user','assistant'])

    def test_reject_reverse_order(self):
        self.assertIsNone(self.run_readback(rows=self.rows[::-1]))

    def test_reject_two_assistant_rows(self):
        self.assertIsNone(self.run_readback(rows=[('assistant','X'),('assistant','Y')]))

    def test_reject_blank_content(self):
        self.assertIsNone(self.run_readback(rows=[('user',' '),('assistant','Y')]))

    def test_reject_missing_or_extra_row(self):
        self.assertIsNone(self.run_readback(rows=self.rows[:1]))
        self.db.execute('DELETE FROM nox_v29_dialog_messages')
        self.assertIsNone(self.run_readback(rows=self.rows+[('assistant','Z')]))

    def test_reject_wrong_owner(self):
        self.assertIsNone(self.run_readback(owner='foreign'))

    def test_reject_undurable_receipt(self):
        self.assertIsNone(self.run_readback(durable=False))

    def test_reject_unverified_receipt(self):
        self.assertIsNone(self.run_readback(verified=False))

    def test_reject_revoked_permission(self):
        self.allowed=False
        self.assertIsNone(self.run_readback())

if __name__ == '__main__':
    unittest.main()
