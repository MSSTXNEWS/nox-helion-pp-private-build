#!/usr/bin/env python3
"""Read-only, offline inspection of local LLM snapshot candidates.

This is not a model/rights attestation and does not load a model, run CUDA,
download weights, or claim successful fine-tuning. The trusted host must
separately bind an approved license, revision, and SHA to its model lock.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path

MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_WEIGHT_FILES = 512
REVISION_RE = re.compile(r"[0-9a-fA-F]{40}")


def _regular(path: Path, directory: bool = False) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode) or (getattr(info, "st_file_attributes", 0) &
                                       getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
        return False
    return stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)


def _safe_root(root: Path) -> Path:
    # Check pre-resolution ancestors as well as the snapshot root.
    original = Path(os.path.abspath(root))
    if not _regular(original, directory=True):
        raise ValueError("MODEL_ROOT_NOT_REGULAR_DIRECTORY")
    for parent in original.parents:
        if parent.exists() and not _regular(parent, directory=True):
            raise ValueError("MODEL_ROOT_REPARSE_ANCESTOR")
    return original


def _json_file(path: Path) -> dict:
    if not _regular(path) or path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("MODEL_METADATA_INVALID")
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError, OSError) as exc:
        raise ValueError("MODEL_METADATA_INVALID") from exc
    if not isinstance(obj, dict):
        raise ValueError("MODEL_METADATA_INVALID")
    return obj


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _weight_header(path: Path) -> frozenset[str]:
    if not _regular(path):
        raise ValueError("MODEL_WEIGHTS_NOT_REGULAR")
    size = path.stat().st_size
    with path.open("rb") as f:
        prefix = f.read(8)
        if len(prefix) != 8:
            raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID")
        length = int.from_bytes(prefix, "little")
        if length < 2 or length > MAX_JSON_BYTES or size < length + 8:
            raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID")
        try:
            header = json.loads(f.read(length))
        except (UnicodeError, ValueError) as exc:
            raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID") from exc
    tensors = [v for k, v in header.items() if k != "__metadata__"] if isinstance(header, dict) else []
    capacity = size - length - 8
    if not tensors or any(
        not isinstance(t, dict) or not isinstance(t.get("dtype"), str) or
        not isinstance(t.get("shape"), list) or
        type(t.get("data_offsets")) is not list or len(t["data_offsets"]) != 2 or
        any(type(n) is not int for n in t["data_offsets"]) or
        not (0 <= t["data_offsets"][0] <= t["data_offsets"][1] <= capacity)
        for t in tensors
    ):
        raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID")
    return frozenset(k for k in header if k != "__metadata__")


def inspect(root: Path, expected_revision: str | None) -> dict:
    report = {
        "schema": "NOX-P04-MODEL-SNAPSHOT-PROBE-v1",
        "status": "HOLD",
        "reason": None,
        "candidate_sha256": None,
        "weight_files": [],
        "tensor_headers": 0,
        "model_license_verified": False,
        "dataset_rights_verified": False,
        "gpu_training_verified": False,
        "snapshot_revision_attested": False,
    }
    try:
        if not isinstance(expected_revision, str) or not REVISION_RE.fullmatch(expected_revision):
            raise ValueError("IMMUTABLE_REVISION_REQUIRED")
        base = _safe_root(root)
        config = _json_file(base / "config.json")
        if not isinstance(config.get("model_type"), str) or not config["model_type"].strip():
            raise ValueError("MODEL_CONFIG_NOT_LLM_SNAPSHOT")
        index = base / "model.safetensors.index.json"
        if index.exists() or index.is_symlink():
            metadata = _json_file(index)
            weights = metadata.get("weight_map")
            if not isinstance(weights, dict) or not weights:
                raise ValueError("MODEL_SHARD_INDEX_INVALID")
            # Linear index-to-shard map; verify actual tensor membership per shard.
            expected_by_shard: dict[str, set[str]] = {}
            for tensor_name, shard_name in weights.items():
                if not isinstance(tensor_name, str) or not tensor_name.strip():
                    raise ValueError("MODEL_SHARD_INDEX_INVALID")
                if not isinstance(shard_name, str) or not shard_name:
                    raise ValueError("MODEL_SHARD_PATH_UNSAFE")
                expected_by_shard.setdefault(shard_name, set()).add(tensor_name)
            names = sorted(expected_by_shard)
        else:
            expected_by_shard = None
            names = ["model.safetensors"]
        if not names or len(names) > MAX_WEIGHT_FILES:
            raise ValueError("MODEL_WEIGHT_COUNT_INVALID")
        for name in names:
            if (not isinstance(name, str) or not name or name != Path(name).name or
                    not name.endswith(".safetensors") or name in {".", ".."}):
                raise ValueError("MODEL_SHARD_PATH_UNSAFE")
            file = base / name
            tensor_names = _weight_header(file)
            if expected_by_shard is not None and tensor_names != expected_by_shard[name]:
                raise ValueError("MODEL_SHARD_TENSOR_MAP_MISMATCH")
            report["tensor_headers"] += len(tensor_names)
            report["weight_files"].append({
                "name": name,
                "bytes": file.stat().st_size,
                "sha256": _sha256(file),
            })
        report["candidate_sha256"] = _sha256(base / "config.json")
        report["status"] = "LOCAL_FILES_PRESENT_ONLY"
        report["reason"] = "LICENSE_DATASET_GPU_AND_REVISION_ATTESTATION_PENDING"
    except (ValueError, OSError) as exc:
        report["reason"] = str(exc)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--expected-revision", required=True)
    args = parser.parse_args()
    result = inspect(args.root, args.expected_revision)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "LOCAL_FILES_PRESENT_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
