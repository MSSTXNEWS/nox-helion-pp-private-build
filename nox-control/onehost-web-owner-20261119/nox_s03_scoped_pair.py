"""Commit a completed authenticated dialog turn using the existing S03 tables."""

from hashlib import sha256
import json
import re
import sqlite3


OWNER = 'nox-single-owner'
ID = re.compile(r'[a-f0-9]{32}')
FORMAT = 'scoped-pair-manifest-v3'
PROVENANCE = 'chat_turn_scoped_v3'
MAX_ANSWER = 2_000_000


def _pair_manifest(dialog_id, request_id, question, answer):
    identity = '|'.join((FORMAT, OWNER, dialog_id, request_id))
    record_id = 'S03-' + sha256(identity.encode()).hexdigest()[:32]
    q, a = question.encode('utf-8'), answer.encode('utf-8')
    fields = {
        'owner': OWNER, 'dialog_id': dialog_id, 'request_id': request_id,
        'turn_format': FORMAT, 'question_bytes': len(q), 'answer_bytes': len(a),
        'question_sha256': sha256(q).hexdigest(), 'answer_sha256': sha256(a).hexdigest(),
    }
    meta = json.dumps(fields, sort_keys=True, separators=(',', ':'))
    # Searchable, bounded evidence for C02. Exact text lives in the dialog pair
    # whose UTF-8 byte lengths and digests are bound to this manifest.
    text = ('Эпизод чата — выдержки.\nВопрос:\n' + question[:300]
            + '\nОтвет:\n' + answer[:600] + '\nКвитанция S03:\n' + meta)
    digest = sha256(('M1|' + text).encode('utf-8')).hexdigest()
    return record_id, text, digest, meta


def _received(db, dialog_id, request_id, question):
    return db.execute(
        'SELECT g.state,g.goal_request_id,g.continuation_kind,g.resolved_by_request_id '
        'FROM nox_chat_received_goals g JOIN nox_v29_dialogs d '
        'ON d.dialog_id=g.dialog_id AND d.owner=g.owner '
        'WHERE d.archived=0 AND g.owner=? AND g.dialog_id=? AND g.request_id=? '
        'AND CAST(g.question AS BLOB)=CAST(? AS BLOB) AND g.question_sha256=?',
        (OWNER, dialog_id, request_id, question, sha256(question.encode('utf-8')).hexdigest()),
    ).fetchone()


def _verified(db, dialog_id, request_id, question, answer, manifest):
    record_id, text, digest, meta = manifest
    return db.execute(
        'SELECT 1 FROM nox_chat_received_goals g '
        'JOIN nox_v29_dialogs d ON d.dialog_id=g.dialog_id AND d.owner=g.owner '
        'JOIN s03_items s ON s.id=g.s03_record_id AND s.sha256=g.s03_sha256 '
        "JOIN nox_v29_dialog_messages u ON u.dialog_id=d.dialog_id AND u.exchange_id=s.id AND u.role='user' "
        "JOIN nox_v29_dialog_messages a ON a.dialog_id=d.dialog_id AND a.exchange_id=s.id AND a.role='assistant' "
        'WHERE g.owner=? AND d.dialog_id=? AND g.request_id=? AND g.resolved_by_request_id=g.request_id '
        "AND g.state='RESPONSE_COMMITTED' AND s.id=? AND s.segment='M1' AND s.provenance=? "
        'AND s.sha256=? AND s.meta=? AND CAST(s.text AS BLOB)=CAST(? AS BLOB) '
        'AND CAST(u.content AS BLOB)=CAST(? AS BLOB) AND CAST(a.content AS BLOB)=CAST(? AS BLOB)',
        (OWNER, dialog_id, request_id, record_id, PROVENANCE, digest, meta, text, question, answer),
    ).fetchone() is not None


def commit_scoped_pair(db_context, now, dialog_id, request_id, question, answer, stop_requested=None):
    """Return an independently read S03 receipt after one atomic, scoped commit.

    Call after a normally completed existing model stream. `db_context` is the
    bridge's original _db write/read context manager and `now` its timestamp.
    Unchanged replays are idempotent. A conflicting replay fails closed.
    """
    if (not isinstance(dialog_id, str) or not ID.fullmatch(dialog_id)
            or not isinstance(request_id, str) or not ID.fullmatch(request_id)
            or not isinstance(question, str) or not 1 <= len(question) <= 8000
            or question != question.strip() or not isinstance(answer, str)
            or not 1 <= len(answer) <= MAX_ANSWER or not answer.strip()):
        return None
    try:
        manifest = _pair_manifest(dialog_id, request_id, question, answer)
        record_id, text, digest, meta = manifest
        if stop_requested is not None and stop_requested():
            return None
        with db_context(True) as db:
            db.execute('BEGIN IMMEDIATE')
            if stop_requested is not None and stop_requested():
                return None
            received = _received(db, dialog_id, request_id, question)
            if received is None:
                return None
            if received['state'] == 'RESPONSE_COMMITTED':
                if received['resolved_by_request_id'] != request_id:
                    return None
            elif received['state'] == 'RECEIVED':
                stamp = now()
                db.execute(
                    'INSERT INTO s03_items(id,segment,text,provenance,sha256,salience,ts,meta) '
                    "VALUES(?,'M1',?,?,?,0.5,?,?)", (record_id, text, PROVENANCE, digest, stamp, meta),
                )
                db.execute(
                    "INSERT INTO s03_fts(id,text,segment) VALUES(?,?,'M1')", (record_id, text),
                )
                db.executemany(
                    'INSERT INTO nox_v29_dialog_messages(dialog_id,exchange_id,role,content,ts) VALUES(?,?,?,?,?)',
                    [(dialog_id, record_id, 'user', question, stamp),
                     (dialog_id, record_id, 'assistant', answer, stamp)],
                )
                db.execute(
                    'UPDATE nox_v29_dialogs SET updated_at=?,revision=revision+1 WHERE owner=? AND dialog_id=?',
                    (stamp, OWNER, dialog_id),
                )
                db.execute(
                    "UPDATE nox_chat_received_goals SET state='RESPONSE_COMMITTED',"
                    'updated_at=?,resolved_by_request_id=?,s03_record_id=?,s03_sha256=? '
                    "WHERE owner=? AND dialog_id=? AND request_id IN (?,?) AND state='RECEIVED'",
                    (stamp, request_id, record_id, digest, OWNER, dialog_id, request_id,
                     request_id if received['continuation_kind'] == 'ATTENTION' else received['goal_request_id']),
                )
            else:
                return None
            if not _verified(db, dialog_id, request_id, question, answer, manifest):
                raise RuntimeError('HOLD_S03_SCOPED_PAIR_COMMIT')
            if stop_requested is not None and stop_requested():
                raise RuntimeError('STOP_BEFORE_S03_SCOPED_PAIR_COMMIT')
        with db_context() as db:
            if _verified(db, dialog_id, request_id, question, answer, manifest):
                return {'record_id': record_id, 'sha256': digest, 'proof': 'M1_SCOPED_PAIR_MANIFEST_V3'}
    except (OSError, sqlite3.Error, RuntimeError, ValueError):
        return None
    return None
