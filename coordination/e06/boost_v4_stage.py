"""NOX EXPRESS: admit existing V4 cache to disposable staging ONLY.
No installation, backend, network, ownership, native callback or source-tree mutation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

EXPECTED_CACHE_SHA = "2ca2647e46edd1e110db1569cb6a636ceee8e8154b416560ad43a87fb95545bd"
COMPACT_CACHE_SHA = "26d2ed7ca66aaa0ce4d2b695537484f51c2080140f79cc576501f211c2190938"
APPROVED_D02 = {
    "home.png": "382c1069afcaaaed11c319796f2c553d2bd977d7e46c68ecd7d55af26e132a4a",
    "menu.png": "4c73d137e6d25f496abb006dbb8af08b1fe272d2f935c5006f0f42b6fd9992b9",
    "core01.png": "343e5c73539358fe2c086706b4155cc0f9cd9702fcd40a98b4aab130585bec97",
    "menu_sections.png": "7d181604f913cf9956c173c14da3dc7fd0238c389322896588cec4407b4024a4",
}
COPY_PREFIX = {"APPROVED_D02/": "approved-d02/", "NUGET_OFFLINE_FEED/": "nuget-feed/", "R11_READY/fluent/": "fluent/"}
COMPACT_PREFIX = {"approved-d02/": "approved-d02/", "nuget-feed/": "nuget-feed/", "fluent/": "fluent/"}
LICENSE_FORBIDDEN = {".ttf", ".otf", ".woff", ".woff2", ".eot"}


def sha256_file(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def stage(archive: Path, out: Path) -> dict:
    if not archive.is_file() or archive.is_symlink():
        raise ValueError("BOOST_CACHE_ARCHIVE_UNAVAILABLE")
    archive_sha = sha256_file(archive)
    if archive_sha not in (EXPECTED_CACHE_SHA, COMPACT_CACHE_SHA):
        raise ValueError("BOOST_CACHE_SHA_HOLD")
    mappings = COPY_PREFIX if archive_sha == EXPECTED_CACHE_SHA else COMPACT_PREFIX
    if out.exists() or out.is_symlink():
        raise FileExistsError("BOOST_CACHE_OUTPUT_MUST_NOT_EXIST")
    if not out.parent.is_dir() or out.parent.is_symlink():
        raise ValueError("BOOST_CACHE_PARENT_REQUIRED")
    seen: set[str] = set()
    extracted: list[dict] = []
    # Staging is a new, disposable sibling; never write into an existing OneHost or source root.
    with tempfile.TemporaryDirectory(prefix=".nox-boost-", dir=out.parent) as tmp:
        target = Path(tmp)
        with zipfile.ZipFile(archive) as handle:
            entries = handle.infolist()
            if len(entries) > 10000:
                raise ValueError("BOOST_CACHE_ARCHIVE_COUNT_HOLD")
            for entry in entries:
                name = entry.filename
                pp = PurePosixPath(name)
                if name.startswith("/") or "\\" in name or ".." in pp.parts or entry.is_dir():
                    if entry.is_dir():
                        continue
                    raise ValueError("BOOST_CACHE_UNSAFE_ENTRY")
                root = next((k for k in mappings if name.startswith(k)), None)
                if root is None:
                    continue
                relative = PurePosixPath(name[len(root):])
                if (not relative.parts or relative.suffix.lower() in LICENSE_FORBIDDEN or
                        ":" in name or name in seen or entry.file_size > 80_000_000):
                    raise ValueError("BOOST_CACHE_ENTRY_HOLD")
                seen.add(name)
                # ZIP links/special files are not permitted.
                mode = (entry.external_attr >> 16) & 0o170000
                if mode not in (0, 0o100000):
                    raise ValueError("BOOST_CACHE_SPECIAL_FILE_HOLD")
                contents = handle.read(entry)
                if len(contents) != entry.file_size:
                    raise ValueError("BOOST_CACHE_TRUNCATED_ENTRY")
                sha = hashlib.sha256(contents).hexdigest()
                if root in ("APPROVED_D02/", "approved-d02/") and sha != APPROVED_D02.get(relative.as_posix()):
                    raise ValueError("BOOST_CACHE_D02_SOURCELOCK_HOLD")
                dest = target / mappings[root] / relative.as_posix()
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(contents)
                extracted.append({"path": mappings[root] + relative.as_posix(),
                                  "sha256": sha, "bytes": len(contents)})
        if {x["path"] for x in extracted if x["path"].startswith("approved-d02/")} != {
            "approved-d02/" + x for x in APPROVED_D02
        }:
            raise ValueError("BOOST_CACHE_D02_SET_INCOMPLETE")
        if len([x for x in extracted if x["path"].startswith("nuget-feed/")]) != 16:
            raise ValueError("BOOST_CACHE_NUGET_SET_INCOMPLETE")
        receipt = {"schema": "NOX-BOOST-V4-STAGE-V1", "archive_sha256": archive_sha,
                   "stage_only": True, "owner_source_mutated": False,
                   "onehost_executed": False, "e07_pass": False, "files": extracted}
        (target / "BOOST_STAGE_RECEIPT.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(target, out)
        return receipt


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    receipt = stage(args.archive, args.out)
    print(json.dumps({"status": "BOOST_CACHE_STAGED", "files": len(receipt["files"]),
                      "output": str(args.out), "e07_pass": False}))


if __name__ == "__main__":
    main()
