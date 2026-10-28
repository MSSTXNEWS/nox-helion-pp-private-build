#!/usr/bin/env python3
"""Reconstruct ORIGINAL approved D02 assets from private, byte-pinned Git fragments.

Runs only in a disposable Windows Actions checkout. No code from NOX_APP_R9.zip
is executed or extracted. Full file SHA-256 matches the E06 R08 original archive.
"""
from __future__ import annotations

import base64
import hashlib
import pathlib
import sys

if len(sys.argv) != 2:
    raise SystemExit("NOX_EXPECTED_R08_ROOT")
root = pathlib.Path(sys.argv[1]).resolve(strict=True)
here = pathlib.Path(__file__).resolve().parent / "original-assets"

# file path -> original SHA256, length and ordered fragment names.
ASSETS = {
    "Assets/home.png": (
        "382c1069afcaaaed11c319796f2c553d2bd977d7e46c68ecd7d55af26e132a4a",
        3707870, ("home.png.part00", "home.png.part01")),
    "Assets/core01.png": (
        "343e5c73539358fe2c086706b4155cc0f9cd9702fcd40a98b4aab130585bec97",
        2285847, ("core01.png",)),
    "Assets/menu.png": (
        "4c73d137e6d25f496abb006dbb8af08b1fe272d2f935c5006f0f42b6fd9992b9",
        2304970, ("menu.png.part00", "menu.png.part01")),
    "Assets/menu_sections.png": (
        "7d181604f913cf9956c173c14da3dc7fd0238c389322896588cec4407b4024a4",
        2662583, ("menu_sections.png.part00", "menu_sections.png.part01")),
    "Modules/NOX_APP_R9.zip": (
        "9753cf8b4e2a8ccf8ce7ee4c4e75b858b5af4f0985642cc95ec06d9e7f71a85b",
        10777015, tuple(f"NOX_APP_R9.zip.part{i:02d}" for i in range(6))),
}

for relative, (expected_sha, expected_bytes, names) in ASSETS.items():
    data = bytearray()
    for name in names:
        path = here / (name + ".base64")
        if not path.is_file():
            raise SystemExit(f"NOX_ORIGINAL_ASSET_FRAGMENT_MISSING:{name}")
        fragment = base64.b64decode(path.read_text(encoding="ascii").strip(), validate=True)
        data.extend(fragment)
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha or len(data) != expected_bytes:
        raise SystemExit(f"NOX_ORIGINAL_ASSET_SHA_OR_SIZE_MISMATCH:{relative}")
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise SystemExit(f"NOX_UNSAFE_DESTINATION:{relative}")
    if target.exists():
        existing = target.read_bytes()
        if hashlib.sha256(existing).hexdigest() != expected_sha:
            raise SystemExit(f"NOX_ORIGINAL_ASSET_CONFLICT:{relative}")
        print(f"NOX_ORIGINAL_ASSET_MATCH {relative} sha256={expected_sha}")
        continue
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    print(f"NOX_ORIGINAL_ASSET_RESTORED {relative} bytes={expected_bytes} sha256={actual}")

print("NOX_R08_FULL_ORIGINAL_D02_AND_LOCAL_APP_SOURCE_RESTORED_COUNT=5")
