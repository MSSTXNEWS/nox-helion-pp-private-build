"""Corrupt/foreign SQLite schema admission preserves existing tables and data."""
import pathlib
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from p02_runtime import P02Store, P02Error


class SchemaAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.store = P02Store(self.db, self.tmp.name)
        self.store.initialize()
        self.store.create_chat('t', 'u', 'c')

    def assert_rejected_without_repair(self, code):
        before = self.db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall()
        with self.assertRaisesRegex(P02Error, code): self.store.initialize()
        self.assertEqual(self.db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall(), before)
        self.assertEqual(self.db.execute('SELECT id,tenant,principal FROM p02_chats').fetchall(), [('c','t','u')])

    def test_partial_unique_storage_is_not_global_blob_ownership(self):
        with self.db:
            self.db.execute('DROP TABLE p02_attachments')
            self.db.execute('''CREATE TABLE p02_attachments(
                id TEXT PRIMARY KEY, chat_id TEXT NOT NULL REFERENCES p02_chats(id) ON DELETE CASCADE,
                storage TEXT NOT NULL, sha256 TEXT NOT NULL, mime TEXT NOT NULL,
                bytes INTEGER NOT NULL CHECK(bytes > 0), created_at INTEGER NOT NULL)''')
            self.db.execute("CREATE UNIQUE INDEX partial_storage ON p02_attachments(storage) WHERE chat_id='restricted'")
        self.store = P02Store(self.db, self.tmp.name,
                              approved_host_tables=frozenset({'partial_storage'}))
        self.assert_rejected_without_repair('STORAGE_UNIQUENESS')

    def test_composite_message_primary_key_is_not_unique_message_id(self):
        with self.db:
            self.db.execute('DROP TABLE p02_messages')
            self.db.execute('''CREATE TABLE p02_messages(
                id TEXT NOT NULL, chat_id TEXT NOT NULL REFERENCES p02_chats(id) ON DELETE CASCADE,
                role TEXT NOT NULL, content TEXT NOT NULL, created_at INTEGER NOT NULL,
                PRIMARY KEY(id,chat_id))''')
        self.assert_rejected_without_repair('PRIMARY_KEY_DRIFT')

    def test_original_global_constraints_remain_accepted(self):
        self.store.initialize()
        self.store.add_message('t','u','c','user','preserved')
        self.store.initialize()
        self.assertEqual(self.store.history('t','u','c')[0]['content'], 'preserved')


if __name__ == '__main__': unittest.main()
