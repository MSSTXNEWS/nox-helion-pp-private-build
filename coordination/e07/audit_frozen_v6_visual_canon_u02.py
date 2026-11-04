"""Fail-closed independent visual review of *two* real frozen-V6 Windows captures.

This binds a reviewer-observed UI conflict to physical source/Setup/screenshot
identities. It does NOT OCR the image, run the installer, change the UI or
synthesize E07 approval. A different image/SHA requires a new real review.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import stat
import struct

SOURCE = "ffca9aaedce9d90750dfb212aabcdfd970162150"
SETUP = "722399ee3d7794a7aa38d93d933026e015fd29b0d8a60fd431b0bc494040a6bc"
BUILD = "NOX-V16-99fce33d002363f6b3e9b9cf"
PNG1 = "0e1d7d23f227d2ea33daa9ba2ff5db3700e2307ed6ca43f488a597d7405ecf96"
PNG2 = "4e303a990e6e76d32df905a562fba46d364450106442f2910b01871ab27d1367"

class Hold(ValueError):
    pass

def demand(test, code):
    if not test:
        raise Hold(code)

def load_json(path):
    demand(path.is_file() and not path.is_symlink() and
           stat.S_ISREG(path.lstat().st_mode) and 0 < path.stat().st_size < 32768,
           "V6_VISUAL_RECEIPT_PATH_HOLD")
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            demand(key not in obj, "V6_VISUAL_DUPLICATE_JSON_KEY_HOLD")
            obj[key] = value
        return obj
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(Hold("V6_VISUAL_NONFINITE_HOLD")))

def check_png(path, expected):
    demand(path.is_file() and not path.is_symlink() and
           stat.S_ISREG(path.lstat().st_mode) and 800000 <= path.stat().st_size <= 3000000,
           "V6_VISUAL_PHYSICAL_PNG_HOLD")
    with path.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    demand(digest == expected, "V6_VISUAL_SCREENSHOT_SHA_HOLD")
    with path.open("rb") as f:
        header = f.read(24)
    demand(header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR" and
           struct.unpack(">II", header[16:24]) == (1044, 788),
           "V6_VISUAL_SCREENSHOT_DIMENSIONS_HOLD")
    return {"sha256": digest, "dimensions": [1044, 788]}

def review(first_png, first_receipt, second_png, second_receipt):
    a = load_json(first_receipt)
    b = load_json(second_receipt)
    demand(a.get("schema") == "NOX-E07-V6-PHYSICAL-VISUAL-WITNESS-v1" and
           b.get("schema") == "NOX-INSTALLED-FULL-D02-VISUAL-V1" and
           all(x.get("source_sha") == SOURCE and x.get("setup_sha256") == SETUP and
               x.get("build_id") == BUILD and x.get("release_accepted") is False and
               x.get("visual_e07") == "HOLD" for x in (a, b)),
           "V6_VISUAL_SETUP_SOURCE_PROVENANCE_HOLD")
    demand(a.get("physical_capture", {}).get("sha256") == PNG1 and
           a["physical_capture"].get("physical_capture") == "PASS" and
           a["physical_capture"].get("independent_visual_review") == "NOT_RUN" and
           b.get("physical_capture") == "PASS" and
           b.get("screenshot_sha256") == PNG2,
           "V6_VISUAL_PHYSICAL_RECEIPT_HOLD")
    w1 = check_png(first_png, PNG1)
    w2 = check_png(second_png, PNG2)
    return {
        "schema": "NOX-V6-U02-REVIEWED-VISUAL-CANON-FAIL-v1",
        "source_sha": SOURCE, "setup_sha256": SETUP, "build_id": BUILD,
        "screenshots": [w1, w2], "physical_windows_runs": [41838092573, 41837132603],
        "manual_review_scope": "VISIBLE_ORIGINAL_WPF_WINDOW_ONLY_NOT_MOTION_OR_FUNCTION",
        "reviewed_observation": [
            "ORIGINAL_LEFT_SIDEBAR_VISIBLE_LITERAL_MENU_CONTRADICTS_GRAPHIC_ONLY_NO_MENU_WORD_CANON",
            "TOP_DEBUG_DIAGNOSTICS_INSTALL_LAUNCH_STOP_REPORT_CONTROLS_OVERLAP_D02_DESIGN",
        ],
        "review_type": "VISUAL_MANUAL_NOT_OCR_NOT_SYNTHETIC",
        "visual_canon": "CONFIRMED_CONFLICT_ON_FROZEN_SETUP",
        "reduced_motion": "NOT_TESTED", "functional_routes": "NOT_TESTED",
        "independent_e07_10_10": "HOLD", "release_accepted": False,
        "next_action": "OWNER_APPROVED_TARGETED_UI_CORRECTION_NEW_SETUP_SHA_FULL_RETEST",
    }

def main():
    p = argparse.ArgumentParser()
    for v in ("first-png", "first-receipt", "second-png", "second-receipt"):
        p.add_argument("--" + v, type=Path, required=True)
    a = p.parse_args()
    try:
        obj = review(a.first_png, a.first_receipt, a.second_png, a.second_receipt)
        print(json.dumps(obj, ensure_ascii=False, sort_keys=True))
        return 2  # Genuine visual conflict; never a success E07 exit.
    except (Hold, OSError, ValueError, KeyError, TypeError) as exc:
        code = str(exc) if isinstance(exc, Hold) else "V6_VISUAL_INPUT_" + type(exc).__name__ + "_HOLD"
        print(json.dumps({"error": code, "independent_e07_10_10": "HOLD", "release_accepted": False}))
        return 3

if __name__ == "__main__":
    raise SystemExit(main())
