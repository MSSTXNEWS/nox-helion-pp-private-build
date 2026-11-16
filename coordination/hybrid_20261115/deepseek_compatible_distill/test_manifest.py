"""Pure source checks only; no network, GPU, checkpoint, or host access."""
import copy
import hashlib
import json
import unittest
from pathlib import Path

from verify_manifest import canonical_sha256, validate

MANIFEST = json.loads(Path(__file__).with_name("manifest.v1.json").read_text(encoding="utf-8"))


class DistillationManifestTest(unittest.TestCase):
    def test_current_candidate_is_pinned_and_fail_closed(self):
        result = validate(MANIFEST)
        self.assertEqual(result["state"], "HOLD")
        self.assertFalse(result["training_started"])
        self.assertIn("STUDENT_LICENSE_REVIEW_REQUIRED", result["blockers"])
        self.assertIn("CORPUS_NOT_VERIFIED", result["blockers"])
        self.assertIn("OWNER_LEASE_NOT_VERIFIED", result["blockers"])
        self.assertIn("CHECKPOINT_RESTORE_NOT_TESTED", result["blockers"])

    def test_exact_teacher_payload_total_matches_reported_missing_bytes(self):
        artifacts = MANIFEST["teacher"]["artifacts"]
        self.assertEqual(sum(a["bytes"] for a in artifacts), 248834257920)
        missing = [a for a in artifacts if a["reported_missing"]]
        self.assertEqual(len(missing), 5)
        self.assertEqual(sum(a["bytes"] for a in missing), 248828477216)

    def test_student_is_non_qwen_pinned_hf_safetensors(self):
        student = MANIFEST["student"]
        self.assertEqual(student["model_id"], "deepseek-ai/DeepSeek-R1-Distill-Llama-8B")
        self.assertEqual(student["revision"], "6a6f4aa4197940add57724a7707d069478df56b1")
        self.assertEqual(student["architecture"], "LlamaForCausalLM")
        self.assertEqual(sum(x["bytes"] for x in student["weight_shards"]),
                         student["expected_weight_bytes"])
        self.assertNotIn("Qwen", student["model_id"])

    def test_teacher_is_explicitly_inference_only(self):
        self.assertIs(MANIFEST["teacher"]["inference_only"], True)
        self.assertEqual(MANIFEST["method"]["teacher_role"],
                         "GGUF inference and teacher-response generation only")
        changed = copy.deepcopy(MANIFEST)
        changed["teacher"]["inference_only"] = False
        result = validate(changed)
        self.assertIn("GGUF_TEACHER_IS_INFERENCE_ONLY", result["blockers"])

    def test_ru_es_scorer_is_pinned_source_only_and_not_promotable(self):
        scorer = MANIFEST["evaluation"]["scoring_harness"]
        source = Path(__file__).with_name("score_ru_es_holdout.py").read_bytes()
        self.assertEqual(scorer["source_sha256"], hashlib.sha256(source).hexdigest())
        self.assertEqual(scorer["status"], "SOURCE_TESTED_NOT_RUN")
        self.assertFalse(scorer["training_started"])
        self.assertFalse(scorer["promotion_authorized"])
        changed = copy.deepcopy(MANIFEST)
        changed["evaluation"]["scoring_harness"]["source_sha256"] = "0" * 64
        self.assertIn("QUALITY_SCORER_SOURCE_SHA256_MISMATCH", validate(changed)["blockers"])

    def test_evaluation_cannot_be_accepted_without_paired_scorer_receipt(self):
        changed = copy.deepcopy(MANIFEST)
        changed["evaluation"].update({
            "status": "VERIFIED_IMPROVEMENT",
            "quality_reviewed": True,
            "frozen_holdout_same_for_baseline_and_candidate": True,
            "holdout_sha256": "a" * 64,
            "fixed_ru_es_case_set_sha256": "b" * 64,
            "baseline_student_sha256": "c" * 64,
            "candidate_adapter_sha256": "d" * 64,
            "evaluator_source_sha256": "e" * 64,
            "evaluation_report_sha256": "f" * 64,
            "minimum_improvement_threshold": 0.01,
            "before_after_metrics": {
                "ru": {"baseline": 0.7, "candidate": 0.8},
                "es": {"baseline": 0.7, "candidate": 0.8},
            },
        })
        blockers = validate(changed)["blockers"]
        self.assertIn("QUALITY_SCORER_REPORT_NOT_ACCEPTED", blockers)
        self.assertIn("QUALITY_SCORER_REPORT_BINDING_MISMATCH", blockers)

    def test_student_cannot_alias_teacher_or_quantized_repo(self):
        changed = copy.deepcopy(MANIFEST)
        changed["student"]["model_id"] = changed["teacher"]["model_id"]
        self.assertIn("STUDENT_MUST_BE_DISTINCT_PINNED_HF_TARGET",
                      validate(changed)["blockers"])
        changed["student"]["model_id"] = changed["teacher"]["quantization_source_id"]
        self.assertIn("STUDENT_MUST_BE_DISTINCT_PINNED_HF_TARGET",
                      validate(changed)["blockers"])

    def test_student_requires_runtime_metadata_and_weight_manifest_hashes(self):
        result = validate(MANIFEST)
        self.assertIn("STUDENT_WEIGHT_MANIFEST_SHA256_MISMATCH", result["blockers"])
        self.assertIn("STUDENT_METADATA_RUNTIME_HASH_MISSING", result["blockers"])
        changed = copy.deepcopy(MANIFEST)
        student = changed["student"]
        student["weight_manifest_sha256"] = canonical_sha256(
            {"weight_shards": student["weight_shards"]}
        )
        for name in ("config.json", "model.safetensors.index.json",
                     "tokenizer.json", "tokenizer_config.json"):
            student["metadata_blobs"][name]["runtime_sha256"] = "a" * 64
        student["config_sha256"] = "a" * 64
        student["tokenizer_sha256"] = "a" * 64
        result = validate(changed)
        self.assertNotIn("STUDENT_WEIGHT_MANIFEST_SHA256_MISMATCH", result["blockers"])
        self.assertNotIn("STUDENT_METADATA_RUNTIME_HASH_MISSING", result["blockers"])
        self.assertNotIn("STUDENT_CONFIG_HASH_MISMATCH", result["blockers"])
        self.assertNotIn("STUDENT_TOKENIZER_HASH_MISMATCH", result["blockers"])

    def test_gguf_cannot_become_trainable_target(self):
        changed = copy.deepcopy(MANIFEST)
        changed["teacher"]["training_target"] = True
        changed["method"]["gguf_direct_weight_training"] = True
        result = validate(changed)
        self.assertIn("GGUF_TEACHER_IS_INFERENCE_ONLY", result["blockers"])
        self.assertIn("GGUF_DIRECT_TRAINING_FORBIDDEN", result["blockers"])

    def test_moving_hf_revision_is_rejected(self):
        changed = copy.deepcopy(MANIFEST)
        changed["student"]["revision"] = "main"
        self.assertIn("STUDENT_REVISION_UNPINNED", validate(changed)["blockers"])

    def test_license_gate_cannot_be_bypassed_by_repo_mit_tag(self):
        changed = copy.deepcopy(MANIFEST)
        changed["student"]["license_review_required"] = False
        changed["native_gates"]["license_review"] = True
        # The source manifest still records Llama 3.1 lineage; the verifier requires
        # an explicit resolution state to remove this hold.
        self.assertIn("STUDENT_LICENSE_REVIEW_REQUIRED", validate(changed)["blockers"])

    def test_holdout_must_remain_frozen_and_hash_pinned(self):
        changed = copy.deepcopy(MANIFEST)
        changed["corpus"]["splits"]["holdout"]["frozen_before_training"] = False
        changed["corpus"]["splits"]["holdout"]["sha256"] = "a" * 64
        self.assertIn("HOLDOUT_NOT_FROZEN", validate(changed)["blockers"])

    def test_v100_rejects_bf16_and_unknown_lora_modules(self):
        changed = copy.deepcopy(MANIFEST)
        changed["method"]["lora"]["precision"] = "bf16"
        changed["method"]["lora"]["target_modules"].append("unsupported_proj")
        result = validate(changed)
        self.assertIn("V100_FP16_ONLY", result["blockers"])
        self.assertIn("LORA_TARGET_MODULES_UNSUPPORTED", result["blockers"])

    def test_staged_pair_has_provenance_hash_and_explicit_split(self):
        corpus = MANIFEST["corpus"]
        self.assertEqual(corpus["staged_examples_count"], 1)
        pair = corpus["staged_pairs"][0]
        self.assertEqual(pair["status"], "STAGED")
        self.assertEqual(pair["split_assignment"], "train_candidate")
        self.assertEqual(pair["excluded_from"], "dev,holdout")
        self.assertEqual(len(pair["pair_sha256"]), 64)
        result = validate(MANIFEST)
        self.assertIn("STAGED_PAIR_HOLDOUT_NOT_VERIFIABLE", result["blockers"])
        self.assertEqual(result["state"], "HOLD")
        self.assertFalse(result["training_started"])

    def test_staged_pair_count_is_bound_to_manifest(self):
        changed = copy.deepcopy(MANIFEST)
        changed["corpus"]["staged_examples_count"] = 0
        self.assertIn("STAGED_PAIR_COUNT_MISMATCH", validate(changed)["blockers"])

    def test_staged_pair_hash_and_holdout_leakage_are_checked(self):
        changed = copy.deepcopy(MANIFEST)
        pair = changed["corpus"]["staged_pairs"][0]
        holdout = changed["corpus"]["splits"]["holdout"]
        holdout["membership_complete"] = True
        holdout["example_hashes"] = []
        holdout["prompt_sha256s"] = [pair["prompt_sha256"]]
        holdout["completion_sha256s"] = []
        self.assertIn("STAGED_PAIR_HOLDOUT_LEAKAGE", validate(changed)["blockers"])

        changed = copy.deepcopy(MANIFEST)
        holdout = changed["corpus"]["splits"]["holdout"]
        holdout["membership_complete"] = True
        holdout["example_hashes"] = []
        holdout["prompt_sha256s"] = []
        holdout["completion_sha256s"] = []
        self.assertNotIn("STAGED_PAIR_HOLDOUT_NOT_VERIFIABLE", validate(changed)["blockers"])

        changed = copy.deepcopy(MANIFEST)
        changed["corpus"]["staged_pairs"][0]["completion"] += " changed"
        self.assertIn("STAGED_PAIR_COMPLETION_HASH_MISMATCH",
                      validate(changed)["blockers"])

    def test_complete_holdout_requires_all_overlap_hash_indexes(self):
        changed = copy.deepcopy(MANIFEST)
        changed["corpus"]["splits"]["holdout"]["membership_complete"] = True
        changed["corpus"]["splits"]["holdout"]["example_hashes"] = []
        self.assertIn("HOLDOUT_HASH_MANIFEST_INCOMPLETE", validate(changed)["blockers"])

    def test_staged_pair_rejects_credential_or_personal_data_patterns(self):
        changed = copy.deepcopy(MANIFEST)
        changed["corpus"]["staged_pairs"][0]["completion"] += " token=abcdef1234567890"
        self.assertIn("STAGED_PAIR_SENSITIVE_DATA_DETECTED",
                      validate(changed)["blockers"])

    def test_verified_status_or_step_count_cannot_replace_ru_es_holdout_metrics(self):
        changed = copy.deepcopy(MANIFEST)
        changed["evaluation"].update({
            "status": "VERIFIED_IMPROVEMENT",
            "quality_reviewed": True,
            "frozen_holdout_same_for_baseline_and_candidate": True,
            "optimizer_steps": 1000000,
            "holdout_sha256": changed["corpus"]["splits"]["holdout"]["sha256"],
            "baseline_student_sha256": "a" * 64,
            "candidate_adapter_sha256": "b" * 64,
            "fixed_ru_es_case_set_sha256": "c" * 64,
            "evaluation_report_sha256": "d" * 64,
            "evaluator_source_sha256": "e" * 64,
            "minimum_improvement_threshold": 0.01,
            "before_after_metrics": {},
        })
        self.assertIn("RU_ES_BASELINE_METRICS_MISSING", validate(changed)["blockers"])

    def test_both_ru_and_es_must_clear_the_metric_threshold(self):
        changed = copy.deepcopy(MANIFEST)
        changed["evaluation"].update({
            "status": "VERIFIED_IMPROVEMENT",
            "quality_reviewed": True,
            "frozen_holdout_same_for_baseline_and_candidate": True,
            "holdout_sha256": changed["corpus"]["splits"]["holdout"]["sha256"],
            "baseline_student_sha256": "a" * 64,
            "candidate_adapter_sha256": "b" * 64,
            "fixed_ru_es_case_set_sha256": "c" * 64,
            "minimum_improvement_threshold": 0.01,
            "before_after_metrics": {
                "ru": {"baseline": 0.70, "candidate": 0.72},
                "es": {"baseline": 0.70, "candidate": 0.705},
            },
        })
        self.assertIn("RU_ES_IMPROVEMENT_THRESHOLD_NOT_MET", validate(changed)["blockers"])

    def test_nonfinite_threshold_cannot_clear_evaluation(self):
        changed = copy.deepcopy(MANIFEST)
        changed["evaluation"].update({
            "status": "VERIFIED_IMPROVEMENT",
            "quality_reviewed": True,
            "frozen_holdout_same_for_baseline_and_candidate": True,
            "holdout_sha256": changed["corpus"]["splits"]["holdout"]["sha256"],
            "baseline_student_sha256": "a" * 64,
            "candidate_adapter_sha256": "b" * 64,
            "fixed_ru_es_case_set_sha256": "c" * 64,
            "evaluation_report_sha256": "d" * 64,
            "evaluator_source_sha256": "e" * 64,
            "minimum_improvement_threshold": float("nan"),
            "before_after_metrics": {
                "ru": {"baseline": 0.70, "candidate": 0.99},
                "es": {"baseline": 0.70, "candidate": 0.99},
            },
        })
        self.assertIn("RU_ES_BASELINE_METRICS_MISSING", validate(changed)["blockers"])

    def test_checkpoint_restore_requires_state_hash_receipt(self):
        changed = copy.deepcopy(MANIFEST)
        changed["checkpoint"]["independent_restore_tested"] = True
        self.assertIn("CHECKPOINT_RESTORE_RECEIPT_INVALID", validate(changed)["blockers"])
        changed["checkpoint"]["restore_evidence"] = {
            "status": "VERIFIED",
            "checkpoint_sha256": "a" * 64,
            "optimizer_state_sha256": "b" * 64,
            "scheduler_state_sha256": "c" * 64,
            "scaler_state_sha256": "d" * 64,
            "rng_state_sha256": "e" * 64,
            "verifier_source_sha256": "f" * 64,
        }
        self.assertNotIn("CHECKPOINT_RESTORE_RECEIPT_INVALID", validate(changed)["blockers"])

    def test_manifest_ci_is_source_only_and_cannot_launch_training_or_gpu(self):
        workflow_path = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "nox-deepseek-distill-source-gate.yml"
        workflow = workflow_path.read_text(encoding="utf-8")
        lowered = workflow.lower()
        self.assertIn("permissions:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn('runs-on: ubuntu-latest', workflow)
        self.assertNotIn("workflow_dispatch:", workflow)
        self.assertIn('python -m unittest discover -s coordination/hybrid_20261115/deepseek_compatible_distill', workflow)
        self.assertIn('python coordination/hybrid_20261115/deepseek_compatible_distill/verify_manifest.py', workflow)
        steps = [
            line.strip() for line in workflow.splitlines()
            if line.strip().startswith(("- uses:", "- name:"))
        ]
        self.assertEqual(steps, [
            "- uses: actions/checkout@v4",
            "- uses: actions/setup-python@v5",
            "- name: Validate source-only learning manifest",
            "- name: Emit current blocked status",
        ])
        run_commands = [
            line.strip() for line in workflow.splitlines()
            if line.strip().startswith("run:")
        ]
        self.assertEqual(run_commands, [
            'run: python -m unittest discover -s coordination/hybrid_20261115/deepseek_compatible_distill -p "test_*.py"',
            "run: python coordination/hybrid_20261115/deepseek_compatible_distill/verify_manifest.py",
        ])
        self.assertNotIn("secrets.", lowered)
        self.assertNotIn("env:", lowered)
        forbidden = (
            "ssh ", "nvidia-smi", "torchrun", "accelerate launch", "trainer.train",
            "optimizer.step", "save_pretrained", "/dev/nvidia", "curl ", "wget ",
        )
        for command in forbidden:
            self.assertNotIn(command, lowered)
        result = validate(MANIFEST)
        self.assertEqual(result["state"], "HOLD")
        self.assertFalse(result["training_started"])

    def test_training_flag_never_clears_other_gates(self):
        changed = copy.deepcopy(MANIFEST)
        changed["training_enabled"] = True
        result = validate(changed)
        self.assertIn("TRAINING_MUST_REMAIN_DISABLED", result["blockers"])
        self.assertEqual(result["state"], "HOLD")


if __name__ == "__main__":
    unittest.main()

