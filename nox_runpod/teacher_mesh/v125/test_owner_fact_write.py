"""V125 live-contract tests against isolated original-S03-schema SQLite.

No Vast connection, second S03 database on server, network calls or test mocks
in the shipping API. TestClient only invokes the actual FastAPI route module.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
import sys
import tempfile
import types
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from nox_runpod.teacher_mesh.v125 import owner_fact_write as writer


class OriginalS03FactTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db=Path(tmp.name)/'existing_original_s03.sqlite'
        with sqlite3.connect(self.db) as db:
            db.execute("""CREATE TABLE s03_items (
                id TEXT PRIMARY KEY, segment TEXT NOT NULL,
                text TEXT NOT NULL, provenance TEXT, sha256 TEXT,
                salience REAL, ts TEXT NOT NULL, meta TEXT)""")
        self.write_count=0
        mock=types.ModuleType("s03_memory")
        mock.DB=self.db
        def real_write(text,segment='M2',provenance=None,salience=0.8,meta=None,db=None):
            self.write_count+=1
            row_id=uuid.uuid4().hex
            with sqlite3.connect(self.db) as conn:
                conn.execute("INSERT INTO s03_items VALUES(?,?,?,?,?,?,?,?)",(
                    row_id,segment,text,provenance,
                    hashlib.sha256(text.encode()).hexdigest(),salience,
                    datetime.now(timezone.utc).isoformat(),json.dumps(meta)))
            return {"id":row_id}
        mock.remember=real_write
        previous=sys.modules.get("s03_memory")
        sys.modules["s03_memory"]=mock
        self.addCleanup(lambda:sys.modules.pop("s03_memory",None) if previous is None
                        else sys.modules.__setitem__("s03_memory",previous))
        patcher=patch.object(writer,"_stopped",return_value=False)
        self.stopped=patcher.start()
        self.addCleanup(patcher.stop)
        self.app=FastAPI()
        writer.register_nox_v125_owner_fact_write(
            self.app,{"_session_ok":lambda req:req.cookies.get('session')=='owner',
                      "_unauthorized":lambda:JSONResponse({'error':'AUTH'},status_code=401)})
        self.client=TestClient(self.app)
        self.addCleanup(self.client.close)
        self.cookie={'session':'owner'}

    def body(self,content='NOX knowledge verified by owner',key='WORK-01'):
        return {'fact_key':key, 'content':content,
                'source_ref':'OWNER-CONFIRMED-NOTE',
                'source_sha256':hashlib.sha256(content.encode()).hexdigest(),
                'valid_from':'2026-11-15T00:00:00.000Z'}

    def records(self):
        with sqlite3.connect(self.db) as db:
            return db.execute(
                'SELECT id,segment,text,provenance,meta FROM s03_items ORDER BY ts').fetchall()

    def test_first_save_is_real_original_m2_row(self):
        note=self.body()
        result=self.client.post('/api/nox/memory/facts',cookies=self.cookie,json=note)
        self.assertEqual(result.status_code,200,result.text)
        data=result.json()
        self.assertEqual(data['status'],'SAVED')
        self.assertIs(data['s03_integrated'],True)
        self.assertIs(data['neural_weights_changed'],False)
        self.assertEqual(data['id'],data['event_id'])
        self.assertIs(data['deduplicated'],False)
        self.assertEqual(self.write_count,1)
        row=self.records()[0]
        self.assertEqual(row[0],data['event_id'])
        self.assertEqual(row[1:3],('M2',note['content']))
        self.assertIn('|OWNER-CONFIRMED-NOTE',row[3])
        meta=json.loads(row[4])
        self.assertEqual(meta['fact_key'],note['fact_key'])
        self.assertTrue(meta['owner_confirmed'])

    def test_second_identical_request_deduplicates_with_original_receipt(self):
        note=self.body()
        first=self.client.post('/api/nox/memory/facts',cookies=self.cookie,json=note).json()
        second=self.client.post('/api/nox/memory/facts',cookies=self.cookie,json=note)
        self.assertEqual(second.status_code,200)
        self.assertEqual(second.json()['event_id'],first['event_id'])
        self.assertIs(second.json()['deduplicated'],True)
        self.assertEqual(self.write_count,1)
        self.assertEqual(len(self.records()),1)

    def test_revised_fact_is_new_append_only_record_and_links_previous(self):
        first=self.body('Первая версия')
        second=self.body('Исправленная версия')
        id1=self.client.post('/api/nox/memory/facts',cookies=self.cookie,json=first).json()['event_id']
        saved=self.client.post('/api/nox/memory/facts',cookies=self.cookie,json=second)
        self.assertEqual(saved.status_code,200)
        self.assertEqual(saved.json()['supersedes'],id1)
        self.assertEqual(len(self.records()),2)
        self.assertEqual(json.loads(self.records()[1][4])['supersedes'],id1)

    def test_new_fact_is_discoverable_by_original_v120_history(self):
        from nox_runpod.teacher_mesh.v120.s03_owner_memory_views import _knowledge
        note=self.body(content='Сохраняем для исходной памяти NOX',key='CHAT-NOTE-EXAMPLE-01')
        response=self.client.post('/api/nox/memory/facts',cookies=self.cookie,json=note)
        self.assertEqual(response.status_code,200)
        matches=_knowledge(q=note['fact_key'],facts_only=True,limit=32)
        self.assertEqual(len(matches),1)
        self.assertEqual(matches[0]['content'],note['content'])
        self.assertEqual(matches[0]['id'],response.json()['event_id'])
        self.assertIn(note['fact_key'],matches[0]['source_ref'])

    def test_key_delimiter_injection_is_rejected_before_s03_write(self):
        data=self.body(key='A|B')
        response=self.client.post('/api/nox/memory/facts',cookies=self.cookie,json=data)
        self.assertEqual(response.status_code,422)
        self.assertEqual(self.write_count,0)

    def test_not_authenticated_is_401_no_write(self):
        result=self.client.post('/api/nox/memory/facts',json=self.body())
        self.assertEqual(result.status_code,401)
        self.assertEqual(self.write_count,0)

    def test_refuses_forged_or_bad_checksum(self):
        data=self.body()
        data['source_sha256']='0'*64
        result=self.client.post('/api/nox/memory/facts',cookies=self.cookie,json=data)
        self.assertEqual(result.status_code,422)
        self.assertEqual(result.json()['error'],'SOURCE_SHA256_MISMATCH')
        self.assertEqual(self.write_count,0)

    def test_stop_gate_forbids_original_s03_mutation(self):
        self.stopped.return_value=True
        result=self.client.post('/api/nox/memory/facts',cookies=self.cookie,json=self.body())
        self.assertEqual(result.status_code,409)
        self.assertEqual(self.write_count,0)

    def test_bad_payload_and_huge_body_are_bounded(self):
        big=self.body(content='x'*5200)
        result=self.client.post('/api/nox/memory/facts',cookies=self.cookie,json=big)
        self.assertEqual(result.status_code,422)
        payload=b' '*18000
        result=self.client.post('/api/nox/memory/facts',cookies=self.cookie,data=payload)
        self.assertEqual(result.status_code,413)
        self.assertEqual(self.write_count,0)

    def test_native_storage_failure_returns_hold_not_fake_saved(self):
        previous=sys.modules['s03_memory'].remember
        def unavailable(*args,**kwargs):
            raise sqlite3.OperationalError('temporary failure from original db')
        sys.modules['s03_memory'].remember=unavailable
        self.addCleanup(lambda:setattr(sys.modules['s03_memory'],'remember',previous)
                        if 's03_memory' in sys.modules else None)
        result=self.client.post('/api/nox/memory/facts',cookies=self.cookie,json=self.body())
        self.assertEqual(result.status_code,503)
        self.assertEqual(result.json()['status'],'HOLD')
        self.assertEqual(len(self.records()),0)

    def test_rejects_conflict_with_existing_native_route(self):
        with self.assertRaisesRegex(RuntimeError,'HOLD_EXISTING_FACT_ROUTE_CONFLICT'):
            writer.register_nox_v125_owner_fact_write(self.app,{
                '_session_ok':lambda req: True,
                '_unauthorized':lambda: JSONResponse({},status_code=401)})


if __name__=='__main__':
    unittest.main()
