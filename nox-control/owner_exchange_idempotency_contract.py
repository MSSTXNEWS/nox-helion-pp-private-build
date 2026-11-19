"""Isolated B1 exchange claim contract; NOT wired to production/S03.

Caller supplies an explicitly approved SQLite connection. A claim is committed
before any model POST. Unknown/aborted exchanges are NEVER reclaimed by age.
A separate independently checked canonical S03 readback is required to certify
a terminal exchange; this module stores no chat content and never replays POSTs.
"""
import re
import sqlite3
from types import MappingProxyType


SCHEMA = """CREATE TABLE IF NOT EXISTS b1_exchange_claims (
    conversation_id TEXT NOT NULL,
    exchange_id TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('IN_FLIGHT','UNCERTAIN','VERIFIED')),
    s03_record_id TEXT,
    s03_proof_sha256 TEXT,
    response_sha256 TEXT,
    PRIMARY KEY (conversation_id, exchange_id)
)"""


class HoldExchange(RuntimeError):
    """A non-retryable gate failure; never turn this into a second POST."""


def _ident(value):
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', value) is None:
        raise HoldExchange('HOLD_EXCHANGE_IDENTITY')
    return value


def _digest(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise HoldExchange('HOLD_EXCHANGE_DIGEST')
    return value


def initialize(conn):
    """Schema initialization is explicit; it must never run at import time."""
    try:
        conn.execute(SCHEMA)
        conn.commit()
    except sqlite3.Error as exc:
        raise HoldExchange('HOLD_EXCHANGE_STORE') from exc


def _execute(conn, operation):
    # BEGIN IMMEDIATE serializes competing processes before checking the key.
    if conn.in_transaction:
        raise HoldExchange('HOLD_EXCHANGE_TRANSACTION')
    try:
        conn.execute('BEGIN IMMEDIATE')
        answer = operation()
        conn.commit()
        return answer
    except sqlite3.Error as exc:
        conn.rollback()
        raise HoldExchange('HOLD_EXCHANGE_STORE') from exc
    except BaseException:
        conn.rollback()
        raise


def claim_once(conn, conversation_id, exchange_id, request_sha256):
    """DISPATCH_ONCE is emitted only for the first durable exact-key insert.

    HOLD_* and READBACK_ONLY must never initiate a model POST.
    READBACK_ONLY requires independent S03 retrieval; it is not an answer.
    """
    key = (_ident(conversation_id), _ident(exchange_id))
    digest = _digest(request_sha256)

    def operation():
        row = conn.execute(
            'SELECT request_sha256,status FROM b1_exchange_claims '
            'WHERE conversation_id=? AND exchange_id=?', key).fetchone()
        if row is None:
            conn.execute(
                'INSERT INTO b1_exchange_claims '
                '(conversation_id,exchange_id,request_sha256,status) '
                "VALUES (?,?,?,'IN_FLIGHT')", (*key, digest))
            return 'DISPATCH_ONCE'
        if row[0] != digest:
            return 'HOLD_EXCHANGE_KEY_CONFLICT'
        if row[1] == 'VERIFIED':
            return 'READBACK_ONLY'
        return 'HOLD_EXCHANGE_UNCERTAIN'
    return _execute(conn, operation)


def mark_uncertain(conn, conversation_id, exchange_id, request_sha256):
    """On STOP, lost SSE, timeout or unknown outcome, retain the durable claim."""
    key = (_ident(conversation_id), _ident(exchange_id))
    digest = _digest(request_sha256)

    def operation():
        row = conn.execute(
            'SELECT request_sha256,status FROM b1_exchange_claims '
            'WHERE conversation_id=? AND exchange_id=?', key).fetchone()
        if row is None or row[0] != digest:
            return 'HOLD_EXCHANGE_UNKNOWN'
        if row[1] == 'VERIFIED':
            return 'READBACK_ONLY'
        conn.execute(
            "UPDATE b1_exchange_claims SET status='UNCERTAIN' "
            'WHERE conversation_id=? AND exchange_id=?', key)
        return 'HOLD_EXCHANGE_UNCERTAIN'
    return _execute(conn, operation)


def certify_readback(conn, conversation_id, exchange_id, request_sha256,
                     proof, immutable_verifier):
    """Persist VERIFIED only after an independently verified S03 proof.

    The verifier must validate the real canonical writer/record and source SHA;
    a self-reported native_verified flag is insufficient. This module cannot
    determine the deployed S03 schema or act as that independent verifier.
    """
    key = (_ident(conversation_id), _ident(exchange_id))
    digest = _digest(request_sha256)
    if not isinstance(proof, dict) or not callable(immutable_verifier):
        raise HoldExchange('HOLD_S03_PROOF')
    # Freeze caller-owned identity before external verification and CAS commit.
    # A verifier cannot rebind the persisted S03 witness through the input dict.
    frozen = MappingProxyType(dict(proof))
    if (frozen.get('conversation_id') != key[0] or
            frozen.get('exchange_id') != key[1] or
            frozen.get('request_sha256') != digest or
            type(frozen.get('s03_record_id')) is not str or
            not frozen['s03_record_id'] or len(frozen['s03_record_id']) > 200):
        raise HoldExchange('HOLD_S03_PROOF')
    psha = _digest(frozen.get('s03_proof_sha256'))
    rsha = _digest(frozen.get('response_sha256'))
    try:
        if immutable_verifier(frozen) is not True:
            raise HoldExchange('HOLD_S03_PROOF')
    except HoldExchange:
        raise
    except Exception as exc:
        raise HoldExchange('HOLD_S03_VERIFIER') from exc

    def operation():
        row = conn.execute(
            'SELECT request_sha256,status,s03_record_id,s03_proof_sha256,response_sha256 '
            'FROM b1_exchange_claims WHERE conversation_id=? AND exchange_id=?',
            key).fetchone()
        if row is None or row[0] != digest:
            return 'HOLD_EXCHANGE_UNKNOWN'
        if row[1] == 'VERIFIED':
            if row[2:] == (frozen['s03_record_id'], psha, rsha):
                return 'READBACK_ONLY'
            return 'HOLD_EXCHANGE_PROOF_CONFLICT'
        conn.execute(
            "UPDATE b1_exchange_claims SET status='VERIFIED', "
            's03_record_id=?,s03_proof_sha256=?,response_sha256=? '
            'WHERE conversation_id=? AND exchange_id=?',
            (frozen['s03_record_id'], psha, rsha, *key))
        return 'READBACK_ONLY'
    return _execute(conn, operation)
