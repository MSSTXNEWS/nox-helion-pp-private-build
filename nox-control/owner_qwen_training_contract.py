#!/usr/bin/env python3
"""Pinned Qwen student contracts; no install, model load, service or queue write.

This is a new student lineage for the EXISTING NOX trainer slot. It cannot
resume a 35B optimizer or promote a model. Native admission remains external.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re

MODEL_ID = "Qwen/Qwen3.5-9B"
REVISION = "c202236235762e1c871ad0ccb60c8ee5ba337b9a"
MANIFEST_SHA = "2275fc88370ca8ba409a791819e13c8ab7d4e38cce4576a13170b05bcb8b839b"
SHA = re.compile(r"^[a-f0-9]{64}$")
GIB = 1024 ** 3
SCHEMA = "NOX_QWEN35_9B_STUDENT_LINEAGE_V1"
PROOF_SCHEMA = "NOX_QWEN35_9B_UPDATE_PROOF_V1"
FULL_ATTENTION = frozenset((3, 7, 11, 15, 19, 23, 27, 31))
REQUIRED_PACKAGE_VERSIONS = {
    "transformers": "5.23.0", "peft": "0.21.3",
    "accelerate": "1.15.0", "bitsandbytes": "0.50.2",
    "tokenizers": "0.23.3", "safetensors": "0.8.0",
}


class Hold(RuntimeError):
    pass


def sha256_file(path, chunk=1024 * 1024):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise Hold("HOLD_FILE_NOT_REGULAR")
    before = path.stat()
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(chunk), b""):
            h.update(data)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise Hold("HOLD_FILE_CHANGED_DURING_HASH")
    return h.hexdigest()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def text_projection_names():
    names = []
    for layer in range(32):
        base = f"model.language_model.layers.{layer}."
        names.extend(base + "mlp." + name for name in ("gate_proj", "up_proj", "down_proj"))
        if layer in FULL_ATTENTION:
            names.extend(base + "self_attn." + name for name in ("q_proj", "k_proj", "v_proj", "o_proj"))
        else:
            names.extend(base + "linear_attn." + name for name in (
                "in_proj_qkv", "in_proj_z", "in_proj_b", "in_proj_a", "out_proj"))
    return tuple(sorted(names))


def validate_target_inventory(module_names):
    expected = set(text_projection_names())
    missing = expected - set(module_names)
    if missing:
        raise Hold("HOLD_QWEN_TEXT_PROJECTION_INVENTORY")
    return sorted(expected)


def validate_manifest(manifest, *, expected_digest=MANIFEST_SHA):
    """Caller also verifies raw manifest SHA; historical download status is data."""
    if (manifest.get("schema") != "NOX_PINNED_FULL_HF_MODEL_MANIFEST_V1"
            or manifest.get("model_id") != MODEL_ID or manifest.get("revision") != REVISION
            or manifest.get("architectures") != ["Qwen3_5ForConditionalGeneration"]
            or manifest.get("model_type") != "qwen3_5"
            or not SHA.fullmatch(expected_digest)):
        raise Hold("HOLD_QWEN_BASE_MANIFEST_IDENTITY")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != 16:
        raise Hold("HOLD_QWEN_BASE_MANIFEST_FILES")
    seen = set()
    weights = []
    for row in files:
        if not isinstance(row, dict):
            raise Hold("HOLD_QWEN_FILE_ENTRY")
        name = row.get("path")
        if (not isinstance(name, str) or PurePosixPath(name).name != name
                or name in (".", "..") or "\\" in name or name in seen
                or type(row.get("bytes")) is not int or row["bytes"] <= 0
                or not isinstance(row.get("sha256"), str) or not SHA.fullmatch(row["sha256"])):
            raise Hold("HOLD_QWEN_FILE_ENTRY")
        if row.get("immutable_url") != f"https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{name}":
            raise Hold("HOLD_QWEN_FILE_ORIGIN")
        seen.add(name)
        if name.endswith(".safetensors"):
            weights.append(row)
    expected_shards = {f"model.safetensors-{i:05d}-of-00004.safetensors" for i in range(1, 5)}
    if ({row["path"] for row in weights} != expected_shards
            or sum(row["bytes"] for row in weights) != 19_306_310_880
            or sum(row["bytes"] for row in files) != 19_329_393_661):
        raise Hold("HOLD_QWEN_SHARD_SET")
    return files


def verify_base_files(directory, manifest_path, expected_digest=MANIFEST_SHA, on_file=None,
                      sealed_registry=None):
    directory, manifest_path = Path(directory), Path(manifest_path)
    if directory.is_symlink() or not directory.is_dir():
        raise Hold("HOLD_QWEN_BASE_DIRECTORY")
    if sha256_file(manifest_path) != expected_digest:
        raise Hold("HOLD_QWEN_MANIFEST_SHA")
    manifest = json.loads(manifest_path.read_text())
    files = validate_manifest(manifest, expected_digest=expected_digest)
    for row in files:
        path = directory / row["path"]
        if sealed_registry is not None:
            # This is the in-process holder that performed the full streaming
            # SHA. It also verifies ownership, inode, size and all memfd seals.
            # Ordinary or arbitrary /proc symlinks remain forbidden.
            sealed_registry.verify_path(path, row["sha256"], row["bytes"])
        else:
            if path.is_symlink() or not path.is_file() or path.stat().st_size != row["bytes"]:
                raise Hold("HOLD_QWEN_BASE_FILE_SIZE")
            if sha256_file(path) != row["sha256"]:
                raise Hold("HOLD_QWEN_BASE_FILE_SHA")
        if on_file:
            on_file(row["path"])
    config = json.loads((directory / "config.json").read_text())
    text = config.get("text_config", {})
    types = text.get("layer_types")
    if (config.get("architectures") != ["Qwen3_5ForConditionalGeneration"]
            or text.get("num_hidden_layers") != 32 or not isinstance(types, list)
            or len(types) != 32 or {i for i, t in enumerate(types) if t == "full_attention"} != FULL_ATTENTION
            or any(t not in ("full_attention", "linear_attention") for t in types)):
        raise Hold("HOLD_QWEN_ARCHITECTURE_CONFIG")
    index = json.loads((directory / "model.safetensors.index.json").read_text())
    keys = index.get("weight_map", {})
    if any(name + ".weight" not in keys for name in text_projection_names()):
        raise Hold("HOLD_QWEN_TENSOR_INDEX")
    return {"model_id": MODEL_ID, "revision": REVISION,
            "manifest_sha256": expected_digest, "verified_files": len(files),
            "verified_bytes": sum(row["bytes"] for row in files),
            "full_base_sha256_verified": True}


def storage_admission(*, destination_free, cgroup_current, cgroup_max, bytes_to_stage,
                      runtime_headroom, destination_is_tmpfs, disk_free,
                      disk_reserve=8 * GIB, memory_reserve=24 * GIB,
                      destination_reserve=2 * GIB):
    values = (destination_free, cgroup_current, cgroup_max, bytes_to_stage,
              runtime_headroom, disk_free, disk_reserve, memory_reserve, destination_reserve)
    if any(type(v) is not int or v < 0 for v in values) or cgroup_max <= 0:
        raise Hold("HOLD_STORAGE_TELEMETRY_REQUIRED")
    if cgroup_current > cgroup_max:
        raise Hold("HOLD_CGROUP_OVER_LIMIT")
    if destination_free < bytes_to_stage + destination_reserve:
        raise Hold("HOLD_DESTINATION_CAPACITY")
    if disk_free < disk_reserve + (0 if destination_is_tmpfs else bytes_to_stage):
        raise Hold("HOLD_SSD_RESERVE")
    charge = runtime_headroom + (bytes_to_stage if destination_is_tmpfs else 0)
    if cgroup_max - cgroup_current < charge + memory_reserve:
        raise Hold("HOLD_CGROUP_STAGING_AND_RUNTIME_BUDGET")
    return {"state": "CAPACITY_ADMITTED_FROM_CALLER_TELEMETRY",
            "bytes_to_stage": bytes_to_stage, "runtime_headroom": runtime_headroom,
            "no_mount_or_cleanup_performed": True}


def validate_environment(observed):
    """Reuse existing CUDA torch only on its own Python ABI and a verified version."""
    python = observed.get("python_version")
    torch = observed.get("torch_version")
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:\+[-\w.]+)?", str(torch))
    if (not isinstance(python, list) or len(python) != 3
            or any(type(v) is not int or v < 0 for v in python) or tuple(python) < (3, 11, 0)
            or not match or tuple(map(int, match.groups())) < (2, 6, 0)):
        raise Hold("HOLD_QWEN_PYTHON_OR_TORCH_VERSION")
    if (not str(observed.get("torch_cuda", "")).startswith("12.")
            or "sm_70" not in observed.get("torch_arch_list", [])
            or observed.get("device_capability") != [7, 0]):
        raise Hold("HOLD_QWEN_VOLTA_CUDA_BUILD")
    packages = observed.get("packages", {})
    if any(packages.get(name) != version for name, version in REQUIRED_PACKAGE_VERSIONS.items()):
        raise Hold("HOLD_QWEN_OVERLAY_PACKAGE_PINS")
    if observed.get("optional_fast_kernels_present"):
        raise Hold("HOLD_UNREVIEWED_QWEN_FAST_KERNEL_ENVIRONMENT")
    return {"state": "VERSION_CONTRACT_ONLY_KERNEL_SMOKE_STILL_REQUIRED",
            "python_version": python, "torch_version": torch,
            "torch_cuda": observed["torch_cuda"], "packages": packages}


def validate_resume_lineage(saved, requested):
    if saved != requested or saved.get("schema") != SCHEMA:
        raise Hold("HOLD_STUDENT_RESUME_LINEAGE_MISMATCH")
    if saved.get("base", {}).get("model_id") != MODEL_ID:
        raise Hold("HOLD_OLD_BASE_OPTIMIZER_FORBIDDEN")


def validate_update_evidence(row):
    """No global Trainer counter, loss decrease, or unchanged adapter counts as update."""
    if (not isinstance(row, dict) or row.get("amp_skipped") is not False
            or type(row.get("optimizer_step_before")) is not int
            or type(row.get("optimizer_step_after")) is not int
            or row["optimizer_step_after"] != row["optimizer_step_before"] + 1
            or row["optimizer_step_before"] < 0
            or row.get("finite_gradients") is not True):
        raise Hold("HOLD_SUCCESSFUL_OPTIMIZER_UPDATE_NOT_PROVEN")
    before, after = row.get("adapter_sha_before"), row.get("adapter_sha_after")
    if (not isinstance(before, str) or not isinstance(after, str)
            or not SHA.fullmatch(before) or not SHA.fullmatch(after) or before == after):
        raise Hold("HOLD_ADAPTER_UNCHANGED")
    if (type(row.get("loss")) not in (float, int)
            or not math.isfinite(row["loss"])):
        raise Hold("HOLD_NONFINITE_LOSS")
    examples = row.get("training_example_sha256")
    if (not isinstance(examples, list) or len(examples) != 8 or len(set(examples)) != 8
            or any(not isinstance(v, str) or not SHA.fullmatch(v) for v in examples)):
        raise Hold("HOLD_REAL_TRAINING_EXAMPLE_PROVENANCE")
    return True


def verify_proof(receipt, *, lineage, minimum_updates=5):
    if (receipt.get("schema") != PROOF_SCHEMA or receipt.get("lineage_sha256") != canonical_sha(lineage)
            or receipt.get("base_manifest_sha256") != MANIFEST_SHA
            or receipt.get("reload_verified") is not True
            or receipt.get("holdout_finite") is not True
            or receipt.get("independent_holdout_accepted") is not True):
        raise Hold("HOLD_STUDENT_PROOF_SCOPE")
    updates = receipt.get("update_evidence")
    if not isinstance(updates, list) or len(updates) < minimum_updates:
        raise Hold("HOLD_FIVE_SUCCESSFUL_UPDATES_REQUIRED")
    previous = None
    for row in updates:
        validate_update_evidence(row)
        if previous is not None and (row["optimizer_step_before"] != previous["optimizer_step_after"]
                                    or row["adapter_sha_before"] != previous["adapter_sha_after"]):
            raise Hold("HOLD_DISCONTINUOUS_UPDATE_PROOF")
        previous = row
    if (receipt.get("successful_optimizer_steps") != len(updates)
            or receipt.get("final_adapter_tensor_sha256") != updates[-1]["adapter_sha_after"]):
        raise Hold("HOLD_STUDENT_PROOF_COUNTER_OR_HASH")
    if len({key for row in updates[:5] for key in row["training_example_sha256"]}) < 40:
        raise Hold("HOLD_FIRST_FIVE_UPDATES_NEED_FORTY_DISTINCT_EXAMPLES")
    return True
