"""Owner-confirmed V125/V130 facts must be discoverable in original V120 S03 history.

Uses original schema with ephemeral fixture only. Never connects to Vast and
never creates a second real S03 database, scheduler, backend or model.
"""
import hashlib
import json
import sqlite3
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from nox_runpod.teacher_mesh.v120 import s03_owner_memory_views as history
from nox_runpod.teacher_mesh.v130 import owner_s03_fact_write as owner


class NativeS03FactHistory(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        db=Path(t.name)/"existing-original-s03.sqlite"
        self.db_path=db
        with sqlite3.connect(db) as con:
            con.execute("""CREATE TABLE s03_items (
                id TEXT PRIMARY KEY, segment TEXT NOT NULL, text TEXT NOT NULL,
                provenance TEXT, sha256 TEXT, salience REAL, ts TEXT NOT NULL, meta TEXT)""")
        self.fake=types.ModuleType("s03_memory")
        self.fake.DB=db
        self.writes=0
        def remember(*,text,segment,provenance,salience,meta):
            self.writes+=1
            identifier=uuid.uuid4().hex
            with sqlite3.connect(db) as con:
                con.execute("INSERT INTO s03_items VALUES(?,?,?,?,?,?,?,?)",(
                    identifier, segment, text, provenance,
                    hashlib.sha256((segment+'|'+text+'|'+provenance+'|'+json.dumps(meta,sort_keys=True)).encode('utf8')).hexdigest(),salience,
                    '2026-11-15T00:00:00Z',json.dumps(meta,ensure_ascii=True)))
            return identifier
        self.fake.remember=remember
        old=sys.modules.get("s03_memory")
        sys.modules["s03_memory"]=self.fake
        self.addCleanup(lambda:sys.modules.pop("s03_memory",None) if old is None
                        else sys.modules.__setitem__("s03_memory",old))
        self.stop_patch=patch.object(owner,"_stopped",return_value=False)
        self.stop_patch.start()
        self.addCleanup(self.stop_patch.stop)
        app=FastAPI()
        authentic={'_session_ok': lambda request:request.cookies.get('owner')=='yes',
                   '_unauthorized':lambda:JSONResponse({"error":"AUTH"},status_code=401)}
        owner.register_nox_v130_owner_fact_write(app,authentic)
        history.register_nox_v120_s03_memory_views(app,authentic)
        self.client=TestClient(app)
        self.addCleanup(self.client.close)
        self.cookies={'owner':'yes'}

    def payload(self,key,content):
        return {'fact_key':key,'content':content,
                'valid_from':'2026-11-15T00:00:00.000Z',
                'source_ref':'NOX-OWNER-VERIFIED',
                'source_sha256':hashlib.sha256(content.encode('utf8')).hexdigest()}

    def save(self,payload):
        return self.client.post('/api/nox/memory/facts',
                                json=payload,cookies=self.cookies)

    def query(self,key):
        return self.client.get('/api/ui/memory/facts/history',
                               params={'fact_key':key},cookies=self.cookies)

    def test_v130_fact_key_search_uses_original_meta_not_missing_provenance(self):
        body=self.payload('OWNED-132-A','Сохранить факт номер один')
        first=self.save(body)
        self.assertEqual(first.status_code,200,first.text)
        id1=first.json()['event_id']
        response=self.query(body['fact_key'])
        self.assertEqual(response.status_code,200,response.text)
        events=response.json()['events']
        self.assertEqual(len(events),1,events)
        self.assertEqual(events[0]['id'],id1)
        self.assertEqual(events[0]['fact_key'],body['fact_key'])
        self.assertEqual(events[0]['content'],body['content'])
        self.assertEqual(events[0]['source_sha256'],body['source_sha256'])
        self.assertEqual(events[0]['submitted_content_sha256'],body['source_sha256'])
        # Real S03 rows can hash structured fields; their record digest is
        # not interchangeable with the user's source text checksum.
        self.assertNotEqual(events[0]['record_sha256'],body['source_sha256'])
        self.assertEqual(first.json()['record_sha256'],events[0]['record_sha256'])
        self.assertEqual(self.writes,1)

    def test_two_identical_contents_different_keys_are_distinct(self):
        content='Одинаковый текст, разные ключи'
        a=self.payload('KEY-A',content)
        b=self.payload('KEY-B',content)
        self.assertEqual(self.save(a).status_code,200)
        self.assertEqual(self.save(b).status_code,200)
        self.assertEqual(self.writes,2)
        for key in ('KEY-A','KEY-B'):
            events=self.query(key).json()['events']
            self.assertEqual(len(events),1)
            self.assertEqual(events[0]['fact_key'],key)

    def test_legacy_v125_provenance_still_searches_literal_key(self):
        marker='NOX-V125-LEGACY-01'
        content='Исторический подтверждённый факт V125'
        metadata={'fact_key':marker,'source_sha256':hashlib.sha256(content.encode()).hexdigest()}
        with sqlite3.connect(self.db_path) as con:
            con.execute("INSERT INTO s03_items VALUES(?,?,?,?,?,?,?,?)",(
                'legacy-v125-record','M2',content,
                'owner-fact:'+marker+'|NOX-LOCAL-QA-VERIFIED',
                hashlib.sha256(content.encode()).hexdigest(),
                0.8,'2026-11-15T00:00:00Z',json.dumps(metadata)))
        response=self.query(marker)
        self.assertEqual(response.status_code,200)
        events=response.json()['events']
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['id'],'legacy-v125-record')
        self.assertEqual(events[0]['fact_key'],marker)

    def test_invalid_meta_source_digest_cannot_replace_native_hash(self):
        marker='SOURCE-META-INVALID'
        content='Original S03 must not advertise a false source digest'
        native_digest=hashlib.sha256(('native-structure|'+content).encode()).hexdigest()
        wrong='a'*64
        self.assertNotEqual(native_digest,wrong)
        with sqlite3.connect(self.db_path) as con:
            con.execute("INSERT INTO s03_items VALUES(?,?,?,?,?,?,?,?)",(
                'legacy-mismatch','M2',content,
                'owner-fact:'+marker+'|OWNER-QA',native_digest,0.5,
                '2026-11-15T00:00:00Z',
                json.dumps({'fact_key':marker,'source_sha256':wrong})))
        result=self.query(marker)
        self.assertEqual(result.status_code,200)
        item=result.json()['events'][0]
        self.assertEqual(item['record_sha256'],native_digest)
        self.assertEqual(item['source_sha256'],native_digest)
        self.assertIsNone(item['submitted_content_sha256'])

    def test_legacy_m2_without_meta_still_retrievable(self):
        with sqlite3.connect(self.db_path) as con:
            con.execute("INSERT INTO s03_items VALUES(?,?,?,?,?,?,?,?)",(
                'legacy-0001','M2','Старый проверенный факт',
                'source:legacy', '0'*64,0.5,'2026-11-15T00:00:00Z',None))
        events=self.query('Старый').json()['events']
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['fact_key'],'legacy-0001')
        self.assertIsNone(events[0]['submitted_content_sha256'])

    def test_metadata_unicode_escapes_are_compatible(self):
        note=self.payload('Заметка-один','Русская запись')
        saved=self.save(note)
        self.assertEqual(saved.status_code,200)
        events=self.query(note['fact_key']).json()['events']
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['fact_key'],note['fact_key'])

    def test_unauthorized_fact_history_never_leaks(self):
        response=self.client.get('/api/ui/memory/facts/history',params={'fact_key':'KEY-A'})
        self.assertEqual(response.status_code,401)
        self.assertEqual(self.writes,0)

    def test_source_history_is_read_only_and_existing_db_remains(self):
        body=self.payload('KEY-C','Реальный пример')
        self.assertEqual(self.save(body).status_code,200)
        self.assertEqual(len(self.query('KEY-C').json()['events']),1)
        self.assertEqual(self.writes,1)
        with sqlite3.connect(self.db_path) as con:
            self.assertEqual(con.execute("PRAGMA quick_check").fetchone()[0],"ok")
            self.assertEqual(con.execute("SELECT COUNT(*) FROM s03_items").fetchone()[0],1)


if __name__=="__main__":
    unittest.main()
