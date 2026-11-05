"""Original S03/OneHost asynchronous RESULT must be atomic against native STOP.

Uses the original Python queue + original owning-thread actor and transient test
SQLite schema. It does NOT prove a real Windows SID, WPF callback or installed E07.
"""
from __future__ import annotations
import json
import sqlite3
import sys
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from nox_selfbuilder.onehost_queue import NativeWorkQueue
from nox_selfbuilder.onehost_store import OneHostStoreActor


@dataclass(frozen=True)
class Scope:
    tenant: str = "local"
    principal: str = "native-test"
    chat_id: str = "existing-default"


class OriginalSchemaTestStore:
    """Test instance only; the product continues using its existing S03 file."""
    def __init__(self, on_audit):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY, title TEXT, created_at TEXT, updated_at TEXT)")
        self.conn.execute("CREATE TABLE audit(id INTEGER PRIMARY KEY, item_id INTEGER, action TEXT, metadata TEXT, at TEXT)")
        self.on_audit = on_audit

    def _audit(self, action, item_id, data):
        at = datetime.now(timezone.utc).isoformat()
        self.conn.execute("INSERT INTO audit(item_id,action,metadata,at) VALUES (?,?,?,?)",
                          (item_id, action, json.dumps(data), at))
        self.on_audit(action, data)

    def close(self):
        self.conn.close()


class NativeResultStopAtomicity(unittest.TestCase):
    def setUp(self):
        self.scope = Scope()
        self.epoch = 0
        self.stopped = False
        self.allowed = True
        self.audit_hook = lambda _action, _data: None
        self.actor = OneHostStoreActor(lambda: OriginalSchemaTestStore(
            lambda action, data: self.audit_hook(action, data)))
        self.queue = NativeWorkQueue(self.actor,
            authorize=lambda scope, operation, data: self.allowed,
            stop_requested=lambda: self.stopped, stop_epoch=lambda: self.epoch)
        self.tid = self.queue.enqueue(self.scope, kind="SELF_WRITE",
                                      payload={"task": "existing native proposal"},
                                      permission="selfbuilder.propose")

    def tearDown(self):
        self.queue.close(timeout=5)
        self.actor.close(timeout=5)

    def run_native(self, callback):
        queued = self.queue.submit_source(self.scope, self.tid, callback)
        self.assertEqual(queued["status"], "QUEUED")
        self.queue.close(timeout=5)
        record = self.queue.get(self.scope, self.tid)
        states = self.actor.call(lambda store: [
            json.loads(raw)["state"] for (raw,) in store.conn.execute(
                "SELECT metadata FROM audit WHERE action='NOX_NATIVE_WORK_RESULT' ORDER BY id")])
        # Original StoreActor deliberately detaches cross-thread lists to immutable tuples.
        return record["state"], states

    def test_01_normal_completion_has_one_durable_result(self):
        self.assertEqual(self.run_native(lambda: {"status": "DONE"}), ("DONE", ("DONE",)))

    def test_02_stop_during_result_audit_rolls_back_done(self):
        def revoke(action, data):
            if action == "NOX_NATIVE_WORK_RESULT" and data["state"] == "DONE":
                self.epoch += 1
                self.stopped = True
        self.audit_hook = revoke
        self.assertEqual(self.run_native(lambda: {"status": "DONE"}), ("HOLD", ("HOLD",)))

    def test_03_consent_revoked_during_audit_rolls_back_done(self):
        def revoke(action, data):
            if action == "NOX_NATIVE_WORK_RESULT" and data["state"] == "DONE":
                self.allowed = False
        self.audit_hook = revoke
        self.assertEqual(self.run_native(lambda: {"status": "DONE"}), ("HOLD", ("HOLD",)))

    def test_04_stop_during_callback_never_persists_done(self):
        def task():
            self.epoch += 1
            self.stopped = True
            return {"status": "DONE"}
        self.assertEqual(self.run_native(task), ("HOLD", ("HOLD",)))


if __name__ == "__main__":
    unittest.main()
