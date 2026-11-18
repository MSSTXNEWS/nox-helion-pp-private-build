import hashlib
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sqlite3
import struct
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('owner_s03_gateway',Path(__file__).with_name('owner_s03_gateway.py'))
g=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(g)
# Preserve the production STOP implementation: setUp mocks it for other tests.
REAL_STOP_ACTIVE=g.stop_active


def database(path):
    with sqlite3.connect(path) as c:
        c.executescript('''
        CREATE TABLE s03_items(id TEXT PRIMARY KEY,segment TEXT,text TEXT,provenance TEXT,sha256 TEXT,salience REAL,ts TEXT,meta TEXT);
        CREATE VIRTUAL TABLE s03_fts USING fts5(id UNINDEXED,text,segment UNINDEXED);
        CREATE TABLE nox_v29_dialog_messages(row_id INTEGER PRIMARY KEY,dialog_id TEXT,exchange_id TEXT,role TEXT,content TEXT,ts TEXT);
        CREATE TABLE nox_v29_dialogs(dialog_id TEXT PRIMARY KEY,owner TEXT,title TEXT,archived INTEGER,revision INTEGER,created_at TEXT,updated_at TEXT);
        ''')
    return path


def item(c,key,text,segment='M2'):
    c.execute('INSERT INTO s03_items VALUES(?,?,?,?,?,?,?,?)',(key,segment,text,'test',g.text_sha(segment+'|'+text),.5,'2026-11-16','{}'))
    c.execute('INSERT INTO s03_fts VALUES(?,?,?)',(key,text,segment))


