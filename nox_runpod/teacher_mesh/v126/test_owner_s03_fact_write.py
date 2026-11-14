"""Isolated source regression. Never touches live S03 or user content."""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from nox_runpod.teacher_mesh.v126 import owner_s03_fact_write as facts

class OriginalS03IsolatedFixtures(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        db=Path(self.tmp.name)/'existing_s03.sqlite'
        with sqlite3.connect(db) as conn:
            conn.executescript("""
            CREATE TABLE s03_items (
              id TEXT PRIMARY KEY, segment TEXT NOT NULL, text TEXT NOT NULL,
              provenance TEXT, sha256 TEXT, salience REAL, ts TEXT NOT NULL, meta TEXT
            );
            """)
        def native_remember(text,segment="M1",provenance="chat",salience=.5,meta=None,db=None):
            with sqlite3.connect(str(db or self.db)) as con:
                con.execute("INSERT INTO s03_items VALUES (?,?,?,?,?,?,?,?)",(
                    uuid.uuid4().hex,segment,text,provenance,
                    hashlib.sha256(text.encode("utf8")).hexdigest(),salience,
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps(meta or {},ensure_ascii=False)))
        self.db=db
        self.s03=SimpleNamespace(DB=str(db),remember=native_remember)
        patcher=patch.dict(sys.modules,{"s03_memory":self.s03})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app=FastAPI()
        facts.register_nox_v126_owner_facts(self.app,{
            "_session_ok":lambda req:req.cookies.get('nox_owner')=='yes',
            "_unauthorized":lambda:JSONResponse({"error":"OWNER_REQUIRED"},status_code=401)})
        self.client=TestClient(self.app)
        self.payload={
            "fact_key":"OWNER-NOTE-V126-TEST",
            "content":"Контрольная запись тестового контура NOX без пользовательских данных",
            "valid_from":datetime.now(timezone.utc).isoformat(),
            "source_ref":"OWNER-CONFIRMED-NOTE"}
        self.payload["source_sha256"]=hashlib.sha256(self.payload["content"].encode()).hexdigest()

    def test_exact_source_and_memory_receipt(self):
        response=self.client.post("/api/nox/memory/facts",json=self.payload,cookies={"nox_owner":"yes"})
        self.assertEqual(response.status_code,200,response.text)
        row=response.json()
        self.assertEqual(row["status"],"COMMITTED")
        self.assertFalse(row["idempotent"])
        self.assertEqual(row["source"],"ORIGINAL_NATIVE_S03_M2")
        self.assertEqual(row["evidence_status"],"OWNER_ATTESTED_NOT_INDEPENDENTLY_VERIFIED")
        with sqlite3.connect(self.db) as db:
            record=db.execute("SELECT segment,sha256,text,provenance,meta FROM s03_items").fetchone()
        self.assertEqual(record[0],"M2")
        self.assertEqual(record[1],self.payload["source_sha256"])
        self.assertEqual(record[2],self.payload["content"])
        self.assertEqual(json.loads(record[4])["fact_key"],self.payload["fact_key"])
        self.assertEqual(self.client.post("/api/nox/memory/facts",json=self.payload,cookies={"nox_owner":"yes"}).json()["idempotent"],True)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM s03_items").fetchone()[0],1)
            self.assertEqual(db.execute("PRAGMA quick_check").fetchone()[0],"ok")
    def test_no_anonymous_write(self):
        response=self.client.post("/api/nox/memory/facts",json=self.payload)
        self.assertEqual(response.status_code,401)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM s03_items").fetchone()[0],0)
    def test_reject_tampered_sha(self):
        change={**self.payload,"source_sha256":"a"*64}
        response=self.client.post("/api/nox/memory/facts",json=change,cookies={"nox_owner":"yes"})
        self.assertEqual(response.status_code,422)
    def test_owner_fact_key_conflict_never_overwrites(self):
        self.assertEqual(self.client.post("/api/nox/memory/facts",json=self.payload,cookies={"nox_owner":"yes"}).status_code,200)
        alternative="Новое утверждение несовместимо с предыдущим"
        change={**self.payload,"content":alternative,
                "source_sha256":hashlib.sha256(alternative.encode()).hexdigest()}
        response=self.client.post("/api/nox/memory/facts",json=change,cookies={"nox_owner":"yes"})
        self.assertEqual(response.status_code,503)
        self.assertIn("HOLD_FACT_KEY_CONFLICT",response.text)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM s03_items").fetchone()[0],1)
    def test_fail_closed_when_original_writer_missing(self):
        self.s03.remember=None
        response=self.client.post("/api/nox/memory/facts",json=self.payload,cookies={"nox_owner":"yes"})
        self.assertEqual(response.status_code,503)
        self.assertIn("HOLD_ORIGINAL_WRITER_MISSING",response.text)
    def test_reject_invalid_json_media_and_length(self):
        with self.assertRaisesRegex(ValueError,"TIMEZONE_REQUIRED"):
            facts._validate({**self.payload,"valid_from":"2026-11-15T12:00:00"})
        self.assertEqual(self.client.post("/api/nox/memory/facts",data="text",headers={"Content-Type":"text/plain"},cookies={"nox_owner":"yes"}).status_code,415)
        self.assertEqual(self.client.post("/api/nox/memory/facts",json={**self.payload,"content":"X"*6000},cookies={"nox_owner":"yes"}).status_code,422)
    def test_new_route_collision_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,"HOLD_OWNER_FACT_ROUTE_CONFLICT"):
            facts.register_nox_v126_owner_facts(self.app,{"_session_ok":lambda req:True,"_unauthorized":lambda:None})

if __name__=="__main__":
    unittest.main()
