"""Read-only source/Setup/BuildID lock *before* the sole costly E07 attempt proceeds.

A successful check is prerequisite provenance, NEVER a functional or visual PASS.
The upstream workflow's duplicate-run guard still owns one-Setup admission.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import independent_setup_e07 as e07


def check(artifact_dir: Path, values: dict[str, str]) -> bool:
    """Fail closed unless real E06 same-Setup receipts match all five pins."""
    try:
        source = values["E07_SOURCE_SHA"]
        setup_sha = values["E07_SETUP_SHA"]
        setup_bytes = values["E07_SETUP_BYTES"]
        build = values["E07_BUILD_ID"]
        owned = values["E07_OWNED_COUNT"]
        if (re.fullmatch(r"[0-9a-f]{40}", source) is None or
                re.fullmatch(r"[0-9a-f]{64}", setup_sha) is None or
                re.fullmatch(r"NOX-V16-[0-9a-f]{24}", build) is None or
                re.fullmatch(r"[1-9][0-9]{0,9}", setup_bytes) is None or
                re.fullmatch(r"[1-9][0-9]{0,5}", owned) is None):
            return False
        locked = {
            "source_sha": source,
            "setup_sha256": setup_sha,
            "setup_bytes": int(setup_bytes),
            "build_id": build,
            "owned_count": int(owned),
        }
        setup = artifact_dir / "e06" / "onehost-wow-diagnostic" / "NOX-HELION-V16-DIAGNOSTIC-SETUP.exe"
        handoff = setup.with_name("E07_BUILT_HANDOFF.json")
        proof = e07.setup_lock(setup, handoff, candidate="d02-pinned", pinned=locked)
        # setup_lock cryptographically verifies the actual PE and three original
        # E06 source/build/same-VM receipts. Never accept a mocked status or
        # a different source/Setup/BuildID with matching CLI inputs alone.
        return (type(proof) is dict and
                proof.get("source_sha") == source and
                proof.get("setup_sha256") == setup_sha and
                proof.get("setup_bytes") == int(setup_bytes) and
                proof.get("build_id") == build and
                proof.get("e06_samevm_pass_not_e07") is True)
    except (KeyError, ValueError, OSError, e07.Hold):
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    arguments = parser.parse_args()
    if not check(arguments.artifact_dir, os.environ):
        print("E07_PRODUCER_READ_ONLY_SOURCE_SETUP_BUILD_RECEIPT_HOLD", flush=True)
        return 1
    print("E07_PRODUCER_SOURCE_SETUP_BUILD_LOCKED_NOT_INDEPENDENT_E07", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
