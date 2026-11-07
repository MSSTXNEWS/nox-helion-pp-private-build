"""D05 R8 SOURCE_ONLY: ATLAS add receives a durable native owner receipt.

Run: python coordination/nox-r8/tests/test_r8_d05_task_add_durable_replay.py
No .NET, Windows, WebView2, owner SQLite or EXE acceptance is implied.
"""
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "overrides" / "src" /
          "MainWindow.xaml.cs").read_text(encoding="utf-8")
ADD = SOURCE.split("private long AddTask(", 1)[1].split(
    "private void HandleTaskToggle(", 1)[0]
HANDLE = SOURCE.split("private void HandleTaskAdd(", 1)[1].split(
    "private void HandleNoteAdd(", 1)[0]


class DurableAtlasAddReceipt(unittest.TestCase):
    def test_schema_migration_runs_under_existing_no_loss_snapshot(self):
        needed = SOURCE.split("string[] needed = {", 1)[1].split("};", 1)[0]
        self.assertIn('"task_add_receipts"', needed)
        self.assertLess(SOURCE.index("CheckpointSqlite(db, \"PRE_SCHEMA_BOOTSTRAP\")"),
                        SOURCE.index("CREATE TABLE IF NOT EXISTS task_add_receipts"))
        self.assertIn("PRIMARY KEY(owner_sid,request_id)", SOURCE)

    def test_native_owner_replay_check_precedes_any_insert(self):
        self.assertIn("string ownerSid = OwnerSid()", ADD)
        self.assertIn("SELECT task_id FROM task_add_receipts WHERE owner_sid=$sid AND request_id=$rid", ADD)
        self.assertIn("TaskAddReplayException", ADD)
        self.assertLess(ADD.index("SELECT task_id FROM task_add_receipts"),
                        ADD.index("INSERT INTO tasks(created_at,title)"))
        self.assertLess(ADD.index("INSERT INTO tasks(created_at,title)"),
                        ADD.index("INSERT INTO task_add_receipts(owner_sid,request_id,task_id,title)"))
        self.assertLess(ADD.index("INSERT INTO task_add_receipts(owner_sid,request_id,task_id,title)"),
                        ADD.index("tx.Commit()"))

    def test_ack_after_independent_joint_readback(self):
        self.assertIn("id = AddTask(title, requestId)", HANDLE)
        self.assertIn("catch (TaskAddReplayException ex)", HANDLE)
        self.assertIn('Send("tasks.add.uncertain"', HANDLE)
        self.assertIn("JOIN task_add_receipts r ON r.task_id=t.id", HANDLE)
        self.assertIn("r.owner_sid=$sid AND r.request_id=$rid", HANDLE)
        self.assertLess(HANDLE.index("JOIN task_add_receipts"),
                        HANDLE.index('Send("tasks.add.receipt"'))

    def test_sqlite_receipt_stops_duplicate_across_connections_and_restart(self):
        match = re.search(r"CREATE TABLE IF NOT EXISTS task_add_receipts[^;]*;", SOURCE)
        self.assertIsNotNone(match)
        create_receipt = match.group(0)
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "owner.sqlite3")
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, title TEXT NOT NULL, complete INTEGER NOT NULL DEFAULT 0)")
                db.execute(create_receipt)
                with db:
                    db.execute("INSERT INTO tasks(created_at,title) VALUES(?,?)",
                               ("2026-11-08T00:00:00Z", "sample owner task"))
                    task_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
                    db.execute("INSERT INTO task_add_receipts(owner_sid,request_id,task_id,title) VALUES($sid,$rid,$id,$title)",
                               {"sid": "S-1-5-21-local-owner", "rid": "stableRequest_A1", "id": task_id, "title": "sample owner task"})
                saved = db.execute("SELECT t.title FROM tasks t JOIN task_add_receipts r ON r.task_id=t.id WHERE t.id=$id AND r.owner_sid=$sid AND r.request_id=$rid AND r.title=$title",
                                   {"id": task_id, "sid": "S-1-5-21-local-owner",
                                    "rid": "stableRequest_A1", "title": "sample owner task"}).fetchone()
                self.assertEqual(saved, ("sample owner task",))
            with sqlite3.connect(path) as restarted:
                existing = restarted.execute(
                    "SELECT task_id FROM task_add_receipts WHERE owner_sid=$sid AND request_id=$rid",
                    {"sid": "S-1-5-21-local-owner", "rid": "stableRequest_A1"}).fetchone()
                self.assertEqual(existing, (task_id,))
                self.assertEqual(restarted.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 1)
                self.assertEqual(restarted.execute("SELECT COUNT(*) FROM task_add_receipts").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
