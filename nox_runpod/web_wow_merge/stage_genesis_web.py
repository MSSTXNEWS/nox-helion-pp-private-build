#!/usr/bin/env python3
"""Stage NOX GENESIS evidence in the *existing* merged WOW V25 + PC V25 site.

- NO independent site/backend/memory DB or port
- No rewrites of original D02 or JS/CSS except a strict one-line HTML script addition
- Fail-closed if physical-merge source receipt is absent, untrusted or contradictory
- No runtime operations; sources only, Windows acceptance remains HOLD
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys, zipfile
from pathlib import Path, PurePosixPath

PAGES = ("site/training.html", "site/pc/resonance.html",
         "site/pc/memory.html", "site/pc/chat.html")
MANDATORY = ("site/training.html", "site/pc/resonance.html", "site/pc/memory.html")
ASSET = "site/nox_genesis_live_panel.mjs"
OUT_ZIP = "NOX_WEB_WOW_V25_GENESIS_S03_SOURCE_CANDIDATE.zip"
STATUS = "SOURCE_MERGED_GENESIS_STAGING_ONEHOST_QA_HOLD"
SCHEMA = "nox-genesis-web-staging-v1"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe(name: str) -> None:
    if (not name or name.startswith("/") or "\\" in name or
        any(x in ("", ".", "..") for x in name.split("/"))):
        raise ValueError("NOX_UNSAFE_ARCHIVE_PATH: " + repr(name))
    if str(PurePosixPath(name)) != name:
        raise ValueError("NOX_UNSAFE_CANONICAL_PATH: " + repr(name))


def patch_one(name: str, content: bytes) -> bytes:
    if not name.endswith(".html") or not content.strip():
        raise ValueError("NOX_HTML_ENTRY_MISSING")
    script = ("../nox_genesis_live_panel.mjs" if name.startswith("site/pc/")
              else "./nox_genesis_live_panel.mjs")
    injection = ('<script type="module" src="' + script + '"></script>').encode("ascii")
    if injection in content:
        raise ValueError("NOX_ALREADY_PATCHED")
    positions = list(re.finditer(rb"</body\s*>", content, flags=re.I))
    if len(positions) != 1:
        raise ValueError("NOX_HTML_SINGLE_BODY_CLOSURE_REQUIRED: " + name)
    start = positions[0].start()
    return content[:start] + injection + b"\n" + content[start:]


def stage(source_zip: Path, module_path: Path, destination: Path) -> dict:
    if not source_zip.is_file() or not module_path.is_file():
        raise ValueError("NOX_MISSING_SOURCE_OR_MODULE")
    if destination.exists():
        raise ValueError("NOX_NO_LOSS_OUTPUT_ALREADY_EXISTS")
    js = module_path.read_bytes()
    if (len(js) < 1000 or b"nox-genesis-live-evidence-v1" not in js or
        b"ONEHOST" in js.upper() and b"HOLD" not in js):
        raise ValueError("NOX_EVIDENCE_JS_CONTRACT_HOLD")
    source_files = {}
    with zipfile.ZipFile(source_zip) as zin:
        if zin.testzip() is not None:
            raise ValueError("NOX_ORIGINAL_SOURCE_CRC_FAIL")
        seen = set()
        for entry in zin.infolist():
            if entry.is_dir():
                continue
            safe(entry.filename)
            folded = entry.filename.casefold()
            if folded in seen:
                raise ValueError("NOX_WINDOWS_NAME_COLLISION")
            seen.add(folded)
            if entry.file_size > 320_000_000:
                raise ValueError("NOX_ENTRY_TOO_LARGE")
            source_files[entry.filename] = zin.read(entry.filename)
    if ASSET in source_files:
        raise ValueError("NOX_ASSET_COLLISION")
    try:
        merger = json.loads(source_files["NOX_PHYSICAL_MERGE_RECEIPT.json"])
    except (KeyError, ValueError, UnicodeDecodeError):
        raise ValueError("NOX_PHYSICAL_MERGE_RECEIPT_MISSING") from None
    if (merger.get("schema") != "NOX-WEB-WOW-V25-PHYSICAL-SOURCE-STAGING-v1" or
        merger.get("status") != "SOURCE_MERGED_PHYSICAL_ONEHOST_QA_HOLD" or
        merger.get("production_modified") is not False or
        merger.get("release_accepted") is not False):
        raise ValueError("NOX_UNTRUSTED_OR_RELEASE_RECEIPT")
    d02 = source_files.get("site/index.html")
    if not d02 or merger.get("original_index_sha256") != sha(d02):
        raise ValueError("NOX_D02_ORIGINAL_SHA_MISMATCH")
    missing = [p for p in MANDATORY if p not in source_files]
    if missing:
        raise ValueError("NOX_REQUIRED_WEB_SOURCE_MISSING: " + ",".join(missing))
    files = dict(source_files)
    changed = {}
    for name in PAGES:
        if name in files:
            after = patch_one(name, files[name])
            changed[name] = {"before_sha256": sha(files[name]),
                             "after_sha256": sha(after)}
            files[name] = after
    files[ASSET] = js
    if files["site/index.html"] != d02:
        raise ValueError("NOX_D02_NO_LOSS_VIOLATION")
    if any(files[name] != source_files[name]
           for name in source_files if name not in changed):
        raise ValueError("NOX_UNRELATED_SOURCE_MUTATION")
    receipt = {
        "schema": SCHEMA, "status": STATUS,
        "original_source_zip_sha256": sha(source_zip.read_bytes()),
        "original_d02_sha256": sha(d02), "staged_d02_sha256": sha(files["site/index.html"]),
        "added_asset_sha256": sha(js), "changed_pages": changed,
        "original_files_preserved_except_targeted_html_injection": True,
        "no_runtime_or_memory_or_training_writes": True,
        "onehost_endpoint_bound": False, "s03_readback_verified": False,
        "gpu_training_verified": False, "windows_e07_accepted": False,
        "release_accepted": False,
        "note": ("The trusted existing OneHost must inject an authenticated same-origin "
                 "endpoint META into the live pages; without it the UI displays HOLD."),
    }
    files["NOX_GENESIS_STAGING_RECEIPT.json"] = (
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf8")
    destination.mkdir(parents=True)
    path = destination / OUT_ZIP
    try:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6) as zout:
            for name, data in sorted(files.items()):
                zout.writestr(name, data)
        with zipfile.ZipFile(path) as zverify:
            if zverify.testzip() is not None:
                raise ValueError("NOX_OUTPUT_ZIP_CRC_FAIL")
            for name in source_files:
                if name not in changed and zverify.read(name) != source_files[name]:
                    raise ValueError("NOX_ORIGINAL_FILE_CHANGED: " + name)
            if zverify.read("site/index.html") != d02:
                raise ValueError("NOX_D02_CHANGED")
        receipt["staged_zip_bytes"] = path.stat().st_size
        receipt["staged_zip_sha256"] = sha(path.read_bytes())
        (destination / "NOX_GENESIS_STAGING_RECEIPT.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
        return {"state": STATUS, "zip": str(path), "files": len(files),
                "pages_patched": len(changed), "source_locked": True,
                "sha256": receipt["staged_zip_sha256"]}
    except BaseException:
        path.unlink(missing_ok=True)
        (destination / "NOX_GENESIS_STAGING_RECEIPT.json").unlink(missing_ok=True)
        destination.rmdir()
        raise


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--merged-web", required=True, type=Path)
    cli.add_argument("--module", required=True, type=Path)
    cli.add_argument("--out", required=True, type=Path)
    a = cli.parse_args()
    try:
        print(json.dumps(stage(a.merged_web, a.module, a.out), ensure_ascii=False))
        return 0
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        print("NOX_HOLD " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
