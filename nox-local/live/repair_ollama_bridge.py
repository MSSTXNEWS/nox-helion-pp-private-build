"""NOX LIVE: conservative Ollama streaming bridge repair.
instructions_version 0.0.6. No model, memory, trainer or interface changes.
Run offline against the existing server_live.py. Never restarts a process.
"""
from pathlib import Path
import argparse, ast, hashlib, json, shutil, sys, time

OLD = "payload=json.dumps({'model':mod,'messages':msgs,'stream':True},ensure_ascii=False).encode('utf-8')"
NEW = "payload=json.dumps({'model':mod,'messages':msgs,'stream':True,'think':False,'options':{'num_ctx':4096,'num_predict':1024}},ensure_ascii=False).encode('utf-8')"

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def repair(path: Path, output_dir: Path) -> dict:
    path = path.resolve(strict=True)
    if path.name != "server_live.py":
        raise ValueError("Refusing any target except server_live.py")
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    if NEW in text:
        return {"status": "ALREADY_PATCHED", "source": str(path), "sha256": sha256(raw)}
    if text.count(OLD) != 1:
        raise ValueError("UNKNOWN_SOURCE: expected exact single Ollama payload signature")
    patched = text.replace(OLD, NEW)
    ast.parse(patched)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = output_dir / ("server_live." + stamp + ".backup")
    if backup.exists():
        raise FileExistsError(backup)
    shutil.copy2(path, backup)
    if sha256(path.read_bytes()) != sha256(raw):
        raise RuntimeError("CONCURRENT_EDIT: source changed before write")
    candidate = path.with_name("server_live." + stamp + ".candidate")
    candidate.write_bytes(patched.encode("utf-8"))
    if candidate.read_bytes() != patched.encode("utf-8"):
        candidate.unlink(missing_ok=True)
        raise RuntimeError("Candidate verification failed")
    # Atomic same-volume replacement after syntax and byte readback.
    candidate.replace(path)
    if path.read_text("utf-8") != patched:
        shutil.copy2(backup, path)
        raise RuntimeError("Write readback failed; original restored")
    return {"status": "PATCHED_RESTART_REQUIRED", "source": str(path),
            "before_sha256": sha256(raw), "after_sha256": sha256(path.read_bytes()),
            "backup": str(backup)}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--backup-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(repair(args.source, args.backup_dir), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)}, ensure_ascii=False))
        sys.exit(1)
