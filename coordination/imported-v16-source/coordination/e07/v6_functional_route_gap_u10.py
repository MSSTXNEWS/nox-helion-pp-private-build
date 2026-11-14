"""QA-only: original V6 five native UIA clicks do NOT prove four functions.
Never attest a Windows run or upgrade independent E07 to PASS.
"""
from __future__ import annotations
import argparse
import json
import stat
from pathlib import Path

SOURCE = "ffca9aaedce9d90750dfb212aabcdfd970162150"
SETUP = "722399ee3d7794a7aa38d93d933026e015fd29b0d8a60fd431b0bc494040a6bc"
BUILD = "NOX-V16-99fce33d002363f6b3e9b9cf"
PRIMARY = ["CHAT", "INSTALL", "MODELS", "LEARN", "SETTINGS"]


class Hold(ValueError):
    """Bounded first-failure code; not a release approval."""


def require(ok, reason):
    if not ok:
        raise Hold(reason)


def classify(uia):
    """Fail closed on source/Setup identity and click-vs-function scope."""
    require(type(uia) is dict
            and uia.get("schema") == "NOX-E07-FULL-D02-UIA-v1"
            and uia.get("source_sha") == SOURCE
            and uia.get("setup_sha256") == SETUP
            and uia.get("build_id") == BUILD
            and uia.get("physical_setup_verified") is True
            and uia.get("five_uia") == "PASS"
            and uia.get("release_accepted") is False
            and uia.get("independent_e07_10_10") == "HOLD",
            "U10_FROZEN_UIA_IDENTITY_HOLD")
    p = uia.get("five_primary")
    require(type(p) is dict
            and p.get("status") == "PASS"
            and type(p.get("actions_invoked")) is int
            and p["actions_invoked"] == 5
            and p.get("actions_with_new_visible_heading") == PRIMARY
            and p.get("scope") == "FIVE_REAL_UIA_CLICKS_AND_NAVIGATION_ONLY"
            and p.get("install_or_model_function_verified") is False
            and p.get("live_inference_verified") is False
            and p.get("release_accepted") is False,
            "U10_UIA_CLICKS_NOT_FUNCTIONS_HOLD")
    return {"schema": "NOX-V6-U10-ROUTE-FUNCTION-GAP-v1",
            "source_sha": SOURCE, "setup_sha256": SETUP, "build_id": BUILD,
            "navigation_clicks": "5/5_PINNED_RECEIPT",
            "functional_routes": "NOT_TESTED",
            "requires_real_function_probes": PRIMARY[1:],
            "same_vm_proven_from_json": False,
            "independent_visual_e07": "HOLD",
            "independent_e07_10_10": "HOLD",
            "release_accepted": False,
            "status": "NAVIGATION_ONLY_FUNCTIONAL_HOLD"}


def read_receipt(path):
    """Small regular JSON only; reject duplicate keys, links and NaN."""
    try:
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and not path.is_symlink()
                and 1 <= info.st_size <= 1048576, "U10_RECEIPT_FILE_HOLD")
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                require(key not in result, "U10_DUPLICATE_KEY_HOLD")
                result[key] = value
            return result
        with path.open("r", encoding="utf-8-sig") as f:
            return json.load(f, object_pairs_hook=unique_pairs,
                             parse_constant=lambda unused: (_ for _ in ()).throw(
                                 Hold("U10_NONFINITE_HOLD")))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise Hold("U10_RECEIPT_IO_OR_JSON_HOLD") from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uia-receipt", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(classify(read_receipt(args.uia_receipt)), sort_keys=True))
        return 0  # QA diagnostic valid; release is STILL HOLD.
    except Hold as exc:
        print(json.dumps({"status": "EVIDENCE_HOLD", "error": str(exc),
                          "independent_e07_10_10": "HOLD", "release_accepted": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
