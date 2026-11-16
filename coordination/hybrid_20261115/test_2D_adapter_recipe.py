"""NOX 2D bounded FORGE recipe source-only regressions; no GPU/network/native access."""
import importlib.util
import hashlib
import json
import re
import unicodedata
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location(
    "nox_original_adapter_recipe",ROOT/"nox_runpod/teacher_mesh/adapter_recipe.py")
recipe=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recipe)
SHA="a"*64

class ForgeRecipeTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="nox_2d_")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.old_roots=recipe.ALLOWED_ROOTS
        recipe.ALLOWED_ROOTS=(self.root,)
        self.addCleanup(setattr,recipe,"ALLOWED_ROOTS",self.old_roots)
        self.corpus=self.root/"approved"
        self.corpus.mkdir()
        self.rows={"train":(json.dumps({"prompt":[{"role":"user","content":"safe train"}],"completion":[{"role":"assistant","content":"answer train"}]})+"\n").encode(),
                   "holdout":(json.dumps({"prompt":[{"role":"user","content":"safe hold"}],"completion":[{"role":"assistant","content":"answer hold"}]})+"\n").encode()}
        for kind,data in self.rows.items():
            (self.corpus/(kind+".jsonl")).write_bytes(data)
        manifest={
            "schema":"nox-teacher-approved-sft-v1",
            "status":"REVIEWED_NOT_OPTIMIZER_TRAINED",
            "response_only_loss_required":True,
            "counts":{"train":1,"holdout":1}}
        for kind,data in self.rows.items():
            manifest[kind+".jsonl_sha256"]=hashlib.sha256(data).hexdigest()
        (self.corpus/"manifest.json").write_text(json.dumps(manifest),encoding="utf8")
        self.kwargs=dict(
            corpus_dir=str(self.corpus),base_model_id="owner/nox-hf-student",
            base_model_sha256=SHA,checkpoint_sha256=SHA,
            base_revision="b"*40,base_architecture="QwenForCausalLM",
            base_config_sha256=SHA,tokenizer_sha256=SHA,
            base_weight_manifest_sha256=SHA,target_modules=["q_proj"])
    def test_exact_pins_create_recipe_only(self):
        out=recipe.plan_adapter(**self.kwargs)
        self.assertEqual(out["state"],"RECIPE_ONLY_NOT_TRAINED")
        self.assertEqual(out["precision"],"fp16")
        self.assertFalse(out["native_writer_lease_verified"])
        self.assertFalse(out["original_optimizer_resume_allowed"])
        self.assertEqual(out["optimizer_steps_verified"],0)
        self.assertEqual(out["training_mode"],"LORA_FP16")
    def test_explicit_rslora_only(self):
        out=recipe.plan_adapter(**self.kwargs,use_rslora=True)
        self.assertEqual(out["training_mode"],"RSLORA_FP16")
        self.assertTrue(out["peft"]["use_rslora"])
        self.assertFalse(recipe.plan_adapter(**self.kwargs)["peft"]["use_rslora"])
    def test_missing_base_revision_hold(self):
        k=dict(self.kwargs);k.pop("base_revision")
        self.assertEqual(recipe.plan_adapter(**k)["state"],"HOLD_IMMUTABLE_HF_REVISION")
    def test_moving_revision_hold(self):
        self.assertEqual(recipe.plan_adapter(**(self.kwargs|{"base_revision":"main"}))["state"],"HOLD_IMMUTABLE_HF_REVISION")
    def test_gguf_cannot_be_hf_training_source(self):
        self.assertEqual(recipe.plan_adapter(**(self.kwargs|{"base_model_id":"old-35B.gguf"}))["state"],"HOLD_GGUF_NOT_TRAINABLE_HF_BASE")
    def test_missing_tokenizer_hash_hold(self):
        self.assertEqual(recipe.plan_adapter(**(self.kwargs|{"tokenizer_sha256":None}))["state"],"HOLD_PROVENANCE_HASH")
    def test_missing_config_hash_hold(self):
        self.assertEqual(recipe.plan_adapter(**(self.kwargs|{"base_config_sha256":None}))["state"],"HOLD_PROVENANCE_HASH")
    def test_invalid_architecture_hold(self):
        self.assertEqual(recipe.plan_adapter(**(self.kwargs|{"base_architecture":""}))["state"],"HOLD_HF_ARCHITECTURE")
    def test_bf16_v100_hold(self):
        self.assertEqual(recipe.plan_adapter(**(self.kwargs|{"precision":"bf16"}))["state"],"HOLD_PRECISION_OR_LR")
    def test_corpus_hash_streams_without_read_bytes(self):
        with patch.object(Path,"read_bytes",side_effect=AssertionError("unbounded read")):
            self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],"VERIFIED_SOURCE_CORPUS")
    def test_same_size_corpus_mutation_hold(self):
        p=self.corpus/"train.jsonl"
        b=p.read_bytes()
        p.write_bytes(b.replace(b"safe",b"fake"))
        self.assertEqual(p.stat().st_size,len(b))
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],"HOLD_CORPUS_HASH")
    def test_manifest_read_is_bounded_and_preserves_valid_corpus(self):
        manifest_file=self.corpus/"manifest.json"
        original_len=len(manifest_file.read_bytes())
        with patch.object(recipe,"MAX_MANIFEST_BYTES",original_len-1):
            with patch.object(Path,"read_text",side_effect=AssertionError("unbounded manifest")):
                self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                                 "HOLD_CORPUS_MANIFEST_TOO_LARGE")
        with patch.object(Path,"read_text",side_effect=AssertionError("unbounded manifest")):
            self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                             "VERIFIED_SOURCE_CORPUS")

    def test_oversized_manifest_rejected_before_json_decode(self):
        manifest_file=self.corpus/"manifest.json"
        manifest_file.write_bytes(b'{"a":' + b' '*8192 + b'1}')
        with patch.object(recipe,"MAX_MANIFEST_BYTES",1024):
            self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                             "HOLD_CORPUS_MANIFEST_TOO_LARGE")

    def test_manifest_symlink_hold(self):
        f=self.corpus/"manifest.json"
        dest=self.root/"actual_manifest.json"
        f.rename(dest);f.symlink_to(dest)
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],"HOLD_CORPUS_MANIFEST_FILE")
    def test_corpus_symlink_hold(self):
        alias=self.root/"alias";alias.symlink_to(self.corpus,target_is_directory=True)
        self.assertEqual(recipe.verify_corpus(str(alias))["state"],"HOLD_CORPUS_DIRECTORY")
    def test_boolean_row_count_hold(self):
        f=self.corpus/"manifest.json"
        m=json.loads(f.read_text());m["counts"]["train"]=True
        f.write_text(json.dumps(m))
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],"HOLD_CORPUS_NO_HOLDOUT")
    def test_incorrect_mode_type_hold(self):
        self.assertEqual(recipe.plan_adapter(**self.kwargs,use_rslora="yes")["state"],"HOLD_RSLORA_MODE")

    def test_malformed_owner_recipe_inputs_hold_not_crash(self):
        cases=[
            ("rank", [], "HOLD_LORA_RANK"),
            ("rank", True, "HOLD_LORA_RANK"),
            ("alpha", None, "HOLD_LORA_RANK"),
            ("alpha", 2.3, "HOLD_LORA_RANK"),
            ("learning_rate", "0.00008", "HOLD_PRECISION_OR_LR"),
            ("learning_rate", float("nan"), "HOLD_PRECISION_OR_LR"),
            ("learning_rate", float("inf"), "HOLD_PRECISION_OR_LR"),
            ("max_steps", "5", "HOLD_STEP_BUDGET"),
            ("max_steps", False, "HOLD_STEP_BUDGET"),
            ("target_modules", [{"q_proj":"bad"}], "HOLD_TARGET_MODULES"),
            ("precision", [], "HOLD_PRECISION_OR_LR"),
            ("expert_target_parameters", 3, "HOLD_EXPERT_TARGETS"),
            ("expert_target_parameters", [None], "HOLD_EXPERT_TARGETS"),
            ("corpus_dir", None, "HOLD_NONLOCAL_CORPUS"),
            ("corpus_dir", "\x00bad", "HOLD_NONLOCAL_CORPUS"),
        ]
        for key,value,expected in cases:
            with self.subTest(key=key,value=repr(value)):
                self.assertEqual(
                    recipe.plan_adapter(**(self.kwargs|{key:value}))["state"],expected)

    def test_format_control_in_prompt_or_completion_is_not_a_clean_holdout(self):
        self._rewrite([self._row("Привет\u200b мир")],[self._row("Hello")])
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],"HOLD_CORPUS_JSONL_FORMAT")
        self._rewrite([self._row("Привет","ES\u200b answer")],[self._row("Hello")])
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],"HOLD_CORPUS_JSONL_FORMAT")

    def _rewrite(self,train,holdout,counts=None):
        m=json.loads((self.corpus/"manifest.json").read_text("utf8"))
        m["counts"]=counts if counts is not None else {"train":len(train),"holdout":len(holdout)}
        for part,rows in (("train",train),("holdout",holdout)):
            raw="".join(json.dumps(row,ensure_ascii=False)+"\n" for row in rows).encode()
            (self.corpus/(part+".jsonl")).write_bytes(raw)
            m[part+".jsonl_sha256"]=hashlib.sha256(raw).hexdigest()
        (self.corpus/"manifest.json").write_text(json.dumps(m))

    @staticmethod
    def _row(question,answer="ok"):
        return {"prompt":[{"role":"user","content":question}],
                "completion":[{"role":"assistant","content":answer}]}

    def test_hash_consistent_empty_train_rejected(self):
        self._rewrite([],[self._row("different")],{"train":1,"holdout":1})
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],"HOLD_CORPUS_COUNT_MISMATCH")

    def test_hash_consistent_inflated_manifest_count_rejected(self):
        self._rewrite([self._row("first")],[self._row("second")],{"train":2,"holdout":1})
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],"HOLD_CORPUS_COUNT_MISMATCH")

    def test_hash_consistent_train_holdout_leakage_rejected(self):
        self._rewrite([self._row("same question","train answer")],[self._row("same question","held answer")])
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],"HOLD_CORPUS_EXACT_HOLDOUT_LEAKAGE")

    def test_unicode_nfkc_holdout_leakage_rejected(self):
        self._rewrite([self._row("ＡＢＣ\u00a0 new\n line")],[self._row("abc new line")])
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],"HOLD_CORPUS_EXACT_HOLDOUT_LEAKAGE")

    def test_hash_consistent_wrong_message_shape_rejected(self):
        self._rewrite([{"prompt":"str not messages","completion":"invalid"}],[self._row("hold")])
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],"HOLD_CORPUS_JSONL_FORMAT")

    def test_duplicate_prompt_same_split_rejected(self):
        self._rewrite([self._row("dup","1"),self._row("dup","2")],[self._row("hold")])
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],"HOLD_CORPUS_DUPLICATE_PROMPT")

    def test_row_size_bounded_without_unbounded_read(self):
        self._rewrite([self._row("x"*recipe.MAX_CORPUS_ROW_BYTES)],[self._row("hold")])
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],"HOLD_CORPUS_ROW_TOO_LARGE")

    def test_good_source_only_not_semantically_independent(self):
        checked=recipe.verify_corpus(str(self.corpus))
        self.assertEqual(checked["state"],"VERIFIED_SOURCE_CORPUS")
        self.assertIn("SEMANTIC_HOLDOUT_UNVERIFIED",checked["split_evidence"])


    def _set_threeway(self, dev_question="safe dev"):
        manifest_file=self.corpus/"manifest.json"
        manifest=json.loads(manifest_file.read_text("utf8"))
        dev_data=(json.dumps(self._row(dev_question,"answer dev"))+"\n").encode()
        # Keep bytes identical to those consumed by the verifier.
        dev_data=dev_data.replace(b"\\\\n",b"\\n")
        (self.corpus/"dev.jsonl").write_bytes(dev_data)
        manifest["schema"]="nox-teacher-owner-threeway-sft-v2"
        manifest["counts"]={"train":1,"dev":1,"holdout":1}
        manifest["splitting"]="OWNER_RECEIPT_SOURCE_GROUP_DISJOINT_SHA256"
        manifest["source_group_shas_by_split"]={"train":["a"*64],"dev":["b"*64],"holdout":["c"*64]}
        def owner_sha(text):
            normalized=unicodedata.normalize("NFKC",text.strip().casefold())
            normalized="".join(ch for ch in normalized if unicodedata.category(ch)!="Cf")
            return hashlib.sha256(re.sub(r"\s+"," ",normalized).encode("utf-8")).hexdigest()
        receipts=[]
        for part,group,source in (("train","a","1"),("dev","b","2"),("holdout","c","3")):
            row=json.loads((self.corpus/(part+".jsonl")).read_text("utf8").splitlines()[0])
            receipts.append({"part":part,"task_id":"nox-task-"+part,
                             "group":group*64,"source":source*64,"privacy":"9"*64,
                             "prompt_sha256":owner_sha(row["prompt"][0]["content"]),
                             "answer_sha256":owner_sha(row["completion"][0]["content"])})
        manifest["source_receipts"]=sorted(receipts,key=lambda x:(x["part"],x["source"],x["task_id"]))
        manifest["dev.jsonl_sha256"]=hashlib.sha256(dev_data).hexdigest()
        manifest_file.write_text(json.dumps(manifest),encoding="utf8")
        return manifest

    def test_owner_threeway_source_gate_is_not_native_authorization(self):
        self._set_threeway()
        out=recipe.verify_corpus(str(self.corpus))
        self.assertEqual(out["state"],"VERIFIED_SOURCE_CORPUS")
        self.assertEqual(out["counts"]["dev"],1)
        self.assertEqual(out["dev_sha256"],
                         hashlib.sha256((self.corpus/"dev.jsonl").read_bytes()).hexdigest())
        self.assertFalse(out["owner_corpus_identity_native_verified"])
        planned=recipe.plan_adapter(**self.kwargs)
        self.assertEqual(planned["state"],"RECIPE_ONLY_NOT_TRAINED")
        self.assertEqual(planned["dev_data_sha256"],out["dev_sha256"])
        self.assertFalse(planned["native_writer_lease_verified"])
        self.assertEqual(planned["optimizer_steps_verified"],0)

    def test_owner_threeway_dev_holdout_leakage_rejected(self):
        self._set_threeway("safe hold")
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                         "HOLD_CORPUS_EXACT_HOLDOUT_LEAKAGE")

    def test_owner_threeway_train_dev_leakage_rejected(self):
        self._set_threeway("safe train")
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                         "HOLD_CORPUS_EXACT_HOLDOUT_LEAKAGE")

    def test_owner_threeway_missing_dev_rejected(self):
        self._set_threeway()
        (self.corpus/"dev.jsonl").unlink()
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                         "HOLD_CORPUS_FILE")

    def test_owner_threeway_cross_split_group_collision_rejected(self):
        m=self._set_threeway()
        m["source_group_shas_by_split"]["dev"]=["a"*64]
        (self.corpus/"manifest.json").write_text(json.dumps(m))
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                         "HOLD_CORPUS_OWNER_GROUP_OVERLAP")

    def test_owner_threeway_unsigned_split_metadata_rejected(self):
        m=self._set_threeway()
        del m["source_group_shas_by_split"]
        (self.corpus/"manifest.json").write_text(json.dumps(m))
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                         "HOLD_CORPUS_OWNER_GROUPS")

    def test_owner_hash_canonical_whitespace_matches_v28(self):
        raw="  Mixed   spaces\t  and\nlines  "
        self.assertEqual(recipe._source_row_sha256(raw),
                         hashlib.sha256("mixed spaces and lines".encode()).hexdigest())

    def test_threeway_missing_row_provenance_is_hold(self):
        m=self._set_threeway()
        del m["source_receipts"]
        (self.corpus/"manifest.json").write_text(json.dumps(m))
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                         "HOLD_CORPUS_SOURCE_RECEIPT_PROOF")

    def test_threeway_rehashed_row_cannot_reuse_approved_receipt(self):
        self._set_threeway()
        path=self.corpus/"dev.jsonl"
        data=path.read_bytes().replace(b"safe dev",b"swapped dev")
        path.write_bytes(data)
        mf=self.corpus/"manifest.json"
        m=json.loads(mf.read_text());m["dev.jsonl_sha256"]=hashlib.sha256(data).hexdigest()
        mf.write_text(json.dumps(m))
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                         "HOLD_CORPUS_ROW_PROVENANCE_MISMATCH")

    def test_threeway_replayed_owner_source_receipt_is_hold(self):
        m=self._set_threeway()
        m["source_receipts"][0]["source"]=m["source_receipts"][1]["source"]
        (self.corpus/"manifest.json").write_text(json.dumps(m))
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                         "HOLD_CORPUS_SOURCE_RECEIPT_REPLAY")

    def test_threeway_fabricated_unused_group_is_hold(self):
        m=self._set_threeway()
        m["source_group_shas_by_split"]["dev"].append("d"*64)
        (self.corpus/"manifest.json").write_text(json.dumps(m))
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                         "HOLD_CORPUS_SOURCE_RECEIPT_GROUPS")

    def test_threeway_wrong_receipt_group_is_hold(self):
        m=self._set_threeway()
        m["source_receipts"][0]["group"]="d"*64
        (self.corpus/"manifest.json").write_text(json.dumps(m))
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                         "HOLD_CORPUS_SOURCE_RECEIPT_GROUPS")

    def test_threeway_owner_prompt_proof_swap_is_hold(self):
        m=self._set_threeway()
        m["source_receipts"][0]["prompt_sha256"]="e"*64
        (self.corpus/"manifest.json").write_text(json.dumps(m))
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                         "HOLD_CORPUS_ROW_PROVENANCE_MISMATCH")

    def test_threeway_hash_consistent_duplicate_completion_is_hold(self):
        # The V28 exporter already rejects this; the FORGE importer must too.
        m=self._set_threeway()
        f=self.corpus/"dev.jsonl"
        raw=f.read_text("utf8").replace("answer dev","answer train")
        f.write_text(raw,encoding="utf8")
        m["dev.jsonl_sha256"]=hashlib.sha256(raw.encode("utf8")).hexdigest()
        for proof in m["source_receipts"]:
            if proof["part"]=="dev":
                proof["answer_sha256"]=recipe._source_row_sha256("answer train")
        (self.corpus/"manifest.json").write_text(json.dumps(m))
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                         "HOLD_CORPUS_DUPLICATE_ANSWER")

    def test_legacy_two_split_duplicate_answer_remains_compatible(self):
        self._rewrite([self._row("first unique", "common short answer")],
                      [self._row("second unique", "common short answer")])
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                         "VERIFIED_SOURCE_CORPUS")

    def test_manifest_duplicate_json_key_rejected_even_if_values_agree(self):
        manifest_path=self.corpus/"manifest.json"
        before=manifest_path.read_text("utf8")
        manifest_path.write_text(before[:-1]+', "counts": {"train": 1, "holdout": 1}}')
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                         "HOLD_CORPUS_UNREADABLE")

    def test_manifest_nonfinite_undeclared_value_is_not_accepted(self):
        manifest_path=self.corpus/"manifest.json"
        m=json.loads(manifest_path.read_text("utf8"))
        m["evaluation_score"]=float("nan")
        manifest_path.write_text(json.dumps(m))
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                         "HOLD_CORPUS_UNREADABLE")

    def test_rehashed_row_cannot_hide_duplicate_nested_role(self):
        file=self.corpus/"train.jsonl"
        raw=file.read_text("utf8").replace('"role": "user"',
              '"role": "assistant", "role": "user"',1)
        file.write_text(raw,encoding="utf8")
        manifest_path=self.corpus/"manifest.json"
        m=json.loads(manifest_path.read_text("utf8"))
        m["train.jsonl_sha256"]=hashlib.sha256(raw.encode("utf8")).hexdigest()
        manifest_path.write_text(json.dumps(m))
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                         "HOLD_CORPUS_JSONL_FORMAT")

    def test_rehashed_row_cannot_hide_duplicate_nested_content(self):
        file=self.corpus/"train.jsonl"
        raw=file.read_text("utf8").replace('"content": "safe train"',
              '"content": "wrong content", "content": "safe train"',1)
        file.write_text(raw,encoding="utf8")
        manifest_path=self.corpus/"manifest.json"
        m=json.loads(manifest_path.read_text("utf8"))
        m["train.jsonl_sha256"]=hashlib.sha256(raw.encode("utf8")).hexdigest()
        manifest_path.write_text(json.dumps(m))
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                         "HOLD_CORPUS_JSONL_FORMAT")

    def test_legacy_manifest_cannot_silently_ignore_dev(self):
        (self.corpus/"dev.jsonl").write_text("extra dev data")
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                         "HOLD_CORPUS_UNDECLARED_SPLIT")
        m=json.loads((self.corpus/"manifest.json").read_text())
        m["counts"]["dev"]=1
        (self.corpus/"manifest.json").write_text(json.dumps(m))
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],
                         "HOLD_CORPUS_SPLIT_SET")

if __name__=="__main__":
    unittest.main()
