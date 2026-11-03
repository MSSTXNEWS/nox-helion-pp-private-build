"""Acceptance contracts (points 9–12).

Records what was checked. Does not declare the product accepted.
"""
from __future__ import annotations

import time
from typing import Mapping


def same_exe_check(
    *,
    exe_sha256: str,
    host_os: str,
    outside_checkout: bool,
) -> dict:
    """Record a same-EXE acceptance attempt."""
    if not isinstance(exe_sha256, str) or len(exe_sha256) != 64:
        raise ValueError("EXE_SHA256_REQUIRED")
    return {
        "schema": "NOX-SAME-EXE-CHECK-v1",
        "exe_sha256": exe_sha256.lower(),
        "host_os": host_os,
        "outside_checkout": outside_checkout is True,
        "native_windows": host_os == "Windows_NT",
        "ts": int(time.time()),
        "status": "RECORDED",
    }


def independent_acceptance(
    *,
    criteria: list[str],
    results: Mapping[str, str],
) -> dict:
    """Record an independent acceptance pass.

    results values must be PASS / FAIL / NOT_RUN.
    """
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("CRITERIA_REQUIRED")
    if not isinstance(results, Mapping):
        raise ValueError("RESULTS_REQUIRED")
    bad = [k for k, v in results.items() if v not in ("PASS", "FAIL", "NOT_RUN")]
    if bad:
        raise ValueError("RESULT_VALUE_INVALID")
    passed = sum(1 for v in results.values() if v == "PASS")
    return {
        "schema": "NOX-INDEPENDENT-ACCEPTANCE-v1",
        "criteria": list(criteria),
        "results": dict(results),
        "passed": passed,
        "total": len(criteria),
        "ts": int(time.time()),
        "status": "RECORDED",
    }
