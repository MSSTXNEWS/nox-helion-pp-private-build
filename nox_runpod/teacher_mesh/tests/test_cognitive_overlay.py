#!/usr/bin/env python3
"""Behavior-level tests for model-agnostic NOX cognitive overlay: no network/GPU."""
from datetime import datetime,timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from cognitive_overlay import (
  CognitiveOverlay,MemoryEvidence,CapabilityEvidence,functional_self_model)
from s03_callback_adapter import CallbackS03Adapter,CallbackNOXModelAdapter

T="2026-11-12T01:00:00Z"
NOW=datetime(2026,11,12,1,30,tzinfo=timezone.utc).timestamp()

class FakeS03:
    def __init__(self):
        self.search_calls=[]
        self.capability_calls=[]
        self.writes=[]
        self.records=[
          MemoryEvidence("m-good","NOX checkpoint 106 saved","M4",
              "nox-checkpoint://nox36/step106",T,.9,True,False,"owner"),
          MemoryEvidence("m-private","another scope confidential","M2",
              "s03://private",T,.9,True,False,"another_user"),
          MemoryEvidence("m-stale","step 85 superseded","M4",
              "s03://old",T,.9,True,True,"owner"),
          MemoryEvidence("m-unverified","NOX invented its birthday","M7",
              "s03://unverified",T,1,False,False,"owner"),
          MemoryEvidence("m-source","NOX evolution approved history","M7",
              "github://nox/history",T,.8,True,False,"owner")
        ]
    def search(self,*,query,scope,limit):
        self.search_calls.append((scope,limit))
        return list(self.records)
    def capabilities(self,*,scope):
        self.capability_calls.append(scope)
        return [
            CapabilityEvidence("cap1","A100 GPU seen online","MEASURED",
                "github://nox/a100-run",T,True),
            CapabilityEvidence("cap2","conscious intelligence confirmed","PASSED",
                "github://nox/no-proof",T,False),
        ]
    def append_approved(self,*,scope,event):
        self.writes.append((scope,event))
        return "s03-confirmed-receipt-001"

class FakeModel:
    def __init__(self):
        self.calls=[]
    def generate(self,prompt,context):
        self.calls.append((prompt,context))
        return "NOX: согласно checkpoint 106, теперь проверяю память"

