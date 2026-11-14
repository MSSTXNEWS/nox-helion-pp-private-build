"""NOX functional duplicate detection is not blob dedup or empty imitation."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase,main
from unittest.mock import patch

import nox_prime_capability_consolidation_v1 as c

def mod(name,sha="a"*64):
    return {"tag":name,"digest":sha,"size_bytes":1024}

class FunctionalConsolidationTests(TestCase):
    def test_distinct_weights_can_overlap_by_capability(self):
        rows=[mod("qwen3:8b","1"*64),mod("qwen3:4b","2"*64),
              mod("qwen2.5-coder:7b","3"*64),mod("qwen3-embedding:0.6b","4"*64)]
        result=c.plan(rows)
        self.assertIn("qwen3:4b",result["potential_functional_overlaps"]["text_reasoning"])
        self.assertIn("qwen3:8b",result["potential_functional_overlaps"]["text_reasoning"])
        self.assertEqual(result["models_deleted"],0)
        self.assertFalse(any(x["auto_delete"] for x in result["models"]))
        self.assertFalse(any(x["retirement_review_only"] for x in result["models"]))

    def test_specialists_survive_general_text_donor_retirement(self):
        rows=[mod("qwen3:8b"),mod("qwen2.5-coder:7b"),
              mod("whisper:latest"),mod("qwen-tts:latest"),
              mod("wan2.2:5b"),mod("qwen3-embedding:0.6b")]
        result=c.plan(rows)
        for m in result["models"]:
            if m["model"] in ("whisper:latest","qwen-tts:latest","wan2.2:5b",
                               "qwen3-embedding:0.6b"):
                self.assertTrue(m["keep_for_now"])

    def test_benchmarks_must_cover_every_skill_for_retirement_review(self):
        rows=[mod("qwen3:8b","a"*64),mod("qwen3:4b","b"*64)]
        only_reason=[{"model":"qwen3:4b","capability":"text_reasoning"}]
        partial=c.plan(rows,only_reason)
        sub=next(x for x in partial["models"] if x["model"]=="qwen3:4b")
        self.assertFalse(sub["retirement_review_only"])
        all_skills=only_reason+[{"model":"qwen3:4b","capability":"tool_use"}]
        proven=c.plan(rows,all_skills)
        sub=next(x for x in proven["models"] if x["model"]=="qwen3:4b")
        self.assertTrue(sub["retirement_review_only"])
        self.assertFalse(sub["auto_delete"])
        prime=next(x for x in proven["models"] if x["model"]=="qwen3:8b")
        self.assertTrue(prime["keep_for_now"])

    def test_fake_receipt_cannot_promote_skills(self):
        with TemporaryDirectory() as d:
            p=Path(d);p.mkdir(exist_ok=True)
            rows={"qwen3:4b":"a"*64}
            record={
                "schema":"NOX_CAPABILITY_EVAL_V1","donor_model":"qwen3:4b",
                "donor_digest":"a"*64,"capability":"text_reasoning",
                "student_family":c.CORE_BASE,"owner_approved":False,
                "independent_qa_pass":True,"source_reproducible":True,
                "rollback_available":True,"old_skills_regression_pass":True,
                "student_inference_verified":True,
                "checks":{"heldout_count":100,"student_score":1.0,
                          "teacher_score":.8,"student_p95_ms":100,
                          "teacher_p95_ms":200}
            }
            (p/"false.json").write_text(json.dumps(record),encoding="utf-8")
            self.assertEqual(c._approved_receipts(p,rows),[])
            record["owner_approved"]=True
            (p/"false.json").write_text(json.dumps(record),encoding="utf-8")
            self.assertEqual(len(c._approved_receipts(p,rows)),1)

    def test_unknown_not_marked_as_same_capability(self):
        cap,role=c.classify("unrecognized-private:latest")
        self.assertEqual(cap,set())
        self.assertEqual(role,"UNKNOWN_REQUIRES_PROFILE")

if __name__=="__main__":
    main()
