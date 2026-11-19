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
AUDIT_ROW_LIMIT = 20000
# Pinned to the existing owner_s03_gateway.py content_identity() contract.
# Recheck that file's pinned model SHA/protocol before changing these values.
GATEWAY_MODEL_CONTENT_SHA256 = '6d39681b26c61279ac1f82db35a04a05009e94c415b51c858ff571489a82fc06'
GATEWAY_IDENTITY_SCHEMA = 'NOX_S03_BGE_CONTENT_IDENTITY_V1'
GATEWAY_EMBEDDING_PROTOCOL = 'BGE_M3_LLAMA_FLOAT32_L2_NORMALIZED_1024_V1'
GATEWAY_MODEL_BYTES = 437778496


def expected_gateway_identity():
    payload = {
        'schema': GATEWAY_IDENTITY_SCHEMA,
        'model_sha256': GATEWAY_MODEL_CONTENT_SHA256,
        'dimensions': EXPECTED_VECTOR_DIM,
        'embedding_protocol': GATEWAY_EMBEDDING_PROTOCOL,
    }
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
        allow_nan=False).encode('utf-8')).hexdigest()


def gateway_identity_record_ok(db, names):
    """The persisted indexer attestation must match the pinned source contract.

    This does NOT independently hash the native model; it prevents arbitrary
    64-hex vector labels from being accepted as the current BGE identity.
    """
    if 'nox_s03_gateway_meta' not in names:
        return False
    try:
        identity_row = db.execute(
            "SELECT value FROM nox_s03_gateway_meta WHERE key='model_content_identity'"
        ).fetchone()
        stat_row = db.execute(
            "SELECT value FROM nox_s03_gateway_meta WHERE key='model_file_stat'"
        ).fetchone()
        if not identity_row or not stat_row:
            return False
        record = json.loads(identity_row[0])
        observed = json.loads(stat_row[0])
        return bool(
            isinstance(record, dict)
            and record.get('schema') == GATEWAY_IDENTITY_SCHEMA
            and record.get('content_sha256') == GATEWAY_MODEL_CONTENT_SHA256
            and record.get('identity') == expected_gateway_identity()
            and record.get('embedding_protocol') == GATEWAY_EMBEDDING_PROTOCOL
            and type(record.get('dimensions')) is int
            and record['dimensions'] == EXPECTED_VECTOR_DIM
            and record.get('full_file_hash_verified') is True
            and isinstance(observed, list) and len(observed) == 5
            and all(type(x) is int for x in observed)
            and observed[2] == GATEWAY_MODEL_BYTES
            and record.get('file_stat') == observed
        )
    except (ValueError, TypeError, sqlite3.Error):
        return False



def sidecar_safety(path: Path, info):
    """Metadata-only WAL/SHM privacy; do not open, copy or print sidecars."""
    private, present = True, 0
    for suffix in ('-wal', '-shm'):
        sidecar = path.with_name(path.name + suffix)
        if sidecar.is_symlink():
            return False, present
        try:
            st = sidecar.stat()
        except FileNotFoundError:
            continue
        present += 1
        if (not stat.S_ISREG(st.st_mode)
                or stat.S_IMODE(st.st_mode) & 0o077
                or st.st_uid != info.st_uid):
            private = False
    return private, present


# Coverage derives from fresh canonical DB rows, never a historical fixed vector goal.


