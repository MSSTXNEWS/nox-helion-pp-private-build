"""B1 source-only exchange contract: no duplicate model dispatch on reconnect."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from owner_exchange_idempotency_contract import (
    HoldExchange, initialize, claim_once, mark_uncertain, certify_readback,
)


C = 'chat-1'
E = 'exchange-1'
H = 'a' * 64
P = 'b' * 64
R = 'c' * 64


def proof():
    return dict(conversation_id=C, exchange_id=E, request_sha256=H,
                s03_record_id='canonical-record-1', s03_proof_sha256=P,
                response_sha256=R)


class B1ExchangeContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'claims.sqlite3')
        self.first = sqlite3.connect(self.db, timeout=0.05)
        initialize(self.first)

    def tearDown(self):
        self.first.close()
        self.tmp.cleanup()

    def test_first_claim_is_only_dispatch_and_reconnect_never_reposts(self):
        self.assertEqual(claim_once(self.first, C, E, H), 'DISPATCH_ONCE')
        restarted = sqlite3.connect(self.db, timeout=0.05)
        try:
            self.assertEqual(claim_once(restarted, C, E, H),
                             'HOLD_EXCHANGE_UNCERTAIN')
            self.assertEqual(mark_uncertain(restarted, C, E, H),
                             'HOLD_EXCHANGE_UNCERTAIN')
            self.assertEqual(claim_once(self.first, C, E, H),
                             'HOLD_EXCHANGE_UNCERTAIN')
            self.assertEqual(claim_once(self.first, C, E, 'd'*64),
                             'HOLD_EXCHANGE_KEY_CONFLICT')
        finally:
            restarted.close()

    def test_independent_s03_proof_only_allows_readback_not_new_post(self):
        self.assertEqual(claim_once(self.first, C, E, H), 'DISPATCH_ONCE')
        with self.assertRaisesRegex(HoldExchange, 'HOLD_S03_PROOF'):
            certify_readback(self.first, C, E, H, proof(), lambda _: False)
        self.assertEqual(claim_once(self.first, C, E, H),
                         'HOLD_EXCHANGE_UNCERTAIN')
        self.assertEqual(certify_readback(self.first, C, E, H, proof(),
                                          lambda _: True), 'READBACK_ONLY')
        self.assertEqual(claim_once(self.first, C, E, H), 'READBACK_ONLY')
        self.assertEqual(mark_uncertain(self.first, C, E, H), 'READBACK_ONLY')
        changed = proof()
        changed['s03_record_id'] = 'other-record'
        self.assertEqual(certify_readback(self.first, C, E, H, changed,
                                          lambda _: True),
                         'HOLD_EXCHANGE_PROOF_CONFLICT')

    def test_verifier_cannot_certify_a_rebound_mutable_caller_proof(self):
        """A mutating verifier must not alter the committed S03 witness."""
        self.assertEqual(claim_once(self.first, C, E, H), 'DISPATCH_ONCE')
        supplied = proof()
        originally_verified = supplied.copy()

        def verifier(frozen):
            self.assertEqual(frozen['s03_record_id'], 'canonical-record-1')
            # Mutate the original dict after verifier looked at its contents.
            supplied['s03_record_id'] = 'forged-record-after-check'
            supplied['response_sha256'] = 'd' * 64
            with self.assertRaises(TypeError):
                frozen['s03_record_id'] = 'another-forgery'
            return True

        self.assertEqual(certify_readback(self.first, C, E, H, supplied,
                                          verifier), 'READBACK_ONLY')
        self.assertEqual(certify_readback(self.first, C, E, H,
                                          originally_verified, lambda _: True),
                         'READBACK_ONLY')
        self.assertEqual(certify_readback(self.first, C, E, H, supplied,
                                          lambda _: True),
                         'HOLD_EXCHANGE_PROOF_CONFLICT')
        self.assertEqual(claim_once(self.first, C, E, H), 'READBACK_ONLY')

    def test_bad_identity_or_cross_exchange_proof_never_claims_success(self):
        with self.assertRaisesRegex(HoldExchange, 'HOLD_EXCHANGE_IDENTITY'):
            claim_once(self.first, '../chat', E, H)
        with self.assertRaisesRegex(HoldExchange, 'HOLD_EXCHANGE_DIGEST'):
            claim_once(self.first, C, E, 'not-sha')
        self.assertEqual(claim_once(self.first, C, E, H), 'DISPATCH_ONCE')
        alien = proof()
        alien['exchange_id'] = 'wrong'
        with self.assertRaisesRegex(HoldExchange, 'HOLD_S03_PROOF'):
            certify_readback(self.first, C, E, H, alien, lambda _: True)
        self.assertEqual(claim_once(self.first, C, E, H),
                         'HOLD_EXCHANGE_UNCERTAIN')

    def test_locked_durable_store_fails_closed_without_dispatch(self):
        other = sqlite3.connect(self.db, timeout=0.05)
        try:
            self.first.execute('BEGIN IMMEDIATE')
            with self.assertRaisesRegex(HoldExchange, 'HOLD_EXCHANGE_STORE'):
                claim_once(other, C, E, H)
            self.first.rollback()
            self.assertEqual(claim_once(other, C, E, H), 'DISPATCH_ONCE')
            self.assertEqual(claim_once(self.first, C, E, H),
                             'HOLD_EXCHANGE_UNCERTAIN')
        finally:
            other.close()


if __name__ == '__main__':
    unittest.main()
