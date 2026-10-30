"""NOX P02 atomic user/assistant turn · real SQLite, no second DB."""
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from p02_runtime import P02Store, Cancelled

class AtomicTurnTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=sqlite3.connect(":memory:",check_same_thread=False)
        self.store=P02Store(self.db,Path(self.tmp.name)/"att")
        self.store.initialize()
        self.store.create_chat("tenant","owner","conversation")
    def tearDown(self):
        self.db.close(); self.tmp.cleanup()

    def test_completed_turn_persists_ordered_pair(self):
        ids=self.store.add_turn("tenant","owner","conversation","User text","Assistant reply")
        self.assertEqual(len(set(ids)),2)
        self.assertEqual([(x["role"],x["content"]) for x in
                          self.store.history("tenant","owner","conversation")],
                         [("user","User text"),("assistant","Assistant reply")])

    def test_failed_assistant_insert_rolls_back_user(self):
        self.db.execute("""CREATE TRIGGER no_assistant BEFORE INSERT ON p02_messages
            WHEN NEW.role='assistant' BEGIN SELECT RAISE(ABORT,'blocked'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.add_turn("tenant","owner","conversation","orphan","fails")
        self.assertEqual(self.store.history("tenant","owner","conversation"),[])

    def test_stop_before_commit_does_not_persist(self):
        stop=threading.Event();stop.set()
        with self.assertRaises(Cancelled):
            self.store.add_turn("tenant","owner","conversation","orphan","reply",stop=stop)
        self.assertEqual(self.store.history("tenant","owner","conversation"),[])

    def test_wrong_principal_cannot_write(self):
        with self.assertRaises(PermissionError):
            self.store.add_turn("tenant","unauthorized","conversation","Private","reply")
        self.assertEqual(self.store.history("tenant","owner","conversation"),[])

if __name__=="__main__": unittest.main()
