"""Source-fixture tests for B1 pinned S03 writer adapter; no live DB."""
import sqlite3
import unittest

from owner_exchange_idempotency_contract import (
    HoldExchange, initialize, claim_once, certify_readback,
)
from owner_exchange_s03_writer_adapter import (
    WRITER_SOURCE_BLOB, PROOF_SCHEMA, read_candidate,
)

H = "a" * 64
S03 = "b" * 64
OWNER = "nox-single-owner"
DIALOG = "dialog-1"
EXCHANGE = "exchange-1"
REQUEST = "request-1"


class B1WriterAdapterTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE nox_chat_requests(
                owner TEXT,request_id TEXT,payload_sha256 TEXT,dialog_id TEXT,
                exchange_id TEXT,state TEXT,saved INTEGER,stop_requested INTEGER,
                s03_record_id TEXT,s03_sha256 TEXT,question TEXT,answer TEXT);
            CREATE TABLE s03_items(id TEXT,sha256 TEXT);
            CREATE TABLE nox_v29_dialogs(
                dialog_id TEXT,owner TEXT,archived INTEGER);
            CREATE TABLE nox_v29_dialog_messages(
                row_id INTEGER PRIMARY KEY,dialog_id TEXT,exchange_id TEXT,
                role TEXT,content TEXT);
        """)
        self.db.execute("INSERT INTO nox_chat_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (OWNER, REQUEST, H, DIALOG, EXCHANGE, "done", 1, 0,
                         "record-1", S03, "first question", "first answer"))
        self.db.execute("INSERT INTO s03_items VALUES (?,?)", ("record-1", S03))
        self.db.execute("INSERT INTO nox_v29_dialogs VALUES (?,?,0)",
                        (DIALOG, OWNER))
        self.db.executemany(
            "INSERT INTO nox_v29_dialog_messages VALUES (?,?,?,?,?)",
            [(1,DIALOG,EXCHANGE,"user","first question"),
             (2,DIALOG,EXCHANGE,"assistant","first answer")])
        self.db.commit()
        self.db.execute("PRAGMA query_only=ON")

    def tearDown(self):
        self.db.close()

    def read(self, **override):
        kwargs = dict(owner=OWNER, request_id=REQUEST, conversation_id=DIALOG,
                      exchange_id=EXCHANGE, request_sha256=H,
                      installed_writer_blob=WRITER_SOURCE_BLOB,
                      permit=lambda: True)
        kwargs.update(override)
        return read_candidate(self.db, **kwargs)

    def mutate(self, sql, parameters=()):
        self.db.execute("PRAGMA query_only=OFF")
        self.db.execute(sql, parameters)
        self.db.commit()
        self.db.execute("PRAGMA query_only=ON")

    def test_exact_two_message_candidate_and_no_replay_contract(self):
        proof = self.read()
        self.assertEqual(proof["schema"], PROOF_SCHEMA)
        self.assertEqual(proof["pair_row_ids"], [1, 2])
        self.assertEqual(len(proof["s03_proof_sha256"]), 64)
        self.assertFalse(self.db.in_transaction)
        store = sqlite3.connect(":memory:")
        try:
            initialize(store)
            self.assertEqual(claim_once(store, DIALOG, EXCHANGE, H), "DISPATCH_ONCE")
            # Only test fixture verifier; NOT native immutable verification.
            self.assertEqual(
                certify_readback(store, DIALOG, EXCHANGE, H, proof,
                                 lambda p: p["schema"] == PROOF_SCHEMA),
                "READBACK_ONLY")
            self.assertEqual(claim_once(store, DIALOG, EXCHANGE, H),
                             "READBACK_ONLY")
        finally:
            store.close()

    def test_duplicate_and_missing_assistant_hold(self):
        self.mutate(
            "INSERT INTO nox_v29_dialog_messages VALUES (?,?,?,?,?)",
            (3,DIALOG,EXCHANGE,"assistant","first answer"))
        with self.assertRaisesRegex(HoldExchange, "PAIR_MISMATCH"):
            self.read()
        self.mutate("DELETE FROM nox_v29_dialog_messages WHERE row_id=3")
        self.mutate("DELETE FROM nox_v29_dialog_messages WHERE row_id=2")
        with self.assertRaisesRegex(HoldExchange, "PAIR_MISMATCH"):
            self.read()

    def test_stop_not_saved_and_wrong_s03_item_hold(self):
        self.mutate("UPDATE nox_chat_requests SET stop_requested=1")
        with self.assertRaisesRegex(HoldExchange, "NOT_COMMITTED"):
            self.read()
        self.mutate("UPDATE nox_chat_requests SET stop_requested=0,saved=0")
        with self.assertRaisesRegex(HoldExchange, "NOT_COMMITTED"):
            self.read()
        self.mutate("UPDATE nox_chat_requests SET saved=1")
        self.mutate("UPDATE s03_items SET sha256=?", ("c" * 64,))
        with self.assertRaisesRegex(HoldExchange, "ITEM_MISMATCH"):
            self.read()

    def test_owner_source_and_request_scope_fail_closed(self):
        with self.assertRaisesRegex(HoldExchange, "WRITER_PIN"):
            self.read(installed_writer_blob="0" * 40)
        with self.assertRaisesRegex(HoldExchange, "OWNER_GATE"):
            self.read(permit=lambda: False)
        with self.assertRaisesRegex(HoldExchange, "NOT_COMMITTED"):
            self.read(owner="different-owner")
        with self.assertRaisesRegex(HoldExchange, "NOT_COMMITTED"):
            self.read(request_sha256="d" * 64)

    def test_read_only_and_owner_revocation_fence(self):
        self.db.execute("PRAGMA query_only=OFF")
        with self.assertRaisesRegex(HoldExchange, "READ_ONLY"):
            self.read()
        self.db.execute("PRAGMA query_only=ON")
        active = iter((True, False))
        with self.assertRaisesRegex(HoldExchange, "OWNER_GATE"):
            self.read(permit=lambda: next(active))
        self.assertFalse(self.db.in_transaction)


if __name__ == "__main__":
    unittest.main()
