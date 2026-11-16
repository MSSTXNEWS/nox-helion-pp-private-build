"""Source-only release preflight contract for Maya + DeepSeek IQ2_XXS.

This module produces a reviewable plan state only. It never launches Maya,
creates CUDA contexts, downloads weights, or changes production state.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path

EXPECTED_FILES = tuple(
    [f"DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-0000{i}-of-00006.gguf"
     for i in range(1, 6)] +
    ["DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf"]
)
# Immutable owner-reviewed six-file manifest pinned by source branch feature/nox-engine-stage-20261116.
# Do not accept caller-controlled sizes or digest strings as evidence of DeepSeek identity.
PINNED_FILE_FACTS = {
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf": (5780704, "f356f198561f56df36f7ab92d7238a926646d76de992c34f15bcb939a5f529b9"),
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00002-of-00006.gguf": (39535781184, "25af3785ccf925f54137e1ead4c481a8952315dc0b1af6519a99407f67bce8f3"),
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00003-of-00006.gguf": (39736712000, "8168d0998fc494def2e1952d83c131425a108660aae9d29190f5a8670ab62b48"),
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00004-of-00006.gguf": (39036908384, "9eb9b4de1968f150dfc207eb31c27be9cd9b5666a9a6246bde8a22b184b4bee0"),
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00005-of-00006.gguf": (19923784832, "7e35f6b4e6fc46f6c4b152b593d84d683c5ece695ae6ad734f556198c041bec1"),
    "DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf": (110595290816, "3dac4c54893ad7aa89103c0028500eadc78e74112cef3a2930a97e67dc9fb4f3"),
}
SUPPORTED_TYPES = frozenset({"BF16", "Q8_0", "Q6_K", "Q5_K", "IQ2_XXS", "IQ4_NL"})
ROLE_FLOAT_TYPES = frozenset({"F32", "F16", "BF16", "Q8_0"})
# This plan is pinned to the declared IQ2_XXS trunk + IQ4_NL Engram artifacts.
ROLE_EXPERT_TYPES = frozenset({"IQ2_XXS"})
ROLE_ENGRAM_TABLE_TYPES = frozenset({"IQ4_NL"})
ROLE_LAYERS = re.compile(r"blk\.(\d+)\.")
EXPECTED_LAYER_IDS = frozenset(range(40))
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def validate_tensor_role_inventory(rows):
    """Validate synthetic/raw GGUF role metadata against Maya's runtime dtype contracts."""
    if not isinstance(rows, (tuple, list)) or not rows:
        return {"state": "HOLD_TENSOR_ROLE_INVENTORY_REQUIRED"}
    embed = []
    routers = []
    router_weight_layers = set()
    router_bias_layers = set()
    experts = {}
    engrams = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not isinstance(row.get("dtype"), str):
            return {"state": "HOLD_TENSOR_ROLE_INVENTORY_MALFORMED"}
        name, dtype = row["name"], row["dtype"]
        dims = row.get("dims")
        if not isinstance(dims, (tuple, list)) or not dims or any(type(x) is not int or x <= 0 for x in dims):
            return {"state": "HOLD_TENSOR_ROLE_INVENTORY_MALFORMED"}
        if name == "token_embd.weight":
            embed.append((name, dtype))
            continue
        match = ROLE_LAYERS.match(name)
        if not match:
            continue
        layer = int(match.group(1))
        tail = name[match.end():]
        if tail in ("ffn_gate_inp.weight", "exp_probs_b.bias", "exp_probs_b_vl.bias"):
            routers.append((name, dtype))
            if tail == "ffn_gate_inp.weight":
                router_weight_layers.add(layer)
            elif tail == "exp_probs_b.bias":
                router_bias_layers.add(layer)
        elif tail in ("ffn_gate_exps.weight", "ffn_up_exps.weight", "ffn_down_exps.weight"):
            role = {"ffn_gate_exps.weight": "w1", "ffn_up_exps.weight": "w3",
                    "ffn_down_exps.weight": "w2"}[tail]
            experts.setdefault(layer, {})[role] = (name, dtype)
        elif tail == "engram_embd.weight":
            engrams.append((name, dtype, dims))
    if len(embed) != 1:
        return {"state": "HOLD_TENSOR_ROLE_INVENTORY_INCOMPLETE", "role": "token_embedding"}
    if embed[0][1] not in {"BF16", "Q8_0", "Q4_K", "Q5_K", "Q6_K"}:
        return {"state": "HOLD_UNSUPPORTED_ROLE_DTYPE", "role": "token_embedding", "dtype": embed[0][1]}
    if (router_weight_layers != EXPECTED_LAYER_IDS or
            router_bias_layers != EXPECTED_LAYER_IDS):
        return {"state": "HOLD_TENSOR_ROLE_INVENTORY_INCOMPLETE", "role": "router",
                "router_weight_layers": len(router_weight_layers),
                "router_bias_layers": len(router_bias_layers)}
    bad_router = next(((name, dtype) for name, dtype in routers if dtype not in ROLE_FLOAT_TYPES), None)
    if bad_router:
        return {"state": "HOLD_UNSUPPORTED_ROLE_DTYPE", "role": "router",
                "name": bad_router[0], "dtype": bad_router[1]}
    if set(experts) != EXPECTED_LAYER_IDS:
        return {"state": "HOLD_TENSOR_ROLE_INVENTORY_INCOMPLETE", "role": "routed_experts",
                "expert_layers": len(experts)}
    for layer, parts in sorted(experts.items()):
        if set(parts) != {"w1", "w2", "w3"}:
            return {"state": "HOLD_TENSOR_ROLE_INVENTORY_INCOMPLETE", "role": "routed_experts",
                    "layer": layer}
        bad_expert = next((v for v in parts.values() if v[1] not in ROLE_EXPERT_TYPES), None)
        if bad_expert:
            return {"state": "HOLD_UNSUPPORTED_ROLE_DTYPE", "role": "routed_expert",
                    "name": bad_expert[0], "dtype": bad_expert[1]}
        if parts["w1"][1] != parts["w3"][1]:
            return {"state": "HOLD_EXPERT_GATE_UP_TYPE_MISMATCH", "layer": layer}
    if not engrams:
        return {"state": "HOLD_TENSOR_ROLE_INVENTORY_INCOMPLETE", "role": "engram_table"}
    for name, dtype, dims in engrams:
        if dtype not in ROLE_ENGRAM_TABLE_TYPES:
            return {"state": "HOLD_UNSUPPORTED_ROLE_DTYPE", "role": "engram_table",
                    "name": name, "dtype": dtype}
        if dtype == "IQ4_NL" and dims[0] % 32 != 0:
            return {"state": "HOLD_ENGRAM_IQ4_NL_BLOCK_ALIGNMENT", "name": name}
    return {"state": "ROLE_DTYPE_METADATA_PASS", "launchable": False,
            "roles_checked": {"token_embedding": len(embed), "router": len(routers),
                              "routed_expert_layers": len(experts), "engram_tables": len(engrams),
                              "engram_layer_coverage": "NOT_TESTED"}}



