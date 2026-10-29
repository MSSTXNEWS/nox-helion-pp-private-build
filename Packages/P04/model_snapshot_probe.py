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
import math
import os
import re
import stat
import unicodedata
from pathlib import Path

MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_WEIGHT_FILES = 512
REVISION_RE = re.compile(r"[0-9a-fA-F]{40}")


def _json_finite_float(token: str) -> float:
    """Reject JSON numeric overflow, which parse_constant does not intercept."""
    result = float(token)
    if not math.isfinite(result):
        raise ValueError("non-finite JSON numeric value")
    return result


def _json_scalar_unicode(obj) -> None:
    """Reject escaped lone UTF-16 surrogates anywhere in model JSON metadata.

    CPython accepts these escapes; native Rust JSON readers reject them.
    Walk iteratively to avoid adding a separate recursion limit to the parser.
    """
    pending = [obj]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            item.encode("utf-8", errors="strict")
        elif isinstance(item, dict):
            for key, value in item.items():
                pending.append(key)
                pending.append(value)
        elif isinstance(item, list):
            pending.extend(item)


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


def _json_file(path: Path, *, return_sha: bool = False):
    if not _regular(path) or path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("MODEL_METADATA_INVALID")
    try:
        def unique_pairs(pairs):
            values = {}
            for key, value in pairs:
                if key in values:
                    raise ValueError("duplicate model metadata key")
                values[key] = value
            return values
        with path.open("rb") as stream:
            initial = os.fstat(stream.fileno())
            if not stat.S_ISREG(initial.st_mode) or initial.st_size > MAX_JSON_BYTES:
                raise ValueError("MODEL_METADATA_INVALID")
            raw = stream.read(MAX_JSON_BYTES + 1)
            final = os.fstat(stream.fileno())
        def stamp(s):
            return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if (len(raw) > MAX_JSON_BYTES or stamp(initial) != stamp(final) or
                not _regular(path) or stamp(path.stat()) != stamp(initial)):
            raise ValueError("MODEL_METADATA_CHANGED_DURING_INSPECTION")
        def reject_nonfinite(value):
            raise ValueError("non-finite JSON token: " + value)
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs,
                         parse_constant=reject_nonfinite,
                         parse_float=_json_finite_float)
        _json_scalar_unicode(obj)
    except (UnicodeError, ValueError, OSError, RecursionError) as exc:
        raise ValueError("MODEL_METADATA_INVALID") from exc
    if not isinstance(obj, dict):
        raise ValueError("MODEL_METADATA_INVALID")
    return (obj, hashlib.sha256(raw).hexdigest()) if return_sha else obj


def _sha256(path: Path) -> str:
    with path.open("rb") as f:
        return _sha256_stream(f)


def _sha256_stream(stream) -> str:
    h = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        h.update(chunk)
    return h.hexdigest()


