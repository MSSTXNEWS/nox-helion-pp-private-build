"""Synthetic, source-only regression. Never connects to production/S03/model."""
import unittest
from owner_exchange_reconnect_event_cursor import HoldReconnect, resume_terminal


H = "a" * 64
S = "b" * 64
R = "c" * 64
U = "d" * 64
I = "e" * 64
KEY = b"fixture-key:" + b"x" * 32


def fixture(exchange="e1"):
    candidate = dict(schema="NOX_B1_SOURCE_S03_WRITER_CANDIDATE_V1",
                     writer_blob_sha1="f" * 40, owner="owner-1",
                     request_id="request-1", conversation_id="dialog-1",
                     exchange_id=exchange, request_sha256=H,
                     s03_record_id="record-1", s03_item_sha256=I,
                     pair_row_ids=[1, 2], user_sha256=U,
                     response_sha256=R, s03_proof_sha256=S)
    receipt = dict(native_verified=True,
                   **{k: candidate[k] for k in (
                       "owner", "request_id", "conversation_id", "exchange_id",
                       "s03_record_id", "request_sha256", "s03_proof_sha256",
                       "response_sha256")})
    return candidate, receipt


def run(candidate=None, receipt=None, **overrides):
    c, p = fixture()
    if candidate is not None: c = candidate
    if receipt is not None: p = receipt
    opts = dict(cursor=None, secret=KEY, permit=lambda: True,
                durable_claim=lambda: "READBACK_ONLY",
                immutable_verifier=lambda a, b: True)
    opts.update(overrides)
    return resume_terminal(c, p, **opts)


class CursorTests(unittest.TestCase):
    def test_final_readback_cursor_ack_no_second_terminal_or_model_post(self):
        first = run()
        second = run(cursor=first["next_cursor"])
        self.assertTrue(first["emit_terminal"])
        self.assertFalse(second["emit_terminal"])
        self.assertEqual(first["event_id"], second["event_id"])
        self.assertEqual(first["next_cursor"], second["next_cursor"])
        self.assertNotIn("response_text", first)

    def test_same_dialog_two_turns_are_not_interchangeable(self):
        first = run()
        c, p = fixture("e2")
        c["pair_row_ids"] = [3, 4]
        second = run(c, p)
        self.assertNotEqual(first["event_id"], second["event_id"])
        with self.assertRaisesRegex(HoldReconnect, "CURSOR_SCOPE"):
            run(c, p, cursor=first["next_cursor"])

    def test_cursor_tamper_wrong_key_and_bad_offset_hold(self):
        ack = run()["next_cursor"]
        with self.assertRaisesRegex(HoldReconnect, "CURSOR_AUTH"):
            run(cursor=ack[:-2] + ("A" if ack[-2] != "A" else "B") + ack[-1])
        with self.assertRaisesRegex(HoldReconnect, "CURSOR_AUTH"):
            run(cursor=ack, secret=b"y" * 32)
        with self.assertRaisesRegex(HoldReconnect, "CURSOR_FORMAT"):
            run(cursor="A" * 1201)
        with self.assertRaisesRegex(HoldReconnect, "CURSOR_FORMAT"):
            run(cursor="bad!token")

    def test_unverified_stale_wrong_owner_or_unknown_durable_hold(self):
        c, p = fixture()
        p["native_verified"] = False
        with self.assertRaisesRegex(HoldReconnect, "NATIVE_PROOF"):
            run(c, p)
        c, p = fixture()
        p["exchange_id"] = "another"
        with self.assertRaisesRegex(HoldReconnect, "PROOF_SCOPE"):
            run(c, p)
        with self.assertRaisesRegex(HoldReconnect, "DURABILITY"):
            run(durable_claim=lambda: "UNCERTAIN")
        with self.assertRaisesRegex(HoldReconnect, "IMMUTABLE_VERIFIER"):
            run(immutable_verifier=lambda a, b: False)

    def test_final_revoke_and_mutating_verifier_cannot_forge_token(self):
        checks = iter((True, False))
        with self.assertRaisesRegex(HoldReconnect, "OWNER_REVOKED"):
            run(permit=lambda: next(checks))
        c, p = fixture()
        def mutate(a, b):
            a["exchange_id"] = "forged"
            b["exchange_id"] = "forged"
            c["exchange_id"] = "forged"
            p["exchange_id"] = "forged"
            return True
        first = run(c, p, immutable_verifier=mutate)
        self.assertEqual(first["exchange_id"], "e1")
        self.assertTrue(first["readback_only"])

    def test_schema_pair_key_and_callback_validation(self):
        c, p = fixture()
        c["pair_row_ids"] = [2, 2]
        with self.assertRaisesRegex(HoldReconnect, "PAIR"):
            run(c, p)
        with self.assertRaisesRegex(HoldReconnect, "SIGNING_KEY"):
            run(secret=b"short")
        with self.assertRaisesRegex(HoldReconnect, "OWNER_GATE"):
            run(permit=None)


if __name__ == "__main__":
    unittest.main()
