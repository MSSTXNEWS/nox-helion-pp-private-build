import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

import owner_s03_diagnostic as diagnostic


class S03DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'kb/knowledge.sqlite'
        self.db.parent.mkdir()
        for key, value in (('ROOT', self.root), ('CANONICAL', self.db)):
            current = patch.object(diagnostic, key, value)
            current.start(); self.addCleanup(current.stop)

    def create_database(self):
        with sqlite3.connect(self.db) as database:
            database.execute('CREATE TABLE s03_items(id TEXT PRIMARY KEY,segment TEXT,text TEXT,provenance TEXT,sha256 TEXT,salience REAL,ts TEXT,meta TEXT)')
            for i, segment in enumerate(['M7'] * 3 + ['M5'] * 2 + ['M0'] * 2 + ['M6'] * 2 + ['M2'] * 2 + ['M3'] * 2 + ['M4']):
                database.execute('INSERT INTO s03_items VALUES(?,?,?,?,?,?,?,?)', (str(i), segment, 'PRIVATE_MEMORY_SENTINEL', 'PRIVATE_PROVENANCE', 'a' * 64, .5, 'private date', '{}'))
            database.execute('CREATE TABLE docs(id TEXT,url TEXT,title TEXT)')
            database.execute('CREATE TABLE chunks(id TEXT,doc_id TEXT,text TEXT)')
            database.execute('CREATE TABLE nox_v29_dialogs(dialog_id TEXT,owner TEXT,title TEXT)')
            database.execute('INSERT INTO nox_v29_dialogs VALUES(?,?,?)', ('private id', 'PRIVATE_OWNER', 'PRIVATE_DIALOG_TITLE'))

    def test_schema_count_and_pin_starvation_without_private_content_or_writes(self):
        self.create_database()
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        result = diagnostic.schema_probe(self.db, time.monotonic() + 2)
        self.assertEqual(result['state'], 'SCHEMA_OBSERVED')
        self.assertEqual(result['legacy_pin_rows_possible'], 14)
        self.assertTrue(result['legacy_pins_can_fill_all_chat_results'])
        self.assertTrue(result['has_docs_chunks'])
        self.assertTrue(result['schema_read_only'])
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)
        serialized = json.dumps(result)
        for value in ('PRIVATE_MEMORY_SENTINEL', 'PRIVATE_PROVENANCE', 'PRIVATE_OWNER', 'PRIVATE_DIALOG_TITLE', 'private id'):
            self.assertNotIn(value, serialized)

    def test_source_is_parsed_not_imported_and_literals_are_not_exported(self):
        path = self.root / 's03_memory.py'
        path.write_text('import sqlite3\nraise RuntimeError("PRIVATE_INITIALIZATION_TEXT")\nDB="' + str(self.db) + '"\ndef recall(query,k=6):\n    return "PRIVATE_FUNCTION_BODY"\n')
        result, paths = diagnostic.source_metadata(path)
        self.assertEqual(result['functions'][0]['name'], 'recall')
        self.assertIn(self.db, paths)
        self.assertNotIn('PRIVATE_', json.dumps(result))

    def test_embedding_probe_uses_only_public_synthetic_batch(self):
        submitted = []
        def local(path, data=None, timeout=4):
            if path == '/health':
                return 200, {'status': 'ok'}
            if path == '/v1/models':
                return 200, {'data': [{'id': 'bge-m3'}]}
            submitted.append(data)
            return 200, {'data': [{'index': i, 'embedding': [1.0] * 1024} for i in range(2)]}
        with patch.object(diagnostic, 'local_json', local):
            result = diagnostic.embedding_probe()
        self.assertEqual(result['state'], 'SYNTHETIC_EMBEDDING_BATCH_VERIFIED')
        self.assertEqual(result['dimensions'], 1024)
        self.assertEqual(submitted, [{'model': 'bge-m3', 'input': diagnostic.PUBLIC_FIXTURES}])
        self.assertFalse(result['vectors_exported'])
        self.assertFalse(result['model_loaded_by_probe'])

    def test_bad_vector_is_not_reported_ready(self):
        responses = [(200, {}), (200, {'data': [{'id': 'bge-m3'}]}),
                     (200, {'data': [{'embedding': [math.nan] * 1024}, {'embedding': [1.0] * 1024}]})]
        with patch.object(diagnostic, 'local_json', side_effect=responses):
            result = diagnostic.embedding_probe()
        self.assertEqual(result['state'], 'EMBEDDING_PROBE_UNAVAILABLE')
        self.assertNotIn('dimensions', result)

    def test_fifo_symlink_and_wrong_endpoint_are_rejected(self):
        fifo = self.root / 'fifo'; os.mkfifo(fifo)
        with self.assertRaises(diagnostic.DiagnosticHold):
            diagnostic.bounded(fifo)
        link = self.root / 'link'; link.symlink_to(self.db)
        with self.assertRaises(diagnostic.DiagnosticHold):
            diagnostic.plain(link)
        with self.assertRaises(diagnostic.DiagnosticHold):
            diagnostic.local_json('https://outside.example')

    def test_dotdot_path_and_unreadable_ancestor_fail_closed(self):
        with self.assertRaisesRegex(diagnostic.DiagnosticHold, 'HOLD_S03_PATH_SCOPE'):
            diagnostic.plain(self.root / '..' / 'outside.sqlite')
        with self.assertRaisesRegex(diagnostic.DiagnosticHold, 'HOLD_S03_PATH_SCOPE'):
            diagnostic.bounded(self.root / '..' / 'outside.sqlite')
        actual_lstat = os.lstat
        def forbidden(path):
            if Path(path) == self.root / 'kb':
                raise PermissionError(13, 'permission denied')
            return actual_lstat(path)
        with patch.object(diagnostic.os, 'lstat', side_effect=forbidden):
            with self.assertRaisesRegex(diagnostic.DiagnosticHold, 'HOLD_S03_PATH_UNREADABLE'):
                diagnostic.plain(self.db)
        def looped(path):
            if Path(path) == self.root / 'kb':
                raise OSError(40, 'too many symlinks')
            return actual_lstat(path)
        with patch.object(diagnostic.os, 'lstat', side_effect=looped):
            with self.assertRaisesRegex(diagnostic.DiagnosticHold, 'HOLD_S03_PATH_UNREADABLE'):
                diagnostic.plain(self.db)

    def test_embedding_http_failures_cannot_claim_verified_vectors(self):
        valid = [
            (200, {'status': 'ok'}),
            (200, {'data': [{'id': 'bge-m3'}]}),
            (200, {'data': [{'embedding': [1.0] * 32} for _ in range(2)]}),
        ]
        for stage in range(3):
            with self.subTest(stage=stage):
                responses = list(valid)
                responses[stage] = (503, valid[stage][1])
                with patch.object(diagnostic, 'local_json', side_effect=responses):
                    result = diagnostic.embedding_probe()
                self.assertEqual(result['state'], 'EMBEDDING_PROBE_UNAVAILABLE')
                self.assertNotIn('dimensions', result)
        for stage in (1, 2):
            responses = list(valid)
            responses[stage] = (200, None)
            with patch.object(diagnostic, 'local_json', side_effect=responses):
                result = diagnostic.embedding_probe()
            self.assertEqual(result['state'], 'EMBEDDING_PROBE_UNAVAILABLE')

    def test_run_does_not_export_faiss_ids_or_claim_indexing(self):
        self.create_database()
        (self.root / 'kb/faiss.index').write_bytes(b'fixture')
        (self.root / 'kb/faiss_meta.json').write_text(json.dumps({'ids': ['PRIVATE_CHUNK_ID']}))
        with patch.object(diagnostic, 'embedding_probe', return_value={'state': 'SYNTHETIC_EMBEDDING_BATCH_VERIFIED', 'dimensions': 1024}):
            result = diagnostic.run()
        self.assertEqual(result['faiss']['id_count'], 1)
        self.assertNotIn('PRIVATE_', json.dumps(result))
        self.assertEqual(result['s03_float32_vector_payload_estimate_bytes'], 14 * 1024 * 4)
        self.assertEqual(result['new_vectors_indexed'], 0)
        self.assertEqual(result['memory_records_merged'], 0)
        self.assertFalse(result['database_mutated'])


if __name__ == '__main__':
    unittest.main()
