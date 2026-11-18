"""Apply NOX Cinema Assist only to the pinned V29.3 UI-choice derivative ZIP."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import posixpath
import zipfile
from pathlib import Path

BASE_SHA256 = "e70f0439fdf0a028c1d52fc638a38086aa7863fb7b33733a9609532dd544a9d5"
BASE_ENTRIES = 1090
ASSET_PREFIX = "site/nox-cinema-assist/"
ASSETS = ("cinema_assist.js", "cinema_assist_audio_worklet.js", "cinema_assist.css")
PAGES = ("site/cinema.html", "site/pc/cinema.html", "site/pc/pages/cinema/index.html")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def attach_page(source: bytes, path: str) -> bytes:
    text = source.decode("utf-8")
    if text.count("</head>") != 1:
        raise ValueError("HOLD_HEAD_ANCHOR:" + path)
    rel = posixpath.relpath(ASSET_PREFIX.rstrip("/"), posixpath.dirname(path))
    css = f'<link rel="stylesheet" href="{rel}/cinema_assist.css" data-nox-cinema-assist="v1">'
    js = f'<script defer src="{rel}/cinema_assist.js" data-nox-cinema-assist="v1"></script>'
    if "data-nox-cinema-assist=\"v1\"" in text or "cinema_assist.js" in text:
        raise ValueError("HOLD_DUPLICATE_CINEMA_ASSIST:" + path)
    return text.replace("</head>", css + "\n" + js + "\n</head>", 1).encode("utf-8")


def build(base: Path, output: Path, asset_dir: Path, receipt: Path) -> dict:
    if file_sha(base) != BASE_SHA256:
        raise ValueError("HOLD_BASE_SOURCE_SHA256")
    if base.resolve() == output.resolve() or output.exists():
        raise ValueError("HOLD_OUTPUT_MUST_BE_NEW_FILE")
    asset_data = {name: (asset_dir / name).read_bytes() for name in ASSETS}
    with zipfile.ZipFile(base) as source:
        names = source.namelist()
        if len(names) != BASE_ENTRIES or source.testzip() is not None:
            raise ValueError("HOLD_BASE_ZIP_INTEGRITY")
        if not set(PAGES).issubset(names):
            raise ValueError("HOLD_REQUIRED_CINEMA_PAGES_MISSING")
        if any(ASSET_PREFIX + name in names for name in ASSETS):
            raise ValueError("HOLD_ASSET_ALREADY_PRESENT")
        changed = {}
        pending = output.with_suffix(output.suffix + ".pending")
        if pending.exists():
            raise ValueError("HOLD_PENDING_FILE_EXISTS")
        try:
            with zipfile.ZipFile(pending, "w", allowZip64=True) as target:
                for item in source.infolist():
                    raw = source.read(item)
                    new = attach_page(raw, item.filename) if item.filename in PAGES else raw
                    if new != raw:
                        changed[item.filename] = {"before": sha(raw), "after": sha(new)}
                    target.writestr(item, new)
                for name, raw in asset_data.items():
                    target.writestr(ASSET_PREFIX + name, raw, compress_type=zipfile.ZIP_DEFLATED)
            with zipfile.ZipFile(pending) as verify:
                if len(verify.namelist()) != BASE_ENTRIES + len(ASSETS) or verify.testzip() is not None:
                    raise ValueError("HOLD_DERIVED_ZIP_INTEGRITY")
                if any(ASSET_PREFIX + name not in verify.namelist() for name in ASSETS):
                    raise ValueError("HOLD_DERIVED_ASSETS_MISSING")
                if len(changed) != len(PAGES):
                    raise ValueError("HOLD_UNEXPECTED_PAGE_PATCH_COUNT")
            os.replace(pending, output)
        except Exception:
            pending.unlink(missing_ok=True)
            raise
    receipt_data = {
        "schema": "NOX_CINEMA_ASSIST_V1_ZIP_PATCH",
        "base_sha256": BASE_SHA256,
        "base_entries": BASE_ENTRIES,
        "derived_sha256": file_sha(output),
        "derived_entries": BASE_ENTRIES + len(ASSETS),
        "patched_pages": changed,
        "added_assets": {name: sha(data) for name, data in asset_data.items()},
        "backend_status": "separate local services required; see README",
        "player_live_status": "not installed by this build script",
    }
    receipt.write_text(json.dumps(receipt_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt_data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--assets", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.base, args.output, args.assets, args.receipt), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
