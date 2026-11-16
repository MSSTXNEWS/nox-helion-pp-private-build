#!/usr/bin/env python3
"""NOX AUTO 2B: five metadata-only gates for the ORIGINAL canonical S03.

Read-only. No memory text, embeddings, credentials, owners or PersonaIDs appear
in output. Does not create a DB, alter the live proxy, enqueue work or train.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import stat
import time
import urllib.parse

CANONICAL = Path('/root/nox/kb/knowledge.sqlite')
EXPECTED_VECTOR_DIM = 1024
# Coverage derives from fresh canonical DB rows, never a historical fixed vector goal.


def gate(name, state, reason, **counts):
    return dict(task=name, state=state, reason=reason, **counts)


def inspect(path: Path, *, fixture=False):
    """Return exactly five bounded checks; unknown behavior remains HOLD."""
    path = Path(path)
    results = []
    if not fixture and path != CANONICAL:
        raise ValueError('HOLD_NONCANONICAL_DB_PATH')
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError('HOLD_SYMLINK_DB_PATH')
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 512 * 1024**2:
            raise ValueError('HOLD_S03_FILE_TYPE_OR_SIZE')
    except FileNotFoundError:
        return [gate(i, 'HOLD', 'CANONICAL_DB_NOT_ACCESSIBLE') for i in range(1, 6)]
    uri = 'file:' + urllib.parse.quote(str(path.resolve()), safe='/') + '?mode=ro'
    db = sqlite3.connect(uri, uri=True, timeout=.2)
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('PRAGMA trusted_schema=OFF')
        db.execute('PRAGMA busy_timeout=200')
        deadline = time.monotonic() + 3.0
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        names = {row[0]: row[1] for row in db.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table'")}
        required = {'s03_items', 's03_fts'}
        ready = required <= names.keys()
        mode_private = (stat.S_IMODE(info.st_mode) & 0o077) == 0
        integrity_ok = db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        schema_safe = ready and mode_private and integrity_ok
        results.append(gate(1, 'DONE_SOURCE' if schema_safe else 'HOLD',
                            'CANONICAL_SCHEMA_MODE_INTEGRITY_READ_ONLY' if schema_safe else 'S03_SCHEMA_MODE_OR_INTEGRITY_HOLD',
                            canonical_path=bool(path == CANONICAL),
                            mode_private=mode_private, sqlite_quick_check_ok=integrity_ok,
                            s03_items=int(db.execute('SELECT count(*) FROM s03_items').fetchone()[0]) if ready else None))
        results.append(gate(2, 'HOLD', 'LIVE_PROXY_ALIAS_AND_OWNER_SCOPE_REQUIRE_NATIVE_CALLBACK_READBACK'))
        if ready:
            fts_ok = 'using fts5' in (names.get('s03_fts') or '').lower()
            items = db.execute('SELECT count(*) FROM s03_items').fetchone()[0]
            eligible = db.execute(
                "SELECT count(*) FROM s03_items WHERE typeof(text)='text' AND length(trim(text))>0"
            ).fetchone()[0]
            fts_rows = db.execute('SELECT count(*) FROM s03_fts').fetchone()[0]
            # Row-count equality is not sufficient: an orphan and a missing row cancel.
            fts_bad = db.execute(
                'SELECT count(*) FROM s03_items i LEFT JOIN s03_fts f ON f.id=i.id '
                'WHERE f.id IS NULL OR f.text != i.text OR f.segment != i.segment'
            ).fetchone()[0]
            fts_orphans = db.execute(
                'SELECT count(*) FROM s03_fts f LEFT JOIN s03_items i ON i.id=f.id '
                'WHERE i.id IS NULL'
            ).fetchone()[0]
            valid_shape = valid_hash = valid_both = vectors = 0
            active_models = set()
            vector_orphans = 0
            if 'nox_s03_vectors' in names:
                vector_orphans = db.execute(
                    'SELECT count(*) FROM nox_s03_vectors v '
                    'LEFT JOIN s03_items i ON i.id=v.item_id WHERE i.id IS NULL'
                ).fetchone()[0]
                for item_text, content_sha, model, dims, blob_size in db.execute(
                    'SELECT i.text,v.content_sha256,v.model_identity,v.dimensions,length(v.embedding) '
                    'FROM nox_s03_vectors v JOIN s03_items i ON i.id=v.item_id LIMIT 20001'):
                    vectors += 1
                    if isinstance(model, str) and model:
                        active_models.add(model)
                    shape_ok = dims == EXPECTED_VECTOR_DIM and blob_size == 4 * EXPECTED_VECTOR_DIM
                    hash_ok = isinstance(item_text, str) and hashlib.sha256(item_text.encode()).hexdigest() == content_sha
                    valid_shape += int(shape_ok)
                    valid_hash += int(hash_ok)
                    valid_both += int(shape_ok and hash_ok)
            identity_ok = len(active_models) == 1 and all(
                len(model) == 64 and all(c in '0123456789abcdef' for c in model)
                for model in active_models
            )
            complete = bool(
                fts_ok and items > 0 and eligible > 0 and fts_rows == items
                and fts_bad == 0 and fts_orphans == 0
                and vectors == eligible == valid_both and vector_orphans == 0
                and identity_ok
            )
            results.append(gate(3, 'DONE_SOURCE' if complete else 'HOLD',
                                'CURRENT_CANONICAL_VECTOR_AND_FTS_COVERAGE' if complete else 'LIVE_VECTOR_FTS_COVERAGE_INCOMPLETE',
                                fts5=fts_ok, items=items, eligible_nonblank_items=eligible,
                                fts_rows=fts_rows, fts_mismatched_or_missing=fts_bad, fts_orphans=fts_orphans,
                                vector_rows=vectors, vector_orphans=vector_orphans, valid_shape=valid_shape,
                                valid_content_sha=valid_hash, valid_shape_and_content=valid_both,
                                observed_coverage_percent=round(100 * valid_both / eligible, 2) if eligible else None,
                                distinct_vector_model_ids=len(active_models),
                                active_model_sha_identity_valid=identity_ok))
            origins = db.execute('SELECT count(*) FROM nox_s03_origins').fetchone()[0] if 'nox_s03_origins' in names else 0
            imported = 0
            unscoped_imports = 0
            for (meta,) in db.execute('SELECT meta FROM s03_items LIMIT 20001'):
                try:
                    value = json.loads(meta) if isinstance(meta, str) else {}
                except (ValueError, TypeError):
                    value = {}
                if isinstance(value, dict) and value.get('history_import') is True:
                    imported += 1
                    if not isinstance(value.get('persona_id'), str) or not value['persona_id']:
                        unscoped_imports += 1
            results.append(gate(4, 'HOLD' if unscoped_imports else 'DONE_SOURCE',
                                'IMPORTED_PERSONA_SCOPE_MISSING_FAIL_CLOSED' if unscoped_imports else 'METADATA_PERSONA_CHECK_ONLY_NOT_ACL_E2E',
                                imported_history_items=imported, imported_without_persona_scope=unscoped_imports,
                                provenance_origin_links=origins, provenance_payload_exported=False))
        else:
            results += [gate(3, 'HOLD', 'NO_FTS_OR_VECTOR_SCHEMA'), gate(4, 'HOLD', 'NO_ORIGIN_PERSONA_SCHEMA')]
        dialogs = 'nox_v29_dialogs' in names and 'nox_v29_dialog_messages' in names
        results.append(gate(5, 'HOLD', 'CROSS_CHAT_RECALL_AND_INDEPENDENT_OFFSITE_RESTORE_NOT_DEMONSTRATED',
                            canonical_dialog_tables=dialogs, original_db_unchanged=True))
        return results
    finally:
        db.close()


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'knowledge.sqlite'
        with sqlite3.connect(path) as db:
            db.executescript('''
            CREATE TABLE s03_items(id TEXT PRIMARY KEY,segment TEXT,text TEXT,provenance TEXT,sha256 TEXT,salience REAL,ts TEXT,meta TEXT);
            CREATE VIRTUAL TABLE s03_fts USING fts5(id UNINDEXED,text,segment UNINDEXED);
            CREATE TABLE nox_s03_vectors(item_id TEXT PRIMARY KEY,content_sha256 TEXT,model_identity TEXT,dimensions INTEGER,embedding BLOB,created_at REAL);
            CREATE TABLE nox_s03_origins(item_id TEXT,source_key TEXT,source_row_key TEXT,version_sha256 TEXT,chunk_index INTEGER,chunk_sha256 TEXT);
            CREATE TABLE nox_v29_dialogs(dialog_id TEXT PRIMARY KEY);
            CREATE TABLE nox_v29_dialog_messages(row_id INTEGER PRIMARY KEY);
            ''')
            text = 'PUBLIC_SYNTHETIC_FIXTURE'
            db.execute('INSERT INTO s03_items VALUES (?,?,?,?,?,?,?,?)',
                       ('item','M1',text,'synthetic','a'*64,.5,'2026','{"history_import":true}'))
            db.execute('INSERT INTO s03_fts VALUES (?,?,?)', ('item', text, 'M1'))
            db.execute('INSERT INTO nox_s03_vectors VALUES (?,?,?,?,?,?)',
                       ('item',hashlib.sha256(text.encode()).hexdigest(),'model',1024,b'\0'*4096,0))
        path.chmod(0o600)
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        report = inspect(path, fixture=True)
        after = hashlib.sha256(path.read_bytes()).hexdigest()
        assert len(report) == 5 and [x['task'] for x in report] == [1,2,3,4,5]
        assert report[0]['state'] == 'DONE_SOURCE' and report[1]['state'] == 'HOLD'
        assert report[2]['valid_content_sha'] == 1 and report[2]['fts5'] is True
        assert report[2]['eligible_nonblank_items'] == 1 and 'reindex_target' not in report[2]
        assert report[0]['mode_private'] and report[0]['sqlite_quick_check_ok']
        assert report[2]['state'] == 'HOLD' and report[3]['imported_without_persona_scope'] == 1
        assert report[4]['state'] == 'HOLD' and before == after
        assert not any('PUBLIC_SYNTHETIC_FIXTURE' in json.dumps(x) for x in report)
        with sqlite3.connect(path) as db:
            db.execute('UPDATE s03_fts SET text=? WHERE id=?', ('MISMATCH_SYNTHETIC', 'item'))
        bad_fts = inspect(path, fixture=True)
        assert bad_fts[2]['fts_mismatched_or_missing'] == 1 and bad_fts[2]['state'] == 'HOLD'
        assert 'MISMATCH_SYNTHETIC' not in json.dumps(bad_fts)
        try:
            inspect(Path(temp) / 'other.sqlite')
        except ValueError as exc:
            assert str(exc) == 'HOLD_NONCANONICAL_DB_PATH'
        else:
            raise AssertionError('noncanonical path admitted')
    return 'SOURCE_SELFTEST_PASS; synthetic SQLite fixtures only; native state not measured'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        print(selftest())
    else:
        print(json.dumps({'schema':'NOX_S03_FIVE_GATE_READONLY_V1', 'results':inspect(CANONICAL),
                          'source_only':False,'native_writer_authorized':False},
                         ensure_ascii=False, sort_keys=True))
