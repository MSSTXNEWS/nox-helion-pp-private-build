#!/usr/bin/env python3
"""Fail-closed, read-only SHA-256 audit of the original three NOX ZIP parts."""
from __future__ import annotations
import argparse, hashlib, json, os, pathlib, re, stat, sys, tempfile, zipfile

PARTS = ("source_00.part", "source_01.part", "source_02.part")
EXPECTED_SIZE = 60364346
EXPECTED_SHA256 = "ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a"
BAD = re.compile(r'[<>:"|?*\x00-\x1f]')
RESERVED = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$', re.I)

def safe_name(name: str) -> bool:
    if not name or name.startswith("/") or "\\" in name or BAD.search(name):
        return False
    parts = name.rstrip("/").split("/")
    return bool(parts) and all(p not in ("", ".", "..")
                               and not p.endswith((" ", "."))
                               and not RESERVED.match(p) for p in parts)

def audit(directory: pathlib.Path, expected_files: int):
    paths = [directory / p for p in PARTS]
    if any(not p.is_file() or p.is_symlink() for p in paths):
        raise ValueError("Missing or nonregular part / symlink detected")
    sizes = [p.stat().st_size for p in paths]
    if sum(sizes) != EXPECTED_SIZE:
        raise ValueError(f"Part sizes mismatch {sizes}")
    sha = hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix="nox-original-audit-") as tmp:
        out = pathlib.Path(tmp) / "input-original.zip"
        with out.open("wb") as dest:
            for p in paths:
                with p.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024*1024), b""):
                        sha.update(chunk)
                        dest.write(chunk)
        actual = sha.hexdigest()
        if actual != EXPECTED_SHA256:
            raise ValueError(f"ZIP SHA256 mismatch: {actual}")
        entries, seen, total = [], set(), 0
        with zipfile.ZipFile(out) as z:
            for info in z.infolist():
                name = info.filename
                if not safe_name(name):
                    raise ValueError(f"Unsafe path: {name!r}")
                folded = name.rstrip("/").casefold()
                if folded in seen:
                    raise ValueError(f"Duplicate/case collision: {name!r}")
                seen.add(folded)
                mode = info.external_attr >> 16
                if info.create_system == 3 and stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ValueError(f"Symlink/special file: {name!r}")
                if info.is_dir():
                    continue
                total += info.file_size
                if total > 4*1024**3 or info.flag_bits & 1:
                    raise ValueError(f"Archive quota/encryption gate: {name!r}")
                digest, count = hashlib.sha256(), 0
                with z.open(info) as stream:
                    for chunk in iter(lambda: stream.read(1024*1024), b""):
                        count += len(chunk); digest.update(chunk)
                if count != info.file_size:
                    raise ValueError(f"Entry length mismatch: {name!r}")
                entries.append({"path": name, "bytes": count, "sha256": digest.hexdigest()})
        if len(entries) != expected_files:
            raise ValueError(f"Expected {expected_files} files, observed {len(entries)}")
    return {"schema": "NOX_ORIGINAL_SOURCE_729_SHA256_V1",
            "status": "SOURCE_ARCHIVE_VERIFIED_ONLY_NOT_E07_RELEASE",
            "zip_bytes": EXPECTED_SIZE, "zip_sha256": actual,
            "parts": [{"name": name, "bytes": length} for name, length in zip(PARTS, sizes)],
            "file_count": len(entries), "files": entries}


def publish_manifest_exclusive(output: pathlib.Path, data: dict) -> None:
    """Publish an audited receipt atomically, never replacing or following an output.

    The private temp leaf is only linked into place after fsync. A hard-link
    create is atomic and fails if even a dangling destination symlink exists.
    This preserves previous SourceLock/owner receipts during concurrent jobs.
    """
    def require_trusted_parents() -> None:
        for ancestor in (output.parent, *output.parent.parents):
            try:
                info = ancestor.lstat()
            except FileNotFoundError:
                continue
            if (stat.S_ISLNK(info.st_mode) or
                    getattr(info, "st_file_attributes", 0) &
                    getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
                raise ValueError("OUTPUT_PARENT_REPARSE_HOLD")

    require_trusted_parents()
    output.parent.mkdir(parents=True, exist_ok=True)
    require_trusted_parents()
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         prefix=".nox-source-audit-", suffix=".tmp",
                                         dir=output.parent, delete=False) as handle:
            temporary = pathlib.Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # Never os.replace/rename: both can overwrite a concurrent valid receipt.
        # NTFS and POSIX hard-link creation both reject an existing output leaf.
        try:
            os.link(temporary, output)
        except FileExistsError as exc:
            raise ValueError("OUTPUT_EXISTS_NO_OVERWRITE") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts-dir", type=pathlib.Path, default=pathlib.Path("."))
    ap.add_argument("--output", type=pathlib.Path, required=True)
    ap.add_argument("--expected-files", type=int, default=729)
    args = ap.parse_args()
    try:
        data = audit(args.parts_dir, args.expected_files)
        publish_manifest_exclusive(args.output, data)
        print(json.dumps({k: v for k, v in data.items() if k != "files"}))
        return 0
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)}), file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