def inspect_wheel(path: Path, *, expected_sha256: str, target_tags,
                  target_python: str, expected_license: str) -> dict:
    """Compare local wheel bytes with caller-supplied artifact/target policy.

    No install, resolution, download or rights approval. Target tags must come
    from the intended worker (PyPA sys_tags), not an assumed CUDA/build profile.
    """
    import zipfile
    from email.parser import Parser
    report = {"status": "HOLD", "reason": None, "sha256": None,
              "rights_verified": False, "hardware_verified": False,
              "dependency_lock_verified": False}
    try:
        from packaging.tags import Tag, parse_tag
        from packaging.utils import canonicalize_name, parse_wheel_filename
        from packaging.version import Version
        from packaging.specifiers import SpecifierSet
    except ImportError:
        report["reason"] = "WHEEL_PYPA_PARSER_UNAVAILABLE"
        return report
    try:
        if (not isinstance(expected_sha256, str) or
                not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256) or
                not isinstance(target_python, str) or
                not isinstance(expected_license, str) or not expected_license.strip()):
            raise ValueError("WHEEL_TARGET_CONTRACT_INVALID")
        target = set(target_tags)
        if not target or any(not isinstance(tag, Tag) for tag in target):
            raise ValueError("WHEEL_TARGET_CONTRACT_INVALID")
        python = Version(target_python)
        name, version, _, filename_tags = parse_wheel_filename(path.name)
        if not filename_tags & target:
            raise ValueError("WHEEL_TARGET_TAG_MISMATCH")
        with path.open("rb") as stream:
            initial = os.fstat(stream.fileno())
            if not stat.S_ISREG(initial.st_mode):
                raise ValueError("WHEEL_NOT_REGULAR_FILE")
            def stamp(info):
                return (info.st_dev, info.st_ino, info.st_size,
                        info.st_mtime_ns, info.st_ctime_ns)
            def require_stable_artifact():
                if stamp(os.fstat(stream.fileno())) != stamp(initial):
                    raise ValueError("WHEEL_ARTIFACT_CHANGED_DURING_INSPECTION")
            report["sha256"] = _sha256_stream(stream)
            require_stable_artifact()
            if report["sha256"] != expected_sha256.lower():
                raise ValueError("WHEEL_SHA256_MISMATCH")
            stream.seek(0)
            with zipfile.ZipFile(stream) as wheel:
                names = wheel.namelist()
                metadata_names = [n for n in names if n.endswith(".dist-info/METADATA")]
                if len(names) != len(set(names)) or len(metadata_names) != 1:
                    raise ValueError("WHEEL_METADATA_AMBIGUOUS")
                folder = metadata_names[0].rsplit("/", 1)[0]
                if "/" in folder or "\\" in folder:
                    raise ValueError("WHEEL_METADATA_IDENTITY_MISMATCH")
                folder_name, folder_version = folder[:-10].rsplit("-", 1)
                if canonicalize_name(folder_name) != name or Version(folder_version) != version:
                    raise ValueError("WHEEL_METADATA_IDENTITY_MISMATCH")

                def metadata_file(member):
                    info = wheel.getinfo(member)
                    if info.file_size < 1 or info.file_size > MAX_JSON_BYTES // 4:
                        raise ValueError("WHEEL_METADATA_SIZE_INVALID")
                    # ZIP read verifies CRC. Only bounded metadata is inflated;
                    # the large wheel payload was hashed incrementally above.
                    return Parser().parsestr(wheel.read(info).decode("utf-8"))

                def field(message, key, required=True):
                    values = message.get_all(key, [])
                    if len(values) > 1 or (required and (not values or not values[0].strip())):
                        raise ValueError("WHEEL_METADATA_FIELDS_INVALID")
                    return values[0].strip() if values else None

                meta = metadata_file(metadata_names[0])
                wheel_meta = metadata_file(folder + "/WHEEL")
                if canonicalize_name(field(meta, "Name")) != name or Version(field(meta, "Version")) != version:
                    raise ValueError("WHEEL_METADATA_IDENTITY_MISMATCH")
                if field(wheel_meta, "Wheel-Version") != "1.0":
                    raise ValueError("WHEEL_VERSION_UNSUPPORTED")
                metadata_tags = set()
                for tag in wheel_meta.get_all("Tag", []):
                    metadata_tags.update(parse_tag(tag))
                if metadata_tags != filename_tags:
                    raise ValueError("WHEEL_TAG_METADATA_MISMATCH")
                requires_python = field(meta, "Requires-Python", required=False)
                if requires_python and not SpecifierSet(requires_python).contains(python):
                    raise ValueError("WHEEL_TARGET_PYTHON_MISMATCH")
                expression = field(meta, "License-Expression", required=False)
                legacy = field(meta, "License", required=False)
                if expression and legacy:
                    raise ValueError("WHEEL_METADATA_FIELDS_INVALID")
                if (expression or legacy) != expected_license:
                    raise ValueError("WHEEL_DECLARED_LICENSE_MISMATCH")
                report.update(name=str(name), version=str(version), license_field="License-Expression" if expression else "License",
                              declared_license=expression or legacy, target_python=str(python),
                              matching_tags=sorted(str(tag) for tag in filename_tags & target))
            # One descriptor protects against rename, not in-place mutation.
            # This binds metadata to the observed hash without rereading GBs.
            require_stable_artifact()
        report["status"] = "ARTIFACT_CONTRACT_MATCH_ONLY"
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile, RuntimeError) as exc:
        report["reason"] = str(exc)
    return report


