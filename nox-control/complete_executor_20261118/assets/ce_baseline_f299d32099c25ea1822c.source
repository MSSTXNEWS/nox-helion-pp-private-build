"""Exchange receipts must describe the exact durable user/assistant sequence.

Standalone owner-reviewed regression for the existing S03/bridge interfaces.
It does not provide, import, or select an implementation of the requested fix.
"""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

import native_v29_full_bridge as bridge
from owner_chat_request_ledger import LedgerError, RequestLedger


DIALOG = "c" * 32
QUESTION = "Вопрос 🌌"
ANSWER = "Ответ — mañana"


class ExchangeReceiptOrderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "original-s03.sqlite"
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE s03_items(id TEXT PRIMARY KEY,sha256 TEXT,ts REAL,text TEXT)")
        replacement = patch.dict(sys.modules, s03_memory=types.SimpleNamespace(DB=self.path))
        replacement.start()
        self.addCleanup(replacement.stop)
        self.assertTrue(bridge.ensure_dialog_schema())
        with bridge._db(True) as db:
            db.execute("INSERT INTO nox_v29_dialogs VALUES(?,?,?,?,?,?,?)",
                       (DIALOG, bridge.OWNER, "receipt-order", 0, 7, bridge._now(), bridge._now()))
        self.ledger = RequestLedger(bridge._db, bridge.OWNER)

    def insert_pair(self, exchange, pairs):
        with bridge._db(True) as db:
            for role, content in pairs:
                db.execute("INSERT INTO nox_v29_dialog_messages(dialog_id,exchange_id,role,content,ts) "
                           "VALUES(?,?,?,?,?)", (DIALOG, exchange, role, content, bridge._now()))

    def durable_state(self):
        # Observe rows in their durable order, including identity and revision.
        with bridge._db() as db:
            return {
                "dialogs": [tuple(r) for r in db.execute("SELECT * FROM nox_v29_dialogs ORDER BY dialog_id")],
                "messages": [tuple(r) for r in db.execute("SELECT * FROM nox_v29_dialog_messages ORDER BY row_id")],
                "requests": [tuple(r) for r in db.execute("SELECT * FROM nox_chat_requests ORDER BY owner,request_id")],
                "events": [tuple(r) for r in db.execute("SELECT * FROM nox_chat_events ORDER BY owner,request_id,event_id")],
                "s03": [tuple(r) for r in db.execute("SELECT * FROM s03_items ORDER BY id")],
            }

    def running_request(self):
        row, token = self.ledger.accept("ordered-request", QUESTION, DIALOG,
                                        {"message": QUESTION, "dialog_id": DIALOG}, "session-order")
        self.ledger.append("ordered-request", token, {"type": "delta", "text": ANSWER})
        proof = {"record_id": "native-s03-order", "sha256": "a" * 64}
        with bridge._db(True) as db:
            db.execute("INSERT INTO s03_items VALUES(?,?,?,?)",
                       (proof["record_id"], proof["sha256"], time.time(), QUESTION + " " + ANSWER))
        return row, token, proof

    def test_bridge_reversed_existing_pair_refuses_without_rewrite(self):
        exchange = "existing-reverse"
        self.insert_pair(exchange, [("assistant", ANSWER), ("user", QUESTION)])
        before = self.durable_state()
        self.assertFalse(bridge._save_exchange(DIALOG, QUESTION, ANSWER, exchange),
                         "A reversed durable sequence must not certify a saved exchange")
        self.assertEqual(self.durable_state(), before)

    def test_ledger_reversed_existing_pair_refuses_before_done(self):
        row, token, proof = self.running_request()
        self.insert_pair(row["exchange_id"], [("assistant", ANSWER), ("user", QUESTION)])
        before = self.durable_state()
        with self.assertRaisesRegex(LedgerError, "HOLD_DIALOG_RECEIPT_COLLISION"):
            self.ledger.complete("ordered-request", token, proof)
        self.assertEqual(self.durable_state(), before,
                         "Refusal must not alter event cursor, state, saved bit, S03, or revision")

    def test_bridge_new_pair_and_exact_retry_keep_one_ordered_exchange(self):
        exchange = "new-ordered"
        self.assertTrue(bridge._save_exchange(DIALOG, QUESTION, ANSWER, exchange))
        saved = self.durable_state()
        self.assertEqual([(r[3], r[4]) for r in saved["messages"]],
                         [("user", QUESTION), ("assistant", ANSWER)])
        self.assertEqual(saved["dialogs"][0][4], 8)
        self.assertTrue(bridge._save_exchange(DIALOG, QUESTION, ANSWER, exchange))
        self.assertEqual(self.durable_state(), saved,
                         "Exact retry must not add a row, revision, or timestamp")

    def test_ledger_existing_ordered_pair_keeps_identity_and_revision(self):
        row, token, proof = self.running_request()
        self.insert_pair(row["exchange_id"], [("user", QUESTION), ("assistant", ANSWER)])
        before = self.durable_state()
        done = self.ledger.complete("ordered-request", token, proof)
        after = self.durable_state()
        self.assertEqual(after["messages"], before["messages"])
        self.assertEqual(after["dialogs"], before["dialogs"])
        self.assertEqual(after["s03"], before["s03"])
        self.assertEqual(done["exchange_id"], row["exchange_id"])
        self.assertEqual(done["type"], "done")
        self.assertTrue(done["saved"])
        self.assertEqual(len(after["events"]), len(before["events"]) + 1)

    def test_bridge_replay_uses_row_order_even_if_sqlite_reverses_unordered_selects(self):
        exchange = "ordered-existing"
        self.insert_pair(exchange, [("user", QUESTION), ("assistant", ANSWER)])
        before = self.durable_state()
        original_db = bridge._db

        @contextmanager
        def reverse_unordered(write=False):
            with original_db(write) as db:
                db.execute("PRAGMA reverse_unordered_selects=ON")
                yield db

        with patch.object(bridge, "_db", reverse_unordered):
            self.assertTrue(bridge._save_exchange(DIALOG, QUESTION, ANSWER, exchange))
        self.assertEqual(self.durable_state(), before)

    def test_ledger_partial_pair_refuses_without_filling_or_saving(self):
        row, token, proof = self.running_request()
        self.insert_pair(row["exchange_id"], [("user", QUESTION)])
        before = self.durable_state()
        with self.assertRaisesRegex(LedgerError, "HOLD_DIALOG_RECEIPT_COLLISION"):
            self.ledger.complete("ordered-request", token, proof)
        self.assertEqual(self.durable_state(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
