"""Read-only S03 receipt verification for the existing authenticated NOX QA turn."""

from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time


DB = Path('/root/nox/kb/knowledge.sqlite')
WRITER = Path('/root/nox/scripts/nox_s03_scoped_pair.py')
WRITER_SHA = 'd347ff7247e2f883b955094ca4e98205346ddb6e39b0fa52e13c360a8144c57f'
QUESTION = 'Кто ты? Ты голоден? Что сейчас делаешь?'
ANSWER_SHA = '13d4daf0713273858d46332185eb4fea6fefac44ea3884e4bf2aa2a99a5e9318'
TITLES = tuple(f'NOX QA nox_policy_qa_{second}' for second in range(1795113247, 1795113266))
OWNER = 'nox-single-owner'
QUERY = '''
SELECT d.dialog_id,g.request_id,g.received_at,g.s03_record_id,g.s03_sha256,
       s.segment,s.provenance,s.text,s.meta,s.sha256,u.content,a.content
  FROM nox_v29_dialogs d
  JOIN nox_chat_received_goals g ON g.dialog_id=d.dialog_id AND g.owner=d.owner
  JOIN s03_items s ON s.id=g.s03_record_id AND s.sha256=g.s03_sha256
  JOIN nox_v29_dialog_messages u ON u.dialog_id=d.dialog_id AND u.exchange_id=s.id AND u.role='user'
  JOIN nox_v29_dialog_messages a ON a.dialog_id=d.dialog_id AND a.exchange_id=s.id AND a.role='assistant'
 WHERE d.owner=? AND d.archived=0 AND d.title IN ({titles})
   AND g.request_id=g.resolved_by_request_id AND g.state='RESPONSE_COMMITTED'
   AND g.question_sha256=? AND CAST(g.question AS BLOB)=CAST(? AS BLOB)
 LIMIT 33
'''


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_S03_QA_' + code)


def digest(value):
    return sha256(value).hexdigest()


def anchored_regular(path):
    for parent in path.parents:
        row = parent.lstat()
        require(stat.S_ISDIR(row.st_mode) and row.st_uid == 0 and not row.st_mode & 0o002, 'PATH_SCOPE')
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o002,
            'FILE_SCOPE')
    return info.st_dev, info.st_ino


def load_manifest_builder():
    before = anchored_regular(WRITER)
    fd = os.open(WRITER, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as handle:
        row = os.fstat(handle.fileno())
        raw = handle.read(65537)
        require((row.st_dev, row.st_ino) == before == anchored_regular(WRITER)
                and len(raw) <= 65536 and digest(raw) == WRITER_SHA, 'WRITER_PIN')
    namespace = {}
    exec(compile(raw, str(WRITER), 'exec'), namespace)
    return namespace['_pair_manifest']


def verify(connection, build_manifest):
    question_sha = digest(QUESTION.encode())
    rows = connection.execute(QUERY.format(titles=','.join('?' for _ in TITLES)),
                              (OWNER, *TITLES, question_sha, QUESTION)).fetchall()
    require(len(rows) <= 32, 'MATCH_BOUND')
    matches = []
    for dialog, request, received, record, goal_sha, segment, provenance, text, meta, stored_sha, user, assistant in rows:
        if user != QUESTION or not isinstance(assistant, str) or digest(assistant.encode()) != ANSWER_SHA:
            continue
        require(all(isinstance(v, str) and re.fullmatch(r'[a-f0-9]{32}', v)
                    for v in (dialog, request)), 'BINDING')
        event = datetime.fromisoformat(received.replace('Z', '+00:00'))
        require(event.tzinfo is not None, 'TIMEZONE')
        expected = build_manifest(dialog, request, QUESTION, assistant, event)
        require((record, text, stored_sha, meta) == expected and goal_sha == stored_sha
                and segment == 'M1' and provenance == 'chat_turn_scoped_v3', 'MANIFEST')
        matches.append((record, stored_sha))
    require(len(matches) == 1, 'OWNER_PAIR_UNPROVEN')
    return {'canonical_s03_write_verified': True, 's03_record_id_sha256': digest(matches[0][0].encode()),
            's03_item_sha256': matches[0][1], 'answer_sha256': ANSWER_SHA, 'segment': 'M1',
            'exact_matches': 1, 'model_requests': 0, 'host_writes': 0}


def main():
    require(re.fullmatch(r'[1-9][0-9]{0,23}', os.environ.get('NOX_OWNER_REQUEST_ID', ''))
            and re.fullmatch(r'[0-9a-f]{40}', os.environ.get('NOX_OWNER_SOURCE_SHA', '')), 'OWNER_CONTEXT')
    identity = anchored_regular(DB)
    wal, shm = Path(str(DB) + '-wal'), Path(str(DB) + '-shm')
    if os.path.lexists(wal) or os.path.lexists(shm):
        anchored_regular(wal)
        anchored_regular(shm)
    with sqlite3.connect(DB.as_uri() + '?mode=ro', uri=True, timeout=0.5) as db:
        deadline = time.monotonic() + 2
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        result = verify(db, load_manifest_builder())
        require(anchored_regular(DB) == identity, 'DB_CHANGED')
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 's03_qa_receipt', 'data': result}, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        reason = str(error)
        code = reason if re.fullmatch(r'HOLD_S03_QA_[A-Z_]+', reason) else 'HOLD_S03_QA_READ'
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 's03_qa_receipt', 'data': {'state': code}}), flush=True)
        raise SystemExit(2) from None
