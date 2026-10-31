#!/usr/bin/env python3
"""G6B: opt-in, fail-closed R76 MENU10 mobile asteroid hitbox CSS repair.

This does not modify the GitLab donor, the original PNG, the ZIP729, or any
active Windows branch. Run on a reviewed disposable R76 CSS copy and pass
--patched-out to produce a NEW file. I0 alone may approve its admission.
Source-only remediation; not installed Windows E2E evidence.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

DONOR_R76_CSS_BLOB = "24e5eecf7d55994f6b2e1f32c296305503a63d5a"
OLD = (
    b"@media(max-width:780px){\n"
    b" .mega814-asteroid-button{display:none}\n"
    b" .mega814-mobile-worlds{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:12px}\n"
    b"}"
)
NEW = (
    b"@media(max-width:780px){\n"
    b" /* Original MENU10 bitmap + ten transparent hitboxes remain interactive.\n"
    b"    At narrow widths pan the canonical image; do not replace it with tiles. */\n"
    b" .mega814-menu-scene{overflow-x:auto;overscroll-behavior-x:contain}\n"
    b" .mega814-spatial{min-width:800px}\n"
    b" .mega814-mobile-worlds{display:none}\n"
    b"}"
)
SHA_FAIL_FALLBACK = b".mega814-menu-scene.mega814-image-hold .mega814-mobile-worlds{display:grid"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def rewrite(data: bytes, *, check_blob: bool = True) -> bytes:
    if check_blob and git_blob(data) != DONOR_R76_CSS_BLOB:
        raise ValueError("G6B_R76_CSS_PREIMAGE_BLOB_HOLD")
    if data.count(OLD) != 1:
        raise ValueError("G6B_MOBILE_780_RULE_NOT_UNIQUE_HOLD")
    if data.count(SHA_FAIL_FALLBACK) != 1:
        raise ValueError("G6B_APPROVED_IMAGE_SHA_FAIL_FALLBACK_MISSING")
    corrected = data.replace(OLD, NEW, 1)
    if corrected.replace(NEW, OLD, 1) != data:
        raise AssertionError("G6B_NONREVERSIBLE_DIFF_HOLD")
    if OLD in corrected or corrected.count(NEW) != 1:
        raise AssertionError("G6B_MOBILE_HITBOX_REPAIR_HOLD")
    return corrected


def self_test() -> None:
    fixture = b"prefix\n" + OLD + b"\n" + SHA_FAIL_FALLBACK + b"}\nsuffix"
    result = rewrite(fixture, check_blob=False)
    assert NEW in result and OLD not in result
    assert result.replace(NEW, OLD, 1) == fixture
    for wrong in (fixture.replace(b"display:none", b"display:block"),
                  fixture + OLD, fixture.replace(SHA_FAIL_FALLBACK, b"x")):
        try:
            rewrite(wrong, check_blob=False)
        except ValueError:
            pass
        else:
            raise AssertionError("G6B_FAIL_CLOSED_MUTANT_ACCEPTED")
    try:
        rewrite(fixture)
    except ValueError as exc:
        assert str(exc) == "G6B_R76_CSS_PREIMAGE_BLOB_HOLD"
    else:
        raise AssertionError("G6B_SHA_PREIMAGE_MISSING")
    print("G6B_MOBILE_ASTEROID_SOURCE_UNIT_PASS 5/5")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--donor-css", type=Path)
    ap.add_argument("--patched-out", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.donor_css:
        ap.error("--donor-css required unless --self-test")
    if args.donor_css.is_symlink() or not args.donor_css.is_file():
        raise ValueError("G6B_DONOR_MUST_BE_REGULAR_FILE")
    raw = args.donor_css.read_bytes()
    corrected = rewrite(raw)
    print("G6B_PRE_GIT_BLOB", git_blob(raw))
    print("G6B_POST_GIT_BLOB", git_blob(corrected))
    print("G6B_POST_SHA256", hashlib.sha256(corrected).hexdigest())
    print("G6B_CSS_ONLY_CHANGE", len(raw), len(corrected))
    if args.patched_out:
        dest = args.patched_out
        if (dest.resolve(strict=False) == args.donor_css.resolve() or
                dest.is_symlink() or not dest.parent.is_dir() or
                dest.parent.is_symlink() or dest.suffix.lower() != ".css"):
            raise ValueError("G6B_OUTPUT_NOT_SEPARATE_REGULAR_CSS")
        with dest.open("xb") as f:
            f.write(corrected)
        if dest.read_bytes() != corrected:
            raise AssertionError("G6B_OUTPUT_READBACK_HOLD")
        print("G6B_NEW_DISPOSABLE_CSS_WRITTEN_NOT_INTEGRATED", dest)


if __name__ == "__main__":
    main()
