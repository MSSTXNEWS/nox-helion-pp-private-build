"""Multi-rate memory candidate QA; no Ollama, GPU, native S03 or network."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from datetime import datetime, timezone
from nox_prime_memory_continuum_v1 import snapshot, write_proposal, CORE_IDS, MEMORY_LAYERS

def event(root, role, content, time="2026-11-06T10:00:00Z", persona="PRIME"):
    p=Path(root)/"brain"/"history"/"unified_chat_v1.jsonl"
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("a",encoding="utf-8") as f:
        f.write(json.dumps({"role":role,"content":content,"time":time,
                            "persona_id":persona},ensure_ascii=False)+"\n")

class MemoryContinuumTests(unittest.TestCase):
    def test_layers_are_typed(self):
        self.assertEqual(len(CORE_IDS),8)
        self.assertEqual(len(MEMORY_LAYERS),8)
    def test_frequent_and_less_frequent_views(self):
        with TemporaryDirectory() as d:
            event(d,"user","У нас ошибка старого обучения RX6650M Hot Spot.")
            event(d,"assistant","Мы сохраняли checkpoint и исправляли датчик.")
            result=snapshot(d,query="ошибка обучение",now=datetime(2026,11,7,tzinfo=timezone.utc))
            self.assertEqual(result["m0_events_total"],1)
            self.assertEqual(len(result["fast_session"]),1)
            self.assertEqual(len(result["medium_episodes"]),1)
            self.assertFalse(result["s03_written"])
            self.assertFalse(result["new_llm_weights_trained"])
    def test_no_private_persona_memories(self):
        with TemporaryDirectory() as d:
            event(d,"user","Private KV secret",persona="KV")
            event(d,"assistant","Never leak",persona="KV")
            result=snapshot(d,"private",now=datetime.now(timezone.utc))
            self.assertEqual(result["fast_session"],[])
    def test_skill_requires_evidence_and_owner(self):
        sha="a"*64
        receipts=[{"persona_id":"PRIME","skill":"Windows repair","source_sha256":sha,"status":"PASS"},
                  {"persona_id":"KV","skill":"Do not leak","source_sha256":sha,"status":"PASS"},
                  {"persona_id":"PRIME","skill":"Pretend success","source_sha256":"fake","status":"PASS"}]
        with TemporaryDirectory() as d:
            x=snapshot(d,receipts=receipts)
        self.assertEqual(len(x["slow_skill_candidates"]),1)
        self.assertEqual(x["slow_skill_candidates"][0]["passed"],1)
        self.assertEqual(x["slow_skill_candidates"][0]["admission"],"HOLD_OWNER_QA_AND_S03_BRIDGE")
    def test_restricted_proposal_write(self):
        with TemporaryDirectory() as d:
            event(d,"user","Project architecture and memory")
            event(d,"assistant","This was already documented.")
            target=Path(d)/"brain"/"experiments"/"memory_candidates"/"trial.json"
            receipt=write_proposal(d,target,"memory project")
            self.assertTrue(target.is_file())
            self.assertEqual(receipt["events"],1)
            with self.assertRaises(FileExistsError):
                write_proposal(d,target)
            with self.assertRaises(PermissionError):
                write_proposal(d,Path(d)/"soul_gpu"/"soul.sqlite3")
    def test_invalid_time_timezone(self):
        with TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                snapshot(d,now=datetime(2026,11,7))
if __name__=="__main__":
    unittest.main()
