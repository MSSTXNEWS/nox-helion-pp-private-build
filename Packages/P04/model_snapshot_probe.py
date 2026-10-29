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
import unicodedata
from pathlib import Path

MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_WEIGHT_FILES = 512
REVISION_RE = re.compile(r"[0-9a-fA-F]{40}")

# Safetensors primitive widths in bytes. Unsupported types remain HOLD rather
# than being guessed as a valid model snapshot.
_TENSOR_WIDTH = {
    "BOOL": 1, "U8": 1, "I8": 1,
    "F8_E4M3": 1, "F8_E4M3FN": 1, "F8_E5M2": 1,
    "U16": 2, "I16": 2, "F16": 2, "BF16": 2,
    "U32": 4, "I32": 4, "F32": 4,
    "U64": 8, "I64": 8, "F64": 8,
}
_MAX_TENSOR_RANK = 32
_MAX_TENSOR_NAME = 1024

# Windows path semantics must be checked even when the probe runs on Linux.
# Reject reserved device names, NTFS alternate data streams and paths whose
# case-folded names collide on a later Windows filesystem import.
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL"}
_WINDOWS_RESERVED.update(f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1, 10))
_WINDOWS_RESERVED.update(f"{prefix}{n}" for prefix in ("COM", "LPT") for n in ("¹", "²", "³"))
_INVALID_WINDOWS_FILENAME_CHARS = frozenset('<>:"/\\|?*')


def _valid_shard_filename(name: object) -> bool:
    return (isinstance(name, str) and bool(name) and
            name == Path(name).name and name.endswith(".safetensors") and
            sum(2 if ord(c) > 0xFFFF else 1 for c in name) <= 255 and
            not any(0xD800 <= ord(c) <= 0xDFFF for c in name) and
            not any(c in _INVALID_WINDOWS_FILENAME_CHARS or
                    ord(c) < 32 or ord(c) == 127 for c in name) and
            name.split(".", 1)[0].rstrip(" ").upper() not in _WINDOWS_RESERVED)


def _strict_json_object(raw: str | bytes) -> dict:
    """Reject ambiguous duplicate keys and nonfinite JSON constants at every depth."""
    def unique_pairs(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("MODEL_DUPLICATE_JSON_KEY")
            obj[key] = value
        return obj

    def reject_constant(_value):
        raise ValueError("MODEL_NONFINITE_JSON_CONSTANT")

    obj = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    if not isinstance(obj, dict):
        raise ValueError("MODEL_JSON_NOT_OBJECT")
    return obj



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
        obj = _strict_json_object(path.read_text(encoding="utf-8"))
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
            header = _strict_json_object(f.read(length))
        except (UnicodeError, ValueError) as exc:
            raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID") from exc
    capacity = size - length - 8
    tensors = [(name, value) for name, value in header.items() if name != "__metadata__"]
    metadata = header.get("__metadata__", {})
    if (not tensors or not isinstance(metadata, dict) or
        any(not isinstance(v, str) for v in metadata.values())):
        raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID")
    for name, tensor in tensors:
        if (not name or len(name) > _MAX_TENSOR_NAME or
            any(ord(c) < 32 or ord(c) == 127 for c in name) or
            not isinstance(tensor, dict)):
            raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID")
        width = _TENSOR_WIDTH.get(tensor.get("dtype")) if isinstance(tensor.get("dtype"), str) else None
        shape = tensor.get("shape")
        offsets = tensor.get("data_offsets")
        if (width is None or type(shape) is not list or len(shape) > _MAX_TENSOR_RANK or
            any(type(dim) is not int or dim < 0 for dim in shape) or
            type(offsets) is not list or len(offsets) != 2 or
            any(type(n) is not int for n in offsets) or
            not (0 <= offsets[0] <= offsets[1] <= capacity)):
            raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID")
        # Bound each multiplication by the actual file capacity. A zero-sized
        # tensor legitimately occupies no bytes; an empty rank is one scalar.
        expected = 0 if 0 in shape else width
        if expected:
            for dimension in shape:
                if dimension and expected > capacity // dimension:
                    raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID")
                expected *= dimension
        if offsets[1] - offsets[0] != expected:
            raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID")
    # The safetensors buffer must be fully indexed: no overlapping or hidden
    # gaps/trailing bytes. Empty tensors (zero-length spans) remain permitted.
    spans = sorted((t["data_offsets"][0], t["data_offsets"][1]) for _, t in tensors)
    position = 0
    for begin, end in spans:
        if begin != position:
            raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID")
        position = end
    if position != capacity:
        raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID")
    return frozenset(name for name, _ in tensors)


def inspect(root: Path, expected_revision: str | None) -> dict:
    report = {
        "schema": "NOX-P04-MODEL-SNAPSHOT-PROBE-v1",
        "status": "HOLD",
        "reason": None,
        "candidate_sha256": None,
        "candidate_sha256_scope": "CONFIG_JSON_ONLY",
        "snapshot_manifest_sha256": None,
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
            # Cross-platform shard admission: canonicalize Unicode before casefold
            if len({unicodedata.normalize("NFC", name.casefold()) for name in names}) != len(names):
                raise ValueError("MODEL_SHARD_PATH_UNSAFE")
        else:
            expected_by_shard = None
            names = ["model.safetensors"]
        if not names or len(names) > MAX_WEIGHT_FILES:
            raise ValueError("MODEL_WEIGHT_COUNT_INVALID")
        for name in names:
            if not _valid_shard_filename(name):
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
        # The historical candidate SHA covers config only; keep semantics explicit.
        config_sha = _sha256(base / "config.json")
        index_sha = _sha256(index) if expected_by_shard is not None else None
        manifest = {
            "schema": "NOX-P04-LOCAL-SNAPSHOT-CONTENT-v1",
            "config_sha256": config_sha,
            "index_sha256": index_sha,
            "weight_files": report["weight_files"],
        }
        encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True).encode("utf-8")
        report["snapshot_manifest_sha256"] = hashlib.sha256(encoded).hexdigest()
        report["candidate_sha256"] = config_sha
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
