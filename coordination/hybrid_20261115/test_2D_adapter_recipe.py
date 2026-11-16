"""NOX 2D bounded FORGE recipe source-only regressions; no GPU/network/native access."""
import importlib.util
import hashlib
import json
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
            ("corpus_dir", "\\x00bad", "HOLD_NONLOCAL_CORPUS"),
        ]
        for key,value,expected in cases:
            with self.subTest(key=key,value=repr(value)):
                self.assertEqual(
                    recipe.plan_adapter(**(self.kwargs|{key:value}))["state"],expected)

    def test_format_control_in_prompt_or_completion_is_not_a_clean_holdout(self):
        self._rewrite([self._row("Привет\\u200b мир")],[self._row("Hello")])
        self.assertEqual(recipe.verify_corpus(str(self.corpus))["state"],"HOLD_CORPUS_JSONL_FORMAT")
        self._rewrite([self._row("Привет","ES\\u200b answer")],[self._row("Hello")])
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

if __name__=="__main__":
    unittest.main()
