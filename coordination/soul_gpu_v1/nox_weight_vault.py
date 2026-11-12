r"""NOX weight vault V2: verified ingestion, cross-folder deduplication, no unsafe deletions.

Source files are never removed by this script. It uses a canonical content-addressed
vault and an explicit removal manifest for *verified redundant copies only*.
Usage:
  python nox_weight_vault.py scan --source "C:\Users\USER\Downloads" --root "C:\NOX_HELION\NOX_NEW\soul_gpu"
  python nox_weight_vault.py import --source "C:\Users\USER\Downloads" --root "C:\NOX_HELION\NOX_NEW\soul_gpu"
  python nox_weight_vault.py verify --root "C:\NOX_HELION\NOX_NEW\soul_gpu"
  python nox_weight_vault.py plan-cleanup --source "C:\Users\USER\Downloads" --root "C:\NOX_HELION\NOX_NEW\soul_gpu"
No commands delete source data. The removal plan is reviewable JSON, not executable.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timezone

EXTENSIONS = {".safetensors", ".gguf", ".bin", ".pt", ".pth", ".ckpt", ".onnx", ".adapter"}
BUDGET = 270 * 10**9
FREE_RESERVE = 60 * 10**9
VAULT_LIMIT = 70 * 10**9
CHUNK = 8 * 1024 * 1024

def digest(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(CHUNK), b""):
            h.update(b)
    return h.hexdigest()

def eligible(path: Path):
    return path.is_file() and not path.is_symlink() and path.suffix.lower() in EXTENSIONS

def candidates(source: Path, root: Path):
    source = source.resolve()
    root = root.resolve()
    if source == root or source in root.parents or root in source.parents:
        raise ValueError("Source and NOX root must not overlap")
    for folder, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(folder) / d).is_symlink()]
        for name in files:
            f = Path(folder) / name
            if eligible(f):
                yield f

def database(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / "weight_vault.sqlite3")
    db.execute("""CREATE TABLE IF NOT EXISTS weight_files (
        sha256 TEXT PRIMARY KEY, canonical_path TEXT NOT NULL,
        bytes INTEGER NOT NULL, first_seen_utc TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS sources (
        source_path TEXT PRIMARY KEY, sha256 TEXT NOT NULL,
        last_verified_utc TEXT NOT NULL)""")
    db.commit()
    return db

def used(root: Path):
    total = 0
    for p in root.rglob("*"):
        if p.is_file() and not p.is_symlink():
            total += p.stat().st_size
    return total

def canonical(root: Path, sha: str, suffix: str):
    return root / "brain" / "intelligence" / "weights" / sha[:2] / (sha + suffix.lower())

def scan(source, root):
    records = []
    for p in candidates(source, root):
        stat = p.stat()
        records.append({"path": str(p), "bytes": stat.st_size, "sha256": digest(p)})
    return records

def ingest(source: Path, root: Path):
    root.mkdir(parents=True, exist_ok=True)
    output = []
    with database(root) as db:
        for item in scan(source, root):
            src = Path(item["path"])
            sha = item["sha256"]
            size = item["bytes"]
            dest = canonical(root, sha, src.suffix)
            if dest.exists():
                if dest.stat().st_size != size or digest(dest) != sha:
                    raise RuntimeError(f"Canonical collision or damaged weight file: {dest}")
                result = "already-present"
            else:
                weight_root = root / "brain" / "intelligence" / "weights"
                if used(weight_root) + size > VAULT_LIMIT:
                    raise RuntimeError("70GB intelligence weight vault quota exceeded")
                if used(root) + size > BUDGET:
                    raise RuntimeError("270GB total SOUL storage quota exceeded")
                if shutil.disk_usage(root).free < size + FREE_RESERVE:
                    raise RuntimeError("Cannot preserve 60GB free-space reserve")
                dest.parent.mkdir(parents=True, exist_ok=True)
                # Same-volume temporary file + atomic rename, never rename original.
                fd, tmp = tempfile.mkstemp(prefix=".nox-staging-", dir=dest.parent)
                os.close(fd)
                try:
                    shutil.copyfile(src, tmp)
                    if Path(tmp).stat().st_size != size or digest(Path(tmp)) != sha:
                        raise RuntimeError(f"Copy verification failed: {src}")
                    os.replace(tmp, dest)
                finally:
                    if os.path.exists(tmp):
                        os.unlink(tmp)
                result = "copied-and-verified"
            now = datetime.now(timezone.utc).isoformat()
            db.execute("INSERT OR REPLACE INTO weight_files VALUES (?,?,?,?)",
                       (sha, str(dest), size, now))
            db.execute("INSERT OR REPLACE INTO sources VALUES (?,?,?)",
                       (str(src), sha, now))
            db.commit()
            output.append({"source":str(src),"canonical":str(dest),"sha256":sha,"bytes":size,"result":result})
    return output

def verify(root):
    with database(root) as db:
        records = db.execute("SELECT sha256, canonical_path, bytes FROM weight_files").fetchall()
    output = []
    for sha, path, count in records:
        p = Path(path)
        ok = p.is_file() and p.stat().st_size == count and digest(p) == sha
        output.append({"canonical":path, "sha256":sha, "ok":ok})
    return output

def cleanup_plan(source, root):
    checked = {r["sha256"]:r for r in verify(root) if r["ok"]}
    plan = []
    for item in scan(source,root):
        match = checked.get(item["sha256"])
        if match:
            plan.append({"source":item["path"],"bytes":item["bytes"],
                "sha256":item["sha256"],"verified_canonical":match["canonical"],
                "action":"REVIEW_FOR_DELETION_ONLY",
                "warning":"No deletion performed. Keep independent recovery backup."})
    return plan

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("command", choices=("scan","import","verify","plan-cleanup"))
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("NOX_SOUL_ROOT",r"C:\NOX_HELION\NOX_NEW\soul_gpu")))
    parser.add_argument("--source", type=Path)
    args=parser.parse_args()
    root=args.root.resolve()
    if args.command!="verify" and not args.source:
        parser.error("--source is required")
    if args.command=="scan":
        result=scan(args.source,root)
    elif args.command=="import":
        result=ingest(args.source,root)
    elif args.command=="verify":
        result=verify(root)
    else:
        result=cleanup_plan(args.source,root)
    print(json.dumps({"command":args.command,"records":result},ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()
