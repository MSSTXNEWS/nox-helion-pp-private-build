"""R64 source QA: NOX global P02 on one original-v4 SQLite file."""
import os
from contextlib import closing
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

# The official production owner module is present ONLY in the SHA-pinned
# disposable original-source stage, never at checkout/source root.
STAGED = os.environ.get("NOX_R64_STAGED_ROOT", "")
if STAGED:
    stage = Path(STAGED)
    if not (stage / "helion/e06_native_stdio_owner.py").is_file():
        raise RuntimeError("NOX_R64_STAGED_OWNER_REQUIRED")
    sys.path.insert(0, str(stage))
    from helion.e06_native_stdio_owner import (
        ORIGINAL_V4_OBJECTS, admit_shared_p02_store,
        require_original_v4_before_store,
    )
else:
    ORIGINAL_V4_OBJECTS = frozenset()
    admit_shared_p02_store = None
    require_original_v4_before_store = None

# Initialize the REAL original Store. No hand-authored fake table/index layout.
if STAGED:
    from helion.storage import Store

@unittest.skipUnless(STAGED, "requires exact stage of approved original 729-file source")
class OriginalDbTest(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.path=Path(self.dir.name)/"helion.sqlite3"
        self.owner=Store(self.path, native_thread_safe=True)
        self.owner.add_task("preserve original task")
        self.assertEqual(self.owner.conn.execute("PRAGMA user_version").fetchone(), (4,))
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
        backup=self.path.with_name(self.path.name+".pre-p02-native.sqlite3")
        self.assertTrue(backup.is_file())
        with closing(sqlite3.connect(backup)) as read:
            self.assertEqual(read.execute("PRAGMA quick_check").fetchone(), ("ok",))
            self.assertEqual(read.execute("SELECT title FROM tasks").fetchone(), ("preserve original task",))
            self.assertEqual(read.execute("SELECT COUNT(*) FROM p02_chats").fetchone() if
                             "p02_chats" in [x[0] for x in read.execute(
                                 "SELECT name FROM sqlite_master WHERE type='table'")] else None, None)
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
    def test_existing_legacy_v3_denied_before_store_migration(self):
        self.owner.close()
        with closing(sqlite3.connect(self.path)) as raw:
            with raw:
                raw.execute("PRAGMA user_version=3")
        with self.assertRaisesRegex(RuntimeError, "PREEXISTING_DB_NOT_V4"):
            require_original_v4_before_store(self.path)
        with closing(sqlite3.connect(self.path)) as raw:
            self.assertEqual(raw.execute("PRAGMA user_version").fetchone(), (3,))
            self.assertEqual(raw.execute("SELECT title FROM tasks").fetchone(), ("preserve original task",))
        # Mark the already closed owner; tearDown does not reuse this connection.
        self.owner.conn=sqlite3.connect(":memory:")

    def test_new_db_and_real_v4_preflight(self):
        require_original_v4_before_store(self.path)
        require_original_v4_before_store(Path(self.dir.name)/"not-yet-created.sqlite3")

    def test_reopen_original_database_preserves_history(self):
        first=admit_shared_p02_store(self.owner,"owner")
        first.add_turn("local","owner","default","Persist","Confirmed")
        again=admit_shared_p02_store(self.owner,"owner")
        self.assertEqual(len(again.history("local","owner","default")),2)

if __name__=="__main__":
    unittest.main()
