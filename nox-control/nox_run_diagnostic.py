#!/usr/bin/env python3
"""NOX run-state diagnosis. Read-only; never opens model weights or modifies processes."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path("/workspace/nox")
SUFFIXES = {".safetensors", ".pt", ".pth", ".bin", ".ckpt"}
STATE_NAMES = {"trainer_state.json", "training_state.json", "optimizer.pt", "optimizer.bin", "scheduler.pt", "adapter_model.safetensors", "adapter_model.bin", "pytorch_model.bin"}
SKIP = {".git", "node_modules", "site-packages", "__pycache__", "venv", "prime9b-venv", "datasets", "THREE_TEACHERS", "cache"}
def run(args):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=12,check=False)
        return {"exit":p.returncode,"output":(p.stdout or p.stderr)[-3500:]}
    except Exception as exc: return {"error":str(exc)[:300]}
def process_info():
    result=[]
    for p in Path("/proc").iterdir():
        if not p.name.isdigit(): continue
        try:
            cmd=(p/"cmdline").read_bytes().replace(b"\0",b" ").decode("utf-8","replace")
            if not any(x in cmd.lower() for x in ("train", "distill", "accelerate", "deepspeed", "torchrun")): continue
            if "nox_run_diagnostic.py" in cmd: continue
            cmd=cmd[:450]
            result.append({"pid":int(p.name),"command":cmd})
        except (OSError,PermissionError): continue
    return result[:50]
def inventory():
    files=[]
    if not ROOT.is_dir(): return files
    for base,dirs,names in os.walk(ROOT):
        depth=len(Path(base).relative_to(ROOT).parts)
        dirs[:]=[d for d in dirs if d not in SKIP and not d.startswith(".")] if depth<7 else []
        for name in names:
            if not (name in STATE_NAMES or "checkpoint" in name.lower() or ("adapter" in name.lower() and Path(name).suffix in SUFFIXES)): continue
            p=Path(base)/name
            try:
                st=p.stat()
                files.append({"path":str(p.relative_to(ROOT)),"bytes":st.st_size,"mtime_utc":dt.datetime.fromtimestamp(st.st_mtime,dt.timezone.utc).isoformat()})
            except OSError: pass
    return sorted(files,key=lambda f:f["mtime_utc"],reverse=True)[:70]
if __name__=="__main__":
    info={"checked_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
    "root":str(ROOT),"training_process_candidates":process_info(),
    "weight_or_trainer_state_files":inventory(),
    "gpu":run(["nvidia-smi","--query-compute-apps=pid,used_gpu_memory","--format=csv,noheader,nounits"])}
    info["training_verified"]=False
    info["note"]="Process existence and file names do not prove optimizer updates. Inspect trainer_state and checkpoint contents separately; no changes were made."
    print("NOX_RUN_DIAGNOSTIC "+json.dumps(info,ensure_ascii=False))