def _parse_weight_tensor_names(f, size: int) -> frozenset[str]:
    prefix = f.read(8)
    if len(prefix) != 8:
        raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID")
    length = int.from_bytes(prefix, "little")
    if length < 2 or length > MAX_JSON_BYTES or size < length + 8:
        raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID")
    try:
        def unique_pairs(pairs):
            values = {}
            for key, value in pairs:
                if key in values:
                    raise ValueError("duplicate tensor metadata key")
                values[key] = value
            return values
        raw_header = f.read(length)
        if not raw_header.startswith(b"{"):
            raise ValueError("invalid safetensors header prefix")
        def reject_nonfinite(_token):
            raise ValueError("non-finite safetensors header token")
        header = json.loads(raw_header.decode("utf-8"),
                            object_pairs_hook=unique_pairs,
                            parse_constant=reject_nonfinite,
                            parse_float=_json_finite_float)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID") from exc
    tensors = [v for k, v in header.items() if k != "__metadata__"] if isinstance(header, dict) else []
    capacity = size - length - 8
    if not tensors or any(
        not isinstance(t, dict) or not isinstance(t.get("dtype"), str) or
        not isinstance(t.get("shape"), list) or
        any(type(n) is not int or n < 0 for n in t["shape"]) or
        type(t.get("data_offsets")) is not list or len(t["data_offsets"]) != 2 or
        any(type(n) is not int for n in t["data_offsets"]) or
        not (0 <= t["data_offsets"][0] <= t["data_offsets"][1] <= capacity)
        for t in tensors
    ):
        raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID")
    metadata = header.get("__metadata__", {})
    if not isinstance(metadata, dict) or any(not isinstance(v, str) for v in metadata.values()):
        raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID")
    # Python's JSON decoder permits lone escaped UTF-16 surrogates (\\uD800),
    # whereas the native safetensors parser rejects them. A successful probe
    # must not claim a snapshot that the model loader cannot deserialize.
    # Check names AND metadata keys/values before any shard hashing.
    try:
        for tensor_name in header:
            tensor_name.encode("utf-8", errors="strict")
        for meta_key, meta_value in metadata.items():
            meta_key.encode("utf-8", errors="strict")
            meta_value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID") from exc
    # Offset bounds alone can accept a tensor with impossible shape/byte length.
    # Accept documented byte-addressable dtypes; unknown future dtypes HOLD.
    element_bytes = {"BOOL": 1, "U8": 1, "I8": 1,
                     "F8_E4M3FN": 1, "F8_E5M2": 1,
                     "F16": 2, "BF16": 2, "I16": 2, "U16": 2,
                     "F32": 4, "I32": 4, "U32": 4,
                     "F64": 8, "I64": 8, "U64": 8}
    for tensor in tensors:
        width = element_bytes.get(tensor["dtype"])
        if width is None:
            raise ValueError("MODEL_UNSUPPORTED_TENSOR_DTYPE")
        start, end = tensor["data_offsets"]
        count = 1
        for dim in tensor["shape"]:
            if dim == 0:
                count = 0
                break
            if count > capacity // width // dim:
                raise ValueError("MODEL_TENSOR_SHAPE_BYTES_MISMATCH")
            count *= dim
        if count * width != end - start:
            raise ValueError("MODEL_TENSOR_SHAPE_BYTES_MISMATCH")
    # Safetensors requires complete, nonoverlapping byte-buffer coverage.
    # Empty tensors use zero-width intervals and scalar shape [] is valid.
    cursor = 0
    for start, end in sorted(t["data_offsets"] for t in tensors):
        if start != cursor:
            raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID")
        cursor = end
    if cursor != capacity:
        raise ValueError("MODEL_SAFETENSORS_HEADER_INVALID")
    return frozenset(k for k in header if k != "__metadata__")



