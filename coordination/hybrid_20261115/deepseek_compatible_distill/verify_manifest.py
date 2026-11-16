"""Fail-closed validator for the source-only DeepSeek distillation candidate.

This file does not download weights, inspect host paths, or start training.
"""
from __future__ import annotations
import hashlib
import json
import re

SCHEMA = "NOX_DEEPSEEK_TEACHER_STUDENT_SOURCE_MANIFEST_V1"
HEX64 = re.compile(r"^[a-f0-9]{64}$")
HEX40 = re.compile(r"^[a-f0-9]{40}$")
SENSITIVE_PATTERN = re.compile(r"(?i)\b(?:bearer\s+[a-z0-9._-]{12,}|(?:api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,]{8,}|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,})|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def canonical_sha256(value: dict) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def staged_pair_blockers(corpus: dict) -> list[str]:
    blockers: list[str] = []
    pairs = corpus.get("staged_pairs", [])
    holdout = corpus.get("splits", {}).get("holdout", {})
    holdout_hashes = holdout.get("example_hashes", [])
    if not isinstance(pairs, list):
        return ["STAGED_PAIR_SCHEMA_INVALID"]
    if not isinstance(holdout_hashes, list) or any(not isinstance(x, str) or not HEX64.fullmatch(x) for x in holdout_hashes):
        blockers.append("HOLDOUT_HASH_LIST_INVALID")
        holdout_hashes = []
    seen = set()
    for pair in pairs:
        if not isinstance(pair, dict):
            blockers.append("STAGED_PAIR_SCHEMA_INVALID")
            continue
        if pair.get("status") != "STAGED" or pair.get("split_assignment") != "train_candidate" or pair.get("excluded_from") != "dev,holdout":
            blockers.append("STAGED_PAIR_SPLIT_INVALID")
        if pair.get("id") in seen or not isinstance(pair.get("id"), str) or not pair.get("id"):
            blockers.append("STAGED_PAIR_ID_DUPLICATE_OR_INVALID")
        seen.add(pair.get("id"))
        for key in ("prompt", "completion"):
            text_value = pair.get(key)
            if not isinstance(text_value, str) or not text_value.strip():
                blockers.append("STAGED_PAIR_TEXT_MISSING")
            elif SENSITIVE_PATTERN.search(text_value):
                blockers.append("STAGED_PAIR_SENSITIVE_DATA_DETECTED")
        if pair.get("prompt_sha256") != hashlib.sha256(pair.get("prompt", "").encode("utf-8")).hexdigest():
            blockers.append("STAGED_PAIR_PROMPT_HASH_MISMATCH")
        if pair.get("completion_sha256") != hashlib.sha256(pair.get("completion", "").encode("utf-8")).hexdigest():
            blockers.append("STAGED_PAIR_COMPLETION_HASH_MISMATCH")
        hash_input = {key: value for key, value in pair.items() if key != "pair_sha256"}
        pair_hash = canonical_sha256(hash_input)
        if pair.get("pair_sha256") != pair_hash:
            blockers.append("STAGED_PAIR_HASH_MISMATCH")
        if pair_hash in holdout_hashes:
            blockers.append("STAGED_PAIR_HOLDOUT_LEAKAGE")
        source = pair.get("source", {})
        safety = pair.get("safety", {})
        if source.get("type") != "session_and_canonical_memory_context" or not source.get("verified_claim") or not source.get("unverified_claim"):
            blockers.append("STAGED_PAIR_PROVENANCE_INCOMPLETE")
        if (safety.get("contains_credentials") is not False or safety.get("contains_personal_data") is not False
                or safety.get("stop_gate") != "PRESERVE"):
            blockers.append("STAGED_PAIR_SAFETY_GATE_FAILED")
    if pairs and holdout.get("membership_complete") is not True:
        blockers.append("STAGED_PAIR_HOLDOUT_NOT_VERIFIABLE")
    return sorted(set(blockers))
KNOWN_LORA_MODULES = {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"}


def validate(manifest: dict) -> dict:
    blockers: list[str] = []
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        return {"state": "FAILED_SCHEMA", "blockers": ["SCHEMA"]}
    teacher = manifest.get("teacher", {})
    student = manifest.get("student", {})
    method = manifest.get("method", {})
    corpus = manifest.get("corpus", {})
    checkpoint = manifest.get("checkpoint", {})
    evaluation = manifest.get("evaluation", {})
    gates = manifest.get("native_gates", {})

    if manifest.get("training_enabled") is not False:
        blockers.append("TRAINING_MUST_REMAIN_DISABLED")
    if teacher.get("format") != "GGUF" or teacher.get("training_target") is not False:
        blockers.append("GGUF_TEACHER_IS_INFERENCE_ONLY")
    if method.get("gguf_direct_weight_training") is not False:
        blockers.append("GGUF_DIRECT_TRAINING_FORBIDDEN")
    lora = method.get("lora", {})
    if lora.get("precision") != "fp16" or method.get("bf16_allowed") is not False:
        blockers.append("V100_FP16_ONLY")
    targets = lora.get("target_modules", [])
    if (not isinstance(targets, list) or not targets
            or any(not isinstance(x, str) or x not in KNOWN_LORA_MODULES for x in targets)):
        blockers.append("LORA_TARGET_MODULES_UNSUPPORTED")
    if type(lora.get("rank")) is not int or lora["rank"] not in {8, 16, 32, 64, 128}:
        blockers.append("LORA_RANK_UNSUPPORTED")
    if (type(lora.get("learning_rate")) not in {int, float}
            or not 0 < lora["learning_rate"] <= 0.001):
        blockers.append("LORA_LEARNING_RATE_INVALID")
    if type(lora.get("max_steps")) is not int or not 1 <= lora["max_steps"] <= 10000:
        blockers.append("LORA_MAX_STEPS_INVALID")
    if method.get("name") != "response_level_distillation_sft":
        blockers.append("UNSUPPORTED_METHOD")

    artifacts = teacher.get("artifacts", [])
    if not isinstance(artifacts, list) or not artifacts:
        blockers.append("TEACHER_ARTIFACT_MANIFEST_MISSING")
    else:
        if any(type(x.get("bytes")) is not int or x["bytes"] <= 0
               or not isinstance(x.get("sha256"), str)
               or not HEX64.fullmatch(x["sha256"]) for x in artifacts):
            blockers.append("TEACHER_ARTIFACT_PIN_INVALID")
        if sum(x.get("bytes", 0) for x in artifacts) != teacher.get("required_unique_bytes"):
            blockers.append("TEACHER_TOTAL_BYTES_MISMATCH")
        missing = [x for x in artifacts if x.get("reported_missing") is True]
        if (len(missing) != teacher.get("reported_missing_payloads")
                or sum(x.get("bytes", 0) for x in missing)
                != teacher.get("reported_missing_payload_bytes")):
            blockers.append("TEACHER_MISSING_BYTES_MISMATCH")
        if any(x.get("local_sha256_verified") is not True for x in artifacts):
            blockers.append("TEACHER_LOCAL_HASHES_UNVERIFIED")
    if teacher.get("local_presence") != "LIVE_VERIFIED":
        blockers.append("TEACHER_LOCAL_PRESENCE_UNVERIFIED")

    revision = student.get("revision")
    if not isinstance(revision, str) or not HEX40.fullmatch(revision):
        blockers.append("STUDENT_REVISION_UNPINNED")
    if student.get("format") != "safetensors":
        blockers.append("STUDENT_FORMAT_UNSUPPORTED")
    if student.get("architecture") != "LlamaForCausalLM" or student.get("model_type") != "llama":
        blockers.append("STUDENT_ARCHITECTURE_UNVERIFIED")
    shards = student.get("weight_shards", [])
    if (not shards or any(type(x.get("bytes")) is not int or x["bytes"] <= 0
                          or not isinstance(x.get("sha256"), str)
                          or not HEX64.fullmatch(x["sha256"]) for x in shards)
            or sum(x.get("bytes", 0) for x in shards) != student.get("expected_weight_bytes")):
        blockers.append("STUDENT_WEIGHT_MANIFEST_INVALID")
    if student.get("local_weight_readback") is not True:
        blockers.append("STUDENT_LOCAL_WEIGHTS_UNVERIFIED")
    if student.get("architecture_load_tested") is not True:
        blockers.append("STUDENT_LOAD_NOT_TESTED")
    if student.get("memory_fit_tested") is not True:
        blockers.append("STUDENT_MEMORY_FIT_UNKNOWN")
    if (student.get("license_review_required") is not False
            or student.get("license_review_resolution") != "APPROVED"
            or gates.get("license_review") is not True):
        blockers.append("STUDENT_LICENSE_REVIEW_REQUIRED")

    blockers.extend(staged_pair_blockers(corpus))
    splits = corpus.get("splits", {})
    if corpus.get("status") != "VERIFIED_OWNER_CORPUS":
        blockers.append("CORPUS_NOT_VERIFIED")
    if set(splits) != {"train", "dev", "holdout"}:
        blockers.append("THREEWAY_SPLITS_REQUIRED")
    else:
        for name in ("train", "dev", "holdout"):
            part = splits[name]
            if (type(part.get("count")) is not int or part["count"] < 1
                    or not isinstance(part.get("sha256"), str)
                    or not HEX64.fullmatch(part["sha256"])):
                blockers.append("CORPUS_" + name.upper() + "_NOT_PINNED")
    holdout = splits.get("holdout", {})
    if holdout.get("frozen_before_training") is not True or holdout.get("used_for_gradient_updates") is not False:
        blockers.append("HOLDOUT_NOT_FROZEN")
    if corpus.get("source_license_reviewed") is not True or corpus.get("provenance_required") is not True:
        blockers.append("CORPUS_RIGHTS_OR_PROVENANCE_NOT_VERIFIED")

    required = {"trainer_state.json", "optimizer.pt", "scheduler.pt", "rng_state.pth",
                "scaler.pt", "adapter_config.json", "adapter_model.safetensors"}
    if set(checkpoint.get("required_files", [])) != required:
        blockers.append("CHECKPOINT_STATE_INCOMPLETE")
    if checkpoint.get("independent_restore_tested") is not True:
        blockers.append("CHECKPOINT_RESTORE_NOT_TESTED")

    if evaluation.get("status") != "VERIFIED_IMPROVEMENT":
        blockers.append("HOLDOUT_EVALUATION_NOT_ACCEPTED")
    if evaluation.get("quality_reviewed") is not True:
        blockers.append("QUALITY_REVIEW_REQUIRED")
    for key, label in (
        ("existing_onehost_owner_lease", "OWNER_LEASE_NOT_VERIFIED"),
        ("owner_stop_admission", "STOP_ADMISSION_NOT_VERIFIED"),
        ("two_v100_resource_readback", "GPU_RESOURCE_READBACK_MISSING"),
        ("ssd_capacity_and_storage_auth", "STORAGE_ADMISSION_MISSING"),
        ("teacher_gguf_local_sha_readback", "TEACHER_HASH_READBACK_MISSING"),
        ("student_hf_local_sha_readback", "STUDENT_HASH_READBACK_MISSING"),
        ("student_load_and_training_preflight", "TRAINING_PREFLIGHT_MISSING"),
        ("independent_checkpoint_restore", "NATIVE_RESTORE_NOT_VERIFIED"),
        ("frozen_holdout_eval", "NATIVE_HOLDOUT_NOT_VERIFIED"),
    ):
        if gates.get(key) is not True:
            blockers.append(label)

    return {
        "state": "HOLD" if blockers else "READY_FOR_OWNER_ADMISSION_ONLY",
        "training_started": False,
        "blockers": sorted(set(blockers)),
    }


if __name__ == "__main__":
    import json
    from pathlib import Path
    path = Path(__file__).with_name("manifest.v1.json")
    result = validate(json.loads(path.read_text(encoding="utf-8")))
    print(json.dumps(result, sort_keys=True))
    if result["state"] != "HOLD":
        raise SystemExit("Unexpectedly cleared owner and training gates.")
