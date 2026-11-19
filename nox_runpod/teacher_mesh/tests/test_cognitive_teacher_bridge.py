#!/usr/bin/env python3
"""Cognitive teacher bridge: NOX is always final-answer model."""
from datetime import datetime,timezone
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from cognitive_overlay import CognitiveOverlay,MemoryEvidence,CapabilityEvidence
from cognitive_teacher_bridge import CognitiveTeacherBridge
from teacher_ensemble import TeacherCall

T="2026-11-12T01:00:00Z"
NOW=datetime(2026,11,12,1,30,tzinfo=timezone.utc).timestamp()

class FakeS03:
    def search(self,*,query,scope,limit):
        return [MemoryEvidence("p1","NOX studies answers using its own adapters",
                    "M5","s03://p1",T,.9,True,False,scope)]
    def capabilities(self,*,scope):
        return [CapabilityEvidence("e1","actual GPU snapshot","MEASURED",
                    "nox-checkpoint://snap1",T,True)]
    def append_approved(self,*,scope,event):raise AssertionError("Unexpected write")

class FakeModel:
    def __init__(self): self.calls=[]
    def generate(self,prompt,context):
        self.calls.append(context)
        return "NOX final response"

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.model=FakeModel()
        self.bridge=CognitiveTeacherBridge(CognitiveOverlay(
            FakeS03(),self.model,clock=lambda:NOW))

    def test_nox_first_no_teacher(self):
        out=self.bridge.fast("Что я помню?")
        self.assertEqual(out["state"],"NOX_COGNITIVE_REPLY")
        self.assertEqual(out["answer"],"NOX final response")
        self.assertEqual(len(self.model.calls),1)
        self.assertNotIn("teacher_evidence",self.model.calls[0])

    def test_nox_composes_from_teacher_evidence_and_s03(self):
        teachers=[TeacherCall("teacher_1",lambda p:{
            "status":"MEASURED","answer":"teacher text only","model_id":"Qwen3 8B",
            "model_card_url":"https://huggingface.co/Qwen/Qwen3-8B"},True)]
        out=self.bridge.compare("Изучи вопрос",teachers,
                                contains_private_information=True)
        self.assertEqual(out["state"],"NOX_REFINED_WITH_TEACHER_EVIDENCE")
        self.assertEqual(out["nox_answer"],"NOX final response")
        self.assertEqual(out["teacher_count"],1)
        self.assertEqual(out["cognitive_memory_hits"],1)
        self.assertEqual(out["verified_self_capabilities"],1)
        self.assertEqual(self.model.calls[0]["teacher_evidence"][0]["answer"],
                         "teacher text only")
        self.assertEqual(out["training_state"],
                         "NO_WEIGHT_UPDATE_UNTIL_SEPARATE_QUALITY_GATES")

    def test_external_private_prompt_is_blocked(self):
        teachers=[TeacherCall("cloud",lambda p:{
            "status":"MEASURED","answer":"unsafe outbound"},False)]
        out=self.bridge.compare("Приватная история",teachers,
                                 contains_private_information=True)
        self.assertEqual(out["state"],"HOLD_PRIVATE_EXTERNAL")
        self.assertEqual(len(self.model.calls),0)

if __name__=="__main__":
    unittest.main()