def _file_signature(info) -> tuple:
    """Identity/metadata snapshot; not a cryptographic file-content attestation."""
    return (info.st_dev, info.st_ino, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _inspect_weight(path: Path, *, include_hash: bool = False) -> dict:
    if not _regular(path):
        raise ValueError("MODEL_WEIGHTS_NOT_REGULAR")
    with path.open("rb") as stream:
        initial = os.fstat(stream.fileno())
        if not stat.S_ISREG(initial.st_mode):
            raise ValueError("MODEL_WEIGHTS_NOT_REGULAR")
        stamp = _file_signature
        names = _parse_weight_tensor_names(stream, initial.st_size)
        payload_bytes = initial.st_size - stream.tell()
        digest = None
        if include_hash:
            stream.seek(0)
            digest = _sha256_stream(stream)
        # A shared descriptor prevents rename mixing; timestamps catch writes
        # through the same inode. The receipt names must still bind this file.
        if (stamp(os.fstat(stream.fileno())) != stamp(initial) or
                not _regular(path) or stamp(path.stat()) != stamp(initial)):
            raise ValueError("MODEL_WEIGHTS_CHANGED_DURING_INSPECTION")
        return {"names": names, "bytes": initial.st_size,
                "payload_bytes": payload_bytes, "sha256": digest,
                "stat_signature": stamp(initial)}


def _weight_tensor_names(path: Path) -> frozenset[str]:
    return _inspect_weight(path)["names"]


def _weight_header(path: Path) -> int:
    """Retain the count-only helper contract for existing callers."""
    return len(_weight_tensor_names(path))


def _validate_windows_shard_names(names: list[str]) -> None:
    """Reject DOS device aliases, invalid Unicode and casefold aliases before I/O."""
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
    folded = set()
    for name in names:
        if not isinstance(name, str):
            raise ValueError("MODEL_SHARD_PATH_UNSAFE")
        # JSON allows escaped lone surrogates; passing them to Path.lstat()
        # can raise UnicodeEncodeError outside inspect()'s HOLD boundary.
        try:
            name.encode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise ValueError("MODEL_SHARD_PATH_UNSAFE") from exc
        # Win32 treats trailing spaces before the first extension as aliases.
        # Superscript digits ¹²³ are also reserved by COM/LPT device names.
        stem = name.split(".", 1)[0].rstrip(" .").upper()
        # Canonically equivalent names can alias on normalization-aware volumes.
        alias_key = unicodedata.normalize("NFC", name).casefold()
        if (not name or
                re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or
                name != Path(name).name or
                not name.endswith(".safetensors") or
                name in {".", ".."} or
                stem in reserved or
                re.fullmatch(r"(?:COM|LPT)[¹²³]", stem) is not None or
                alias_key in folded):
            raise ValueError("MODEL_SHARD_PATH_UNSAFE")
        folded.add(alias_key)


def _index_total_size(index_metadata: dict) -> int | None:
    """Validate optional HF safetensors index payload size before weight I/O."""
    meta = index_metadata.get("metadata", {})
    if not isinstance(meta, dict):
        raise ValueError("MODEL_SHARD_INDEX_METADATA_INVALID")
    if "total_size" not in meta:
        return None
    total = meta["total_size"]
    if type(total) is not int or total < 0:
        raise ValueError("MODEL_SHARD_INDEX_METADATA_INVALID")
    return total


def inspect(root: Path, expected_revision: str | None) -> dict:
    report = {
        "schema": "NOX-P04-MODEL-SNAPSHOT-PROBE-v1",
        "status": "HOLD",
        "reason": None,
        "candidate_sha256": None,
        "shard_index_sha256": None,
        "observed_snapshot_sha256": None,
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
        config, config_sha256 = _json_file(base / "config.json", return_sha=True)
        if not isinstance(config.get("model_type"), str) or not config["model_type"].strip():
            raise ValueError("MODEL_CONFIG_NOT_LLM_SNAPSHOT")
        index = base / "model.safetensors.index.json"
        weights = None
        expected_total_bytes = None
        if index.exists() or index.is_symlink():
            metadata, index_sha256 = _json_file(index, return_sha=True)
            report["shard_index_sha256"] = index_sha256
            weights = metadata.get("weight_map")
            if not isinstance(weights, dict) or not weights:
                raise ValueError("MODEL_SHARD_INDEX_INVALID")
            expected_total_bytes = _index_total_size(metadata)
            # Validate decoded metadata before hashing/sorting: malformed shard
            # values must produce an installer HOLD report, not a TypeError.
            for tensor, shard in weights.items():
                if not isinstance(tensor, str) or not tensor.strip():
                    raise ValueError("MODEL_SHARD_INDEX_INVALID")
                try:
                    tensor.encode("utf-8", errors="strict")
                except UnicodeError as exc:
                    raise ValueError("MODEL_SHARD_INDEX_INVALID") from exc
                if not isinstance(shard, str):
                    raise ValueError("MODEL_SHARD_PATH_UNSAFE")
            names = sorted(set(weights.values()))
        else:
            names = ["model.safetensors"]
        if not names or len(names) > MAX_WEIGHT_FILES:
            raise ValueError("MODEL_WEIGHT_COUNT_INVALID")
        _validate_windows_shard_names(names)
        observed_total_bytes = 0
        weight_signatures = []
        for name in names:
            file = base / name
            artifact = _inspect_weight(file, include_hash=True)
            observed_total_bytes += artifact["payload_bytes"]
            tensor_names = artifact["names"]
            if weights is not None:
                expected_names = frozenset(tensor for tensor, shard in weights.items() if shard == name)
                if tensor_names != expected_names:
                    raise ValueError("MODEL_SHARD_TENSOR_MAP_MISMATCH")
            report["tensor_headers"] += len(tensor_names)
            report["weight_files"].append({
                "name": name,
                "bytes": artifact["bytes"],
                "sha256": artifact["sha256"],
            })
            weight_signatures.append((name, artifact["stat_signature"]))
        if expected_total_bytes is not None and observed_total_bytes != expected_total_bytes:
            raise ValueError("MODEL_SHARD_TOTAL_SIZE_MISMATCH")
        # Hashing many shards can take hours. Re-read bounded metadata before
        # publishing a complete observation: index/config replacements during
        # hashing must HOLD. This is not a cross-file atomic snapshot lock.
        _, config_sha256_after = _json_file(base / "config.json", return_sha=True)
        if config_sha256_after != config_sha256:
            raise ValueError("MODEL_CONFIG_CHANGED_DURING_INSPECTION")
        if weights is None:
            if index.exists() or index.is_symlink():
                raise ValueError("MODEL_SHARD_INDEX_APPEARED_DURING_INSPECTION")
        else:
            _, index_sha256_after = _json_file(index, return_sha=True)
            if index_sha256_after != report["shard_index_sha256"]:
                raise ValueError("MODEL_SHARD_INDEX_CHANGED_DURING_INSPECTION")
        # A shard verified early may change while later GB-sized shards hash.
        # Fail closed on late deletion, link replacement, inode/size/time change.
        # This is a best-effort stat fence, NOT an atomic multi-file snapshot.
        for name, before in weight_signatures:
            try:
                after = (base / name).lstat()
            except OSError as exc:
                raise ValueError("MODEL_SHARD_CHANGED_AFTER_HASH") from exc
            if (not stat.S_ISREG(after.st_mode) or
                    (getattr(after, "st_file_attributes", 0) &
                     getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)) or
                    _file_signature(after) != before):
                raise ValueError("MODEL_SHARD_CHANGED_AFTER_HASH")
        report["candidate_sha256"] = config_sha256
        # Observation-only fingerprint, not a trusted cross-file atomic lock.
        observed = {"config": config_sha256,
                    "index": report["shard_index_sha256"],
                    "weights": report["weight_files"]}
        raw_observed = json.dumps(observed, sort_keys=True, separators=(",", ":"))
        report["observed_snapshot_sha256"] = hashlib.sha256(
            raw_observed.encode("utf-8")).hexdigest()
        report["status"] = "LOCAL_FILES_PRESENT_ONLY"
        report["reason"] = "LICENSE_DATASET_GPU_AND_REVISION_ATTESTATION_PENDING"
    except (ValueError, OSError) as exc:
        # Partial shard evidence must never look like a verified complete set.
        report["weight_files"].clear()
        report["tensor_headers"] = 0
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

