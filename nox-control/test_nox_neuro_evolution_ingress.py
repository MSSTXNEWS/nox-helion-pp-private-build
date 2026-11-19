"""Regression tests for NOX verified neural learning-data ingress."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script = Path(__file__).with_name("nox_neuro_evolution_ingress.py")
spec = importlib.util.spec_from_file_location("nox_neuro_evolution_ingress",script)
nox = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nox)

def evidence(task, *, handler="ensure_scheduler"):
    group=nox.digest({"task":task,"handler":handler})
    proof={"kind":"native_supervisor_running","service":"nox-priority-scheduler",
           "state":"RUNNING","pid":1234}
    return {"schema":nox.SCHEMA,"source":nox.SOURCE,
            "task_id":task,"handler":handler,"group_sha256":group,
            "dedup_sha256":nox.digest({"group":group,"verification":proof}),
            "verification":proof,"accepted":True,"partition":"train",
            "prompt":"What native evidence verifies the NOX operation "+handler+"?",
            "answer":json.dumps(proof,sort_keys=True,ensure_ascii=False),
            "provenance":{"task":task,"handler":handler,"group_sha256":group,
                          "verification":proof}}

def valid():
    for i in range(300):
        row=evidence("task."+str(i))
        if int(row["group_sha256"][:8],16)%10:
            return row
    raise RuntimeError("unexpected partition")

class NeuroDataTests(unittest.TestCase):
    def paths(self,d):
        return (Path(d)/"accepted.jsonl",Path(d)/"holdout.jsonl",Path(d)/"output.jsonl")

    def test_valid_native_receipt_only_candidate_not_weight_training(self):
        row=valid()
        with tempfile.TemporaryDirectory() as d:
            input,holdout,output=self.paths(d)
            input.write_text(json.dumps(row)+"\n")
            result=nox.build(input,holdout,output)
            self.assertEqual(result["accepted"],1)
            self.assertFalse(result["weights_updated"])
            self.assertFalse(result["training_started"])
            self.assertEqual(len(output.read_text().splitlines()),1)
            rec=json.loads(output.read_text())
            self.assertEqual(rec["schema"],nox.OUT_SCHEMA)
            self.assertEqual(rec["lineage"]["dedup_sha256"],row["dedup_sha256"])

    def test_fake_success_and_changed_receipt_never_admitted(self):
        for case in ("accepted","sha","partition","answer"):
            row=valid()
            if case=="accepted":row["accepted"]=False
            if case=="sha":row["dedup_sha256"]="0"*64
            if case=="partition":row["partition"]="holdout"
            if case=="answer":row["answer"]="FAKE_PASS"
            with tempfile.TemporaryDirectory() as d:
                input,holdout,output=self.paths(d)
                input.write_text(json.dumps(row)+"\n")
                result=nox.build(input,holdout,output)
                self.assertEqual(result["accepted"],0)
                self.assertFalse(output.exists())

    def test_existing_model_output_preserved_on_hold(self):
        row=valid();row["accepted"]=False
        with tempfile.TemporaryDirectory() as d:
            input,holdout,output=self.paths(d)
            input.write_text(json.dumps(row)+"\n")
            output.write_text("previous_verified_dataset\n")
            result=nox.build(input,holdout,output)
            self.assertEqual(result["state"],"HOLD_NO_VERIFIED_TRAINING_EVIDENCE")
            self.assertEqual(output.read_text(),"previous_verified_dataset\n")

    def test_group_holdout_leakage_blocked(self):
        row=valid()
        with tempfile.TemporaryDirectory() as d:
            input,holdout,output=self.paths(d)
            input.write_text(json.dumps(row)+"\n")
            holdout.write_text(json.dumps({"schema":nox.SCHEMA,"partition":"holdout",
                                           "group_sha256":row["group_sha256"]})+"\n")
            result=nox.build(input,holdout,output)
            self.assertEqual(result["accepted"],0)

    def test_duplicate_data_is_deduplicated(self):
        row=valid()
        with tempfile.TemporaryDirectory() as d:
            input,holdout,output=self.paths(d)
            input.write_text(json.dumps(row)+"\n"+json.dumps(row)+"\n")
            result=nox.build(input,holdout,output)
            self.assertEqual(result["accepted"],1)
            self.assertEqual(len(output.read_text().splitlines()),1)

    def test_untrusted_symlink_or_oversized_data_rejected(self):
        row=valid()
        with tempfile.TemporaryDirectory() as d:
            input,holdout,output=self.paths(d)
            input.write_text(json.dumps(row)+"\n")
            link=Path(d)/"link"
            link.symlink_to(input)
            with self.assertRaises(ValueError):
                nox.build(link,holdout,output)
            input.write_text(" "* (nox.MAX_LINE_BYTES+1) + "\n")
            with self.assertRaises(ValueError):
                nox.build(input,holdout,output)
            self.assertFalse(output.exists())

if __name__=="__main__":
    unittest.main()
