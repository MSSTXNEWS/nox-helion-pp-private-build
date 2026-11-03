#!/usr/bin/env python3
"""Strict Git-SHA-pinned source-only ZIP. NOT Windows Setup or E07 acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE).decode().strip()


def build(repo: Path, sha: str, destination: Path):
    repo = repo.resolve(strict=True)
    if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha.lower()):
        raise ValueError("full 40-character SHA required")
    if git(repo, "rev-parse", "--show-toplevel") != str(repo):
        raise ValueError("must use repository root")
    if git(repo, "rev-parse", "HEAD") != sha:
        raise ValueError("HEAD_SHA_MISMATCH")
    if git(repo, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("DIRTY_CHECKOUT_HOLD")
    names = subprocess.check_output(["git", "-C", str(repo), "ls-files", "-z"]).split(b"\0")
    names = sorted(p.decode("utf-8", "surrogateescape") for p in names if p)
    seen = set()
    records = []
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".tmp", delete=False) as tmp:
        pending = Path(tmp.name)
    try:
        with zipfile.ZipFile(pending, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            for name in names:
                path = Path(name)
                if path.is_absolute() or ".." in path.parts or "\\" in name:
                    raise ValueError("UNSAFE_PATH: " + name)
                if name.casefold() in seen:
                    raise ValueError("WINDOWS_CASE_COLLISION: " + name)
                seen.add(name.casefold())
                source = repo / path
                if source.is_symlink() or not source.is_file():
                    raise ValueError("NONREGULAR_TRACKED_PATH: " + name)
                size = source.stat().st_size
                digest = hashlib.sha256()
                entry = zipfile.ZipInfo("source/" + name, (1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                with z.open(entry, "w", force_zip64=True) as target, source.open("rb") as handle:
                    while True:
                        chunk = handle.read(1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                        target.write(chunk)
                if source.stat().st_size != size:
                    raise ValueError("SOURCE_CHANGED: " + name)
                records.append({"path": name, "size": size, "sha256": digest.hexdigest()})
            manifest = {
                "schema": "nox.express.source-snapshot.v1",
                "git_sha": sha,
                "kind": "SOURCE_ONLY_NOT_SETUP_NOT_RELEASE",
                "gates": {"G1": "NOT_ASSERTED", "G2": "NOT_ASSERTED", "G3": "NOT_RUN", "G4_E07": "NOT_RUN"},
                "file_count": len(records),
                "files": records,
            }
            entry = zipfile.ZipInfo("SOURCE_MANIFEST.json", (1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(entry, json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2))
        if git(repo, "rev-parse", "HEAD") != sha or git(repo, "status", "--porcelain", "--untracked-files=normal"):
            raise ValueError("SOURCE_MOVED_DURING_PACK")
        os.replace(pending, destination)
        with destination.open("rb") as handle:
            zip_sha = hashlib.file_digest(handle, "sha256").hexdigest()
        return {"sha": sha, "files": len(records), "zip_sha256": zip_sha, "archive": str(destination)}
    finally:
        pending.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.repo, args.sha, args.out), sort_keys=True))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print("EXPRESS_SOURCE_ARCHIVE_HOLD:", exc, file=sys.stderr)
        raise SystemExit(2)
