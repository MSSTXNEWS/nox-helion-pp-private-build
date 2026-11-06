"""NOX GENESIS / SEGMENT 1 V9: READ-ONLY evidence reconciliation.

Only inspects NOX-owned paths. No automatic removal, no Downloads scanning,
no stale progress as live training, no training a second time.
Gates are observations, not a human-like intelligence score.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
from datetime import datetime,timezone
from urllib.request import urlopen

MAX_FILES = 1000
SAFE_EXTS={".safetensors",".gguf",".onnx",".pt",".pth",".ckpt",".bin"}
ROOT=Path(r"C:\NOX_HELION\NOX_NEW") if os.name=="nt" else Path(".")
LOCATIONS=("soul_gpu/adapters","brain/intelligence/adapters","soul_gpu/nox_lora_weights","brain/intelligence/weights")
GB=1_000_000_000
SOURCE_LABELS={
 "archive_numeric_weights":"Drive historical R12 trained numeric classifiers - not current language model",
 "cpu_sft_screenshot":"CPU SFT/LoRA observed 22/50 steps on 2026-11-06 - saved adapter unverified",
 "qwen_installed":"Owner screenshot confirmed Qwen3 4B, 8B and embedding on local Ollama",
}

def sha256(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(8*1024*1024),b""):
            h.update(b)
    return h.hexdigest()

def read_json(p:Path):
    try:
        if not p.is_file() or p.stat().st_size>2_000_000:return None
        return json.loads(p.read_text("utf-8-sig"))
    except (OSError,UnicodeError,ValueError):return None

def model_catalog():
    try:
        with urlopen("http://127.0.0.1:11434/api/tags",timeout=5) as f:
            obj=json.loads(f.read(1_000_000))
        return sorted([{"tag":r["name"],"digest":r.get("digest"),"bytes":r.get("size")}
                       for r in obj.get("models",[]) if isinstance(r,dict) and isinstance(r.get("name"),str)],
                      key=lambda r:r["tag"])
    except (OSError,ValueError,KeyError,TypeError):return []

def files_to_audit(root:Path):
    for rel in LOCATIONS:
        p=root.joinpath(*rel.split("/"))
        if p.is_symlink() or not p.is_dir():continue
        count=0
        for folder, dirs, names in os.walk(p,followlinks=False):
            dirs[:]=[d for d in dirs if not (Path(folder)/d).is_symlink()]
            for name in names:
                f=Path(folder)/name
                if f.is_symlink() or not f.is_file() or f.suffix.lower() not in SAFE_EXTS:continue
                count+=1
                if count>MAX_FILES:raise RuntimeError("Weight audit file count bound exceeded")
                yield f

def adapter_audit(root:Path):
    files=[]
    by_hash={}
    for f in files_to_audit(root):
        digest=sha256(f)
        rel=f.relative_to(root).as_posix()
        files.append({"path":rel,"bytes":f.stat().st_size,"sha256":digest})
        by_hash.setdefault(digest,[]).append(rel)
    duplicates=[{"sha256":key,"paths":paths} for key,paths in by_hash.items() if len(paths)>1]
    candidates=[]
    for row in files:
        p=root/row["path"]
        if p.suffix.lower()!=".safetensors":continue
        parent=p.parent
        config=read_json(parent/"adapter_config.json")
        proof=read_json(parent/"TRAINING_EVIDENCE.json")
        if config is None:continue
        accepted=(
            isinstance(proof,dict) and proof.get("status")=="holdout-passed" and
            bool(proof.get("base")) and isinstance(proof.get("holdout_loss_before"),(int,float)) and
            isinstance(proof.get("holdout_loss_after"),(int,float)) and
            proof.get("holdout_loss_after")<=proof.get("holdout_loss_before")*1.07
        )
        candidates.append({"path":row["path"],"sha256":row["sha256"],
            "base_model":config.get("base_model_name_or_path"),
            "adapter_file":True,"evidence_status":proof.get("status") if isinstance(proof,dict) else None,
            "accepted_receipt":accepted,
            "compatibility_with_installed_ollama":"NOT_TESTED",
            "loaded_in_native_Nox":"NOT_TESTED"})
    return {"files":files,"duplicates":duplicates,"adapters":candidates,
            "deletions_performed":0,"uploads_performed":0}

def prior_results(root:Path):
    receipts=[]
    for rel in ("brain/telemetry/training.json","brain/RUN_RECEIPT.json",
                "brain/telemetry/genesis_live.json","brain/telemetry/genesis_last_candidate.json"):
        x=read_json(root.joinpath(*rel.split("/")))
        if x is None:continue
        f=root.joinpath(*rel.split("/"))
        receipts.append({"path":rel,"last_modified_utc":
                        datetime.fromtimestamp(f.stat().st_mtime,timezone.utc).isoformat(),
                        "data":{k:x.get(k) for k in
                            ("status","stage","actual_steps","requested_steps","training_steps","gpu",
                             "holdout_loss_before","holdout_loss_after","safety_hold")
                            if k in x}})
    return receipts

def hardware():
    out={"nvidia_gpu":False,"gpu_names":[],"amd_present":False,
         "directml_tensor_smoke":"NOT_TESTED","amd_qlora_supported":"UNVERIFIED",
         "thermal_sensor_ready":False,"thermal_sensor_source":None}
    try:
        p=subprocess.run(["nvidia-smi","--query-gpu=name,temperature.gpu",
                          "--format=csv,noheader,nounits"],capture_output=True,
                         text=True,timeout=6,check=True)
        for line in p.stdout.splitlines():
            parts=line.rsplit(",",1)
            if len(parts)!=2:continue
            try: t=int(parts[1].strip())
            except ValueError:continue
            out["gpu_names"].append(parts[0].strip())
            out["nvidia_gpu"]=True
            if 0<=t<110:
                out["thermal_sensor_ready"]=True
                out["thermal_sensor_source"]="nvidia-smi"
    except (OSError,subprocess.SubprocessError):pass
    if os.name=="nt":
        try:
            p=subprocess.run(["powershell","-NoProfile","-Command",
                "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
                capture_output=True,text=True,timeout=15)
            names=[x.strip() for x in p.stdout.splitlines() if x.strip()]
            out["gpu_names"]=sorted(set(out["gpu_names"]+names))
            out["amd_present"]=any("AMD" in s.upper() or "RADEON" in s.upper() for s in names)
        except (OSError,subprocess.SubprocessError):pass
    # DirectML packages and GPU thermal telemetry are NOT assumed present.
    return out

def db_status(root:Path):
    paths=(root/"soul_gpu"/"soul.sqlite3",root/"brain"/"memory"/"synaptic.sqlite3")
    out=[]
    for path in paths:
        item={"path":str(path.relative_to(root)),"present":path.is_file(),
              "writable_by_this_script":False,"record_count":None}
        if path.is_file():
            try:
                db=sqlite3.connect("file:"+path.as_posix()+"?mode=ro",uri=True,timeout=2)
                tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                known=("memories","nodes")
                item["record_count"]=sum(db.execute("SELECT count(*) FROM "+t).fetchone()[0]
                                         for t in known if t in tables)
                db.close()
            except sqlite3.Error:pass
        out.append(item)
    return {"observations":out,"native_S03_binding":"NOT_VERIFIED"}

def audit(root:Path):
    root=root.resolve()
    if not root.is_dir():raise FileNotFoundError("NOX_NEW root unavailable")
    disk=shutil.disk_usage(root)
    weights=adapter_audit(root)
    models=model_catalog()
    hardware_info=hardware()
    result={"schema":"NOX-GENESIS-V9-EVIDENCE",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "root":str(root),"historical_provenance":SOURCE_LABELS,
        "models":models,"weights":weights,"previous_receipts":prior_results(root),
        "hardware":hardware_info,"memory":db_status(root),
        "storage":{"free_bytes":disk.free,"minimum_free_reserve_bytes":60*GB,
                   "intelligence_limit_bytes":70*GB,"memory_limit_bytes":70*GB,
                   "skills_limit_bytes":70*GB},
        "training":{"approved_data_verified":False,"new_training_performed":False,
                    "accepted_adapter_loaded":False,"real_qlora_gpu":"NOT_VERIFIED"},
        "native":{"exe_present":(root/"release"/"NOX.HELION.exe").is_file(),
                  "onehost_S03_bound":"NOT_VERIFIED","same_sha_E07":"NOT_VERIFIED",
                  "exe_replaced":False},
        "rule":"Do not retrain/replace/erase without provenance and physical verification"}
    dest=root/"brain"/"telemetry"/"genesis_v9_audit.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    tmp=dest.with_suffix(".tmp")
    tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(tmp,dest)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=ROOT)
    a=p.parse_args()
    res=audit(a.root)
    print(json.dumps({"evidence_file":str(a.root/"brain"/"telemetry"/"genesis_v9_audit.json"),
                      "models":len(res["models"]),
                      "adapters_found":len(res["weights"]["adapters"]),
                      "accepted_adapters_receipt":sum(bool(x["accepted_receipt"]) for x in res["weights"]["adapters"]),
                      "amd_present":res["hardware"]["amd_present"],
                      "training":res["training"]},ensure_ascii=False,indent=2))
