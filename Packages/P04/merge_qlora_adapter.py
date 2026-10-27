#!/usr/bin/env python3
"""Safely merge one completed NOX LoRA adapter into its exact local base."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_sha256(root: Path, *, skip_merge_receipt: bool = False) -> str:
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
    parser.add_argument("--output-dir", required=True, type=Path, help="must not exist")
    args = parser.parse_args()

    temp_output: Path | None = None
    try:
        model_dir = args.model_dir.resolve(strict=True)
        adapter_dir = args.adapter_dir.resolve(strict=True)
        receipt_path = args.training_receipt.resolve(strict=True)
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
        if receipt.get("schema") != "NOX-QLORA-TRAINING-RECEIPT-v1" or receipt.get("status") != "COMPLETED":
            raise ValueError("TRAINING_RECEIPT_NOT_COMPLETED")
        if receipt.get("model", {}).get("id") != model_id or receipt.get("model", {}).get("revision") != revision:
            raise ValueError("TRAINING_RECEIPT_BASE_MISMATCH")
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
        if (not isinstance(baseline_loss, (int, float)) or not math.isfinite(float(baseline_loss))
                or not isinstance(adapter_loss, (int, float)) or not math.isfinite(float(adapter_loss))
                or float(adapter_loss) >= float(baseline_loss)):
            raise ValueError("ADAPTER_VALIDATION_DID_NOT_IMPROVE")
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
