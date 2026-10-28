#!/usr/bin/env python3
"""E06 diagnostic-only P05 C# raw HTML string compatibility fix.

Never mutates the frozen Drive donor, GitHub original, or other owner branches.
Updates only the extracted copy after strict pre- and post-SHA-256 validation.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

PRE = "7a3056d025aeedc3117e5245ac9f84fe76ea4d4afd75e9d9570b31cbfc4e1c1d"
POST = "1a6fcfff72924260a9e913f8af26a7c1009482bbdef67b85e5c11c0709ca8a4e"
SOURCE = "R11/Packages/P05/InstallerRunReport.cs"
RUN = "NOX-V16-E06-EXPRESS-R08-P05-DIAG-20261028"

def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def main(root: Path) -> None:
    target = root / SOURCE
    original = target.read_bytes()
    if sha(original) != PRE:
        raise RuntimeError("P05_OWNER_PREIMAGE_HOLD")
    txt = original.decode("utf-8-sig")
    start = txt.index('        return """<!doctype html>')
    end = txt.index('</main></body></html>""";', start) + len('</main></body></html>""";')
    sections = txt[start:end].split('"""')
    if len(sections) != 35:
        raise RuntimeError("P05_RAW_FRAGMENT_SHAPE_HOLD")
    # Keep the exact HTML and concatenation expressions. Translate only raw
    # literal chunks to equivalent C# verbatim literals (double embedded quotes).
    converted = ''.join(
        '@"' + part.replace('"', '""') + '"' if i % 2 else part
        for i, part in enumerate(sections)
    )
    updated = (txt[:start] + converted + txt[end:]).encode("utf-8")
    if sha(updated) != POST:
        raise RuntimeError("P05_OWNER_POSTIMAGE_HOLD")
    target.write_bytes(updated)
    evidence = Path("ci-evidence")
    evidence.mkdir(exist_ok=True)
    (evidence / "p05-diagnostic-source-correction.json").write_text(
        json.dumps({
            "schema": "NOX_DIAGNOSTIC_OWNER_P05_REPAIR_V1",
            "run_id": RUN,
            "owner": 5,
            "path": SOURCE,
            "pre_sha256": PRE,
            "post_sha256": POST,
            "diagnostic_only": True,
            "original_preserved": True,
            "product_integrated": False,
            "fix": "C# raw HTML chunks converted to equivalent verbatim strings"
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("P05_DIAGNOSTIC_SHA_GUARD_PASS", PRE, POST)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: diagnostic_p05_rawstring_fix.py <extracted_source_root>")
    main(Path(sys.argv[1]))
