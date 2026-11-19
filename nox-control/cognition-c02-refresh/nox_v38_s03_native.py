"""Read-only C02 adapter for the existing, single-owner NOX S03 store."""

import __future__
import ast
from contextlib import closing
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import stat
import sys
import time
from types import FunctionType


DB = Path('/root/nox/kb/knowledge.sqlite')
SOURCE = Path('/root/nox/scripts/s03_memory.py')
SOURCE_SHA256 = '776a6dc25726540d75ec51216d1e333ca89b24e803ba3620f9b5e470a3c81476'
TENANT = 'nox'
OWNER = 'nox-single-owner'
SHARED_SEGMENTS = frozenset(('M2', 'M4', 'M7'))
SEGMENTS = frozenset(f'M{i}' for i in range(8))
IDENTITY = re.compile(r'[A-Za-z0-9._:-]{1,100}')
RECORD_ID = re.compile(r'[A-Za-z0-9._:-]{6,128}')
DIGEST = re.compile(r'[a-f0-9]{64}')
MAX_QUERY = 8000
MAX_HITS = 8
MAX_CANDIDATES = 24
MAX_CONTENT = 1800
MAX_TOTAL_CONTENT = 4400
DEADLINE_SECONDS = 0.50


def _owner_session(session):
    return (session.tenant == TENANT and session.principal == OWNER
            and isinstance(session.chat_id, str) and IDENTITY.fullmatch(session.chat_id) is not None)


def owner_shared_scope_authorize(session, row):
    """C02's only exception to exact chat scope is a row emitted as owner-shared."""
    return (_owner_session(session) and row.get('tenant') == TENANT
            and row.get('principal') == OWNER and row.get('chat_id') is None
            and row.get('persona_id') is None and row.get('owner_shared') is True
            and row.get('verified') is True and row.get('segment') in SHARED_SEGMENTS)


def _connect(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RuntimeError('HOLD_S03_RECALL_DEADLINE')
    connection = sqlite3.connect(DB.as_uri() + '?mode=ro', uri=True, timeout=min(0.05, remaining))
    try:
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 250)
        return connection
    except BaseException:
        connection.close()
        raise


def _record_scope(meta, segment, session):
    if not isinstance(meta, dict) or meta.get('superseded') is True or meta.get('history_import') is True:
        return None
    explicit = meta.get('scope')
    if explicit is not None and not isinstance(explicit, dict):
        return None
    sources = (meta, explicit or {})
    chat_ids, personas = set(), set()
    for claims in sources:
        for key, expected in (('owner_scope', OWNER), ('owner', OWNER), ('principal', OWNER), ('tenant', TENANT)):
            if claims.get(key) not in (None, expected):
                return None
        if claims.get('acl') not in (None, 'owner', 'owner-only', 'owner-shared', 'private'):
            return None
        for values, aliases in ((chat_ids, ('chat_id', 'dialog_id')), (personas, ('persona_id', 'PersonaID'))):
            for key in aliases:
                value = claims.get(key)
                if value is not None:
                    if not isinstance(value, str) or not IDENTITY.fullmatch(value):
                        return None
                    values.add(value)
    if len(chat_ids) > 1 or len(personas) > 1:
        return None
    chat_id = next(iter(chat_ids), None)
    persona = next(iter(personas), None)
    if persona is not None and (session.persona_enabled is not True or session.persona_id != persona):
        return None
    if chat_id == session.chat_id:
        return chat_id, persona, False
    if chat_id is None and persona is None and segment in SHARED_SEGMENTS:
        owner_bound = any(claims.get(key) == OWNER for claims in sources
                          for key in ('owner_scope', 'owner', 'principal'))
        shared_declared = any(claims.get('acl') == 'owner-shared' or claims.get('owner_shared') is True
                              for claims in sources)
        sharing_consistent = all(claims.get('acl') != 'private'
                                 and (claims.get('owner_shared') is None or claims.get('owner_shared') is True)
                                 for claims in sources)
        if owner_bound and shared_declared and sharing_consistent:
            return None, None, True
    if chat_id is None and persona is None and segment == 'M1':
        return None, None, False  # Requires an independently verified dialog exchange below.
    return None


