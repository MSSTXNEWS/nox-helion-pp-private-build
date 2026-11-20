"""NOX E02 C6: fast deterministic regression for same-second chat ordering.
Original SQLite file bytes are not migrated; tests use isolated temporary databases.
"""
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from p02_runtime import P02Store, P02Error


class SameSecondHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = sqlite3.connect(self.root / "history.sqlite")
        self.store = P02Store(self.db, self.root / "attachments")
        self.store.initialize()
        self.store.create_chat("t", "alice", "c")

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def insert(self, *items, chat="c", epoch=1000):
        for ident, role, content in items:
            self.db.execute("INSERT INTO p02_messages(id, chat_id, role, content, created_at) VALUES(?,?,?,?,?)",
                            (ident, chat, role, content, epoch))
        self.db.commit()

    def texts(self, limit=250, chat="c"):
        return [x["content"] for x in self.store.history("t", "alice", chat, limit)]

    def test_01_random_uuid_is_not_a_valid_time_tiebreak(self):
        self.insert(("f"*32, "user", "first"), ("0"*32, "assistant", "second"))
        self.assertEqual(self.texts(), ["first", "second"])

    def test_02_several_roles_in_one_second_preserve_insertion(self):
        self.insert(("f"*32, "user", "prompt"), ("b"*32, "tool", "retrieval"),
                    ("0"*32, "assistant", "answer"))
        self.assertEqual(self.texts(), ["prompt", "retrieval", "answer"])

    def test_03_limit_selects_last_insertion_not_lexicographic_id(self):
        self.insert(("f"*32, "user", "one"), ("c"*32, "assistant", "two"),
                    ("b"*32, "user", "three"), ("0"*32, "assistant", "four"))
        self.assertEqual(self.texts(limit=2), ["three", "four"])

    def test_04_history_is_stable_after_database_reopen(self):
        self.insert(("f"*32, "user", "first"), ("0"*32, "assistant", "second"))
        self.db.close()
        self.db = sqlite3.connect(self.root / "history.sqlite")
        self.store = P02Store(self.db, self.root / "attachments")
        self.store.initialize()
        self.assertEqual(self.texts(), ["first", "second"])

    def test_05_chat_scope_does_not_leak_foreign_rows(self):
        self.store.create_chat("t", "alice", "other")
        self.insert(("f"*32, "user", "one"), ("0"*32, "assistant", "two"))
        self.insert(("a"*32, "user", "other chat"), chat="other")
        self.assertEqual(self.texts(), ["one", "two"])
        self.assertEqual(self.texts(chat="other"), ["other chat"])

    def test_06_acl_is_applied_even_with_shared_timestamp(self):
        self.insert(("f"*32, "user", "private"))
        with self.assertRaises(PermissionError):
            self.store.history("t", "mallory", "c")

    def test_07_pruning_older_seconds_preserves_surviving_order(self):
        self.insert(("f"*32, "user", "old"), epoch=999)
        self.insert(("d"*32, "user", "first"), ("0"*32, "assistant", "second"), epoch=1000)
        self.assertEqual(self.store.prune("t", "alice", "c", 1000), 1)
        self.assertEqual(self.texts(), ["first", "second"])

    def test_08_random_uuid_generation_same_second_from_real_api(self):
        with patch("p02_runtime.time.time", return_value=1234567890), \
                patch("p02_runtime.uuid.uuid4") as mock_uuid:
            mock_uuid.side_effect = [type("U", (), {"hex": "f"*32})(),
                                     type("U", (), {"hex": "0"*32})()]
            self.store.add_message("t", "alice", "c", "user", "prompt")
            self.store.add_message("t", "alice", "c", "assistant", "response")
        self.assertEqual(self.texts(), ["prompt", "response"])

    def test_09_without_rowid_existing_variant_is_held_without_repair(self):
        db = sqlite3.connect(":memory:")
        try:
            db.execute("CREATE TABLE p02_messages(id TEXT PRIMARY KEY,chat_id TEXT NOT NULL,role TEXT NOT NULL,content TEXT NOT NULL,created_at INTEGER NOT NULL) WITHOUT ROWID")
            db.execute("CREATE TABLE p02_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            db.execute("INSERT INTO p02_meta VALUES('schema','1')")
            db.commit()
            store = P02Store(db, self.root / "other_attachments")
            with self.assertRaises(P02Error):
                store.initialize()
            self.assertEqual(db.execute("SELECT count(*) FROM p02_messages").fetchone(), (0,))
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

class InputFailClosedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = sqlite3.connect(":memory:")
        self.store = P02Store(self.conn, Path(self.tmp.name) / "attachments")
        self.store.initialize()
        self.store.create_chat("tenant", "alice", "chat")
        self.store.add_message("tenant", "alice", "chat", "user", "Keep me")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_10_bool_limit_rejected(self):
        with self.assertRaises(ValueError):
            self.store.history("tenant", "alice", "chat", True)
        self.assertEqual(len(self.store.history("tenant", "alice", "chat")), 1)

    def test_11_millisecond_retention_cutoff_rejected_without_loss(self):
        with self.assertRaises(ValueError):
            self.store.prune("tenant", "alice", "chat", 9999999999999)
        self.assertEqual(len(self.store.history("tenant", "alice", "chat")), 1)

    def test_12_bool_retention_cutoff_rejected(self):
        with self.assertRaises(ValueError):
            self.store.prune("tenant", "alice", "chat", True)
        self.assertEqual(len(self.store.history("tenant", "alice", "chat")), 1)

    def test_13_control_character_scope_rejected(self):
        for invalid in ("\x00", "\x1f", " \t "):
            with self.subTest(invalid=repr(invalid)):
                with self.assertRaises(ValueError):
                    self.store.history("tenant", "alice", invalid)
        self.assertEqual(len(self.store.history("tenant", "alice", "chat")), 1)