def begin_read_snapshot(db):
    """Pin one WAL-aware SQLite snapshot for every multi-query S03 audit gate."""
    db.execute('BEGIN')
    # BEGIN is deferred in SQLite: the first read pins the actual snapshot.
    db.execute('SELECT count(*) FROM sqlite_master').fetchone()


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
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16 * 1024**3:
            raise ValueError('HOLD_S03_FILE_TYPE_OR_SIZE')
    except FileNotFoundError:
        return [gate(i, 'HOLD', 'CANONICAL_DB_NOT_ACCESSIBLE') for i in range(1, 6)]
    # The main-file mode alone cannot protect newer S03 writes in the live WAL.
    db_private = (stat.S_IMODE(info.st_mode) & 0o077) == 0
    sidecars_private, sidecars_present = sidecar_safety(path, info)
    if not db_private or not sidecars_private:
        return [gate(i, 'HOLD', 'CANONICAL_DB_OR_WAL_SHM_ACL_UNSAFE',
                     db_private=db_private, sidecars_private=sidecars_private,
                     sidecars_present=sidecars_present) for i in range(1, 6)]
    uri = 'file:' + urllib.parse.quote(str(path.resolve()), safe='/') + '?mode=ro'
    try:
        db = sqlite3.connect(uri, uri=True, timeout=.2)
    except sqlite3.Error:
        return [gate(i, 'HOLD', 'S03_READ_ONLY_CONNECTION_UNAVAILABLE') for i in range(1, 6)]
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('PRAGMA trusted_schema=OFF')
        db.execute('PRAGMA busy_timeout=200')
        deadline = time.monotonic() + 3.0
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        begin_read_snapshot(db)
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
                'WHERE f.id IS NULL OR f.text IS NOT i.text OR f.segment IS NOT i.segment'
            ).fetchone()[0]
            fts_orphans = db.execute(
                'SELECT count(*) FROM s03_fts f LEFT JOIN s03_items i ON i.id=f.id '
                'WHERE i.id IS NULL'
            ).fetchone()[0]
            valid_shape = valid_hash = valid_both = vectors = 0
            invalid_or_missing_model_ids = 0
            active_models = set()
            vector_orphans = 0
            total_vector_rows = (int(db.execute('SELECT count(*) FROM nox_s03_vectors').fetchone()[0])
                                 if 'nox_s03_vectors' in names else 0)
            vector_scan_complete = total_vector_rows <= AUDIT_ROW_LIMIT
            if 'nox_s03_vectors' in names:
                vector_orphans = db.execute(
                    'SELECT count(*) FROM nox_s03_vectors v '
                    'LEFT JOIN s03_items i ON i.id=v.item_id WHERE i.id IS NULL'
                ).fetchone()[0]
                for item_text, content_sha, model, dims, blob_size in db.execute(
                    'SELECT i.text,v.content_sha256,v.model_identity,v.dimensions,length(v.embedding) '
                    'FROM nox_s03_vectors v JOIN s03_items i ON i.id=v.item_id LIMIT 20001'):
                    vectors += 1
                    model_id_valid = (isinstance(model, str) and len(model) == 64
                                      and all(c in '0123456789abcdef' for c in model))
                    invalid_or_missing_model_ids += int(not model_id_valid)
                    if model_id_valid:
                        active_models.add(model)
                    shape_ok = dims == EXPECTED_VECTOR_DIM and blob_size == 4 * EXPECTED_VECTOR_DIM
                    hash_ok = isinstance(item_text, str) and hashlib.sha256(item_text.encode()).hexdigest() == content_sha
                    valid_shape += int(shape_ok)
                    valid_hash += int(hash_ok)
                    valid_both += int(shape_ok and hash_ok)
            gateway_record_ok = gateway_identity_record_ok(db, names)
            identity_ok = (vector_scan_complete and vectors > 0
                           and invalid_or_missing_model_ids == 0
                           and len(active_models) == 1
                           and expected_gateway_identity() in active_models
                           and gateway_record_ok)
            complete = bool(
                fts_ok and items > 0 and eligible > 0 and fts_rows == items
                and fts_bad == 0 and fts_orphans == 0
                and vector_scan_complete and vectors == total_vector_rows
                and vectors == eligible == valid_both and vector_orphans == 0
                and identity_ok
            )
            results.append(gate(3, 'DONE_SOURCE' if complete else 'HOLD',
                                'CURRENT_CANONICAL_VECTOR_AND_FTS_COVERAGE' if complete else 'LIVE_VECTOR_FTS_COVERAGE_INCOMPLETE',
                                fts5=fts_ok, items=items, eligible_nonblank_items=eligible,
                                fts_rows=fts_rows, fts_mismatched_or_missing=fts_bad, fts_orphans=fts_orphans,
                                vector_rows=vectors, vector_total_rows=total_vector_rows,
                                vector_scan_complete=vector_scan_complete,
                                vector_orphans=vector_orphans, valid_shape=valid_shape,
                                valid_content_sha=valid_hash, valid_shape_and_content=valid_both,
                                observed_coverage_percent=(round(100 * valid_both / eligible, 2)
                                                           if eligible and vector_scan_complete else None),
                                distinct_vector_model_ids=len(active_models),
                                invalid_or_missing_vector_model_ids=invalid_or_missing_model_ids,
                                active_model_sha_identity_valid=identity_ok,
                                model_identity_matches_pinned_gateway=(expected_gateway_identity() in active_models),
                                gateway_model_attestation_consistent=gateway_record_ok,
                                native_embedding_model_artifact_verified=False))
            origins = db.execute('SELECT count(*) FROM nox_s03_origins').fetchone()[0] if 'nox_s03_origins' in names else 0
            imported = 0
            unscoped_imports = 0
            invalid_meta_rows = 0
            persona_scan_complete = items <= AUDIT_ROW_LIMIT
            for (meta,) in db.execute('SELECT meta FROM s03_items LIMIT 20001'):
                # Fail closed: malformed/non-object metadata must not hide imports.
                try:
                    value = json.loads(meta) if isinstance(meta, str) else None
                except (ValueError, TypeError):
                    value = None
                if not isinstance(value, dict):
                    invalid_meta_rows += 1
                    continue
                # "true" is not a reliable import marker; do not silently skip it.
                if 'history_import' in value and not isinstance(value['history_import'], bool):
                    invalid_meta_rows += 1
                    continue
                if value.get('history_import') is True:
                    imported += 1
                    persona_id = value.get('persona_id')
                    if not isinstance(persona_id, str) or not persona_id.strip():
                        unscoped_imports += 1
            metadata_safe = not (invalid_meta_rows or unscoped_imports or not persona_scan_complete)
            results.append(gate(4, 'DONE_SOURCE' if metadata_safe else 'HOLD',
                                ('S03_METADATA_UNPARSABLE_OR_INVALID_FAIL_CLOSED' if invalid_meta_rows
                                 else 'IMPORTED_PERSONA_SCOPE_MISSING_FAIL_CLOSED' if unscoped_imports
                                 else 'METADATA_PERSONA_CHECK_ONLY_NOT_ACL_E2E'),
                                imported_history_items=imported, imported_without_persona_scope=unscoped_imports,
                                invalid_meta_rows=invalid_meta_rows, persona_scan_complete=persona_scan_complete,
                                provenance_origin_links=origins, provenance_payload_exported=False))
        else:
            results += [gate(3, 'HOLD', 'NO_FTS_OR_VECTOR_SCHEMA'), gate(4, 'HOLD', 'NO_ORIGIN_PERSONA_SCHEMA')]
        dialogs = 'nox_v29_dialogs' in names and 'nox_v29_dialog_messages' in names
        results.append(gate(5, 'HOLD', 'CROSS_CHAT_RECALL_AND_INDEPENDENT_OFFSITE_RESTORE_NOT_DEMONSTRATED',
                            canonical_dialog_tables=dialogs, original_db_unchanged=True))
        return results
    except sqlite3.Error:
        # Busy/checkpoint contention or read deadline is NOT a memory PASS.
        # Do not leak table contents, owner identifiers or SQL exception text.
        return [gate(i, 'HOLD', 'S03_SNAPSHOT_READ_INCOMPLETE') for i in range(1, 6)]
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
            CREATE TABLE nox_s03_gateway_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE nox_v29_dialogs(dialog_id TEXT PRIMARY KEY);
            CREATE TABLE nox_v29_dialog_messages(row_id INTEGER PRIMARY KEY);
            ''')
            synthetic_stat = [1, 2, GATEWAY_MODEL_BYTES, 4, 5]
            synthetic_attestation = {
                'schema': GATEWAY_IDENTITY_SCHEMA,
                'content_sha256': GATEWAY_MODEL_CONTENT_SHA256,
                'identity': expected_gateway_identity(),
                'embedding_protocol': GATEWAY_EMBEDDING_PROTOCOL,
                'dimensions': EXPECTED_VECTOR_DIM,
                'full_file_hash_verified': True,
                'file_stat': synthetic_stat,
            }
            db.executemany('INSERT INTO nox_s03_gateway_meta VALUES(?,?)', [
                ('model_content_identity', json.dumps(synthetic_attestation)),
                ('model_file_stat', json.dumps(synthetic_stat)),
            ])
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
        # Synthetic regressions: SQL NULL mismatch and one missing model ID.
        with sqlite3.connect(path) as db:
            db.execute('UPDATE s03_fts SET text=NULL WHERE id=?', ('item',))
        assert inspect(path, fixture=True)[2]['fts_mismatched_or_missing'] == 1
        with sqlite3.connect(path) as db:
            db.execute('UPDATE s03_fts SET text=?,segment=NULL WHERE id=?', (text, 'item'))
        assert inspect(path, fixture=True)[2]['fts_mismatched_or_missing'] == 1
        with sqlite3.connect(path) as db:
            db.execute('UPDATE s03_fts SET segment=? WHERE id=?', ('M1', 'item'))
            db.execute('UPDATE nox_s03_vectors SET model_identity=? WHERE item_id=?', (expected_gateway_identity(), 'item'))
            second = 'SECOND_PUBLIC_SYNTHETIC_FIXTURE'
            db.execute('INSERT INTO s03_items VALUES (?,?,?,?,?,?,?,?)',
                       ('second', 'M2', second, 'synthetic', 'a'*64, .5, '2026', '{}'))
            db.execute('INSERT INTO s03_fts VALUES (?,?,?)', ('second', second, 'M2'))
            db.execute('INSERT INTO nox_s03_vectors VALUES (?,?,?,?,?,?)',
                       ('second', hashlib.sha256(second.encode()).hexdigest(), None,
                        1024, bytes(4096), 0))
        invalid_model = inspect(path, fixture=True)
        assert invalid_model[2]['valid_shape_and_content'] == 2
        assert invalid_model[2]['invalid_or_missing_vector_model_ids'] == 1
        assert not invalid_model[2]['active_model_sha_identity_valid']
        assert invalid_model[2]['state'] == 'HOLD'
        # Malformed JSON and whitespace-only persona scopes cannot give false PASS.
        with sqlite3.connect(path) as db:
            db.execute('UPDATE s03_items SET meta=? WHERE id=?',
                       ('{"history_import":true,"persona_id":"  "}', 'item'))
            db.execute('UPDATE s03_items SET meta=? WHERE id=?',
                       ('{broken-json', 'second'))
        bad_meta = inspect(path, fixture=True)[3]
        assert bad_meta['state'] == 'HOLD' and bad_meta['invalid_meta_rows'] == 1
        assert bad_meta['imported_without_persona_scope'] == 1
        assert bad_meta['reason'] == 'S03_METADATA_UNPARSABLE_OR_INVALID_FAIL_CLOSED'
        with sqlite3.connect(path) as db:
            db.execute('UPDATE s03_items SET meta=? WHERE id=?',
                       ('{"history_import":"true","persona_id":"p"}', 'item'))
        assert inspect(path, fixture=True)[3]['invalid_meta_rows'] == 2
        # Positive source-only case: complete metadata and matching model IDs.
        with sqlite3.connect(path) as db:
            db.execute('UPDATE s03_items SET meta=? WHERE id=?',
                       ('{"history_import":true,"persona_id":"p"}', 'item'))
            db.execute('UPDATE s03_items SET meta=? WHERE id=?', ('{}', 'second'))
            db.execute('UPDATE nox_s03_vectors SET model_identity=? WHERE item_id=?',
                       (expected_gateway_identity(), 'second'))
        clean = inspect(path, fixture=True)
        assert clean[2]['state'] == 'DONE_SOURCE'
        assert clean[3]['state'] == 'DONE_SOURCE' and clean[3]['invalid_meta_rows'] == 0
        assert clean[2]['gateway_model_attestation_consistent']
        assert clean[2]['model_identity_matches_pinned_gateway']
        assert clean[2]['active_model_sha_identity_valid']
        # A 64-hex digest alone is NOT the canonical BGE model identity.
        with sqlite3.connect(path) as db:
            db.execute('UPDATE nox_s03_vectors SET model_identity=? WHERE item_id=?',
                       ('f'*64, 'item'))
        wrong_vector_model = inspect(path, fixture=True)[2]
        assert wrong_vector_model['state'] == 'HOLD'
        assert not wrong_vector_model['active_model_sha_identity_valid']
        with sqlite3.connect(path) as db:
            db.execute('UPDATE nox_s03_vectors SET model_identity=? WHERE item_id=?',
                       (expected_gateway_identity(), 'item'))
            forged = dict(synthetic_attestation, full_file_hash_verified=False)
            db.execute("UPDATE nox_s03_gateway_meta SET value=? WHERE key='model_content_identity'",
                       (json.dumps(forged),))
        unverified_attestation = inspect(path, fixture=True)[2]
        assert unverified_attestation['state'] == 'HOLD'
        assert not unverified_attestation['gateway_model_attestation_consistent']
        with sqlite3.connect(path) as db:
            db.execute("UPDATE nox_s03_gateway_meta SET value=? WHERE key='model_content_identity'",
                       (json.dumps(synthetic_attestation),))
        assert inspect(path, fixture=True)[2]['state'] == 'DONE_SOURCE'
        wal = path.with_name(path.name + '-wal')
        wal.write_bytes(b'SYNTHETIC_NO_REAL_S03')
        wal.chmod(0o644)
        unsafe = inspect(path, fixture=True)
        assert len(unsafe) == 5 and all(x['state'] == 'HOLD' for x in unsafe)
        assert unsafe[0]['reason'] == 'CANONICAL_DB_OR_WAL_SHM_ACL_UNSAFE'
        wal.chmod(0o600)
        assert sidecar_safety(path, path.stat()) == (True, 1)
        wal.unlink()
        wal.symlink_to(path)
        assert sidecar_safety(path, path.stat())[0] is False
        wal.unlink()
        # WAL concurrent-writer regression: all audit SELECTs must see one
        # snapshot; a later successful write cannot shift mid-scan counts.
        snapshot_path = Path(temp) / 'concurrent.sqlite'
        with sqlite3.connect(snapshot_path) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute('CREATE TABLE tick(x INTEGER)')
            writer.execute('INSERT INTO tick VALUES(1)')
        reader = sqlite3.connect('file:' + urllib.parse.quote(str(snapshot_path), safe='/') + '?mode=ro', uri=True)
        try:
            reader.execute('PRAGMA query_only=ON')
            begin_read_snapshot(reader)
            assert reader.execute('SELECT count(*) FROM tick').fetchone()[0] == 1
            with sqlite3.connect(snapshot_path) as concurrent_writer:
                concurrent_writer.execute('INSERT INTO tick VALUES(2)')
            assert reader.execute('SELECT count(*) FROM tick').fetchone()[0] == 1
            reader.rollback()
            assert reader.execute('SELECT count(*) FROM tick').fetchone()[0] == 2
        finally:
            reader.close()
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
