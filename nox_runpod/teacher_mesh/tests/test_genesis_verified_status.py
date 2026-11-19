#!/usr/bin/env python3
"""Source-level regression only. No real GPU, no live S03, no invented OneHost API."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import sys, unittest
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from genesis_verified_status import normalize_live_receipt, web_payload, SCHEMA

NOW=datetime(2026,11,12,18,0,tzinfo=timezone.utc)
SHA="f"*64

def sample():
    return {"schema":"nox-onehost-training-receipt-v1","origin":"existing_onehost",
            "observed_at_utc":NOW.isoformat(),"student_model_sha256":SHA,
            "optimizer_steps":105,"checkpoint_sha256":"c"*64,
            "evidence_uri":"nox-checkpoint://nox/sha/" + SHA,
            "evaluation":{"same_harness":True,"heldout":True,"benchmark":"IFEval",
                          "correct":54,"total":100},
            "s03":{"authenticated":True,"readback_verified":True,
                   "last_readback_at_utc":NOW.isoformat()}}

class EvidenceTests(unittest.TestCase):
    def test_unbound_host_is_hold(self):
        out=web_payload(None,now_utc=NOW)
        self.assertEqual(out["state"],"HOLD")
        self.assertFalse(out["neural_training_confirmed"])
    def test_truthful_receipt_is_not_independent_gpu_proof(self):
        out=normalize_live_receipt(sample(),now_utc=NOW)
        self.assertEqual(out["schema"],SCHEMA)
        self.assertEqual(out["state"],"RECEIPT_FORMAT_VALIDATED_NOT_GPU_REPLAYED")
        self.assertFalse(out["neural_training_confirmed"])
        self.assertEqual(out["training"]["optimizer_steps_claimed"],105)
        self.assertEqual(out["quality"]["score"],0.54)
        self.assertEqual(out["memory"]["state"],"CONNECTED_BY_TRUSTED_HOST")
    def test_stale_forged_and_garbage_rejected(self):
        examples=[dict(sample(),schema="forged"),dict(sample(),origin="teacher"),
                  dict(sample(),checkpoint_sha256="bad"),
                  dict(sample(),optimizer_steps=True),
                  dict(sample(),evidence_uri="nox-checkpoint://nox /foo"),
                  dict(sample(),observed_at_utc=(NOW-timedelta(hours=2)).isoformat())]
        for item in examples:
            with self.subTest(item=item):
                self.assertEqual(normalize_live_receipt(item,now_utc=NOW)["state"],"HOLD")
    def test_no_onehost_callback_receipt_fails(self):
        self.assertEqual(web_payload(lambda:(_ for _ in ()).throw(RuntimeError()),now_utc=NOW)["state"],"HOLD")
    def test_fabricated_benchmark_without_holdout_cannot_be_visible(self):
        data=sample();data["evaluation"]["heldout"]=False
        out=normalize_live_receipt(data,now_utc=NOW)
        self.assertIsNone(out["quality"])
if __name__=="__main__":unittest.main()
