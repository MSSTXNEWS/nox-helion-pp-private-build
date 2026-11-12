#!/usr/bin/env python3
"""Pure unit tests; never call a model, network, subprocess or cloud service."""
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from offline_teacher import OfflineTeacher, infer_offline
from teacher_ensemble import fast_reply, compare_teacher_answers, TeacherCall
from teacher_mesh import TeacherEndpoint, request_teacher

class TestNOXTeacherMesh(unittest.TestCase):
    def test_fast_answer_without_teacher_wait(self):
        calls=[]
        def generate(p,e):
            calls.append((p,e))
            return "NOX отвечает сам"
        out=fast_reply("Привет",nox_generate=generate)
        self.assertEqual(out["state"],"NOX_FIRST_ANSWER")
        self.assertEqual(calls,[("Привет",[])])
        self.assertFalse(out["teachers_pending"])
    def test_background_opt_in_excludes_private(self):
        jobs=[]
        def enqueue(j):
            jobs.append(j); return True
        kwargs=dict(nox_generate=lambda p,e:"Ответ NOX",
                    enqueue_existing_job=enqueue,
                    consent_to_background_learning=True)
        self.assertFalse(fast_reply("private",contains_private_information=True,**kwargs)["teachers_pending"])
        self.assertTrue(fast_reply("public",contains_private_information=False,**kwargs)["teachers_pending"])
        self.assertEqual(len(jobs),1)
        self.assertNotIn("prompt",jobs[0])
    def test_three_teachers_only_nox_final(self):
        def answer(label):
            return lambda prompt: {"status":"MEASURED","answer":"teacher "+label,
                "model_id":label,"model_card_url":"https://huggingface.co/some/card",
                "approved_for_learning":False}
        ts=[TeacherCall(f"t{i}",answer(f"m{i}")) for i in range(3)]
        supplied=[]
        def synth(p,e):
            supplied.extend(e);return "Единый ответ NOX"
        out=compare_teacher_answers("Вопрос",ts,nox_generate=synth,max_concurrent_vms=2,
                                    contains_private_information=False)
        self.assertEqual(out["state"],"NOX_REFINED_WITH_TEACHER_EVIDENCE")
        self.assertEqual(out["teacher_count"],3)
        self.assertEqual(out["nox_answer"],"Единый ответ NOX")
        self.assertEqual(len(supplied),3)
        self.assertEqual(out["training_state"],"NO_WEIGHT_UPDATE_UNTIL_SEPARATE_QUALITY_GATES")
    def test_reject_outbound_private(self):
        t=TeacherCall("remote",lambda x:{"status":"MEASURED","answer":"wrong"},
                      isolated_vm=False)
        out=compare_teacher_answers("private",[t],nox_generate=lambda p,e:"NOX",
                                    contains_private_information=True)
        self.assertEqual(out["state"],"HOLD_PRIVATE_EXTERNAL")
    def test_offline_does_not_download_missing(self):
        t=OfflineTeacher("local","Qwen/Qwen3.5-4B","https://huggingface.co/Qwen/Qwen3.5-4B",
                         "llama_cpp_cli","/models/absent.gguf")
        out=infer_offline(t,"Hello")
        self.assertEqual(out["status"],"HOLD_GGUF_NOT_STAGED")
    def test_external_api_default_off(self):
        t=TeacherEndpoint("remote","Qwen/Qwen3.5-4B",
                          "https://example.org/v1/chat/completions",
                          "https://huggingface.co/Qwen/Qwen3.5-4B",external=True)
        out=request_teacher(t,"my question",external_consent=False,private_prompt=True)
        self.assertEqual(out["status"],"HOLD_EXTERNAL_CONSENT_OR_PRIVATE")
    def test_catalog_exact_50_plus_20(self):
        features=json.loads((ROOT/"catalog_50.json").read_text())
        web=json.loads((ROOT/"web_coding_offline_20.json").read_text())
        models=json.loads((ROOT/"models_registry.json").read_text())
        architecture=json.loads((ROOT/"mycelium_architecture.json").read_text())
        self.assertEqual(len(features["features"]),50)
        self.assertEqual(len(web["items"]),20)
        self.assertEqual(len({x["id"] for x in features["features"]+web["items"]}),70)
        self.assertGreaterEqual(len(models["models"]),12)
        self.assertFalse(models["privacy"]["external_provider_enabled"])
        self.assertEqual(architecture["modes"]["deliberate_comparison"]["teacher_count_max"],5)

if __name__=="__main__":
    unittest.main()
