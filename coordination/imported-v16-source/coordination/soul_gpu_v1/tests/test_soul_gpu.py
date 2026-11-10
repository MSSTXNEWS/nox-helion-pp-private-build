import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from soul_gpu import SoulStore, choose_model, is_deep, system_text, gpu_info, installed_model_pair
from identity_behavior import CORE_IDS,PERSONA_NAMES
from unittest.mock import patch
from io import BytesIO

class SoulTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.db = SoulStore(Path(self.t.name))

    def tearDown(self):
        self.t.cleanup()

    def test_requires_approval(self):
        with self.assertRaises(PermissionError):
            self.db.remember(persona="KV",project="p",text="secret",kind="fact",source="test",approved=False)

    def test_persona_project_isolation(self):
        self.db.remember(persona="KV",project="p",text="passwordless cat catalogue",kind="fact",source="owner:test",approved=True)
        self.assertEqual(len(self.db.recall("KV","p","cat")),1)
        self.assertEqual(self.db.recall("AM","p","cat"),[])
        self.assertEqual(self.db.recall("KV","other","cat"),[])

    def test_duplicate_memory_dedup(self):
        for _ in range(3):
            self.db.remember(persona="KV",project="p",text="memorable",kind="fact",source="owner:1",approved=True)
        self.assertEqual(len(self.db.recall("KV","p","memorable")),1)

    def test_skills_require_evidence_and_isolate(self):
        with self.assertRaises(ValueError): self.db.skill_event("KV","p","test",True,"")
        self.db.skill_event("KV","p","programming",True,"run#1 success")
        x = self.db.skill_event("KV","p","programming",False,"run#2 failure")
        self.assertEqual((x["successes"],x["failures"]),(1,1))
        self.assertEqual(self.db.skills("EV","p"),[])

    def test_simulated_affect_no_conscious_claim(self):
        self.assertTrue(self.db.affect_event("LA","success","unit test")["simulated"])
        prompt=system_text(self.db,"LA","p","hello",True)
        self.assertIn("Ты — NOX HELION",prompt)
        self.assertIn("Твои вычислительные состояния моделируют",prompt)
        self.assertIn("Кайрен",",".join(PERSONA_NAMES.values()))

    def test_persistent_behavior_events_dedup_and_isolation(self):
        kwargs=dict(persona="KV",project="p",event_id="evt-20261106-001",
                    kind="discovery",evidence="owner reviewed hypothesis",
                    source="owner:review")
        with self.assertRaises(PermissionError):
            self.db.behavior_event(**kwargs,approved=False)
        before=self.db.behavior_state("KV","p")
        one=self.db.behavior_event(**kwargs,approved=True)
        self.assertEqual(one["status"],"observed")
        self.assertGreater(one["curiosity"],before["curiosity"])
        twice=self.db.behavior_event(**kwargs,approved=True)
        self.assertEqual(twice["status"],"already-observed")
        self.assertEqual(twice["events"],1)
        self.assertEqual(self.db.behavior_state("AM","p")["events"],0)
        self.assertEqual(self.db.behavior_state("KV","different")["events"],0)
        reopened=SoulStore(Path(self.t.name))
        self.assertEqual(reopened.behavior_state("KV","p")["events"],1)
        self.assertIn("HF08",system_text(reopened,"KV","p","hi",False))

    def test_behavior_event_bounds_and_source_integrity(self):
        with self.assertRaises(ValueError):
            self.db.behavior_event(persona="EV",project="p",event_id="short",
                  kind="success",evidence="ok",source="owner",approved=True)
        with self.assertRaises(ValueError):
            self.db.behavior_event(persona="EV",project="p",event_id="evt-20261106",
                  kind="made-up",evidence="ok",source="owner",approved=True)

    def test_existing_ollama_model_pair_for_amd_no_cuda(self):
        class Response:
            def __enter__(self):
                return BytesIO(b'{"models":[{"name":"qwen3:4b-instruct"},{"name":"qwen3:8b"},{"name":"qwen3-embedding:0.6b"}]}')
            def __exit__(self,*args):
                pass
        with patch("soul_gpu.request.urlopen",return_value=Response()):
            self.assertEqual(installed_model_pair(),("qwen3:4b-instruct","qwen3:8b"))

    def test_invalid_persona(self):
        with self.assertRaises(ValueError):self.db.recall("unknown","p","x")

    def test_auto_model_gpu(self):
        self.assertEqual(choose_model({"gpus":[{"vram_mib":12288}]}),"qwen3:4b-instruct")
        self.assertEqual(choose_model({"gpus":[{"vram_mib":12288}]},True),"qwen3:8b")
        self.assertEqual(choose_model({"gpus":[]}),"qwen3:1.7b")

    def test_complexity(self):
        self.assertTrue(is_deep("сделай алгоритм"))
        self.assertFalse(is_deep("привет"))

if __name__ == "__main__": unittest.main()
