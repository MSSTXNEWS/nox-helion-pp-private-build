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
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def evaluate_source_plan(*, stop_present, gpu_ids, tp, max_context, reserve_mib,
                         verified_files, tensor_types):
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
