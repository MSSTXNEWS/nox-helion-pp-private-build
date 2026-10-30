"""R64 source QA: NOX global P02 on one original-v4 SQLite file."""
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from p02_runtime import P02Store
from helion.e06_native_stdio_owner import (
    ORIGINAL_V4_OBJECTS, admit_shared_p02_store,
)

class ApprovedOriginal:
    def __init__(self, file):
        self.path=file
        self.conn=sqlite3.connect(str(file), check_same_thread=False)
        for n in ORIGINAL_V4_OBJECTS:
            if n.startswith("ix_"):
                continue
            self.conn.execute(f'CREATE TABLE "{n}" (id INTEGER)')
        for n in ORIGINAL_V4_OBJECTS:
            if n.startswith("ix_"):
                self.conn.execute(f'CREATE INDEX "{n}" ON tasks(id)')
        self.conn.execute("PRAGMA user_version=4")
        self.conn.commit()

class OriginalDbTest(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.path=Path(self.dir.name)/"helion.sqlite3"
        self.owner=ApprovedOriginal(self.path)
    def tearDown(self):
        self.owner.conn.close()
        self.dir.cleanup()
    def test_original_v4_one_file_shared_p02_chat(self):
        original=self.owner.conn
        store=admit_shared_p02_store(self.owner,"owner")
        self.assertIs(store.db,original)
        self.assertEqual(original.execute("PRAGMA user_version").fetchone(),(4,))
        store.add_turn("local","owner","default","Hi","Hello")
        self.assertEqual(len(store.history("local","owner","default")),2)
        self.assertTrue((self.path.with_name(self.path.name+".pre-p02-native.sqlite3")).is_file())
    def test_unknown_original_object_fails_before_p02_schema(self):
        self.owner.conn.execute('CREATE TABLE unexpected_secret(id INTEGER)')
        with self.assertRaisesRegex(RuntimeError,"UNRECOGNIZED_OBJECTS"):
            admit_shared_p02_store(self.owner,"owner")
        self.assertNotIn("p02_chats",[r[0] for r in self.owner.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")])
    def test_legacy_version_mismatch_fails_closed(self):
        self.owner.conn.execute("PRAGMA user_version=3")
        with self.assertRaisesRegex(RuntimeError,"V4_SCHEMA_REQUIRED"):
            admit_shared_p02_store(self.owner,"owner")
    def test_reopen_original_database_preserves_history(self):
        first=admit_shared_p02_store(self.owner,"owner")
        first.add_turn("local","owner","default","Persist","Confirmed")
        again=admit_shared_p02_store(self.owner,"owner")
        self.assertEqual(len(again.history("local","owner","default")),2)

if __name__=="__main__":
    unittest.main()
