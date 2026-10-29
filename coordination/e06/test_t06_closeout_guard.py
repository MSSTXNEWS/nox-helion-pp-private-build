"""Focused negative/positive T06 closeout checks; no CI or Windows build."""
import importlib.util
import pathlib
import unittest

f=pathlib.Path(__file__).with_name("t06_closeout_guard.py")
sp=importlib.util.spec_from_file_location("t06_guard",f)
g=importlib.util.module_from_spec(sp)
sp.loader.exec_module(g)
def proof(done=False, name="P02"):
    evidence = ({"canonical_head_sha":"a"*40, "source_choice_receipt":"approved-choice-blob"}
                if name == "base" else {k:k for k in g.PROOF})
    return {"status":"DONE" if done else "HOLD", "owner":"T06",
            "next_action":"Obtain exact source attestation",
            "evidence":evidence if done else {}}
class Closeout(unittest.TestCase):
    def test_fake_done_rejected_at_one_of_eight(self):
        x={"run_id":"R06","claimed_status":"DONE",
           "criteria":{name:proof(name=="base",name) for name in g.CRITERIA}}
        o=g.decide(x)
        self.assertEqual((o["completed"],len(o["remaining"])),(1,7))
        self.assertEqual(o["progress_pct"],12.5)
        self.assertTrue(o["premature_closeout_rejected"])
        self.assertFalse(o["done"])
    def test_fake_done_without_owner_evidence(self):
        x={"claimed_status":"DONE","criteria":{name:{"status":"DONE","evidence":{}} for name in g.CRITERIA}}
        self.assertEqual(g.decide(x)["completed"],0)
    def test_independent_qa_is_required(self):
        x={"claimed_status":"DONE","criteria":{name:proof(True,name) for name in g.CRITERIA},
           "head_sha":"a"*40,"tree_sha":"b"*40,"manifest_blob_sha":"c"*40,
           "owner_acceptance":True,"independent_source_qa":False}
        self.assertFalse(g.decide(x)["done"])
        x["independent_source_qa"]=True
        self.assertTrue(g.decide(x)["done"])
    def test_baseline_not_falsely_failed_for_missing_prepost(self):
        x={"criteria":{n:proof(n=="base",n) for n in g.CRITERIA}}
        self.assertEqual(g.decide(x)["completed"],1)

    def test_missing_criterion_rejected(self):
        with self.assertRaises(ValueError):
            g.decide({"criteria":{"base":proof()}})
if __name__=="__main__":unittest.main()
