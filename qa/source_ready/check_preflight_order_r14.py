#!/usr/bin/env python3
"""Independent NOX E07 raw-JSON preflight order gate (source-only).

Checks the existing E07 handoff invokes an exact SHA-pinned Python receipt
validator before its first lossy ConvertFrom-Json, with immediate error exit.
No EXE/NSIS/second JSON engine/release acceptance; owner #1 integrates product.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

HELPER = "qa/source_ready/strict_receipt_json_r13.py"
HANDOFF = "coordination/e06/Emit-E07ImmutableHandoff.ps1"
APPROVED_HELPER_SHA = "34476faf6b3dbfc6ba1c08009ffe298dd61e799003e26668a07ee91c0256bf41"


def check(root: Path, *, expected_helper_sha: str = APPROVED_HELPER_SHA) -> dict:
    root = root.resolve(strict=True)
    path = root / HANDOFF
    helper = root / HELPER
    if not path.is_file() or path.is_symlink() or not helper.is_file() or helper.is_symlink():
        raise ValueError("E07_SOURCE_OR_HELPER_NOT_ADMITTED")
    blob = helper.read_bytes()
    sha = hashlib.sha256(blob).hexdigest()
    if sha != expected_helper_sha:
        raise ValueError("E07_APPROVED_RAW_JSON_HELPER_SHA_MISMATCH")
    script_bytes = path.read_bytes()
    script = script_bytes.decode("utf-8", "strict")
    if script.count("E07_BUILDID_SEALED") != 1 or "FileMode]::CreateNew" not in script:
        raise ValueError("E07_IMMUTABLE_SEAL_OR_NO_CLOBBER_MISSING")
    lines = [s for s in script.splitlines() if s.strip() and not s.lstrip().startswith("#")]
    executable = "\n".join(lines)
    if "<#" in executable or "#>" in executable:
        raise ValueError("E07_BLOCK_COMMENT_UNVERIFIABLE")
    p = re.search(r"\|\s*ConvertFrom-Json\b", executable, re.I)
    if p is None:
        raise ValueError("E07_FIRST_LOSSY_PARSER_NOT_FOUND")
    before = executable[:p.start()]
    invoke = re.search(
        r"(?im)^\s*(?:&\s*)?(?:python(?:\.exe)?|py(?:\.exe)?)\s+"
        r"(?:\.\\|\./)?qa[/\\]source_ready[/\\]strict_receipt_json_r13\.py\s+"
        r"--original\s+\$Original729Receipt\s+--owner\s+\$Owner729Receipt\s+"
        r"--onehost\s+\$OneHostReceipt\s*$", before)
    if invoke is None:
        raise ValueError("E07_APPROVED_RAW_JSON_CALL_NOT_BEFORE_FIRST_PARSE")
    remainder = before[invoke.end():]
    guard = re.match(
        r"(?is)^\s*if\s*\(\s*\$LASTEXITCODE\s+-ne\s+0\s*\)\s*"
        r"\{[^{}]{0,400}\bthrow\b[^{}]*\}", remainder)
    if guard is None:
        raise ValueError("E07_PREVALIDATION_EXIT_NOT_IMMEDIATELY_GUARDED")
    return {"status": "PASS_SOURCE_ORDER_ONLY", "handoff_sha256": hashlib.sha256(script_bytes).hexdigest(),
            "helper_sha256": sha, "original_owner_onehost_inputs": 3,
            "source_ready_accepted": False, "release_accepted": False, "native_e07": "NOT_RUN"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = check(args.repo)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc),
                          "source_ready_accepted": False, "release_accepted": False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