def _legacy_dialog(reader, session, record, meta, full_turn_episode):
    if (record['provenance'] != 'chat_turn' or meta.get('turn_format') != 'length-framed-v2'
            or meta.get('full_turn') is not True or not callable(full_turn_episode)):
        return None
    pairs = reader.execute(
        "SELECT d.dialog_id, u.content AS question, a.content AS answer FROM nox_v29_dialogs d "
        "JOIN nox_v29_dialog_messages u ON u.dialog_id=d.dialog_id AND u.role='user' "
        "JOIN nox_v29_dialog_messages a ON a.dialog_id=d.dialog_id AND a.exchange_id=u.exchange_id "
        "AND a.role='assistant' WHERE d.owner=? AND d.dialog_id=? AND d.archived=0 AND u.exchange_id=? "
        "AND length(CAST(u.content AS BLOB))+length(CAST(a.content AS BLOB))<=32000 LIMIT 2",
        (OWNER, session.chat_id, record['id'])).fetchall()
    if len(pairs) != 1:
        return None
    pair = pairs[0]
    question, answer = pair['question'], pair['answer']
    if (not isinstance(question, str) or not isinstance(answer, str)
            or type(meta.get('question_chars')) is not int or meta['question_chars'] != len(question)
            or type(meta.get('answer_chars')) is not int or meta['answer_chars'] != len(answer)
            or full_turn_episode(question, answer) != record['text']):
        return None
    return pair['dialog_id']


@lru_cache(maxsize=1)
def _pinned_functions(source):
    parsed = ast.parse(source, filename=str(SOURCE))
    definitions = [
        node for node in parsed.body
        if isinstance(node, ast.FunctionDef) and node.name in ('recall', 'full_turn_episode')
    ]
    if [node.name for node in definitions] != ['recall', 'full_turn_episode']:
        raise RuntimeError('HOLD_S03_RECALL_SOURCE_PIN')
    # Execute the two exact definitions only. Importing s03_memory afresh
    # would also run its owner gateway binding and other module initialization.
    definition_module = ast.Module(body=definitions, type_ignores=[])
    environment = {'DB': DB}
    exec(compile(definition_module, str(SOURCE), 'exec',
                 flags=__future__.annotations.compiler_flag, dont_inherit=True), environment)
    return environment['recall'].__code__, environment['full_turn_episode']


