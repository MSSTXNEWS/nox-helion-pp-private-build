#!/usr/bin/env python3
"""Fail-closed source-pin validator for the canonical NOX 4A01 manifest.

Reads only the small JSON manifest. It validates fixed source pins and the recorded provenance/byte-check fields structurally; it does not independently inspect URLs, verify downloaded bytes, open model/tokenizer/data payloads, use the network, or authorize a training run.
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
EXPECTED_DATASET_REVISION = "218ec52e09a7e7462a5400043bb9a69a41d06b76"
EXPECTED_DATASET_README = "https://huggingface.co/datasets/Rowan/hellaswag/blob/218ec52e09a7e7462a5400043bb9a69a41d06b76/README.md"
EXPECTED_DATASET_LICENSE_URL = "https://github.com/rowanz/hellaswag/blob/master/LICENSE"
EXPECTED_SPLITS = {
    "train": {
        "path": "data/train-00000-of-00001.parquet",
        "sha256": "cacb12587faa63d7f723a72d61d12bfa94b140446f5a6a0a2e1c6906ab88bf02",
        "size_bytes": 24365524,
    },
    "validation": {
        "path": "data/validation-00000-of-00001.parquet",
        "sha256": "899813071e1e95efafec90f856e1987d2150fa4d020fc005df6962c259f660cd",
        "size_bytes": 6315951,
    },
}


def at(obj: Any, dotted: str) -> Any:
    value = obj
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def validate(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        return {
            "validator_schema": "NOX_4A01_SOURCE_PIN_VALIDATION_V1",
            "manifest_path": str(path),
            "state": "HOLD",
            "execution_authorized": False,
            "weights_loaded": False,
            "network_used": False,
            "missing_fields": [],
            "invalid_fields": ["manifest: exceeds 256 KiB bound"],
            "verified_fields": [],
        }
    raw = path.read_bytes()
    report: dict[str, Any] = {
        "validator_schema": "NOX_4A01_SOURCE_PIN_VALIDATION_V1",
        "manifest_path": str(path),
        "verification_scope": "STRUCTURAL_SOURCE_PIN_CHECK_ONLY; URLs and payload bytes are not independently reverified",
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
        "training_recipe.data.license": "MIT",
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

    revision = at(doc, "training_recipe.data.snapshot_revision")
    if revision is None or revision == "":
        report["missing_fields"].append("training_recipe.data.snapshot_revision")
    elif not isinstance(revision, str) or not HEX40.fullmatch(revision):
        report["invalid_fields"].append("training_recipe.data.snapshot_revision: expected full immutable revision")
    elif revision != EXPECTED_DATASET_REVISION:
        report["invalid_fields"].append("training_recipe.data.snapshot_revision: unexpected pinned dataset revision")
    else:
        report["verified_fields"].append("training_recipe.data.snapshot_revision")

    split_files = at(doc, "training_recipe.data.split_files")
    if not isinstance(split_files, dict):
        report["missing_fields"].append("training_recipe.data.split_files")
    else:
        for split, expected in EXPECTED_SPLITS.items():
            field = "training_recipe.data.split_files." + split
            entry = split_files.get(split)
            if not isinstance(entry, dict):
                report["missing_fields"].append(field)
                continue
            for key, expected_value in (
                ("path", expected["path"]),
                ("sha256", expected["sha256"]),
                ("lfs_oid_sha256", expected["sha256"]),
                ("size_bytes", expected["size_bytes"]),
            ):
                value = entry.get(key)
                if value is None or value == "":
                    report["missing_fields"].append(field + "." + key)
                elif value != expected_value:
                    report["invalid_fields"].append(field + "." + key + ": unexpected immutable pin")
            expected_url = (
                "https://huggingface.co/datasets/Rowan/hellaswag/resolve/"
                + EXPECTED_DATASET_REVISION + "/" + expected["path"]
            )
            if entry.get("immutable_url") != expected_url:
                report["invalid_fields"].append(field + ".immutable_url: must use the pinned revision and split path")
            receipt = entry.get("byte_verification")
            if not isinstance(receipt, dict):
                report["missing_fields"].append(field + ".byte_verification")
            else:
                if receipt.get("result") != "BYTE_HASH_AND_SIZE_MATCH":
                    report["invalid_fields"].append(field + ".byte_verification.result: unsupported status")
                if receipt.get("measured_sha256") != expected["sha256"]:
                    report["invalid_fields"].append(field + ".byte_verification.measured_sha256: does not match pinned LFS OID")
                if receipt.get("measured_size_bytes") != expected["size_bytes"]:
                    report["invalid_fields"].append(field + ".byte_verification.measured_size_bytes: does not match pinned size")
                if receipt.get("payload_retained") is not False:
                    report["invalid_fields"].append(field + ".byte_verification.payload_retained: expected false")
                if receipt.get("content_inspected") is not False:
                    report["invalid_fields"].append(field + ".byte_verification.content_inspected: expected false")
            report["verified_fields"].append(field + " (fixed source pin and recorded byte-check structure)")

    license_provenance = at(doc, "training_recipe.data.license_provenance")
    if not isinstance(license_provenance, dict):
        report["missing_fields"].append("training_recipe.data.license_provenance")
    else:
        license_expectations = {
            "claim": "MIT",
            "source_kind": "PINNED_DATASET_CARD_BODY",
            "dataset_card_revision": EXPECTED_DATASET_REVISION,
            "dataset_card_readme_url": EXPECTED_DATASET_README,
            "linked_license_url": EXPECTED_DATASET_LICENSE_URL,
        }
        for key, expected_value in license_expectations.items():
            if license_provenance.get(key) != expected_value:
                report["invalid_fields"].append("training_recipe.data.license_provenance." + key + ": unexpected source claim")
        if not isinstance(license_provenance.get("statement"), str) or not license_provenance["statement"].startswith("MIT "):
            report["invalid_fields"].append("training_recipe.data.license_provenance.statement: expected pinned card statement")
        if license_provenance.get("direct_license_text_verified") is not False:
            report["invalid_fields"].append("training_recipe.data.license_provenance.direct_license_text_verified: must remain false")
        access_result = license_provenance.get("linked_license_access_result")
        if not isinstance(access_result, str) or "HTTP 451" not in access_result:
            report["invalid_fields"].append("training_recipe.data.license_provenance.linked_license_access_result: preserve access limitation")
        report["verified_fields"].append("training_recipe.data.license_provenance (dataset-card-stated only; LICENSE text not verified)")

    identity = at(doc, "tokenizer.byte_identity_to_1017_tokenizer_file")
    if not isinstance(identity, str) or "NOT_CLAIMED" not in identity:
        report["invalid_fields"].append("tokenizer.byte_identity_to_1017_tokenizer_file: preserve explicit qualification")
    else:
        report["verified_fields"].append("tokenizer.byte_identity_to_1017_tokenizer_file")

    unresolved = at(doc, "acceptance.unresolved_source_requirements")
    if not isinstance(unresolved, list) or not unresolved:
        report["invalid_fields"].append("acceptance.unresolved_source_requirements: explicit outstanding source gates required")
        unresolved = []
    report["unresolved_source_requirements"] = [
        item for item in unresolved if isinstance(item, str) and item.strip()
    ]
    if len(report["unresolved_source_requirements"]) != len(unresolved):
        report["invalid_fields"].append("acceptance.unresolved_source_requirements: expected nonempty strings")

    report["missing_fields"] = sorted(set(report["missing_fields"]))
    report["invalid_fields"] = sorted(set(report["invalid_fields"]))
    report["verified_fields"] = sorted(set(report["verified_fields"]))
    report["state"] = "HOLD" if report["missing_fields"] or report["invalid_fields"] or report.get("unresolved_source_requirements") else "SOURCE_PINS_COMPLETE_NOT_TRAINING_ADMISSION"
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
