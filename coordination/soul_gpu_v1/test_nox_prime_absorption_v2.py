"""NOX multi-weight absorption is a real typed registry and candidate process.

Tests use local fake Ollama records; no real local models, network, training,
S03, delete commands or GPU. They ensure honest model classification and
non-destructive per-teacher data preparation.
"""
import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import nox_prime_absorption_registry_v1 as reg
import nox_prime_absorb_text_v2 as distill

def tag(name,digest="a"*64,size=2400000000,family="qwen"):
    return {"name":name,"digest":digest,"size":size,"details":{"family":family}}

class RegistryTests(unittest.TestCase):
    def test_donors_are_not_merged_and_keep_originals(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"brain").mkdir()
            raw=[tag("qwen3:8b"),tag("qwen2.5-coder:7b","b"*64),
                 tag("qwen3-embedding:0.6b","c"*64),tag("wan2.2:5b","d"*64)]
            state=reg.inventory(root,raw)
            self.assertEqual(state["installed_total"],4)
            self.assertEqual(state["eligible_text_teachers"],2)
            self.assertEqual(state["retired_models"],0)
            self.assertFalse(state["weights_merged"])
            self.assertTrue(all(x["original_retained"] for x in state["models"]))
            self.assertFalse(any(x["trained_into_prime"] for x in state["models"]))
            registry=reg.store(root,state)
            self.assertTrue(Path(registry["path"]).is_file())
            self.assertEqual(hashlib.sha256(Path(registry["path"]).read_bytes()).hexdigest(),registry["sha256"])

    def test_vision_audio_embedding_need_other_student(self):
        for name,expected in (("qwen3-embedding:0.6b","embedding_or_reranker"),
                              ("qwen-image:latest","image_or_video"),
                              ("qwen3-tts","audio"),("llava:7b","vision")):
            self.assertEqual(reg._classify(name,{})[0],expected)

    def test_no_blind_model_without_digest(self):
        with TemporaryDirectory() as tmp:
            state=reg.inventory(tmp,[{"name":"unknown:latest","size":700,"details":{}}])
            self.assertEqual(state["eligible_text_teachers"],0)

class TextDistillTests(unittest.TestCase):
    def test_capture_real_teacher_response_with_model_source(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"brain").mkdir()
            raw=[tag("qwen3:8b"),tag("qwen2.5-coder:7b","b"*64),
                 tag("qwen3-embedding:0.6b","c"*64)]
            captured=[]
            def reply(model,prompt):
                captured.append(model)
                return ("Actual mocked teacher response for "+model+" to "+prompt[:50]+
                        " with source-scoped explanation and evidence."),{"eval_count":8,"eval_duration_ns":123}
            with patch.object(distill,"inventory",return_value=reg.inventory(root,raw)),\
                 patch.object(distill,"trainer_active",return_value=False),\
                 patch.object(distill,"_teacher_text",side_effect=reply),\
                 patch.object(distill,"_unload"):
                obj=distill.run(root,questions_per_model=2)
            self.assertEqual(obj["models_scanned"],3)
            self.assertEqual(obj["models_used"],2)
            self.assertEqual(obj["examples"],4)
            self.assertEqual(obj["skipped"],1)
            rows=[json.loads(x) for x in Path(obj["dataset"]).read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows),4)
            self.assertTrue(all(not x["human_verified"] for x in rows))
            self.assertTrue(all(not x["student_weights_trained"] for x in rows))
            self.assertEqual(set(captured),{"qwen3:8b","qwen2.5-coder:7b"})
            self.assertTrue(all(x["source_model_digest"] for x in rows))

    def test_training_active_never_loads_teachers(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"brain").mkdir()
            with patch.object(distill,"trainer_active",return_value=True),\
                 patch.object(distill,"inventory",side_effect=AssertionError("should not call")):
                with self.assertRaises(RuntimeError):distill.run(root)

    def test_invalid_counts_rejected(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"brain").mkdir()
            with self.assertRaises(ValueError):distill.run(root,questions_per_model=0)
            with self.assertRaises(ValueError):distill.run(root,max_models=100)
if __name__=="__main__":
    unittest.main()