def scoped_recall(native_recall, session, prompt, limit):
    """Use the exact native selector once and re-read each candidate by canonical ID."""
    if not _owner_session(session) or not isinstance(prompt, str) or not 0 < len(prompt) <= MAX_QUERY:
        raise ValueError('HOLD_S03_RECALL_OWNER_SCOPE')
    if type(limit) is not int or not 1 <= limit <= MAX_HITS:
        raise ValueError('HOLD_S03_RECALL_LIMIT')
    deadline = time.monotonic() + DEADLINE_SECONDS
    module = sys.modules.get('s03_memory')
    module_file = getattr(module, '__file__', None)
    if (not callable(native_recall) or getattr(module, 'recall', None) is not native_recall
            or not isinstance(module_file, str) or Path(module_file) != SOURCE
            or getattr(module, 'DB', None) != DB
            or not stat.S_ISREG(SOURCE.lstat().st_mode) or not stat.S_ISREG(DB.lstat().st_mode)
            or SOURCE.resolve(strict=True) != SOURCE or DB.resolve(strict=True) != DB):
        raise RuntimeError('HOLD_S03_RECALL_SOURCE_PIN')
    source = SOURCE.read_bytes()
    if sha256(source).hexdigest() != SOURCE_SHA256:
        raise RuntimeError('HOLD_S03_RECALL_SOURCE_PIN')
    recall_code, full_turn_episode = _pinned_functions(source)
    with closing(_connect(deadline)) as selection:
        recent = [dict(record) for record in selection.execute(
            'SELECT s.id,s.segment,s.text,s.provenance FROM nox_v29_dialog_messages m '
            'JOIN nox_v29_dialogs d ON d.dialog_id=m.dialog_id '
            'JOIN s03_items s ON s.id=m.exchange_id '
            "WHERE m.dialog_id=? AND d.owner=? AND d.archived=0 AND m.role='assistant' "
            "AND s.segment='M1' AND length(s.text)<=8000 ORDER BY m.row_id DESC LIMIT ?",
            (session.chat_id, OWNER, limit))]
    # Use plain lexical tokens with the legacy selector. Punctuation cannot
    # send SQLite down its whole-table substring fallback on ordinary turns.
    terms = re.findall(r'[^\W_]{3,32}', prompt.casefold())
    query = ' OR '.join(list(dict.fromkeys(terms))[:6])
    with closing(_connect(min(deadline, time.monotonic() + 0.20))) as selection:
        # The installed selector calls init_db(), which can write schema/WAL.
        # Execute its same code once with a private read-only connection factory.
        # No native module global is changed and no default DB is initialized.
        readonly_recall = FunctionType(recall_code,
            {'init_db': lambda db: selection, 'sqlite3': sqlite3}, name='recall')
        try:
            candidates = readonly_recall(query, limit, DB)
        except sqlite3.OperationalError as error:
            if getattr(error, 'sqlite_errorcode', None) != sqlite3.SQLITE_INTERRUPT:
                raise
            candidates = []  # The bounded, same-dialog read above already succeeded.
    if not isinstance(candidates, list) or len(candidates) > MAX_CANDIDATES:
        raise RuntimeError('HOLD_S03_RECALL_CANDIDATES')

    rows, seen, total = [], set(), 0
    with closing(_connect(deadline)) as reader:
        reader.execute('BEGIN')
        for candidate in (recent + candidates)[:MAX_CANDIDATES]:
            if time.monotonic() >= deadline:
                raise RuntimeError('HOLD_S03_RECALL_DEADLINE')
            if not isinstance(candidate, dict):
                continue
            record_id = candidate.get('id')
            if not isinstance(record_id, str) or not RECORD_ID.fullmatch(record_id) or record_id in seen:
                continue
            seen.add(record_id)
            record = reader.execute(
                'SELECT id, segment, text, provenance, sha256, meta FROM s03_items WHERE id=? '
                'AND length(text)<=8000 AND coalesce(length(meta),0)<=8192', (record_id,)).fetchone()
            if record is None or any(record[key] != candidate.get(key) for key in ('segment', 'text', 'provenance')):
                continue
            segment, content, digest = record['segment'], record['text'], record['sha256']
            if (segment not in SEGMENTS or not isinstance(content, str) or not content.strip()
                    or not isinstance(digest, str) or not DIGEST.fullmatch(digest)
                    or sha256((segment + '|' + content).encode()).hexdigest() != digest):
                continue
            try:
                meta = json.loads(record['meta']) if record['meta'] is not None else {}
            except (TypeError, ValueError):
                continue
            scope = _record_scope(meta, segment, session)
            if scope is None:
                continue
            chat_id, persona, owner_shared = scope
            if chat_id is None and not owner_shared:
                chat_id = _legacy_dialog(reader, session, record, meta, full_turn_episode)
                if chat_id is None:
                    continue
            body = content[:MAX_CONTENT]
            size = len(body.encode())
            if total + size > MAX_TOTAL_CONTENT:
                continue
            total += size
            rows.append({'id': record_id, 'sha256': digest, 'segment': segment, 'content': body,
                         'source_uri': f's03://{record_id}?sha256={digest}', 'tenant': TENANT,
                         'principal': OWNER, 'chat_id': chat_id, 'persona_id': persona,
                         'owner_shared': owner_shared, 'verified': True})
            if len(rows) == limit:
                break
    if time.monotonic() >= deadline:
        raise RuntimeError('HOLD_S03_RECALL_DEADLINE')
    return rows
