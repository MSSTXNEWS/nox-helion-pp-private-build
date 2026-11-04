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



# Windows WPF/NSIS must consume the same immutable Linux-built source ZIP.
# Git permits device aliases and punctuation that Win32 normalizes/rejects.
# Fail closed BEFORE opening the output archive rather than publishing an
# apparently SHA-locked bundle that cannot safely stage on Windows.
_WINDOWS_DEVICES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"{prefix}{suffix}" for prefix in ("COM", "LPT")
       for suffix in "123456789¹²³"}
)
_WINDOWS_FORBIDDEN = frozenset('<>:"\\|?*')


def _validate_windows_source_path(name: str) -> None:
    if not name or name.startswith("/") or "\\" in name:
        raise ValueError("WINDOWS_SOURCE_PATH_HOLD: " + repr(name))
    for part in name.split("/"):
        if (not part or part in (".", "..") or part.endswith((".", " ")) or
                len(part.encode("utf-16-le", "surrogatepass")) // 2 > 255 or
                any(ord(ch) < 32 or ord(ch) == 127 or
                    0xD800 <= ord(ch) <= 0xDFFF or
                    ch in _WINDOWS_FORBIDDEN for ch in part) or
                part.split(".", 1)[0].upper() in _WINDOWS_DEVICES):
            raise ValueError("WINDOWS_SOURCE_PATH_HOLD: " + repr(name))


def _committed_source_blobs(repo: Path) -> dict[str, str]:
    """Bind archive bytes to immutable HEAD, not a mutable Git index.

    Git status can suppress tracked edits using assume-unchanged or
    skip-worktree. Reject Git symlinks and submodules rather than packaging
    them as regular build inputs.
    """
    entries = subprocess.check_output(
        ["git", "-C", str(repo), "ls-tree", "-r", "--full-tree", "-z", "HEAD"],
        stderr=subprocess.PIPE,
    ).split(b"\0")
    pins = {}
    for entry in entries:
        if not entry:
            continue
        metadata, sep, filename = entry.partition(b"\t")
        fields = metadata.split(b" ")
        if not sep or len(fields) != 3:
            raise ValueError("INVALID_HEAD_TREE_ENTRY")
        mode, kind, blob = fields
        if mode not in (b"100644", b"100755") or kind != b"blob" or len(blob) != 40:
            raise ValueError("NONREGULAR_HEAD_TREE_ENTRY")
        name = filename.decode("utf-8", "surrogateescape")
        if name in pins:
            raise ValueError("DUPLICATE_HEAD_TREE_PATH")
        pins[name] = blob.decode("ascii")
    if not pins:
        raise ValueError("EMPTY_HEAD_TREE_HOLD")
    return pins


def build(repo: Path, sha: str, destination: Path):
    repo = repo.resolve(strict=True)
    if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha.lower()):
        raise ValueError("full 40-character SHA required")
    if os.path.normcase(str(Path(git(repo, "rev-parse", "--show-toplevel")).resolve(strict=True))) != os.path.normcase(str(repo)):
        raise ValueError("must use repository root")
    if git(repo, "rev-parse", "HEAD") != sha:
        raise ValueError("HEAD_SHA_MISMATCH")
    if git(repo, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("DIRTY_CHECKOUT_HOLD")
    names = subprocess.check_output(["git", "-C", str(repo), "ls-files", "-z"]).split(b"\0")
    names = sorted(p.decode("utf-8", "surrogateescape") for p in names if p)
    committed = _committed_source_blobs(repo)
    if len(names) != len(committed) or set(names) != set(committed):
        raise ValueError("HEAD_INDEX_PATHS_MISMATCH")
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
                _validate_windows_source_path(name)
                if name.casefold() in seen:
                    raise ValueError("WINDOWS_CASE_COLLISION: " + name)
                seen.add(name.casefold())
                source = repo / path
                if source.is_symlink() or not source.is_file():
                    raise ValueError("NONREGULAR_TRACKED_PATH: " + name)
                size = source.stat().st_size
                digest = hashlib.sha256()
                # Bind the exact ZIP-written bytes to Git's immutable HEAD blob.
                immutable_blob = hashlib.sha1(b"blob " + str(size).encode() + b"\0")
                entry = zipfile.ZipInfo("source/" + name, (1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                with z.open(entry, "w", force_zip64=True) as target, source.open("rb") as handle:
                    while True:
                        chunk = handle.read(1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                        immutable_blob.update(chunk)
                        target.write(chunk)
                if source.stat().st_size != size:
                    raise ValueError("SOURCE_CHANGED: " + name)
                if immutable_blob.hexdigest() != committed[name]:
                    raise ValueError("TRACKED_GIT_BLOB_MISMATCH: " + name)
                records.append({"path": name, "size": size, "sha256": digest.hexdigest(),
                                "git_blob_sha1": committed[name]})
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
