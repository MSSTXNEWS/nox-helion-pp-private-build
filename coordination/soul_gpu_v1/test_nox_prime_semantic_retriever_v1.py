"""NOX local semantic retrieval contract; no real GPU/API/network."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import nox_prime_semantic_retriever_v1 as m

def save(root,role,content,persona="PRIME"):
    p=Path(root)/"brain"/"history"/"unified_chat_v1.jsonl"
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("a",encoding="utf-8") as f:
        f.write(json.dumps({"persona_id":persona,"role":role,"content":content,
                            "time":"2026-11-07T12:00:00+00:00"},ensure_ascii=False)+"\n")

class SemanticTests(unittest.TestCase):
    def test_memory_query_is_explicit(self):
        self.assertTrue(m.explicit_memory_query("Что мы обсуждали вчера?"))
        self.assertFalse(m.explicit_memory_query("Привет, как дела?"))
    def test_gpu_busy_no_semantic_request(self):
        with TemporaryDirectory() as d:
            save(d,"user","Мы исправляли PowerShell.")
            save(d,"assistant","Нашли кавычку.")
            with patch.object(m,"trainer_active",return_value=True),\
                 patch.object(m,"_embedding_batch",side_effect=AssertionError("Cannot use GPU")):
                x=m.retrieve(d,"Помнишь PowerShell?")
            self.assertEqual(x["method"],"LEXICAL")
            self.assertEqual(x["reason"],"GPU_TRAINING_ACTIVE_OR_UNVERIFIED")
    def test_actual_semantic_vector_ranking(self):
        with TemporaryDirectory() as d:
            save(d,"user","Как мы исправили проблему в PowerShell?")
            save(d,"assistant","Заменили неправильно экранированные кавычки.")
            save(d,"user","Что с графикой D02?")
            save(d,"assistant","Скорость анимации зависит от GPU.")
            vecs=[[1.0]+[0.0]*31,[0.99,0.01]+[0.0]*30,
                  [0.0,1.0]+[0.0]*30]
            with patch.object(m,"trainer_active",return_value=False),\
                 patch.object(m,"_embedding_batch",return_value=vecs) as emb:
                x=m.retrieve(d,"Помнишь проблему консоли?",limit=1)
            self.assertEqual(x["method"],"QWEN3_EMBEDDING_LOCAL")
            self.assertEqual(len(x["results"]),1)
            self.assertIn("PowerShell",x["results"][0]["user"])
            self.assertFalse(x["results"][0]["verified"])
            self.assertEqual(emb.call_count,1)
    def test_safety_unknown_gpu(self):
        with TemporaryDirectory() as d:
            save(d,"user","Исправляли ошибки памяти.")
            save(d,"assistant","Тесты пройдены.")
            with patch.object(m,"trainer_active",return_value=None),\
                 patch.object(m,"_embedding_batch",side_effect=AssertionError("skip")):
                x=m.retrieve(d,"Что помнишь о памяти?")
            self.assertEqual(x["method"],"LEXICAL")
    def test_private_persona_not_embedded(self):
        with TemporaryDirectory() as d:
            save(d,"user","Секретный проект KV",persona="KV")
            save(d,"assistant","Нельзя переносить в PRIME",persona="KV")
            with patch.object(m,"trainer_active",return_value=False),\
                 patch.object(m,"_embedding_batch",side_effect=AssertionError("skip")):
                x=m.retrieve(d,"Помнишь секретный проект?")
            self.assertEqual(x["results"],[])
if __name__=="__main__":
    unittest.main()
