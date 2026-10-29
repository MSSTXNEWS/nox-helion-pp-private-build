#!/usr/bin/env python3
"""Read-only, exact-blob P04 snapshot security-delta check for manual #3 -> T06.

This is not product QA, and does not import/load weights or run training.
Requires four locally materialized GitHub blobs, from the exact SHA-pinned refs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

EXPECTED = {
    "integrated_source": "f5cf5df231ee9ba4344a6445358034b5aaad9241",
    "integrated_tests": "15a81d1bd44c65625d99fdb617abf434d5a6fe0e",
    "donor_source": "98b51bdbf59e56a629dbafc81d74b5c03a67e7b5",
    "donor_tests": "4f60e931161bbaedba25a417a3610c7e6da2505d",
}

def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def method_names(value: str) -> set[str]:
    return set(re.findall(r"def (test_[a-zA-Z_0-9]+)\(", value))

def contract(integrated: str, integrated_tests: str,
             donor: str, donor_tests: str) -> dict:
    old = method_names(integrated_tests)
    new = method_names(donor_tests)
    checks = {
        "donor_has_windows_filename_validation":
            "_valid_shard_filename" not in integrated and
            "_valid_shard_filename" in donor,
        "donor_has_reserved_device_check":
            "_WINDOWS_RESERVED" not in integrated and
            "_WINDOWS_RESERVED" in donor,
        "donor_has_casefold_collision_check":
            "casefold()" not in integrated and "casefold()" in donor,
        "overlap_validation_preserved":
            "spans = sorted" in integrated and "spans = sorted" in donor,
        "weight_map_validation_preserved":
            "MODEL_SHARD_TENSOR_MAP_MISMATCH" in integrated and
            "MODEL_SHARD_TENSOR_MAP_MISMATCH" in donor,
        "donor_new_negative_tests_present":
            {"test_rejects_windows_specific_shard_paths_on_any_host_os",
             "test_rejects_casefold_colliding_windows_shard_names"} <= new-old,
        "integrated_regressions_must_not_be_lost":
            {"test_rejects_windows_backslash_shard_path",
             "test_rejects_windows_drive_relative_shard_path",
             "test_rejects_control_character_shard_path"} <= old-new,
    }
    return {"checks": checks, "passed": sum(checks.values()),
            "total": len(checks), "integrated_test_count": len(old),
            "donor_test_count": len(new),
            "donor_only": sorted(new-old), "integrated_only": sorted(old-new),
            "required_action": "Selective owner-approved merge, NOT full donor replacement"}

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--integrated-source", type=Path)
    p.add_argument("--integrated-tests", type=Path)
    p.add_argument("--donor-source", type=Path)
    p.add_argument("--donor-tests", type=Path)
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        # Checks only guard classification, not the remotely pinned product.
        i = 'spans = sorted\nMODEL_SHARD_TENSOR_MAP_MISMATCH'
        d = i + '\n_valid_shard_filename\n_WINDOWS_RESERVED\ncasefold()'
        it = '\n'.join('def '+s+'(self): pass' for s in (
            'test_rejects_windows_backslash_shard_path',
            'test_rejects_windows_drive_relative_shard_path',
            'test_rejects_control_character_shard_path'))
        dt = '\n'.join('def '+s+'(self): pass' for s in (
            'test_rejects_windows_specific_shard_paths_on_any_host_os',
            'test_rejects_casefold_colliding_windows_shard_names'))
        r = contract(i, it, d, dt)
        print(json.dumps({"self_test_only": True, **r}, sort_keys=True))
        return 0 if r['passed'] == r['total'] == 7 else 1
    required = {k: getattr(a, k) for k in EXPECTED}
    if any(v is None for v in required.values()):
        p.error("Four exact source/test blob paths are required")
    actual = {k: git_blob(v.read_bytes()) for k, v in required.items()}
    if actual != EXPECTED:
        print(json.dumps({"status": "STALE_BLOB_BLOCKED", "expected": EXPECTED,
                          "actual": actual}, sort_keys=True))
        return 3
    texts = {k: v.read_text(encoding="utf-8") for k, v in required.items()}
    r = contract(texts["integrated_source"], texts["integrated_tests"],
                 texts["donor_source"], texts["donor_tests"])
    print(json.dumps({"status": "STATIC_DELTA_PROOF_ONLY", "blobs": actual,
                      **r}, sort_keys=True))
    return 0 if r["passed"] == r["total"] == 7 else 2

if __name__ == "__main__":
    raise SystemExit(main())