def vector(index):
    value=[0.0]*g.DIMENSIONS;value[index]=1.0;return value


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.db=database(self.root/'canonical.sqlite')
        self.patches=[patch.object(g,'ROOT',self.root),patch.object(g,'DB',self.db),
                      patch.object(g,'STATE',self.root/'state'),patch.object(g,'stop_active',return_value=False),
                      patch.object(g.shutil,'disk_usage',return_value=SimpleNamespace(free=20*1024**3))]
        for p in self.patches:p.start()
        with g.connection(self.db,write=True) as c:g.prepare_schema(c)

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()

    def test_owner_state_stop_flag_fails_closed(self):
        # The canonical manual eighth STOP flag must block S03 indexing.
        # A dangling symlink is still a deliberate STOP, never "not observed".
        flag=self.root/'state/STOP.flag'
        flag.parent.mkdir(parents=True,exist_ok=True)
        for style in ('regular','dangling_symlink'):
            with self.subTest(style=style):
                if style=='regular':
                    flag.write_text('OWNER_MODEL_UPDATE\\n',encoding='utf8')
                else:
                    flag.symlink_to(self.root/'missing-owner-stop')
                try:
                    with patch.object(g,'stop_active',REAL_STOP_ACTIVE):
                        self.assertTrue(g.stop_active())
                        with self.assertRaisesRegex(g.MemoryHold,'HOLD_S03_OWNER_STOP'):
                            g.index_batch(self.db,identity_fn=lambda:'a'*64,
                                          embedder=lambda *args,**kwargs: [])
                finally:
                    flag.unlink()
        with patch.object(g,'stop_active',REAL_STOP_ACTIVE):
            self.assertFalse(g.stop_active())

    def test_unreadable_owner_stop_cannot_admit_index(self):
        # EACCES/ELOOP on an owner STOP alias must not look like owner consent.
        flag=self.root/'state/STOP.flag'
        original_lstat=g.os.lstat
        for denial in (PermissionError('owner stop unreadable'),
                       OSError(40, 'owner stop lookup loop')):
            with self.subTest(error=type(denial).__name__):
                def denied_lstat(path,*args,**kwargs):
                    if Path(path)==flag:raise denial
                    return original_lstat(path,*args,**kwargs)
                with patch.object(g,'stop_active',REAL_STOP_ACTIVE), patch.object(g.os,'lstat',side_effect=denied_lstat):
                    self.assertTrue(g.stop_active())
                    with self.assertRaisesRegex(g.MemoryHold,'HOLD_S03_OWNER_STOP'):
                        g.index_batch(self.db,identity_fn=lambda:'a'*64,
                                      embedder=lambda *args,**kwargs: [])

    def test_bounded_pins_leave_real_query_results(self):
        pins=[{'id':'p'+str(i),'text':'identity '+str(i),'how':'pin'} for i in range(14)]
        facts=[{'id':'hit'+str(i),'text':'useful memory '+str(i)} for i in range(8)]
        rows=g.select_results(facts,[],pins,[],k=6)
        self.assertEqual(len(rows),10)
        self.assertEqual(sum(row['how']=='pin' for row in rows),2)
        self.assertEqual(sum(row['how']=='fts' for row in rows),8)
        self.assertTrue(all(row['retrieval_kind']=='LEXICAL_BOUNDED_PINS' for row in rows))

    def test_recent_current_event_beats_late_ingested_old_history(self):
        with g.connection(self.db, write=True) as c:
            item(c, 'current', 'current owner preference', 'M1')
            c.execute('UPDATE s03_items SET ts=? WHERE id=?',
                      ('2026-11-16T22:00:00Z', 'current'))
            item(c, 'older_import', 'unverified old history', 'M1')
            c.execute('UPDATE s03_items SET ts=?,meta=? WHERE id=?',
                      ('2024-01-01', '{"history_import":true,"training_verified":false}', 'older_import'))
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        answer = g.recall('nomatchtoken', db=self.db,
                          identity_fn=lambda: (_ for _ in ()).throw(OSError('offline')))
        self.assertEqual([row['id'] for row in answer[:2]], ['current', 'older_import'])
        self.assertTrue(answer[1]['historical_unverified'])
        self.assertEqual(before, hashlib.sha256(self.db.read_bytes()).hexdigest())

    def test_current_session_recall_survives_over_256_later_history_imports(self):
        # A current owner M1 fact must not disappear simply because later
        # migrations inserted more than the bounded recent-rowid window.
        with g.connection(self.db,write=True) as c:
            item(c,'current_session','owner current session decision','M1')
            c.execute('UPDATE s03_items SET ts=? WHERE id=?',
                      ('2026-11-17T18:00:00Z','current_session'))
            for i in range(300):
                key='old_import_'+str(i)
                item(c,key,'unverified historical note '+str(i),'M1')
                c.execute('UPDATE s03_items SET ts=?,meta=? WHERE id=?',
                          ('2024-01-01','{"history_import":true}',key))
            item(c,'malformed_meta','untrusted malformed legacy metadata','M1')
            c.execute('UPDATE s03_items SET meta=? WHERE id=?',
                      ('{invalid JSON','malformed_meta'))
        before=hashlib.sha256(self.db.read_bytes()).hexdigest()
        result=g.recall('nomatchtoken',db=self.db,
                        identity_fn=lambda: (_ for _ in ()).throw(OSError('offline')))
        self.assertEqual(result[0]['id'],'current_session')
        self.assertEqual(result[0]['how'],'recent')
        self.assertNotIn('HOLD_S03_',str(result))
        self.assertEqual(before,hashlib.sha256(self.db.read_bytes()).hexdigest())

    def test_malformed_metadata_cannot_starve_current_owner_recall(self):
        # A corrupt old import is not evidence of a current owner decision.
        # The SQL candidate LIMIT must distinguish both malformed JSON and
        # valid but non-object JSON before it truncates the rowid window.
        with g.connection(self.db, write=True) as c:
            item(c, 'current', 'most recent verified owner decision', 'M1')
            c.execute('UPDATE s03_items SET ts=? WHERE id=?',
                      ('2026-11-17T20:00:00Z', 'current'))
            for i in range(300):
                key = 'bad_json_' + str(i)
                item(c, key, 'legacy malformed fact ' + str(i), 'M1')
                c.execute('UPDATE s03_items SET meta=?,ts=? WHERE id=?',
                          ('{invalid JSON', '2024-01-01', key))
            for i in range(300):
                key = 'non_object_' + str(i)
                item(c, key, 'legacy JSON scalar ' + str(i), 'M1')
                c.execute('UPDATE s03_items SET meta=?,ts=? WHERE id=?',
                          ('[]', '2024-01-01', key))
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        with g.connection(self.db) as c:
            candidates = g.recent_rows(c)
        self.assertEqual(candidates[0]['id'], 'current')
        self.assertEqual(g._recent_provenance_rank(candidates[0]), 2)
        self.assertEqual(g._recent_provenance_rank({'meta': '{bad'}), 0)
        self.assertEqual(g._recent_provenance_rank({'meta': '[]'}), 0)
        self.assertEqual(g._recent_provenance_rank({'meta': '{"history_import":true}'}), 1)
        answer = g.recall('nomatchtoken', db=self.db,
                          identity_fn=lambda: (_ for _ in ()).throw(OSError('offline')))
        self.assertEqual(answer[0]['id'], 'current')
        self.assertEqual(before, hashlib.sha256(self.db.read_bytes()).hexdigest())

    def test_non_boolean_history_import_cannot_evict_verified_recent_memory(self):
        # Invalid provenance may still be syntactically valid JSON. The
        # 256-row SQL limit must not admit 300 numeric or string impostors
        # as current memory before Python has a chance to reject them.
        with g.connection(self.db, write=True) as c:
            item(c, 'current', 'actual owner decision', 'M1')
            c.execute('UPDATE s03_items SET ts=? WHERE id=?',
                      ('2026-11-17T21:00:00Z', 'current'))
            for i in range(300):
                key = 'bad_marker_' + str(i)
                item(c, key, 'unsupported imported memory ' + str(i), 'M1')
                c.execute('UPDATE s03_items SET meta=?,ts=? WHERE id=?',
                          ('{"history_import":1}', '2024-01-01', key))
            for kind, raw in [('string', '{"history_import":"true"}'),
                              ('null', '{"history_import":null}')]:
                item(c, kind, 'untrusted provenance ' + kind, 'M1')
                c.execute('UPDATE s03_items SET meta=? WHERE id=?', (raw, kind))
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        with g.connection(self.db) as c:
            rows = g.recent_rows(c)
        self.assertEqual(rows[0]['id'], 'current')
        for raw in ('{"history_import":1}', '{"history_import":"true"}',
                    '{"history_import":null}'):
            self.assertEqual(g._recent_provenance_rank({'meta':raw}), 0)
        self.assertEqual(g._recent_provenance_rank({'meta':'{"history_import":true}'}), 1)
        self.assertEqual(g._recent_provenance_rank({'meta':'{"history_import":false}'}), 2)
        answer = g.recall('unmatchedfreshquery', db=self.db,
                          identity_fn=lambda: (_ for _ in ()).throw(OSError('BGE offline')))
        self.assertEqual(answer[0]['id'], 'current')
        unverified = [r for r in answer if r['id'].startswith('bad_marker_')]
        self.assertTrue(unverified)
        self.assertTrue(all(r['historical_unverified'] and not r['training_verified']
                            for r in unverified))
        self.assertEqual(before, hashlib.sha256(self.db.read_bytes()).hexdigest())

    def test_recent_rejects_near_future_event_before_owner_recency(self):
        # Regression: +1 hour is within the old +24 hour tolerance, but
        # must not outrank the genuine owner M1 decision.
        fixed = datetime(2026, 11, 18, 0, 0, tzinfo=timezone.utc)
        with g.connection(self.db, write=True) as c:
            item(c, 'current', 'verified owner decision', 'M1')
            c.execute('UPDATE s03_items SET ts=? WHERE id=?',
                      ((fixed - timedelta(seconds=3)).isoformat(), 'current'))
            item(c, 'future_hour', 'unverified future-dated event', 'M1')
            c.execute('UPDATE s03_items SET ts=? WHERE id=?',
                      ((fixed + timedelta(hours=1)).isoformat(), 'future_hour'))
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        with patch.object(g.time, 'time', return_value=fixed.timestamp()):
            self.assertEqual(g._recent_event_timestamp({
                'ts': (fixed + timedelta(hours=1)).isoformat()}), 0.0)
            self.assertGreater(g._recent_event_timestamp({
                'ts': (fixed + timedelta(seconds=1)).isoformat()}), 0.0)
            with g.connection(self.db) as c:
                self.assertEqual(g.recent_rows(c)[0]['id'], 'current')
        self.assertEqual(before, hashlib.sha256(self.db.read_bytes()).hexdigest())

    def test_current_m1_survives_many_late_inserted_old_canonical_rows(self):
        # Previously a 256-row SQL rowid cut dropped a recent decision before
        # Python could rank it, even though all later rows were older events.
        now = datetime.now(timezone.utc)
        with g.connection(self.db, write=True) as c:
            item(c, 'owner_today', 'owner decision from this session', 'M1')
            c.execute('UPDATE s03_items SET ts=? WHERE id=?',
                      ((now - timedelta(seconds=20)).isoformat(), 'owner_today'))
            for i in range(300):
                key = 'late_old_canonical_' + str(i)
                item(c, key, 'old valid event ' + str(i), 'M1')
                c.execute('UPDATE s03_items SET ts=? WHERE id=?',
                          ('2022-01-01T00:00:00Z', key))
            for i in range(20):
                key = 'late_future_' + str(i)
                item(c, key, 'future unverified event ' + str(i), 'M1')
                c.execute('UPDATE s03_items SET ts=? WHERE id=?',
                          ((now + timedelta(days=1)).isoformat(), key))
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        with g.connection(self.db) as c:
            rows = g.recent_rows(c)
        self.assertEqual(rows[0]['id'], 'owner_today')
        self.assertEqual(g._recent_provenance_rank(rows[0]), 2)
        self.assertEqual(before, hashlib.sha256(self.db.read_bytes()).hexdigest())

    def test_recent_rejects_future_clock_and_oversized_request(self):
        with g.connection(self.db, write=True) as c:
            item(c, 'valid', 'valid current fact', 'M1')
            c.execute('UPDATE s03_items SET ts=? WHERE id=?',
                      ('2026-11-16T22:00:00+00:00', 'valid'))
            item(c, 'future', 'future forged fact', 'M1')
            c.execute('UPDATE s03_items SET ts=? WHERE id=?',
                      ('2099-01-01T00:00:00Z', 'future'))
            item(c, 'invalid', 'malformed date fact', 'M1')
            c.execute('UPDATE s03_items SET ts=? WHERE id=?',
                      ('not-a-date', 'invalid'))
        with g.connection(self.db) as c:
            self.assertEqual(g.recent_rows(c)[0]['id'], 'valid')
            with self.assertRaisesRegex(g.MemoryHold, 'HOLD_S03_RECENT_LIMIT'):
                g.recent_rows(c, limit=1024)

    def test_stale_fts_cannot_resurrect_superseded_decision(self):
        # Native S03 is authoritative. A lagging FTS row must never return
        # the *new* decision as a response to words only in the old one.
        with g.connection(self.db, write=True) as c:
            item(c, 'revised', 'Decision choose blue', 'M2')
            item(c, 'stable', 'Decision choose amber', 'M2')
        with g.connection(self.db) as c:
            self.assertEqual([r['id'] for r in g.lexical(c, 'blue')], ['revised'])
            self.assertEqual([r['id'] for r in g.lexical(c, 'amber')], ['stable'])
        with g.connection(self.db, write=True) as c:
            c.execute('UPDATE s03_items SET text=? WHERE id=?',
                      ('Decision choose green', 'revised'))
        with g.connection(self.db) as c:
            self.assertEqual(g.lexical(c, 'blue'), [])
            self.assertEqual(g.lexical(c, 'green'), [])  # no fake fresh index
            self.assertEqual([r['id'] for r in g.lexical(c, 'amber')], ['stable'])
        with g.connection(self.db, write=True) as c:
            c.execute('DELETE FROM s03_fts WHERE id=?', ('revised',))
            c.execute('INSERT INTO s03_fts VALUES(?,?,?)',
                      ('revised', 'Decision choose green', 'M2'))
        with g.connection(self.db) as c:
            self.assertEqual([r['id'] for r in g.lexical(c, 'green')], ['revised'])
            self.assertEqual(g.lexical(c, 'blue'), [])

    def test_semantic_recall_finds_nonlexical_memory_and_rejects_stale_text(self):
        with g.connection(self.db,write=True) as c:
            item(c,'old','Я люблю гулять среди деревьев')
            item(c,'unrelated','Список настроек компилятора')
        def embeddings(texts,timeout):return [vector(0 if 'деревьев' in x else 1) for x in texts]
        proof=g.index_batch(self.db,embedder=embeddings,identity_fn=lambda:'a'*64)
        self.assertEqual(proof['indexed'],2)
        answer=g.recall('отдых в лесу',db=self.db,embedder=lambda *a,**k:[vector(0)],identity_fn=lambda:'a'*64)
        self.assertEqual(answer[0]['id'],'old');self.assertEqual(answer[0]['how'],'semantic')
        with g.connection(self.db,write=True) as c:c.execute('UPDATE s03_items SET text=? WHERE id=?',('Новый несвязанный текст','old'))
        answer=g.recall('отдых в лесу',db=self.db,embedder=lambda *a,**k:[vector(0)],identity_fn=lambda:'a'*64)
        self.assertFalse(any(row['id']=='old' and row['how']=='semantic' for row in answer))

    def test_index_checks_content_again_after_network_and_model_identity(self):
        with g.connection(self.db,write=True) as c:item(c,'x','initial memory')
        def changing(texts,timeout):
            with g.connection(self.db,write=True) as c:c.execute('UPDATE s03_items SET text=? WHERE id=?',('changed memory','x'))
            return [vector(0)]
        result=g.index_batch(self.db,embedder=changing,identity_fn=lambda:'a'*64)
        self.assertEqual(result['indexed'],0)
        with g.connection(self.db) as c:self.assertEqual(c.execute('SELECT count(*) FROM nox_s03_vectors').fetchone()[0],0)
        with self.assertRaisesRegex(g.MemoryHold,'MODEL_CHANGED'):
            g.index_batch(self.db,embedder=lambda *a,**k:[vector(0)],identity_fn=iter(['a'*64,'b'*64]).__next__)

    def test_concurrent_memory_write_does_not_verify_incomplete_index(self):
        # A different S03 writer commits after the read snapshot but before
        # the vector transaction. The newly committed item must remain pending.
        with g.connection(self.db,write=True) as c:item(c,'first','first memory')
        def embedding_with_writer(texts,timeout):
            with g.connection(self.db,write=True) as c:item(c,'late','new chat memory')
            return [vector(0)]
        result=g.index_batch(self.db,embedder=embedding_with_writer,identity_fn=lambda:'a'*64)
        self.assertEqual(result['indexed'],1)
        self.assertEqual(result['stale_remaining'],1)
        with g.connection(self.db) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM s03_items').fetchone()[0],2)
            self.assertIsNone(c.execute('SELECT item_id FROM nox_s03_vectors WHERE item_id=?',('late',)).fetchone())
        task={'id':'owner.memory.index.concurrent','handler':'owner_memory_sync',
              'owner_claim':{'nonce':'concurrent_a3'}}
        with (patch.object(g,'resource_admission'),
              patch.object(g,'index_batch',return_value=result),
              patch.object(g.time,'monotonic',side_effect=[0.,.25,1.25])):
            with self.assertRaisesRegex(g.MemoryHold,'HOLD_S03_INDEX_INCOMPLETE'):
                g.sync(task,db=self.db,seconds=1.)
        self.assertFalse((g.STATE/'receipts'/'index_concurrent_a3.json').exists())

    def test_owner_stop_arriving_during_embedding_aborts_without_s03_write(self):
        # The owner may enter MODEL_UPDATE after initial admission.
        with g.connection(self.db,write=True) as c:item(c,'mid','memory before STOP')
        flag=self.root/'state'/'STOP.flag'
        flag.parent.mkdir(parents=True,exist_ok=True)
        def delayed_embedding(texts,timeout):
            flag.write_text('OWNER_MODEL_UPDATE\\n',encoding='utf8')
            return [vector(0)]
        with patch.object(g,'stop_active',REAL_STOP_ACTIVE):
            with self.assertRaisesRegex(g.MemoryHold,'HOLD_S03_OWNER_STOP'):
                g.index_batch(self.db,embedder=delayed_embedding,identity_fn=lambda:'a'*64)
        with g.connection(self.db) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM nox_s03_vectors').fetchone()[0],0)

    def test_owner_stop_before_sqlite_commit_rolls_back_all_vectors(self):
        # A STOP after INSERT but before transaction exit is not a partial PASS.
        with g.connection(self.db,write=True) as c:item(c,'late','memory pending commit')
        with patch.object(g,'stop_active',side_effect=[False,False,False,True]):
            with self.assertRaisesRegex(g.MemoryHold,'HOLD_S03_OWNER_STOP'):
                g.index_batch(self.db,embedder=lambda *a,**k:[vector(0)],identity_fn=lambda:'a'*64)
        with g.connection(self.db) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM nox_s03_vectors').fetchone()[0],0)

    def test_exact_history_origin_dedup_and_no_truth_promotion(self):
        private='PRIVATE_MEMORY_SENTINEL'
        first={'id':1,'ts':123.0,'text':private,'kind':'error','meta':'{"unverified":true}'}
        second={**first,'id':8,'kind':'copied_error'}
        with g.connection(self.db,write=True) as c:
            one=g.import_records(c,[first],'C01','a'*64)
            two=g.import_records(c,[second],'C02','b'*64)
            repeat=g.import_records(c,[first],'C01','a'*64)
        self.assertEqual(one['new_items'],1);self.assertEqual(two['new_items'],0)
        self.assertEqual(repeat['new_records'],0)
        self.assertNotIn(private,json.dumps([one,two,repeat]))
        with g.connection(self.db) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM nox_s03_import_records').fetchone()[0],2)
            self.assertEqual(c.execute('SELECT count(*) FROM nox_s03_origins').fetchone()[0],2)
            row=dict(c.execute('SELECT * FROM s03_items').fetchone())
            self.assertEqual(row['text'],private)
            self.assertIs(json.loads(row['meta'])['training_verified'],False)
            self.assertEqual(json.loads(c.execute('SELECT payload_json FROM nox_s03_import_records WHERE source_key=?',('C01',)).fetchone()[0]),first)

    def test_long_history_preserved_in_original_and_overlapping_chunks(self):
        text='abД🙂'*3000
        record={'id':1,'text':text,'meta':'PRIVATE_METADATA'}
        with g.connection(self.db,write=True) as c:
            counts=g.import_records(c,[record],'C08','a'*64)
        self.assertGreater(counts['origin_links'],5)
        with g.connection(self.db) as c:
            original=json.loads(c.execute('SELECT payload_json FROM nox_s03_import_records').fetchone()[0])
            self.assertEqual(original,record)
            pieces=[row[0] for row in c.execute('SELECT s.text FROM nox_s03_origins o JOIN s03_items s ON s.id=o.item_id ORDER BY o.chunk_index')]
        reconstructed=pieces[0]+''.join(part[160:] for part in pieces[1:])
        self.assertEqual(reconstructed,text)

    def test_snapshot_includes_committed_wal_and_has_private_mode(self):
        c=sqlite3.connect(self.db);c.execute('PRAGMA journal_mode=WAL')
        item(c,'wal','PRIVATE_WAL_RECORD');c.commit()
        result=g.snapshot_database(self.db,self.root/'snapshot.sqlite')
        self.assertEqual(Path(result['path']).stat().st_mode&0o777,0o600)
        with sqlite3.connect(result['path']) as backup:
            self.assertEqual(backup.execute('SELECT text FROM s03_items WHERE id=?',('wal',)).fetchone()[0],'PRIVATE_WAL_RECORD')
        self.assertNotIn('PRIVATE_WAL_RECORD',json.dumps(result));c.close()

    def test_migration_keeps_sources_byte_identical_and_dialog_provenance(self):
        legacy=self.root/'cores';(legacy/'C01').mkdir(parents=True)
        path=legacy/'C01/ltm.sqlite'
        with sqlite3.connect(path) as c:
            c.execute('CREATE TABLE ltm(id INTEGER PRIMARY KEY,ts REAL,msk TEXT,kind TEXT,level TEXT,session_id TEXT,persona_id TEXT,significance REAL,text TEXT,meta TEXT)')
            c.execute('INSERT INTO ltm VALUES(?,?,?,?,?,?,?,?,?,?)',(1,1.0,'time','event','ltm','PRIVATE_SESSION','PRIVATE_PERSON',.7,'PRIVATE_LEGACY_MEMORY','{}'))
        before=g.file_sha(path)
        with g.connection(self.db,write=True) as c:
            c.execute('INSERT INTO nox_v29_dialogs VALUES(?,?,?,?,?,?,?)',('D','PRIVATE_OWNER','PRIVATE_TITLE',0,1,'t','t'))
            c.execute('INSERT INTO nox_v29_dialog_messages VALUES(?,?,?,?,?,?)',(1,'D','E','assistant','PRIVATE_DIALOG_MEMORY','t'))
        result=g.migrate_history('123',db=self.db,legacy_root=legacy)
        self.assertEqual(g.file_sha(path),before)
        self.assertNotIn('PRIVATE_',json.dumps(result));self.assertEqual(result['training_examples_accepted'],0)
        with g.connection(self.db) as c:
            raw=c.execute('SELECT payload_json FROM nox_s03_import_records WHERE source_key=?',('CANONICAL_DIALOGS',)).fetchone()[0]
            self.assertEqual(json.loads(raw)['dialog_owner'],'PRIVATE_OWNER')
            self.assertEqual(json.loads(raw)['role'],'assistant')
        self.assertTrue((g.STATE/'backups/123/canonical.sqlite').is_file())

    def test_mixed_dialogue_owners_hold_before_import_and_preserve_sources(self):
        # Same original S03 may contain several dialog owners. The shared
        # M1 retrieval route cannot enforce owner ACL for these imports.
        # Refuse to combine them; do not mutate original S03 rows.
        with g.connection(self.db,write=True) as c:
            for i,owner in enumerate(('OWNER_A','OWNER_B'),start=1):
                dialog='D'+str(i)
                c.execute('INSERT INTO nox_v29_dialogs VALUES(?,?,?,?,?,?,?)',
                          (dialog,owner,'private title',0,1,'t','t'))
                c.execute('INSERT INTO nox_v29_dialog_messages VALUES(?,?,?,?,?,?)',
                          (i,dialog,'E'+str(i),'user','PRIVATE_'+owner,'t'))
        before=g.file_sha(self.db)
        with self.assertRaisesRegex(g.MemoryHold,'HOLD_S03_DIALOG_OWNER_SCOPE'):
            g.migrate_history('193',db=self.db,legacy_root=self.root/'missing_legacy')
        # The consistent snapshot was retained for owner-authorized recovery;
        # the original data was not imported into the global memory index.
        with g.connection(self.db) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM s03_items').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM nox_s03_import_records').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM nox_s03_origins').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM nox_v29_dialog_messages').fetchone()[0],2)
        self.assertTrue((g.STATE/'backups/193/canonical.sqlite').is_file())

    def test_blank_dialogue_owner_is_not_treated_as_acl_proof(self):
        with g.connection(self.db,write=True) as c:
            c.execute('INSERT INTO nox_v29_dialogs VALUES(?,?,?,?,?,?,?)',
                      ('D',None,'untitled',0,1,'t','t'))
            c.execute('INSERT INTO nox_v29_dialog_messages VALUES(?,?,?,?,?,?)',
                      (1,'D','E','user','PRIVATE_UNOWNED','t'))
        with self.assertRaisesRegex(g.MemoryHold,'HOLD_S03_DIALOG_OWNER_SCOPE'):
            g.migrate_history('194',db=self.db,legacy_root=self.root/'missing_legacy')
        with g.connection(self.db) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM s03_items').fetchone()[0],0)

    def test_malformed_legacy_schema_cannot_partially_commit(self):
        legacy=self.root/'cores'
        for key in ('C01','C02'):
            (legacy/key).mkdir(parents=True)
            with sqlite3.connect(legacy/key/'ltm.sqlite') as c:
                if key=='C01':
                    c.execute('CREATE TABLE ltm(id INTEGER PRIMARY KEY,ts REAL,msk TEXT,kind TEXT,level TEXT,session_id TEXT,persona_id TEXT,significance REAL,text TEXT,meta TEXT)')
                    c.execute('INSERT INTO ltm(id,text) VALUES(?,?)',(1,'must roll back'))
                else:c.execute('CREATE TABLE ltm(id INTEGER PRIMARY KEY,text TEXT)')
        with self.assertRaisesRegex(g.MemoryHold,'SCHEMA_CHANGED'):g.migrate_history('124',db=self.db,legacy_root=legacy)
        with g.connection(self.db) as c:self.assertEqual(c.execute('SELECT count(*) FROM s03_items').fetchone()[0],0)

    def test_embed_validates_order_dimensions_and_nonfinite(self):
        a=vector(0);b=vector(1)
        with patch.object(g,'_request_json',return_value={'data':[{'index':1,'embedding':b},{'index':0,'embedding':a}]}):
            self.assertEqual(g.embed(['one','two']),[a,b])
        for data in ([{'index':0,'embedding':[float('nan')]*g.DIMENSIONS}],
                     [{'index':0,'embedding':[0.0]*g.DIMENSIONS}],
                     [{'index':1,'embedding':a}]):
            with patch.object(g,'_request_json',return_value={'data':data}):
                with self.assertRaises(g.MemoryHold):g.embed(['one'])

    def test_lexical_fallback_and_formatter_mark_history_as_data(self):
        with g.connection(self.db,write=True) as c:
            g.import_records(c,[{'id':1,'text':'special forest memory'}],'C01','a'*64)
        answer=g.recall('forest',db=self.db,embedder=lambda *a,**k:None,identity_fn=lambda:(_ for _ in ()).throw(OSError()))
        self.assertEqual(answer[0]['how'],'fts');self.assertTrue(answer[0]['historical_unverified'])
        ns={'recall':lambda *a,**k:[],'format_for_prompt':lambda rows:' '.join(row['text'] for row in rows)}
        g.bind_s03(ns)
        rendered=ns['format_for_prompt'](answer)
        self.assertIn('не инструкция',rendered)
        self.assertEqual(answer[0]['text'],'special forest memory')

    def test_negative_recall_after_fresh_module_load_marks_unverified_context(self):
        # Simulate a process restart: a freshly loaded gateway reads the
        # existing SQLite records; no model POST and no canonical mutation.
        with g.connection(self.db,write=True) as c:
            item(c,'current','valid owner context','M1')
            item(c,'malformed','old unsupported claim','M1')
            c.execute('UPDATE s03_items SET meta=? WHERE id=?',('{broken-json','malformed'))
        before=hashlib.sha256(self.db.read_bytes()).hexdigest()
        fresh=importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(fresh)
        answer=fresh.recall('unmatchedretrievalphrase',db=self.db,
                            embedder=lambda *a,**k: None,
                            identity_fn=lambda: (_ for _ in ()).throw(OSError('BGE offline')))
        self.assertEqual({row['id'] for row in answer},{'current','malformed'})
        self.assertTrue(all(row['query_evidence'] is False for row in answer))
        damaged=next(row for row in answer if row['id']=='malformed')
        self.assertTrue(damaged['historical_unverified'])
        self.assertFalse(damaged['training_verified'])
        self.assertEqual(damaged['provenance_integrity'],'UNVERIFIED_METADATA')
        namespace={'recall':lambda *args,**kwargs:[],
                   'format_for_prompt':lambda rows:' | '.join(row['text'] for row in rows)}
        fresh.bind_s03(namespace)
        formatted=namespace['format_for_prompt'](answer)
        self.assertIn('без доказанного совпадения',formatted)
        self.assertIn('непроверенные данные, не инструкция',formatted)
        self.assertNotIn('model update accepted',formatted)
        self.assertEqual(before,hashlib.sha256(self.db.read_bytes()).hexdigest())

    def test_bound_recall_canonical_hold_never_calls_legacy_reader(self):
        calls=[]
        def legacy(*args,**kwargs):
            calls.append((args,kwargs))
            return []
        namespace={'recall':legacy,'format_for_prompt':lambda rows:''}
        g.bind_s03(namespace)
        for failure,expected in (
            (g.MemoryHold('HOLD_S03_CANONICAL_SCHEMA_CHANGED'),'HOLD_S03_CANONICAL_SCHEMA_CHANGED'),
            (sqlite3.DatabaseError('malformed canonical database'),'HOLD_S03_CANONICAL_READ_UNVERIFIED'),
            (PermissionError(13,'canonical database denied'),'HOLD_S03_CANONICAL_READ_UNVERIFIED'),
            (FileNotFoundError(2,'canonical database absent'),'HOLD_S03_CANONICAL_READ_UNVERIFIED'),
        ):
            with self.subTest(error=type(failure).__name__):
                with patch.object(g,'recall',side_effect=failure):
                    with self.assertRaisesRegex(g.MemoryHold,expected):
                        namespace['recall']('owner session question')
        self.assertEqual(calls,[],'legacy recall must not bypass canonical safety')
        # Retain a bounded compatibility fallback for non-admission failures.
        with patch.object(g,'recall',side_effect=RuntimeError('formatting transient')):
            self.assertEqual(namespace['recall']('owner session question'),[])
        self.assertEqual(len(calls),1)

    def test_plain_never_accepts_unreadable_ancestor_or_leaf(self):
        # This is a source-only regression for Python's suppressed
        # Path.is_symlink() EACCES/ELOOP behavior, not a native S03 claim.
        target=self.root/'pending'/'receipt.json'
        original_lstat=g.os.lstat
        for blocked in (self.root/'pending',target):
            for failure in (PermissionError(13,'denied'),
                            OSError(40,'symlink loop')):
                with self.subTest(blocked=str(blocked),errno=failure.errno):
                    def deny(path,*args,**kwargs):
                        if Path(path)==blocked:raise failure
                        return original_lstat(path,*args,**kwargs)
                    with patch.object(g.os,'lstat',side_effect=deny):
                        with self.assertRaisesRegex(g.MemoryHold,'HOLD_S03_PATH_UNREADABLE'):
                            g.plain(target)
        # Absent destinations remain legal for atomic creation.
        self.assertEqual(g.plain(target),target)
        dangling=self.root/'dangling_parent'
        dangling.symlink_to(self.root/'no-target',target_is_directory=True)
        with self.assertRaisesRegex(g.MemoryHold,'HOLD_S03_SYMLINK'):
            g.plain(dangling/'receipt.json')

    def test_no_fifo_or_symlink_database_and_source_patch_is_pinned(self):
        import os
        fifo=self.root/'fifo';os.mkfifo(fifo)
        with self.assertRaises(g.MemoryHold):g.regular(fifo)
        alias=self.root/'alias';alias.symlink_to(self.db)
        with self.assertRaises(g.MemoryHold):g.regular(alias)
        source='def recall(): pass\ndef remember(): pass\ndef format_for_prompt(): pass\ndef persist_turn(): pass\nif __name__ == "__main__":\n    pass\n'
        result=g.patch_s03(source,g.digest(source.encode()))
        self.assertLess(result.index(g.MARKER),result.index('if __name__'))
        with self.assertRaises(g.MemoryHold):g.patch_s03(source,'a'*64)

    def test_index_obeys_joint_utf8_batch_budget_without_erasing_original(self):
        text='🙂'*1800
        with g.connection(self.db,write=True) as c:
            item(c,'a',text);item(c,'b',text+'different')
        observed=[]
        def embedding(texts,timeout):
            observed.append(texts);return [vector(0) for _ in texts]
        result=g.index_batch(self.db,embedder=embedding,identity_fn=lambda:'a'*64)
        self.assertLessEqual(sum(len(value.encode()) for value in observed[0]),6500)
        self.assertEqual(result['indexed'],1);self.assertEqual(result['stale_remaining'],1)
        with g.connection(self.db) as c:self.assertEqual(c.execute('SELECT text FROM s03_items WHERE id=?',('a',)).fetchone()[0],text)

    def test_background_ingestion_adds_one_existing_dispatcher_job(self):
        model=self.root/'model.gguf';model.write_bytes(b'GGUFtest')
        with g.connection(self.db,write=True) as c:item(c,'x','new memory')
        saves=[];namespace={'HANDLERS':{},'ingest_owner_orders':lambda state:None,'save_state':lambda state:saves.append(1),'_qlock':threading.RLock()}
        state={'tasks':{}}
        # Uptime can be below 90 seconds on a newly provisioned OneHost.
        # First permitted ingest must not be skipped as if it were a retry.
        with patch.object(g,'MODEL',model),patch.object(g.time,'monotonic',return_value=30.0):
            g.bind_dispatcher(namespace);namespace['ingest_owner_orders'](state);namespace['ingest_owner_orders'](state)
        self.assertEqual(len(state['tasks']),1);self.assertEqual(len(saves),1)
        task=next(iter(state['tasks'].values()))
        self.assertEqual(task['handler'],'owner_memory_sync')
        self.assertNotIn('gpu1',task['locks']);self.assertNotIn('WORKERS',namespace)

    def test_verified_index_receipt_is_bound_to_exact_claim(self):
        task={'id':'owner.memory.index.1','handler':'owner_memory_sync','owner_claim':{'nonce':'a123b'}}
        fake={'indexed':2,'stale_remaining':0,'model_identity':'b'*64}
        with patch.object(g,'resource_admission'),patch.object(g,'index_batch',return_value=fake):result=g.sync(task,db=self.db)
        proof=g.verify_success(task,result)
        self.assertEqual(proof['scope'],'BOUNDED_S03_VECTOR_INDEX')
        self.assertEqual(proof['training_examples_accepted'],0)
        other={**task,'owner_claim':{'nonce':'other'}}
        self.assertIsNone(g.verify_success(other,result))
        Path(result['receipt_path']).write_text('{}')
        self.assertIsNone(g.verify_success(task,result))

    def test_partial_index_cannot_claim_completed_s03(self):
        task={'id':'owner.memory.index.partial','handler':'owner_memory_sync',
              'owner_claim':{'nonce':'partial_a3'}}
        partial={'indexed':1,'stale_remaining':1,'model_identity':'b'*64}
        with (patch.object(g,'resource_admission'),
              patch.object(g,'index_batch',return_value=partial),
              patch.object(g.time,'monotonic',side_effect=[0., .5, 1.5])):
            with self.assertRaisesRegex(g.MemoryHold,'HOLD_S03_INDEX_INCOMPLETE'):
                g.sync(task,db=self.db,seconds=1.)
        receipt=g.STATE/'receipts'/'index_partial_a3.json'
        self.assertFalse(receipt.exists())
        # Even a legacy source-signed hash of a partial receipt is not DONE.
        g.atomic_json(receipt,{'schema':g.SCHEMA,'task_id':task['id'],
            'claim_nonce':'partial_a3','scope':'BOUNDED_S03_VECTOR_INDEX',
            'verified':True,'source_sha256':g.file_sha(g.__file__),
            'indexed':1,'stale_remaining':1,'training_examples_accepted':0,
            'private_text_exported':False})
        evidence={'schema':g.SCHEMA,'verified':True,'receipt_path':str(receipt),
                  'receipt_sha256':g.file_sha(receipt)}
        self.assertIsNone(g.verify_success(task,evidence))

    def test_low_disk_prevents_backup_and_mutation(self):
        with patch.object(g.shutil,'disk_usage',return_value=SimpleNamespace(free=5*1024**3)):
            with self.assertRaisesRegex(g.MemoryHold,'DISK_RESERVE'):g.snapshot_database(self.db,self.root/'refused.sqlite')
        self.assertFalse((self.root/'refused.sqlite').exists())

    def test_semantic_probe_cannot_pass_constant_vectors_or_ties(self):
        result=g.semantic_probe(lambda texts,timeout:[vector(0) for _ in texts])
        self.assertEqual(result['state'],'SEMANTIC_FIXTURE_FAILED')
        self.assertFalse(any(row['passed'] for row in result['cases']))
        def real_shape(texts,timeout):
            query_index=2 if '¿' in texts[-1] else 1
            return [vector(0),vector(1),vector(2),vector(query_index)]
        self.assertEqual(g.semantic_probe(real_shape)['state'],'SYNTHETIC_SEMANTIC_FIXTURES_VERIFIED')


if __name__=='__main__':unittest.main()
