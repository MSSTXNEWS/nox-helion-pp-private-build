#!/usr/bin/env python3
"""Regression: NOX remembers verified autobiography, not a fictional consumption story."""
import sys,unittest
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from cognitive_overlay import CognitiveOverlay,MemoryEvidence,_autobiographical_recall_queries

NOW=datetime(2026,11,12,14,0,tzinfo=timezone.utc).timestamp()
STAMP="2026-11-12T12:30:00Z"

class S03:
    def __init__(self):self.queries=[]
    def search(self,*,query,scope,limit):
        self.queries.append((query,scope,limit))
        if "дистилляция" not in query:return []
        return [
           MemoryEvidence("verified-teacher","NOX дистилляция учителя с подтверждённым checkpoint SHA",
              "M7","s03://verified-teacher",STAMP,.9,True,False,scope),
           MemoryEvidence("invented","NOX съел 3 учителей и стал сознательным",
              "M7","s03://unverified",STAMP,1.0,False,False,scope),
           MemoryEvidence("other-scope","чужая память",
              "M7","s03://private",STAMP,1.0,True,False,"someone_else")
        ]
    def capabilities(self,*,scope):return []
    def append_approved(self,*,scope,event):raise AssertionError("no writes")

class Model:
    def __init__(self):self.calls=[]
    def generate(self,prompt,context):
        self.calls.append((prompt,context))
        return "Согласно подтверждённым данным"

class Tests(unittest.TestCase):
    def test_teacher_euphemism_reads_real_s03_evidence(self):
        s03,model=S03(),Model()
        out=CognitiveOverlay(s03,model,clock=lambda:NOW).respond("Ты кого съел?")
        self.assertEqual(out["state"],"NOX_COGNITIVE_REPLY")
        self.assertEqual(out["memory_hits"],1)
        self.assertEqual([m["id"] for m in model.calls[0][1]["memories"]],["verified-teacher"])
        self.assertEqual(len(s03.queries),2)
        self.assertTrue(all(x[1]=="owner" for x in s03.queries))
        self.assertEqual(out["weight_updates"],0)
        self.assertIn("дистилляция",s03.queries[1][0])
    def test_no_autobiography_claim_without_record(self):
        s03,model=S03(),Model()
        response=CognitiveOverlay(s03,model,clock=lambda:NOW).respond("Привет")
        self.assertEqual(response["memory_hits"],0)
        self.assertEqual(len(s03.queries),1)
    def test_bounded_multilingual_expansion(self):
        self.assertLessEqual(len(_autobiographical_recall_queries("Кто ты и кого съел и что помнишь и чему научился?")),2)
        self.assertTrue(_autobiographical_recall_queries("Who did you absorb?"))
        self.assertTrue(_autobiographical_recall_queries("¿Quién eres?"))
        self.assertEqual(_autobiographical_recall_queries("Обычный привет"),[])
if __name__=="__main__":unittest.main()
