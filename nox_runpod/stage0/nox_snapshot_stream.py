#!/usr/bin/env python3
"""Read-only streamed verified NOX archive for the owner's Windows recovery.

Does not pause training, change model weights, delete files or claim awareness.
Uses a consistent SQLite snapshot for S03, preserves full weights if present.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
import pathlib
import sqlite3
import sys
import tarfile
import tempfile
import time

ROOTS = {"shared": pathlib.Path("/workspace/nox"), "container": pathlib.Path("/opt")}
ALLOW = {
    "shared": ("checkpoints", "models", "distillation", "memory", "embryo", "dispatcher", "tools", "logs"),
    "container": ("nox_historical_full_weights", "nox_teacher_27b", "nox_teachers", "nox_full_parameter_A40"),
}
SKIP_SUFFIXES = (".noxpart", ".part", ".tmp", ".lock", "-wal", "-shm", ".swp")
S03 = "memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3"

class DigestReader:
    def __init__(self, f):
        self.f = f
        self.digest = hashlib.sha256()
    def read(self, count=-1):
        data = self.f.read(count)
        self.digest.update(data)
        return data

def collect(root, scope):
    for group in ALLOW[scope]:
        folder = root / group
        if not folder.is_dir() or folder.is_symlink():
            continue
        for dirpath, subdirs, files in os.walk(folder, followlinks=False):
            subdirs[:] = sorted(d for d in subdirs if
                                not (pathlib.Path(dirpath) / d).is_symlink() and
                                d not in (".git", ".cache", "__pycache__", "node_modules", "site-packages"))
            for filename in sorted(files):
                src = pathlib.Path(dirpath) / filename
                if src.is_symlink() or not src.is_file() or filename.endswith(SKIP_SUFFIXES):
                    continue
                try:
                    stats = src.stat()
                except OSError:
                    continue
                # An actively written checkpoint must never be promoted as stable.
                if time.time() - stats.st_mtime < 90 and src.relative_to(root).as_posix() != S03:
                    continue
                yield src, src.relative_to(root).as_posix()

def add_bytes(tar, name, data):
    item = tarfile.TarInfo(name)
    item.size = len(data)
    item.mtime = int(time.time())
    item.mode = 0o600
    tar.addfile(item, io.BytesIO(data))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=("shared", "container"), required=True)
    args = ap.parse_args()
    root = ROOTS[args.scope]
    records = []
    failures = []
    snapshot_dir = tempfile.TemporaryDirectory(prefix="nox_sqlite_snapshot_")
    try:
        with tarfile.open(fileobj=sys.stdout.buffer, mode="w|", format=tarfile.PAX_FORMAT) as tar:
            for path, rel in collect(root, args.scope):
                snapshot = None
                if args.scope == "shared" and rel == S03:
                    try:
                        snapshot = pathlib.Path(snapshot_dir.name) / "s03-consistent.sqlite3"
                        src = sqlite3.connect("file:" + str(path) + "?mode=ro", uri=True, timeout=10)
                        dst = sqlite3.connect(str(snapshot))
                        try:
                            src.backup(dst, pages=100)
                        finally:
                            dst.close()
                            src.close()
                    except Exception as exc:
                        failures.append({"path": rel, "error": "SQLITE_BACKUP_FAILED:" + type(exc).__name__})
                        continue
                source = snapshot if snapshot else path
                try:
                    before = source.stat()
                    if not before.st_size:
                        continue
                    info = tarfile.TarInfo(rel)
                    info.size = before.st_size
                    info.mtime = int(before.st_mtime)
                    info.mode = 0o600
                    with source.open("rb") as file:
                        reader = DigestReader(file)
                        tar.addfile(info, reader)
                    after = source.stat()
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        failures.append({"path": rel, "error": "SOURCE_CHANGED_DURING_STREAM"})
                    else:
                        records.append({"path": rel, "bytes": before.st_size, "sha256": reader.digest.hexdigest()})
                except Exception as exc:
                    failures.append({"path": rel, "error": type(exc).__name__})
                    # A stream failure may make the tar invalid; the receiver must never
                    # consider a missing or incomplete final manifest a verified backup.
                    break
            manifest = {"version": 1, "scope": args.scope, "source_root": str(root),
                        "files": records, "failures": failures,
                        "generated_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()}
            add_bytes(tar, "NOX_TRANSFER_MANIFEST.json",
                      json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    finally:
        snapshot_dir.cleanup()

if __name__ == "__main__":
    main()