def _path_has_symlink_component(path: Path) -> bool:
    """Reject symlinked ancestors so the checked model/output path has a stable lexical root."""
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            if stat.S_ISLNK(current.lstat().st_mode):
                return True
        except FileNotFoundError:
            return False
        except OSError:
            return True
    return False


def _sha256_file(path: Path) -> str:
    """Hash an open, regular inode; HOLD on symlink swaps or in-place mutation."""
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) |
             getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise OSError("HOLD_PACKER_MODEL_INPUT_NOT_REGULAR")
        digest = hashlib.sha256()
        with os.fdopen(fd, "rb", closefd=False) as source:
            for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
                digest.update(block)
        after = os.fstat(fd)
        at_name = path.lstat()
        keys = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        identity = lambda row: tuple(getattr(row, key) for key in keys)
        if (not stat.S_ISREG(at_name.st_mode) or identity(before) != identity(after)
                or identity(before) != identity(at_name)
                or _path_has_symlink_component(path.parent)):
            raise OSError("HOLD_PACKER_MODEL_CHANGED_DURING_HASH")
        return digest.hexdigest()
    finally:
        os.close(fd)


def observe_packer_output(model_file_paths):
    """Derive the pack output from six real manifest files and lstat it without creating anything."""
    if not isinstance(model_file_paths, (tuple, list)) or len(model_file_paths) != len(EXPECTED_FILES):
        return {"state": "HOLD_PACKER_MODEL_PATH_UNKNOWN"}
    if any(not isinstance(raw, (str, os.PathLike)) for raw in model_file_paths):
        return {"state": "HOLD_PACKER_MODEL_PATH_UNKNOWN"}
    try:
        paths = [Path(raw).absolute() for raw in model_file_paths]
    except (TypeError, ValueError, OSError):
        return {"state": "HOLD_PACKER_MODEL_PATH_UNKNOWN"}
    if (len({p.name for p in paths}) != len(paths) or
            {p.name for p in paths} != set(EXPECTED_FILES) or
            len({p.parent for p in paths}) != 1):
        return {"state": "HOLD_PACKER_MODEL_PATH_UNKNOWN"}
    model_dir = paths[0].parent
    if _path_has_symlink_component(model_dir):
        return {"state": "HOLD_PACKER_MODEL_PATH_SYMLINK"}
    for path in paths:
        try:
            st = path.lstat()
        except OSError:
            return {"state": "HOLD_PACKER_MODEL_INPUT_MISSING"}
        if not stat.S_ISREG(st.st_mode):
            return {"state": "HOLD_PACKER_MODEL_INPUT_NOT_PINNED"}
        expected_bytes, expected_sha256 = PINNED_FILE_FACTS[path.name]
        if st.st_size != expected_bytes:
            return {"state": "HOLD_PACKER_MODEL_INPUT_NOT_PINNED"}
        try:
            if _sha256_file(path) != expected_sha256:
                return {"state": "HOLD_PACKER_MODEL_SHA256_MISMATCH"}
        except OSError:
            return {"state": "HOLD_PACKER_MODEL_SHA256_UNREADABLE"}
    output = model_dir / "maya-ds4"
    try:
        output.lstat()
    except FileNotFoundError:
        return {"state": "PACKER_OUTPUT_ABSENT_VERIFIED",
                "model_dir": str(model_dir), "output_dir": str(output)}
    except OSError:
        return {"state": "HOLD_PACKER_OUTPUT_UNKNOWN"}
    return {"state": "HOLD_PACKER_OUTPUT_EXISTS",
            "model_dir": str(model_dir), "output_dir": str(output)}


