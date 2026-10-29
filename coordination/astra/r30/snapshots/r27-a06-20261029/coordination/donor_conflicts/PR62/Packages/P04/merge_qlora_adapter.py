#!/usr/bin/env python3
"""Safely merge one completed NOX LoRA adapter into its exact local base."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def read_object(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("INPUT_MUST_BE_REGULAR_FILE")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("INPUT_JSON_MUST_BE_OBJECT")
    return value


def verify_dataset_attestation(manifest_path: Path, verifier_path: Path,
                               receipt_dataset: Any) -> dict[str, Any]:
    """Re-check rights authorization at merge time; a receipt alone is not authority."""
    manifest = read_object(manifest_path)
    if verifier_path.is_symlink() or not verifier_path.is_file():
        raise ValueError("RIGHTS_VERIFIER_NOT_REGULAR_FILE")
    for key, expected in (("schema", "nox-dataset-consent-v1"),
                          ("rights_status", "APPROVED"),
                          ("consent_status", "GRANTED")):
        if manifest.get(key) != expected:
            raise ValueError("DATASET_" + key.upper() + "_NOT_APPROVED")
    if not isinstance(receipt_dataset, dict):
        raise ValueError("TRAINING_RECEIPT_DATASET_MISSING")
    fields = {"dataset_id": "id", "dataset_revision": "revision",
              "license_id": "license_id", "owner_approval_id": "owner_approval_id",
              "train_sha256": "train_sha256", "holdout_sha256": "holdout_sha256"}
    for field, receipt_field in fields.items():
        value = manifest.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("DATASET_" + field.upper() + "_MISSING")
        recorded = receipt_dataset.get(receipt_field)
        if not isinstance(recorded, str) or recorded.casefold() != value.casefold():
            raise ValueError("TRAINING_RECEIPT_DATASET_MISMATCH")
    for field in ("train_sha256", "holdout_sha256"):
        if re.fullmatch(r"[0-9a-fA-F]{64}", manifest[field]) is None:
            raise ValueError("DATASET_" + field.upper() + "_INVALID")
    if manifest["train_sha256"].casefold() == manifest["holdout_sha256"].casefold():
        raise ValueError("TRAIN_AND_HOLDOUT_MUST_DIFFER")
    manifest_sha = sha256_file(manifest_path)
    result = subprocess.run(
        [str(verifier_path.resolve(strict=True)), "--manifest", str(manifest_path.resolve(strict=True)),
         "--intent", "training", "--manifest-sha256", manifest_sha],
        check=False, capture_output=True, text=True, timeout=30, shell=False,
    )
    if result.returncode != 0:
        raise ValueError("RIGHTS_VERIFIER_REJECTED_MANIFEST")
    try:
        attestation = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("RIGHTS_VERIFIER_INVALID_RESPONSE") from exc
    expected_attestation = {
        "schema": "nox-rights-attestation-v1",
        "status": "VERIFIED",
        "manifest_sha256": manifest_sha,
        "dataset_id": manifest["dataset_id"],
        "dataset_revision": manifest["dataset_revision"],
        "license_id": manifest["license_id"],
        "owner_approval_id": manifest["owner_approval_id"],
        "train_sha256": manifest["train_sha256"].lower(),
        "holdout_sha256": manifest["holdout_sha256"].lower(),
        "intent": "training",
    }
    if (not isinstance(attestation, dict)
            or any(not isinstance(attestation.get(key), str)
                   or attestation[key].casefold() != expected.casefold()
                   for key, expected in expected_attestation.items())
            or not isinstance(attestation.get("attestation_id"), str)
            or not attestation["attestation_id"].strip()):
        raise ValueError("RIGHTS_VERIFIER_ATTESTATION_MISMATCH")
    attestation_sha = hashlib.sha256(
        json.dumps(attestation, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if (receipt_dataset.get("rights_attestation_id") != attestation["attestation_id"].strip()
            or receipt_dataset.get("rights_attestation_sha256", "").casefold() != attestation_sha):
        raise ValueError("TRAINING_RECEIPT_RIGHTS_ATTESTATION_MISMATCH")
    return manifest



def verified_loss_improvement(baseline_loss: Any, adapter_loss: Any) -> tuple[float, float]:
    """Require real finite measured losses; bool is not a valid metric."""
    if (type(baseline_loss) not in (int, float)
            or type(adapter_loss) not in (int, float)
            or not math.isfinite(float(baseline_loss))
            or not math.isfinite(float(adapter_loss))
            or float(adapter_loss) >= float(baseline_loss)):
        raise ValueError("ADAPTER_VALIDATION_DID_NOT_IMPROVE")
    return float(baseline_loss), float(adapter_loss)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_sha256(root: Path, *, skip_merge_receipt: bool = False) -> str:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("MODEL_TREE_NOT_REGULAR_DIRECTORY")
    digest = hashlib.sha256()
    files = sorted(root.rglob("*"))
    regular_files = [path for path in files if path.is_file()]
    if not regular_files:
        raise ValueError("MODEL_TREE_EMPTY")
    for path in files:
        if path.is_symlink():
            raise ValueError("SYMLINK_IN_MODEL_TREE")
    for path in regular_files:
        if skip_merge_receipt and path.relative_to(root).as_posix() == "merge-receipt.json":
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, type=Path, help="local immutable base snapshot")
    parser.add_argument("--model-lock", required=True, type=Path)
    parser.add_argument("--adapter-dir", required=True, type=Path)
    parser.add_argument("--training-receipt", required=True, type=Path)
    parser.add_argument("--dataset-manifest", required=True, type=Path,
                        help="same consent manifest used by the completed training run")
    parser.add_argument("--rights-verifier", required=True, type=Path,
                        help="local executable that re-attests training rights; no shell")
    parser.add_argument("--output-dir", required=True, type=Path, help="must not exist")
    args = parser.parse_args()

    temp_output: Path | None = None
    try:
        for label, path in (("MODEL", args.model_dir), ("MODEL_LOCK", args.model_lock),
                            ("ADAPTER", args.adapter_dir), ("TRAINING_RECEIPT", args.training_receipt),
                            ("DATASET_MANIFEST", args.dataset_manifest),
                            ("RIGHTS_VERIFIER", args.rights_verifier)):
            if path.is_symlink():
                raise ValueError(label + "_PATH_MUST_NOT_BE_SYMLINK")
        model_dir = args.model_dir.resolve(strict=True)
        adapter_dir = args.adapter_dir.resolve(strict=True)
        receipt_path = args.training_receipt.resolve(strict=True)
        dataset_manifest_path = args.dataset_manifest.resolve(strict=True)
        verifier_path = args.rights_verifier.resolve(strict=True)
        lock = read_object(args.model_lock.resolve(strict=True))
        receipt = read_object(receipt_path)
        adapter_meta = read_object(adapter_dir / "adapter-base.json")
        adapter_config = read_object(adapter_dir / "adapter_config.json")
        if not model_dir.is_dir() or not adapter_dir.is_dir() or model_dir.is_symlink() or adapter_dir.is_symlink():
            raise ValueError("MODEL_AND_ADAPTER_MUST_BE_DIRECTORIES")
        if lock.get("schema") != "nox-model-lock-v1" or lock.get("license_status") != "APPROVED" or not lock.get("owner_approval_id"):
            raise ValueError("MODEL_LOCK_NOT_APPROVED")
        model_id = lock.get("model_id")
        revision = lock.get("revision")
        snapshot_hash = lock.get("snapshot_sha256")
        if not all(isinstance(value, str) and value for value in (model_id, revision, snapshot_hash)):
            raise ValueError("MODEL_LOCK_IDENTITY_INCOMPLETE")
        if tree_sha256(model_dir).lower() != snapshot_hash.lower():
            raise ValueError("BASE_SNAPSHOT_SHA256_MISMATCH")
        if receipt.get("schema") != "NOX-QLORA-TRAINING-RECEIPT-v2" or receipt.get("status") != "COMPLETED":
            raise ValueError("TRAINING_RECEIPT_NOT_COMPLETED")
        receipt_model = receipt.get("model", {})
        if (receipt_model.get("id") != model_id or receipt_model.get("revision") != revision
                or str(receipt_model.get("snapshot_sha256", "")).casefold() != snapshot_hash.casefold()):
            raise ValueError("TRAINING_RECEIPT_BASE_MISMATCH")
        verify_dataset_attestation(dataset_manifest_path, verifier_path, receipt.get("dataset"))
        if receipt.get("adapter_sha256", "").lower() != tree_sha256(adapter_dir).lower():
            raise ValueError("ADAPTER_SHA256_MISMATCH")
        if (adapter_meta.get("model_id") != model_id
                or adapter_meta.get("model_revision") != revision
                or adapter_meta.get("model_snapshot_sha256", "").lower() != snapshot_hash.lower()):
            raise ValueError("ADAPTER_BASE_METADATA_MISMATCH")
        if adapter_config.get("peft_type") != "LORA" or adapter_config.get("task_type") != "CAUSAL_LM":
            raise ValueError("ADAPTER_TYPE_UNSUPPORTED")
        training = receipt.get("training", {})
        baseline_loss = training.get("baseline_eval_loss")
        adapter_loss = training.get("adapter_eval_loss")
        baseline_loss, adapter_loss = verified_loss_improvement(baseline_loss, adapter_loss)
        if args.output_dir.is_symlink():
            raise ValueError("MERGE_OUTPUT_MUST_NOT_BE_SYMLINK")
        output = args.output_dir.absolute()
        if output.exists() or output.is_symlink() or not output.parent.is_dir() or output.parent.is_symlink():
            raise ValueError("MERGE_OUTPUT_MUST_BE_NEW_DIRECTORY_IN_EXISTING_PARENT")
        temp_output = Path(tempfile.mkdtemp(prefix=".nox-merge-", dir=output.parent))

        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if not torch.cuda.is_available():
            raise RuntimeError("NVIDIA_CUDA_GPU_REQUIRED_FOR_ADAPTER_MERGE")
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        base = AutoModelForCausalLM.from_pretrained(
            str(model_dir), local_files_only=True, trust_remote_code=False,
            torch_dtype=dtype, device_map="auto")
        tuned = PeftModel.from_pretrained(base, str(adapter_dir), is_trainable=False)
        merged = tuned.merge_and_unload(safe_merge=True)
        merged.save_pretrained(str(temp_output), safe_serialization=True)
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True, trust_remote_code=False)
        tokenizer.save_pretrained(str(temp_output))
        del merged, tuned, base
        torch.cuda.empty_cache()

        payload_hash = tree_sha256(temp_output)
        merge_receipt = {
            "schema": "NOX-QLORA-MERGE-RECEIPT-v1",
            "status": "CREATED",
            "model_id": model_id,
            "model_revision": revision,
            "model_snapshot_sha256": snapshot_hash.lower(),
            "training_receipt_sha256": sha256_file(receipt_path),
            "adapter_sha256": receipt["adapter_sha256"].lower(),
            "adapter_eval_loss": float(adapter_loss),
            "baseline_eval_loss": float(baseline_loss),
            "merged_payload_sha256": payload_hash,
            "evidence_verified": False,
        }
        (temp_output / "merge-receipt.json").write_text(
            json.dumps(merge_receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.rename(temp_output, output)
        temp_output = None
        print(json.dumps({"status": "CREATED", "output": str(output), "payload_sha256": payload_hash}))
        return 0
    except Exception as exc:
        if temp_output is not None:
            shutil.rmtree(temp_output, ignore_errors=True)
        print(json.dumps({"status": "HOLD", "reason": str(exc) if isinstance(exc, ValueError) else type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