class CognitiveTests(unittest.TestCase):
    def setUp(self):
        self.mem=FakeS03()
        self.model=FakeModel()
        self.overlay=CognitiveOverlay(self.mem,self.model,clock=lambda:NOW,
            approval_validator=lambda scope,event:(
                scope=="owner" and event.get("event_id")=="fix102"))

    def test_single_s03_memory_source_not_new_db(self):
        result=self.overlay.respond("Что известно о checkpoint?")
        self.assertEqual(result["state"],"NOX_COGNITIVE_REPLY")
        self.assertEqual(result["weight_updates"],0)
        self.assertEqual(result["memory_hits"],2)
        self.assertEqual(len(self.mem.search_calls),1)
        self.assertEqual(self.mem.capability_calls,["owner"])
        self.assertEqual(self.mem.writes,[])
        self.assertEqual(result["self_model_evidence_count"],1)
        self.assertIn("NOX:",result["answer"])
        ctx=self.model.calls[0][1]
        self.assertTrue(all(row["id"] not in ("m-private","m-stale","m-unverified")
                           for row in ctx["memories"]))
        self.assertEqual(ctx["self_model"]["subjective_consciousness"],
                         "UNVERIFIED_NOT_CLAIMED")
        self.assertTrue(ctx["self_model"]["archetypes_are_metaphorical"])

    def test_no_private_cross_scope_retrieval(self):
        result=self.overlay.prepare("secret",scope="another_user",language="es")
        self.assertEqual(result["state"],"PREPARED")
        self.assertEqual([x["id"] for x in result["memories"]],["m-private"])
        self.assertEqual(self.mem.search_calls[-1][0],"another_user")

    def test_no_fake_emotions_without_model(self):
        result=self.overlay.prepare("Ура!")
        self.assertEqual(result["affect"]["label"],"uncertain")
        self.assertFalse(result["affect"]["claims_about_internal_emotion"])

    def test_detect_emotion_but_not_diagnose(self):
        self.overlay.affect_classifier=lambda text,lang:{"label":"joy","confidence":0.91,
            "model_id":"cointegrated/rubert-tiny2-cedr-emotion-detection"}
        r=self.overlay.prepare("Радостно!",language="ru")
        self.assertEqual(r["affect"]["label"],"joy")
        self.assertEqual(r["affect"]["state"],"OBSERVED_TONE_NOT_DIAGNOSIS")
        self.assertFalse(r["affect"]["claims_about_internal_emotion"])
        self.overlay.affect_classifier=lambda text,lang:{"label":"joy","confidence":0.1}
        self.assertEqual(self.overlay.prepare("Мне тревожно")["affect"]["label"],"uncertain")

    def test_verified_reflection_stays_candidate(self):
        denied=self.overlay.propose_reflection(task_id="task_00123",
            critique="Исправить ответ",evaluator_receipt={"verified":False,
            "status":"PASSED","source_uri":"github://nox/ci"})
        self.assertEqual(denied["state"],"HOLD_REFLECTION_UNVERIFIED")
        passed=self.overlay.propose_reflection(task_id="task_00123",
            critique="Усилить проверку фактов",evaluator_receipt={"verified":True,
            "status":"PASSED","source_uri":"github://nox/ci"})
        self.assertEqual(passed["state"],"REFLECTION_CANDIDATE_NOT_LEARNED")
        self.assertFalse(passed["adapter_update"])
        self.assertEqual(self.mem.writes,[])

    def test_owner_approved_verified_memory_write_only(self):
        event={"verified":True,"owner_approved":True,"kind":"correction",
               "source_uri":"github://nox/issue","content":"Исправлен факт",
               "event_id":"fix102"}
        self.assertEqual(self.overlay.save_approved_event(dict(event,owner_approved=False))["state"],
                         "HOLD_EVENT_NOT_APPROVED")
        self.assertEqual(self.overlay.save_approved_event(dict(event,verified=False))["state"],
                         "HOLD_EVENT_NOT_APPROVED")
        without_verifier=CognitiveOverlay(self.mem,self.model,clock=lambda:NOW)
        self.assertEqual(without_verifier.save_approved_event(event)["state"],
                         "HOLD_APPROVAL_VERIFIER_MISSING")
        spoofed=dict(event,event_id="self_created_by_model")
        self.assertEqual(self.overlay.save_approved_event(spoofed)["state"],
                         "HOLD_APPROVAL_NOT_CONFIRMED")
        result=self.overlay.save_approved_event(event)
        self.assertEqual(result["state"],"S03_WRITE_CONFIRMED")
        self.assertEqual(len(self.mem.writes),1)

    def test_s03_callback_adapter_existing_contract(self):
        calls=[]
        adapter=CallbackS03Adapter(
            search_fn=lambda **kw:[dict(id="c1",content="remember me",segment="M3",
                source_uri="s03://c1",timestamp_utc=T,importance=.5,verified=True,
                scope=kw["scope"])],
            capabilities_fn=lambda **kw:[dict(id="cap1",capability="GPU available",
                state="MEASURED",evidence_uri="github://runs/1",
                timestamp_utc=T,verified=True)],
            append_fn=lambda **kw:(calls.append(kw) or "receipt"))
        model=CallbackNOXModelAdapter(lambda **kw:"response from NOX")
        r=CognitiveOverlay(adapter,model,clock=lambda:NOW).respond("hello")
        self.assertEqual(r["state"],"NOX_COGNITIVE_REPLY")
        self.assertEqual(r["memory_hits"],1)
        self.assertEqual(r["answer"],"response from NOX")
        self.assertEqual(len(calls),0)

    def test_bad_inputs_and_source_overrides(self):
        self.assertEqual(self.overlay.prepare(" ",scope="owner")["state"],"HOLD_INPUT")
        self.assertEqual(self.overlay.prepare("Hi",language="xx")["state"],"HOLD_INPUT")
        self.assertEqual(self.overlay.prepare("A"*9000)["state"],"HOLD_INPUT")

if __name__=="__main__":
    unittest.main()
