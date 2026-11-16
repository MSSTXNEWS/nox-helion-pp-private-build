"""Source-only release preflight contract for Maya + DeepSeek IQ2_XXS.

This module produces a reviewable plan state only. It never launches Maya,
creates CUDA contexts, downloads weights, or changes production state.
"""
from __future__ import annotations

import re

EXPECTED_FILES = tuple(
    [f"DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-0000{i}-of-00006.gguf"
     for i in range(1, 6)] +
    ["DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf"]
)
SUPPORTED_TYPES = frozenset({"BF16", "Q8_0", "Q6_K", "Q5_K", "IQ2_XXS", "IQ4_NL"})
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def evaluate_source_plan(*, stop_present, gpu_ids, tp, max_context, reserve_mib,
                         verified_files, tensor_types):
    """Return only SOURCE_ONLY_* or HOLD; this function has no launch action."""
    if stop_present:
        return {"state": "HOLD_OWNER_STOP", "launchable": False}
    if tuple(gpu_ids) != (0, 1) or tp != 2:
        return {"state": "HOLD_TWO_V100_TP2_REQUIRED", "launchable": False}
    if type(max_context) is not int or not 1 <= max_context <= 65536:
        return {"state": "HOLD_CONTEXT_EXPLICIT_OR_TOO_LARGE", "launchable": False}
    if type(reserve_mib) is not int or reserve_mib <= 0:
        return {"state": "HOLD_POSITIVE_MEMORY_RESERVE_REQUIRED", "launchable": False}
    rows = {row.get("path"): row for row in verified_files if isinstance(row, dict)}
    if set(rows) != set(EXPECTED_FILES):
        return {"state": "HOLD_ALL_FIVE_SHARDS_AND_ENGRAM_REQUIRED", "launchable": False}
    if any(type(row.get("bytes")) is not int or row["bytes"] <= 0
           or not isinstance(row.get("sha256"), str) or not SHA256.fullmatch(row["sha256"])
           or row.get("sha_verified") is not True for row in rows.values()):
        return {"state": "HOLD_SIZE_OR_SHA256_UNVERIFIED", "launchable": False}
    types = frozenset(tensor_types)
    unknown = sorted(types - SUPPORTED_TYPES)
    if not types or unknown:
        return {"state": "HOLD_UNCONFIRMED_TENSOR_KERNEL", "launchable": False,
                "unknown_types": unknown}
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
        "command_contract": ["--pack", "--gpus 0,1", "--tp 2",
                             "--max-context", "--reserve-mib", "--serve"],
    }
