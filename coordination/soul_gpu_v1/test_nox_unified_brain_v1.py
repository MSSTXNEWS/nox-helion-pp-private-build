"""Contract tests for a single NOX identity/router (no GPU, no network)."""
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import io
import json
import sqlite3
import unittest

import nox_unified_brain_v1 as u


class Response(io.BytesIO):
    def __enter__(self):return self
    def __exit__(self,*exc):self.close()


class UnifiedTests(unittest.TestCase):
    def test_identity(self):
        self.assertEqual(len(u.CORE_IDS),8)
        self.assertIn("NOX PRIME",u.SYSTEM)
        self.assertIn("сознани",u.SYSTEM)
    def test_route(self):
        models=["qwen3:8b","qwen2.5-coder:7b"]
        self.assertEqual(u.choose_model(models,"code"),"qwen2.5-coder:7b")
        self.assertEqual(u.choose_model(models,"general"),"qwen3:8b")
    def test_chat(self):
        requests=[]
        def mocked(req,timeout):
            requests.append(req)
            if isinstance(req,str):return Response(json.dumps({"models":[{"name":"qwen3:8b"}]}).encode())
            request=json.loads(req.data)
            self.assertEqual(request["model"],"qwen3:8b")
            self.assertEqual(request["messages"][0]["role"],"system")
            return Response(json.dumps({"message":{"content":"NOX на связи"}}).encode())
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(u,"urlopen",side_effect=mocked):
                result=u.chat(root,{"message":"Привет","task":"general"})
            self.assertEqual(result["answer"],"NOX на связи")
            self.assertTrue(result["history_persisted"])
            self.assertEqual([v["role"] for v in u.read_history(root)],
                             ["user","assistant"])
        self.assertFalse(result["s03_integrated"])
    def test_read_only_native_db(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            db=root/"soul_gpu"/"soul.sqlite3";db.parent.mkdir()
            # sqlite3.Connection.__exit__ commits/rolls back but does NOT close.
            # Explicit closing is required before TemporaryDirectory cleanup on Windows.
            with closing(sqlite3.connect(db)) as con:
                with con:
                    con.execute("CREATE TABLE demo (x INTEGER)")
            before=db.stat().st_size
            result=u.native_memory_status(root)
            self.assertTrue(result[0]["reachable"])
            self.assertIn("demo",result[0]["tables"])
            self.assertEqual(db.stat().st_size,before)
    def test_never_claim_merge(self):
        with TemporaryDirectory() as tmp:
            with patch.object(u,"available",return_value=["qwen3:8b"]):
                v=u.status(Path(tmp))
            self.assertFalse(v["lora_applied_to_ollama"])
            self.assertFalse(v["native_s03_chat_writes_connected"])
            self.assertFalse(v["subjective_consciousness_verified"])

if __name__=="__main__":unittest.main()