def evaluate_source_plan(*, stop_present, gpu_ids, tp, max_context, reserve_mib,
                         verified_files, tensor_types, tensor_role_inventory=None, model_file_paths=None):
    """Return only SOURCE_ONLY_* or HOLD; this function has no launch action."""
    # Only an explicit owner-confirmed False may pass this source gate.
    if stop_present is not False:
        return {"state": "HOLD_OWNER_STOP", "launchable": False}
    if (not isinstance(gpu_ids, (list, tuple)) or len(gpu_ids) != 2 or
            any(type(x) is not int for x in gpu_ids) or tuple(gpu_ids) != (0, 1) or
            type(tp) is not int or tp != 2):
        return {"state": "HOLD_TWO_V100_TP2_REQUIRED", "launchable": False}
    if type(max_context) is not int or not 1 <= max_context <= 65536:
        return {"state": "HOLD_CONTEXT_EXPLICIT_OR_TOO_LARGE", "launchable": False}
    if type(reserve_mib) is not int or reserve_mib <= 0:
        return {"state": "HOLD_POSITIVE_MEMORY_RESERVE_REQUIRED", "launchable": False}
    if (not isinstance(verified_files, (tuple, list)) or
            len(verified_files) != len(EXPECTED_FILES) or
            any(not isinstance(row, dict) or not isinstance(row.get("path"), str)
                for row in verified_files)):
        return {"state": "HOLD_ALL_FIVE_SHARDS_AND_ENGRAM_REQUIRED", "launchable": False}
    rows = {row.get("path"): row for row in verified_files}
    if set(rows) != set(EXPECTED_FILES) or len(rows) != len(verified_files):
        return {"state": "HOLD_ALL_FIVE_SHARDS_AND_ENGRAM_REQUIRED", "launchable": False}
    if any(type(row.get("bytes")) is not int or row["bytes"] != PINNED_FILE_FACTS[name][0]
           or row.get("sha256") != PINNED_FILE_FACTS[name][1]
           or row.get("sha_verified") is not True for name, row in rows.items()):
        return {"state": "HOLD_SIZE_OR_SHA256_UNVERIFIED", "launchable": False}
    if (not isinstance(tensor_types, (list, tuple, set, frozenset)) or
            any(not isinstance(t, str) for t in tensor_types)):
        return {"state": "HOLD_UNCONFIRMED_TENSOR_KERNEL", "launchable": False}
    types = frozenset(tensor_types)
    unknown = sorted(types - SUPPORTED_TYPES)
    if not types or unknown:
        return {"state": "HOLD_UNCONFIRMED_TENSOR_KERNEL", "launchable": False,
                "unknown_types": unknown}
    # Derive the output from actual input paths. A caller-supplied bool is not evidence.
    packer = observe_packer_output(model_file_paths)
    if packer["state"] != "PACKER_OUTPUT_ABSENT_VERIFIED":
        return {"state": packer["state"], "launchable": False}
    role_gate = validate_tensor_role_inventory(tensor_role_inventory)
    if role_gate["state"] != "ROLE_DTYPE_METADATA_PASS":
        return {"state": role_gate["state"], "launchable": False, **role_gate}
    return {
        "state": "SOURCE_ONLY_PLAN_READY_NOT_LAUNCHABLE",
        "launchable": False,
        "gpu_ids": [0, 1],
        "tp": 2,
        "max_context": max_context,
        "reserve_mib": reserve_mib,
        "unique_verified_files": len(rows),
        "unique_bytes": sum(row["bytes"] for row in rows.values()),
        "tensor_types": sorted(types),
        "packer_model_dir": packer["model_dir"],
        "packer_output_dir": packer["output_dir"],
        "packer_non_clobber_precondition": True,
        "model_content_sha256": "VERIFIED_AGAINST_PINNED_FACTS",
        "model_tensor_inventory": "ROLE_DTYPE_CHECKED_FOR_SUPPLIED_METADATA_ONLY",
        "role_dtype_gate": role_gate,
        "runtime_abi": "NOT_TESTED",
        "sm70_execution": "NOT_TESTED",
        "runtime_compatibility": "NOT_TESTED",
        "command_contract": ["--pack", "--gpus 0,1", "--tp 2",
                             "--max-context", "--reserve-mib", "--serve"],
    }
