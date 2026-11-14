"""Test actual trained-weight loading protocol with synthetic local fixture only."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import nox_prime_affect_runtime_v1 as a

class AffectRuntimeTests(unittest.TestCase):
    def fixture(self,root):
        import torch
        from safetensors.torch import save_file
        from nox_prime_soul_stage1_train import _net,GROUPS
        base=Path(root)/"brain"/"intelligence"/"soul_stage1"
        run=base/"run_fixture"
        run.mkdir(parents=True,exist_ok=True)
        weights=run/"best.safetensors"
        net=_net()
        save_file({k:v.detach().contiguous() for k,v in net.state_dict().items()},
                  str(weights))
        sha=hashlib.sha256(weights.read_bytes()).hexdigest()
        evidence={"status":"HOLDOUT_PASSED",
                  "weights_sha256":sha,"classes":list(GROUPS),
                  "decision_threshold":0.3,"test_micro_f1":0.57}
        (run/"TRAINING_EVIDENCE.json").write_text(json.dumps(evidence),encoding="utf-8")
        pointer={"model_path":str(weights),"model_sha256":sha,
                 "test_micro_f1":0.57}
        (base/"CURRENT_VERIFIED.json").write_text(json.dumps(pointer),encoding="utf-8")
        return weights,base

    def test_missing_weights_not_a_real_engine(self):
        with TemporaryDirectory() as tmp:
            x=a.status(tmp)
            self.assertFalse(x["available"])
            self.assertFalse(a.assess(tmp,"This message is a long English comment.")["available"])

    def test_hash_verified_load_actual_safetensors(self):
        with TemporaryDirectory() as tmp:
            weights,base=self.fixture(tmp)
            status=a.status(tmp)
            self.assertTrue(status["available"])
            self.assertEqual(status["model_sha256"],hashlib.sha256(weights.read_bytes()).hexdigest())
            observed=a.assess(tmp,"I am very happy to help you.")
            self.assertTrue(observed["available"])
            self.assertEqual(len(observed["scores"]),6)
            self.assertEqual(observed["scope"],"EN_ONLY")
            self.assertFalse(observed["connected_to_main_llm"])

    def test_russian_not_claimed(self):
        with TemporaryDirectory() as tmp:
            self.fixture(tmp)
            observed=a.assess(tmp,"Мне сегодня радостно и интересно.")
            self.assertFalse(observed["available"])
            self.assertEqual(observed["reason"],"NON_EN_TEXT_UNVALIDATED")

    def test_corrupt_file_fails_closed(self):
        with TemporaryDirectory() as tmp:
            weights,base=self.fixture(tmp)
            with weights.open("ab") as f:f.write(b"tamper")
            x=a.status(tmp)
            self.assertFalse(x["available"])
            self.assertEqual(x["reason"],"ValueError")

    def test_receipt_cannot_point_outside_nox(self):
        with TemporaryDirectory() as tmp:
            _,base=self.fixture(tmp)
            receipt=base/"CURRENT_VERIFIED.json"
            d=json.loads(receipt.read_text(encoding="utf-8"))
            d["model_path"]=str(Path(tmp)/"somewhere_else"/"stolen.safetensors")
            receipt.write_text(json.dumps(d),encoding="utf-8")
            x=a.status(tmp)
            self.assertFalse(x["available"])

    def test_unaccepted_score_cannot_load(self):
        with TemporaryDirectory() as tmp:
            weights,base=self.fixture(tmp)
            evidence=weights.parent/"TRAINING_EVIDENCE.json"
            d=json.loads(evidence.read_text(encoding="utf-8"))
            d["status"]="RESEARCH_CANDIDATE_HOLD"
            evidence.write_text(json.dumps(d),encoding="utf-8")
            self.assertFalse(a.status(tmp)["available"])

if __name__=="__main__":
    unittest.main()
