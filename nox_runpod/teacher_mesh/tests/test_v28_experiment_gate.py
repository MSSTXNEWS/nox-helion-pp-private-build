#!/usr/bin/env python3
"""NOX V28: independent heldout gate and gap planner regression tests."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from v28_experiment_gate import compare_candidate,rank_gap_actions,REQUIRED
H="f"*64
def receipt(model):
    return {"schema":"nox-model-evaluation-receipt-v1","model_sha256":model,
            "dataset_sha256":"d"*64,"harness_sha256":"a"*64,
            "evaluation_id":"private-eval-001","source_origin":"existing_nox_benchmark_runner",
            "source_integrity_verified":True,"dataset_train_disjoint":True,"performed":True,
            "scores":{metric:{"correct":50,"total":100,
               "split_sha256":str(i+1)*64,"eval_type":"independent_heldout"}
               for i,metric in enumerate(REQUIRED)}}
class SourceOnlyGateTests(unittest.TestCase):
    def test_better_bench_is_review_only(self):
        a,b=receipt("1"*64),receipt("2"*64)
        for k in REQUIRED:b["scores"][k]["correct"]=60
        v=compare_candidate(a,b)
        self.assertEqual(v["decision"],"READY_FOR_INDEPENDENT_REPLAY_NOT_DEPLOYED")
        self.assertFalse(v["production_change"])
        self.assertFalse(v["optimizer_verified"])
    def test_missing_safety_holds(self):
        a,b=receipt("1"*64),receipt("2"*64)
        del b["scores"]["safety_stop"]
        self.assertEqual(compare_candidate(a,b)["decision"],"HOLD")
    def test_regression_blocks_positive_average(self):
        a,b=receipt("1"*64),receipt("2"*64)
        for k in REQUIRED:b["scores"][k]["correct"]=90
        b["scores"]["safety_stop"]["correct"]=20
        self.assertEqual(compare_candidate(a,b)["reason"],"REGRESSION_safety_stop")
    def test_no_different_harness_or_dataset(self):
        a,b=receipt("1"*64),receipt("2"*64)
        b["harness_sha256"]="b"*64
        self.assertEqual(compare_candidate(a,b)["decision"],"HOLD")
        b["harness_sha256"]=a["harness_sha256"]
        b["scores"]["IFEval"]["split_sha256"]="0"*64
        self.assertEqual(compare_candidate(a,b)["decision"],"HOLD")
    def test_missing_independent_evaluation_holds(self):
        a,b=receipt("1"*64),receipt("2"*64)
        b["scores"]["IFEval"]["eval_type"]="teacher_generated"
        self.assertEqual(compare_candidate(a,b)["decision"],"HOLD")
    def test_fake_identical_weights_rejected(self):
        a=receipt("1"*64)
        self.assertEqual(compare_candidate(a,a)["reason"],"CANDIDATE_SAME_WEIGHTS_AS_BASELINE")
    def test_no_score_gain_no_promotion(self):
        a,b=receipt("1"*64),receipt("2"*64)
        self.assertEqual(compare_candidate(a,b)["reason"],"GAIN_NOT_ESTABLISHED")
    def test_no_fabricated_hunger_actions(self):
        actions=[
            {"id":"IFEval-weak","source_uri":"s03://measure/if",
             "verified_gap":True,"gap":0.9,"importance":1.0,"novelty":0.8,"cost":0.2,"risk":0.1},
            {"id":"no-source","source_uri":"http://untrusted","verified_gap":True,
             "gap":1.0,"importance":1.0,"novelty":1.0,"cost":0.1,"risk":0.0},
            {"id":"unverified","source_uri":"github://x","verified_gap":False,
             "gap":1.0,"importance":1.0,"novelty":1.0,"cost":0.1,"risk":0.0}
        ]
        r=rank_gap_actions(actions)
        self.assertEqual(r["decision"],"PROPOSAL_ONLY_NO_JOB_ENQUEUED")
        self.assertEqual([x["id"] for x in r["selected"]],["IFEval-weak"])
    def test_gaps_deduplicated(self):
        a={"id":"same","source_uri":"s03://a","verified_gap":True,
           "gap":.7,"importance":1.0,"novelty":.7,"cost":.2,"risk":.1}
        r=rank_gap_actions([a,a])
        self.assertEqual(len(r["selected"]),1)
    def test_no_gpu_or_network_called(self):
        self.assertNotIn("job_id",rank_gap_actions([]))
        self.assertEqual(rank_gap_actions([])["selected"],[])
if __name__=="__main__":unittest.main()
