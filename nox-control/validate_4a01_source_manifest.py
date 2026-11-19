#!/usr/bin/env python3
"""Fail-closed source-pin validator for the canonical NOX 4A01 manifest.

Reads only the small JSON manifest. It never opens model/tokenizer/data payloads,
uses the network, or authorizes a training run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

DEFAULT_MANIFEST = Path(__file__).parent / "model_manifests" / "4A01_DEEPSEEK_V41_1017_TRAINING_SOURCE_20261119.json"
MAX_MANIFEST_BYTES = 256 * 1024
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash-1017"


def at(obj: Any, dotted: str) -> Any:
    value = obj
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def validate(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    report: dict[str, Any] = {
        "validator_schema": "NOX_4A01_SOURCE_PIN_VALIDATION_V1",
        "manifest_path": str(path),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "execution_authorized": False,
        "weights_loaded": False,
        "network_used": False,
        "missing_fields": [],
        "invalid_fields": [],
        "verified_fields": [],
    }
    if len(raw) > MAX_MANIFEST_BYTES:
        report.update({"state": "HOLD", "invalid_fields": ["manifest: exceeds 256 KiB bound"]})
        return report
    try:
        doc = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        report.update({"state": "HOLD", "invalid_fields": ["manifest: invalid UTF-8 JSON"]})
        return report
    if not isinstance(doc, dict):
        report.update({"state": "HOLD", "invalid_fields": ["manifest: root must be object"]})
        return report

    exact = {
        "schema": "NOX_MODEL_SOURCE_MANIFEST_V1",
        "task_id": "4A01",
        "canonical_target.model_repo": EXPECTED_MODEL,
        "canonical_target.license": "MIT",
        "tokenizer.source_repo": "deepseek-ai/deepseek-recipe",
        "training_recipe.source_repo": "NVIDIA-NeMo/Automodel",
        "training_recipe.data.dataset": "rowan/hellaswag",
    }
    for field, expected in exact.items():
        value = at(doc, field)
        if value is None or value == "":
            report["missing_fields"].append(field)
        elif value != expected:
            report["invalid_fields"].append(field + ": unexpected value")
        else:
            report["verified_fields"].append(field)

    pinned = (
        "canonical_target.model_revision",
        "tokenizer.source_revision",
        "training_recipe.source_commit",
    )
    for field in pinned:
        value = at(doc, field)
        if value is None or value == "":
            report["missing_fields"].append(field)
        elif not isinstance(value, str) or not HEX40.fullmatch(value):
            report["invalid_fields"].append(field + ": expected full 40-hex immutable revision")
        else:
            report["verified_fields"].append(field)

    hash_fields = (
        "tokenizer.sha256",
        "training_recipe.source_git_blob_sha1",
    )
    for field in hash_fields:
        value = at(doc, field)
        pattern = HEX64 if field.endswith("sha256") else HEX40
        if value is None or value == "":
            report["missing_fields"].append(field)
        elif not isinstance(value, str) or not pattern.fullmatch(value):
            report["invalid_fields"].append(field + ": expected full content hash")
        else:
            report["verified_fields"].append(field)

    dtype = at(doc, "training_recipe.training_dtype")
    config_dtype = at(doc, "canonical_target.config_declared_dtype")
    if not dtype:
        report["missing_fields"].append("training_recipe.training_dtype")
    elif not isinstance(dtype, str) or not dtype.startswith("bfloat16 "):
        report["invalid_fields"].append("training_recipe.training_dtype: expected pinned bfloat16 recipe wording")
    elif config_dtype != "bfloat16":
        report["invalid_fields"].append("canonical_target.config_declared_dtype: must equal bfloat16")
    else:
        report["verified_fields"].extend([
            "training_recipe.training_dtype",
            "canonical_target.config_declared_dtype",
        ])

    targets = at(doc, "training_recipe.lora.target_module_patterns")
    if not isinstance(targets, list) or not targets or any(not isinstance(x, str) or not x.strip() for x in targets):
        if targets is None:
            report["missing_fields"].append("training_recipe.lora.target_module_patterns")
        else:
            report["invalid_fields"].append("training_recipe.lora.target_module_patterns: expected nonempty string list")
    else:
        report["verified_fields"].append("training_recipe.lora.target_module_patterns")

    for field in ("training_recipe.data.training_split", "training_recipe.data.validation_split"):
        value = at(doc, field)
        if not isinstance(value, str) or not value.strip():
            report["missing_fields"].append(field)
        else:
            report["verified_fields"].append(field)

    for field, pattern in (
        ("training_recipe.data.snapshot_revision", HEX40),
        ("training_recipe.data.split_file_sha256", HEX64),
    ):
        value = at(doc, field)
        if value is None or value == "":
            report["missing_fields"].append(field)
        elif not isinstance(value, str) or not pattern.fullmatch(value):
            report["invalid_fields"].append(field + ": expected full immutable pin")
        else:
            report["verified_fields"].append(field)

    identity = at(doc, "tokenizer.byte_identity_to_1017_tokenizer_file")
    if not isinstance(identity, str) or "NOT_CLAIMED" not in identity:
        report["invalid_fields"].append("tokenizer.byte_identity_to_1017_tokenizer_file: preserve explicit qualification")
    else:
        report["verified_fields"].append("tokenizer.byte_identity_to_1017_tokenizer_file")

    report["missing_fields"] = sorted(set(report["missing_fields"]))
    report["invalid_fields"] = sorted(set(report["invalid_fields"]))
    report["verified_fields"] = sorted(set(report["verified_fields"]))
    report["state"] = "HOLD" if report["missing_fields"] or report["invalid_fields"] else "SOURCE_PINS_COMPLETE_NOT_TRAINING_ADMISSION"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    try:
        report = validate(args.manifest)
    except OSError as exc:
        report = {
            "validator_schema": "NOX_4A01_SOURCE_PIN_VALIDATION_V1",
            "state": "HOLD",
            "execution_authorized": False,
            "weights_loaded": False,
            "network_used": False,
            "missing_fields": [],
            "invalid_fields": ["manifest: " + type(exc).__name__],
            "verified_fields": [],
        }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report["state"] == "SOURCE_PINS_COMPLETE_NOT_TRAINING_ADMISSION" else 2


if __name__ == "__main__":
    raise SystemExit(main())
