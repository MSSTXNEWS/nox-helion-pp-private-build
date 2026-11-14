"""End-to-end API-contract tests for the existing NOX PRIME router, no real network.

Mock Ollama transport only, but read/write a real temporary JSONL journal.
The test records what is proven at SOURCE level, not Windows/E07 acceptance.
"""
from __future__ import annotations
import io,json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import nox_unified_brain_v1 as core
import nox_prime_semantic_retriever_v1 as semantic

class Response(io.BytesIO):
    def __enter__(self):return self
    def __exit__(self,*exc):self.close()

def remote(request,timeout):
    if isinstance(request,str):
        return Response(json.dumps({"models":[{"name":"qwen3:8b"}]}).encode("utf-8"))
    obj=json.loads(request.data.decode("utf-8"))
    if obj.get("stream"):
        return Response(b'{"message":{"content":"NOX "},"done":false}\n'
                        b'{"message":{"content":"na svyazi"},"done":false}\n'
                        b'{"done":true,"eval_count":5,"eval_duration":1000000000}\n')
    return Response(json.dumps({"message":{"content":"NOX answer"}}).encode("utf-8"))

class LivePipeline(unittest.TestCase):
    def test_first_event_preparing_and_stream_saved(self):
        with TemporaryDirectory() as tmp:
            with patch.object(core,"available",return_value=["qwen3:8b"]),\
                 patch.object(core,"urlopen",side_effect=remote):
                stream=core.stream_chat(Path(tmp),{"message":"Привет","task":"general"})
                self.assertEqual(next(stream)["type"],"preparing")
                events=list(stream)
            self.assertEqual(events[0]["type"],"start")
            self.assertEqual([e["text"] for e in events if e["type"]=="delta"],
                             ["NOX ","na svyazi"])
            self.assertEqual(events[-1]["type"],"done")
            self.assertTrue(events[-1]["saved"])
            entries=core.read_history(Path(tmp))
            self.assertEqual(len(entries),2)
            self.assertEqual(entries[1]["content"],"NOX na svyazi")

    def test_non_stream_is_also_persisted(self):
        with TemporaryDirectory() as tmp:
            with patch.object(core,"available",return_value=["qwen3:8b"]),\
                 patch.object(core,"urlopen",side_effect=remote):
                data=core.chat(Path(tmp),{"message":"Проверка","task":"general"})
            self.assertTrue(data["history_persisted"])
            self.assertFalse(data["s03_integrated"])
            self.assertEqual(core.read_history(Path(tmp))[1]["content"],"NOX answer")

    def test_memory_untrusted_data_not_system(self):
        with TemporaryDirectory() as tmp:
            core.save_turn(Path(tmp),"Что было с GPU?","Мы проверяли температуру Hot Spot.")
            with patch.object(core,"available",return_value=["qwen3:8b"]),\
                 patch.object(semantic,"trainer_active",return_value=True):
                _,messages,_=core.prepare_chat(Path(tmp),{
                    "message":"Помнишь GPU Hot Spot?","task":"general"})
            self.assertEqual(messages[0]["role"],"system")
            payloads=[x for x in messages if "NOX MEMORY EVIDENCE" in x["content"]]
            self.assertEqual(len(payloads),1)
            self.assertEqual(payloads[0]["role"],"user")
            self.assertIn("NOX_LOCAL_TRANSCRIPT",payloads[0]["content"])

    def test_soul_status_does_not_claim_ru_model(self):
        with TemporaryDirectory() as tmp:
            with patch.object(core,"available",return_value=["qwen3:8b","qwen3-embedding:0.6b"]):
                s=core.status(Path(tmp))
            self.assertFalse(s["soul_affect"]["available"])
            self.assertTrue(s["semantic_embedding_installed"])
            self.assertFalse(s["lora_applied_to_ollama"])
            self.assertFalse(s["native_s03_chat_writes_connected"])

    def test_stream_error_no_false_saved_history(self):
        def failure(req,timeout):
            raise OSError("Ollama unavailable")
        with TemporaryDirectory() as tmp:
            with patch.object(core,"available",return_value=["qwen3:8b"]),\
                 patch.object(core,"urlopen",side_effect=failure):
                gen=core.stream_chat(Path(tmp),{"message":"Привет"})
                self.assertEqual(next(gen)["type"],"preparing")
                with self.assertRaises(OSError):
                    list(gen)
            self.assertEqual(core.read_history(Path(tmp)),[])
if __name__=="__main__":
    unittest.main()
