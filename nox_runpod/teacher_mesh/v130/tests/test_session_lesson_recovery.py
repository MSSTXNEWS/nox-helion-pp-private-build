"""Isolated owner-fact lesson import and restart readback; never touches live S03."""
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from nox_runpod.teacher_mesh.v130 import owner_s03_fact_write as api

FIXTURE = Path(__file__).parent / "fixtures/session_access_evidence_lesson.json"


class SessionLessonRecoveryTests(unittest.TestCase):
    def test_lesson_import_survives_disposable_clone_restart_and_deduplicates(self):
        lesson = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(lesson["source_sha256"], hashlib.sha256(lesson["content"].encode()).hexdigest())
        self.assertIn("SOURCE_TESTED", lesson["content"])
        self.assertIn("LIVE_VERIFIED", lesson["content"])
        data = api._validate(lesson)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "synthetic-source.sqlite"
            clone = root / "disposable-clone.sqlite"
            stop = root / "STOP"
            with sqlite3.connect(source) as db:
                db.execute("CREATE TABLE s03_items(id TEXT PRIMARY KEY,segment TEXT,text TEXT,provenance TEXT,sha256 TEXT,meta TEXT,ts TEXT)")
            source_before = hashlib.sha256(source.read_bytes()).hexdigest()
            clone.write_bytes(source.read_bytes())
            clone_digest = hashlib.sha256(clone.read_bytes()).hexdigest()
            self.assertEqual(clone_digest, source_before)
            self.assertEqual(clone.stat().st_size, source.stat().st_size)

            child = r'''
import hashlib, json, sqlite3, sys, types, uuid
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from nox_runpod.teacher_mesh.v130 import owner_s03_fact_write as api
db_path, fixture_path, stop_path = map(Path, sys.argv[1:])
memory = types.ModuleType('s03_memory'); memory.DB = db_path
def remember(*, text, segment, provenance, salience, meta):
    record = hashlib.sha256((segment+'|'+text+'|'+provenance+'|'+json.dumps(meta,sort_keys=True)).encode()).hexdigest()
    with sqlite3.connect(db_path) as db:
        db.execute('INSERT INTO s03_items VALUES(?,?,?,?,?,?,?)',
          (uuid.uuid4().hex,segment,text,provenance,record,json.dumps(meta,ensure_ascii=False),'2026-11-16T00:00:00Z'))
memory.remember=remember; sys.modules['s03_memory']=memory
api._STOP=(str(stop_path),)
app=FastAPI(); api.register_nox_v130_owner_fact_write(app,{
  '_session_ok':lambda r:r.cookies.get('owner')=='yes',
  '_unauthorized':lambda:JSONResponse({'error':'AUTH'},status_code=401)})
with TestClient(app) as client:
    payload=json.loads(fixture_path.read_text(encoding='utf-8'))
    response=client.post('/api/nox/memory/facts',json=payload,cookies={'owner':'yes'})
    assert response.status_code==200, response.text
    proof=response.json()
    assert proof['committed'] and proof['readback_verified'] and not proof['duplicate']
    print(json.dumps(proof,sort_keys=True))
'''
            result = subprocess.run(
                [sys.executable, "-c", child, str(clone), str(FIXTURE), str(stop)],
                check=True, capture_output=True, text=True,
            )
            proof = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(proof["source"], "EXISTING_NATIVE_S03_M2")
            self.assertFalse(proof["duplicate"])

            # New interpreter-equivalent module binding reads the clone after child exit.
            memory = types.ModuleType("s03_memory")
            memory.DB = clone
            previous = sys.modules.get("s03_memory")
            sys.modules["s03_memory"] = memory
            self.addCleanup(lambda: sys.modules.pop("s03_memory", None) if previous is None
                            else sys.modules.__setitem__("s03_memory", previous))
            with mock.patch.object(api, "_STOP", (str(stop),)):
                recalled = api._matching(data)
                self.assertEqual(len(recalled), 1)
                self.assertEqual(recalled[0]["id"], proof["event_id"])
                duplicate = api._persist(data)
                self.assertTrue(duplicate["duplicate"])
                self.assertEqual(duplicate["event_id"], proof["event_id"])

            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), source_before)
            with sqlite3.connect(clone) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM s03_items").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
