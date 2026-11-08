"""Real on-disk source-verified teacher -> student train/holdout splitting."""
import hashlib,json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from nox_prime_student_dataset_v1 import build


class MultiTeacherStudentTests(unittest.TestCase):
    def prepare(self,root,count=15,foreign=False):
        d=Path(root)/"brain"/"intelligence"/"absorption"
        d.mkdir(parents=True,exist_ok=True)
        data=d/"multi_teacher_fixture.jsonl"
        with data.open("w",encoding="utf-8") as f:
            for i in range(count):
                question=f"Question #{i} about local model memory and verified learning"
                answer=f"Teacher answer #{i}: verify source data and benchmark improvements, never claim abilities that are not proven."
                digest=hashlib.sha256(question.encode()).hexdigest()
                record={"source_model":"qwen3:8b","source_model_digest":"a"*64,
                    "teacher_prompt_sha256":digest,
                    "messages":[{"role":"user","content":question},
                                {"role":"assistant","content":answer}]}
                f.write(json.dumps(record)+"\n")
            if foreign:
                question="Unknown model output must not be silently trained into NOX"
                f.write(json.dumps({"source_model":"unknown:latest",
                    "source_model_digest":"b"*64,
                    "teacher_prompt_sha256":hashlib.sha256(question.encode()).hexdigest(),
                    "messages":[{"role":"user","content":question},
                                {"role":"assistant","content":"Do not accept this unapproved teacher."*4}]})+"\n")
        sha=hashlib.sha256(data.read_bytes()).hexdigest()
        manifest=d/"multi_teacher_fixture.manifest.json"
        manifest.write_text(json.dumps({"schema":"NOX_MULTI_TEACHER_CANDIDATES_V2",
            "dataset_path":str(data),"dataset_sha256":sha}),encoding="utf-8")
        return data

    def test_reproducible_split_no_leakage_and_no_original_deleted(self):
        with TemporaryDirectory() as root:
            donor=self.prepare(root,20,True)
            before=donor.read_bytes()
            r=build(root)
            self.assertGreaterEqual(r["train_examples"],8)
            self.assertGreaterEqual(r["heldout_examples"],2)
            self.assertEqual(before,donor.read_bytes())
            train=Path(r["path"])
            held=train.with_name("multi_teacher_holdout_v1.jsonl")
            a=[json.loads(x) for x in train.read_text().splitlines()]
            b=[json.loads(x) for x in held.read_text().splitlines()]
            self.assertTrue(all(row["teacher_model"]=="qwen3:8b" for row in a+b))
            self.assertFalse({x["teacher_prompt_sha256"] for x in a} &
                             {x["teacher_prompt_sha256"] for x in b})
            self.assertTrue(all(row["unverified_teacher_content"] for row in a))
            self.assertEqual(build(root)["status"],"REUSED_VERIFIED_DATASET")

    def test_insufficient_data_is_not_called_training(self):
        with TemporaryDirectory() as root:
            self.prepare(root,3)
            with self.assertRaises(RuntimeError):
                build(root)

    def test_tampered_derived_training_file_halts(self):
        with TemporaryDirectory() as root:
            self.prepare(root,20)
            r=build(root)
            with Path(r["path"]).open("a",encoding="utf-8") as f:
                f.write("TAMPER\n")
            with self.assertRaises(RuntimeError):
                build(root)

if __name__=="__main__":unittest.main()
