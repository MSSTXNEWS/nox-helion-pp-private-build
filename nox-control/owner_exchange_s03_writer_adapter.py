"""B1 source-only read-only adapter for the pinned 2026-11-18 S03 writer baseline.

NOT a deployed writer, authenticated owner claim or independent verifier.
Callers must pin the actual installed writer and canonical database via their
separate owner/CAS gate. Never use a candidate to replay a model POST.
"""
import hashlib
import json
import re
import sqlite3

from owner_exchange_idempotency_contract import HoldExchange

# Git blob SHA-1 of the observed source baseline, NOT host file SHA-256.
WRITER_SOURCE_BLOB = "2f3acd4038f663f150b42f3bdf193507b851371f"
PROOF_SCHEMA = "NOX_B1_SOURCE_S03_WRITER_CANDIDATE_V1"
ID_RE = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")


def _id(value):
    if type(value) is not str or ID_RE.fullmatch(value) is None:
        raise HoldExchange("HOLD_S03_ADAPTER_IDENTITY")
    return value


def _hash(value):
    if type(value) is not str or HASH_RE.fullmatch(value) is None:
        raise HoldExchange("HOLD_S03_ADAPTER_DIGEST")
    return value


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_candidate(conn, *, owner, request_id, conversation_id, exchange_id,
                   request_sha256, installed_writer_blob, permit):
    """Read a single (user, assistant) pair using the baseline writer schema.

    Produces a *candidate*, not S03 verification. An external immutable verifier
    must independently confirm the installed writer, DB inode, lease/STOP,
    same committed S03 row and pair, and receipt before certify_readback().
    No SELECT result authorizes inference, retry, or native acceptance.
    """
    owner = _id(owner)
    request_id = _id(request_id)
    conversation_id = _id(conversation_id)
    exchange_id = _id(exchange_id)
    request_sha256 = _hash(request_sha256)
    if installed_writer_blob != WRITER_SOURCE_BLOB or not callable(permit):
        raise HoldExchange("HOLD_S03_WRITER_PIN")
    if permit() is not True:
        raise HoldExchange("HOLD_S03_OWNER_GATE")
    try:
        # Explicit query_only is required even for a mode=ro URI connection.
        if conn.in_transaction or conn.execute("PRAGMA query_only").fetchone()[0] != 1:
            raise HoldExchange("HOLD_S03_READ_ONLY_SNAPSHOT")
        conn.execute("BEGIN")
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"nox_chat_requests", "nox_v29_dialogs",
                    "nox_v29_dialog_messages", "s03_items"}
        if not required <= tables:
            raise HoldExchange("HOLD_S03_WRITER_SCHEMA")
        row = conn.execute(
            "SELECT payload_sha256,dialog_id,exchange_id,state,saved,"
            "stop_requested,s03_record_id,s03_sha256,question,answer "
            "FROM nox_chat_requests WHERE owner=? AND request_id=?",
            (owner, request_id)).fetchone()
        if (row is None or row[0] != request_sha256 or
                row[1] != conversation_id or row[2] != exchange_id or
                row[3] != "done" or type(row[4]) is not int or row[4] != 1 or
                type(row[5]) is not int or row[5] != 0 or
                type(row[6]) is not str or not row[6] or len(row[6]) > 200 or
                type(row[8]) is not str or not row[8].strip() or
                type(row[9]) is not str or not row[9].strip()):
            raise HoldExchange("HOLD_S03_WRITER_NOT_COMMITTED")
        _hash(row[7])
        linked = conn.execute(
            "SELECT sha256 FROM s03_items WHERE id=?", (row[6],)).fetchone()
        if linked is None or linked[0] != row[7]:
            raise HoldExchange("HOLD_S03_WRITER_ITEM_MISMATCH")
        pair = conn.execute(
            "SELECT m.row_id,m.role,m.content,m.exchange_id "
            "FROM nox_v29_dialog_messages m "
            "JOIN nox_v29_dialogs d ON d.dialog_id=m.dialog_id "
            "WHERE d.owner=? AND d.archived=0 AND d.dialog_id=? "
            "AND m.exchange_id=? ORDER BY m.row_id LIMIT 3",
            (owner, conversation_id, exchange_id)).fetchall()
        if (len(pair) != 2 or
                any(type(r[0]) is not int or type(r[2]) is not str or
                    r[3] != exchange_id or r[1] != ("user", "assistant")[i]
                    for i, r in enumerate(pair)) or
                pair[0][0] >= pair[1][0] or
                pair[0][2] != row[8] or pair[1][2] != row[9]):
            raise HoldExchange("HOLD_S03_WRITER_PAIR_MISMATCH")
        witness = {
            "schema": PROOF_SCHEMA,
            "writer_blob_sha1": WRITER_SOURCE_BLOB,
            "owner": owner,
            "request_id": request_id,
            "conversation_id": conversation_id,
            "exchange_id": exchange_id,
            "request_sha256": request_sha256,
            "s03_record_id": row[6],
            "s03_item_sha256": row[7],
            "pair_row_ids": [pair[0][0], pair[1][0]],
            "user_sha256": _sha(row[8]),
            "response_sha256": _sha(row[9]),
        }
        # Hash only canonical technical witness data, never private chat text.
        encoded = json.dumps(witness, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False)
        witness["s03_proof_sha256"] = _sha(encoded)
        if permit() is not True:
            raise HoldExchange("HOLD_S03_OWNER_GATE")
        return witness
    except sqlite3.Error as exc:
        raise HoldExchange("HOLD_S03_ADAPTER_SQL") from exc
    finally:
        # Release consistent SQLite read snapshot without any write.
        if conn.in_transaction:
            conn.rollback()
