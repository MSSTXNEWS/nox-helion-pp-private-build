"""XP03: a STOP/ACL/epoch revoke while writing CLAIM audit must rollback CLAIM.

Uses the existing OneHostStoreActor + NativeWorkQueue and an isolated fixture
with the ORIGINAL S03 tasks/audit column layout. No alternate runtime/DB service.
Run: PYTHONPATH=src python -m unittest tests.k02.test_xp03_native_claim_stop_atomic -v
SOURCE regression only; never represent this as installed Windows E07.
"""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from threading import Event

from nox_selfbuilder.onehost_store import OneHostStoreActor
from nox_selfbuilder.onehost_queue import NativeWorkQueue


class _OriginalS03Fixture:
    def __init__(self, path, on_claim):
        self.conn = sqlite3.connect(path)
        self.on_claim = on_claim
        self.conn.executescript("""CREATE TABLE tasks(id INTEGER PRIMARY KEY, title TEXT,
            created_at TEXT, updated_at TEXT);
            CREATE TABLE audit(id INTEGER PRIMARY KEY, item_id INTEGER,
            action TEXT, metadata TEXT, at TEXT);""")

    def _audit(self, action, item_id, metadata):
        self.conn.execute(
            "INSERT INTO audit(item_id,action,metadata,at) VALUES(?,?,?,?)",
            (item_id, action, json.dumps(metadata), "2026-11-02T00:00:00Z"))
        if action == "NOX_NATIVE_WORK_CLAIM":
            self.on_claim()  # deterministic revoke AFTER SQL INSERT / BEFORE COMMIT

    def close(self):
        self.conn.close()


class XP03NativeClaimAtomicity(unittest.TestCase):
    def _scenario(self, mode):
        scope = SimpleNamespace(tenant="local", principal="owner", chat_id="default")
        with tempfile.TemporaryDirectory() as td:
            stop = Event()
            acl = {"ok": True}
            epoch = {"value": 1}
            executed = []

            def on_claim():
                if mode == "STOP":
                    stop.set()
                elif mode == "ACL":
                    acl["ok"] = False
                elif mode == "EPOCH":
                    epoch["value"] += 1

            with OneHostStoreActor(
                lambda: _OriginalS03Fixture(Path(td) / "s03.sqlite3", on_claim)
            ) as actor:
                q = NativeWorkQueue(actor, authorize=lambda *_: acl["ok"],
                    stop_requested=stop.is_set, stop_epoch=lambda: epoch["value"])
                tid = q.enqueue(scope, kind="SELF_WRITE",
                    payload={"task": "native reviewed memory"},
                    permission="selfbuilder.propose")
                def authorized_callback():
                    executed.append(True)
                    return {"status": "SUCCESS"}
                try:
                    if mode == "OK":
                        q.submit_source(scope, tid, authorized_callback)
                    else:
                        with self.assertRaisesRegex(PermissionError,
                                                    "NATIVE_WORK_REVOKED"):
                            q.submit_source(scope, tid, authorized_callback)
                finally:
                    q.close(timeout=5)

                state = q.get(scope, tid)["state"]
                count = actor.call(lambda s: s.conn.execute(
                    "SELECT COUNT(*) FROM audit WHERE action='NOX_NATIVE_WORK_CLAIM'"
                ).fetchone()[0])
                if mode == "OK":
                    self.assertEqual((count, len(executed), state),
                                     (1, 1, "SUCCESS"))
                else:
                    # No committed unauthorized CLAIM and no callback execution.
                    self.assertEqual((count, executed, state), (0, [], "QUEUED"))

    def test_acl_revoked_inside_claim_transaction(self):
        self._scenario("ACL")

    def test_stop_during_claim_audit(self):
        self._scenario("STOP")

    def test_epoch_bumped_during_claim_audit(self):
        self._scenario("EPOCH")

    def test_consented_claim_still_executes(self):
        self._scenario("OK")


if __name__ == "__main__":
    unittest.main()
